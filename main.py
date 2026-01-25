import argparse
import asyncio
import logging
import signal
import socket
import json

import aiofiles.tempfile  # type: ignore[import-untyped]
import aiohttp
import m3u8
import os
import sys
import shutil
import copy
import threading

from datetime import timedelta, datetime
from typing import Any, Iterable, Protocol, Tuple, cast, Optional
from faster_whisper import WhisperModel  # type: ignore
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from faster_whisper.utils import available_models  # type: ignore
from m3u8 import PlaylistList, SegmentList

translated_chunk_paths: dict[str, str] = {}
chunk_to_vtt: dict[str, str] = {}
chunk_to_vtt_trans: dict[str, str] = {}  # Dictionary for translated subtitles
chunk_to_vtt_orig: dict[str, str] = {}  # Dictionary for transcribed subtitles

CHUNK_LIST_BASE_URI = None
base_playlist_ser: Optional[bytes] = None
chunk_list_ser: Optional[bytes] = None
sub_list_ser: Optional[bytes] = None
sub_list_trans_ser: Optional[bytes] = None  # Global for translated subtitles playlist
sub_list_orig_ser: Optional[bytes] = None  # Global for transcribed subtitles playlist

TARGET_BUFFER_SECS = 60
MAX_TARGET_BUFFER_SECS = 120

filter_dict: dict[str, Any] = {}  # Dictionary of strings to filter out
filter_file_path = "config/filter.json"  # File to store filter words
vocabulary_file_path = "config/vocabulary.json"  # File to store custom vocabulary

# New global variables for custom vocabulary
custom_vocabulary: list[str] = []  # Custom vocabulary terms
initial_prompt_text = ""  # Initial prompt for Whisper model

# New global variable for container extension
container_ext = ".ts"

# Globals for MP4 init segment
init_segment_path: Optional[str] = None  # Filesystem path of generated init.mp4
INIT_SEGMENT_URI = "/init.mp4"
init_segment_created = False

if sys.version_info < (3, 10):
    print("This script needs to be ran under Python 3.10 at minimum.")
    sys.exit(1)

logger = logging.getLogger("livevtt")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)


class SegmentLike(Protocol):
    start: float
    end: float
    text: str


def segments_to_srt(segments: Iterable[SegmentLike], ts_offset: timedelta) -> str:
    base_ts = datetime(1970, 1, 1, 0, 0, 0) + ts_offset
    segment_chunks = [
        f"{i + 1}\n{(base_ts + timedelta(seconds=segment.start)).strftime('%H:%M:%S,%f')[:-3]} --> {(base_ts + timedelta(seconds=segment.end)).strftime('%H:%M:%S,%f')[:-3]}\n{segment.text}"
        for i, segment in enumerate(segments)
    ]
    return "\n\n".join(segment_chunks)


def segments_to_webvtt(segments: Iterable[SegmentLike], ts_offset: timedelta) -> str:
    base_ts = datetime(1970, 1, 1, 0, 0, 0) + ts_offset
    segment_chunks = [
        f"{i + 1}\n{(base_ts + timedelta(seconds=segment.start)).strftime('%H:%M:%S.%f')[:-3]} --> {(base_ts + timedelta(seconds=segment.end)).strftime('%H:%M:%S.%f')[:-3]}\n{segment.text}"
        for i, segment in enumerate(segments)
    ]
    return "WEBVTT\n\n" + "\n\n".join(segment_chunks)


class HTTPHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        # Handle HEAD requests by calling GET but without sending body
        self._handle_request(send_body=False)

    def do_GET(self):
        # Handle GET requests normally
        self._handle_request(send_body=True)

    def _handle_request(self, send_body: bool = True) -> None:
        response_content = None
        if self.path == "/playlist.m3u8":
            response_content = base_playlist_ser
        elif self.path == "/chunklist.m3u8":
            response_content = chunk_list_ser
        elif self.path == "/subs.m3u8":
            response_content = sub_list_ser
        elif self.path.startswith("/subs_") and self.path.endswith(".m3u8"):
            # Handle language-specific subtitle playlists like /subs_en.m3u8, /subs_ru.m3u8
            if self.path == "/subs_en.m3u8":
                response_content = sub_list_trans_ser
            else:
                response_content = sub_list_orig_ser
        elif self.path == "/subs.trans.m3u8":
            response_content = sub_list_trans_ser
        elif self.path == "/subs.orig.m3u8":
            response_content = sub_list_orig_ser
        elif (
            self.path == INIT_SEGMENT_URI
            and init_segment_created
            and init_segment_path
            and os.path.exists(init_segment_path)
        ):
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(os.path.getsize(init_segment_path)))
            self.end_headers()
            with open(init_segment_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return
        elif self.path in translated_chunk_paths:
            content_type = "video/mp4" if self.path.endswith(".mp4") else "video/mp2t"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header(
                "Content-Length",
                str(os.path.getsize(translated_chunk_paths[self.path])),
            )
            self.end_headers()

            with open(translated_chunk_paths[self.path], "rb") as f:
                shutil.copyfileobj(f, self.wfile)

            return
        elif (
            self.path in chunk_to_vtt
            or self.path in chunk_to_vtt_trans
            or self.path in chunk_to_vtt_orig
        ):
            vtt_content = (
                chunk_to_vtt.get(self.path)
                or chunk_to_vtt_trans.get(self.path)
                or chunk_to_vtt_orig.get(self.path)
            )
            if vtt_content is not None:
                response_content = bytes(vtt_content, "utf-8")

        self.send_response(200 if response_content else 404)

        if self.path.endswith(".m3u8"):
            self.send_header(
                "Content-Type", "application/vnd.apple.mpegurl; charset=utf-8"
            )
        elif self.path.endswith(".vtt"):
            self.send_header("Content-Type", "text/vtt; charset=utf-8")

        if response_content:
            self.send_header("Content-Length", str(len(response_content)))

        self.end_headers()
        if response_content and send_body:
            self.wfile.write(response_content)


def http_listener(server_address: Tuple[str, int], stop_event: threading.Event):
    logger.info(f"Web server now listening on {server_address}...")
    server = ThreadingHTTPServer(server_address, HTTPHandler)
    server.timeout = 1  # Set timeout to allow checking stop_event
    while not stop_event.is_set():
        server.handle_request()
    server.server_close()
    logger.info("HTTP server stopped")


def normalise_chunk_uri(chunk_uri: str) -> str:
    # Use dynamic extension (.ts by default, .mp4 when mp4_container is enabled)
    chunk_uri = os.path.splitext(chunk_uri)[0] + container_ext
    chunk_uri = chunk_uri.replace("../", "").replace("./", "")
    return "/" + chunk_uri


def ensure_segment_uri(uri: Optional[str]) -> str:
    if uri is None:
        raise ValueError("Segment URI is missing")
    return uri


def parse_m3u8_version(value: Optional[str]) -> int:
    if not value:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def check_bindeps_present():
    required_binaries = ("ffmpeg", "ffprobe")
    for required_binary in required_binaries:
        if not shutil.which(required_binary):
            logger.error(
                f"{required_binary} binary not found. Check your platform PATH and ensure that you've installed the required packages."
            )
            sys.exit(1)


async def download_chunk(
    session: aiohttp.ClientSession,
    base_uri: Optional[str],
    segment: m3u8.Segment,
    chunk_dir: str,
):
    if base_uri is None:
        raise ValueError("Base URI is missing for segment download")
    segment_uri = ensure_segment_uri(segment.uri)
    chunk_url = os.path.join(base_uri, segment_uri)
    chunk_uri = normalise_chunk_uri(segment_uri)
    if chunk_uri not in translated_chunk_paths:
        logger.info(f"Downloading segment {chunk_uri}...")
        try:
            async with aiofiles.tempfile.NamedTemporaryFile(
                dir=chunk_dir, delete=False, suffix=".ts"
            ) as chunk_fp:
                async with session.get(chunk_url, raise_for_status=True) as response:
                    async for chunk in response.content.iter_chunked(16384):
                        await chunk_fp.write(chunk)

                    await chunk_fp.close()
        except aiohttp.ClientError as e:
            logger.error(
                f"Failed to download chunk {chunk_uri}, stream may skip...", exc_info=e
            )
            raise e
        else:
            logger.info(f"Downloaded segment {chunk_uri}")
            return chunk_fp.name
    else:
        # Chunk already exists, return the existing path
        return translated_chunk_paths[chunk_uri]


def load_filter_dict():
    global filter_dict
    try:
        if os.path.exists(filter_file_path):
            with open(filter_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                filter_dict = data
    except Exception as e:
        logger.error(f"Failed to load filter dictionary: {e}")


def load_custom_vocabulary(language: str, vocabulary_file: Optional[str] = None):
    """Load language-specific custom vocabulary"""
    global custom_vocabulary, initial_prompt_text

    # Use provided file path or fall back to global
    vocab_file_path = vocabulary_file or vocabulary_file_path

    try:
        if os.path.exists(vocab_file_path):
            with open(vocab_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                # Process custom vocabulary if it exists
                if "custom_vocabulary" in data and isinstance(
                    data["custom_vocabulary"], dict
                ):
                    vocab_dict = data["custom_vocabulary"]

                    if language in vocab_dict and isinstance(
                        vocab_dict[language], list
                    ):
                        custom_vocabulary = vocab_dict[language]

                        # Generate initial prompt for Whisper with the vocabulary words
                        quoted_terms = [f'"{term}"' for term in custom_vocabulary]
                        initial_prompt_text = (
                            "The following terms may appear in this audio: "
                            + ", ".join(quoted_terms)
                            + "."
                        )
                        logger.info(
                            f"Custom vocabulary loaded for language '{language}' with {len(custom_vocabulary)} terms: {', '.join(custom_vocabulary)}"
                        )
                        logger.debug(f"Initial prompt: {initial_prompt_text}")
                    else:
                        # No vocabulary for this language - disable custom vocabulary
                        custom_vocabulary = []
                        initial_prompt_text = ""
                        logger.info(
                            f"No custom vocabulary found for language '{language}' - custom vocabulary disabled"
                        )
                else:
                    # No custom vocabulary section - disable
                    custom_vocabulary = []
                    initial_prompt_text = ""
                    logger.info("No custom vocabulary configuration found")
        else:
            # No vocabulary file - disable
            custom_vocabulary = []
            initial_prompt_text = ""
            logger.info(
                f"Vocabulary file '{vocab_file_path}' not found - custom vocabulary disabled"
            )
    except Exception as e:
        logger.error(f"Failed to load custom vocabulary: {e}")
        custom_vocabulary = []
        initial_prompt_text = ""


def should_filter_segment(text: str) -> bool:
    """Return True if segment should be filtered out based on content."""
    if not filter_dict:
        return False
    text = text.lower()
    raw_filter_words = filter_dict.get("filter_words", [])
    if not isinstance(raw_filter_words, list):
        return False
    filter_words = [
        word for word in cast(list[object], raw_filter_words) if isinstance(word, str)
    ]
    return any(word.lower() in text for word in filter_words)


async def transcribe_chunk(
    args: argparse.Namespace,
    model: WhisperModel,
    chunk_dir: str,
    segment_uri: str,
    chunk_name: str,
) -> Tuple[str, str]:
    global init_segment_created, init_segment_path
    ts_probe_proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-i",
        chunk_name,
        "-show_entries",
        "stream=start_time",
        "-loglevel",
        "quiet",
        "-select_streams",
        "a:0",
        "-of",
        "csv=p=0",
        stdout=asyncio.subprocess.PIPE,
    )
    ts_probe_stdout, _ = await ts_probe_proc.communicate()
    start_ts = timedelta(seconds=float(ts_probe_stdout.splitlines()[0]))

    loop = asyncio.get_running_loop()

    # Add custom vocabulary initial prompt if available
    initial_prompt = (
        initial_prompt_text if initial_prompt_text and not args.debug else None
    )
    if initial_prompt:
        logger.debug(f"Using initial prompt for transcription: {initial_prompt}")

    segments: list[SegmentLike] = []
    segments_orig: list[SegmentLike] = []
    segments_trans: list[SegmentLike] = []

    # Run transcription and translation in parallel if both_tracks is enabled
    if args.both_tracks:
        # Transcribe in source language
        segments_orig_raw, _ = await loop.run_in_executor(
            None,
            lambda: cast(Any, model).transcribe(
                chunk_name,
                beam_size=args.beam_size,
                vad_filter=args.vad_filter,
                language=args.language,
                task="transcribe",
                initial_prompt=initial_prompt,
            ),
        )
        segments_orig = list(cast(Iterable[SegmentLike], segments_orig_raw))
        # Translate to English
        segments_trans_raw, _ = await loop.run_in_executor(
            None,
            lambda: cast(Any, model).transcribe(
                chunk_name,
                beam_size=args.beam_size,
                vad_filter=args.vad_filter,
                language=args.language,
                task="translate",
                initial_prompt=initial_prompt,
            ),
        )
        segments_trans = list(cast(Iterable[SegmentLike], segments_trans_raw))

        # Filter segments
        segments_orig = [
            seg for seg in segments_orig if not should_filter_segment(seg.text)
        ]
        segments_trans = [
            seg for seg in segments_trans if not should_filter_segment(seg.text)
        ]

        if not args.hard_subs and not args.embedded_subs:
            vtt_uri = os.path.splitext(segment_uri)[0]
            if segments_orig:  # Only add if there are segments after filtering
                chunk_to_vtt_orig[vtt_uri + ".orig.vtt"] = segments_to_webvtt(
                    segments_orig, start_ts
                )
            if segments_trans:  # Only add if there are segments after filtering
                chunk_to_vtt_trans[vtt_uri + ".trans.vtt"] = segments_to_webvtt(
                    segments_trans, start_ts
                )
            return segment_uri, chunk_name
    else:
        # Original behavior with filtering
        segments_raw, _ = await loop.run_in_executor(
            None,
            lambda: cast(Any, model).transcribe(
                chunk_name,
                beam_size=args.beam_size,
                vad_filter=args.vad_filter,
                language=args.language,
                task="transcribe" if args.transcribe else "translate",
                initial_prompt=initial_prompt,
            ),
        )
        segments = list(cast(Iterable[SegmentLike], segments_raw))

        # Filter segments
        segments = [seg for seg in segments if not should_filter_segment(seg.text)]

        if not args.hard_subs and not args.embedded_subs:
            vtt_uri = os.path.splitext(segment_uri)[0] + ".vtt"
            if segments:  # Only add if there are segments after filtering
                chunk_to_vtt[vtt_uri] = segments_to_webvtt(segments, start_ts)
            return segment_uri, chunk_name

    if args.embedded_subs:
        logger.info(f"Starting embedded subtitles processing for {segment_uri}")
        # Embedded subtitles logic
        if args.both_tracks:
            logger.info(
                f"Both tracks mode: orig={len(segments_orig)}, trans={len(segments_trans)}"
            )
            # Both tracks mode: embed both original and translated subtitles
            if segments_orig or segments_trans:
                srt_files: list[str] = []
                ffmpeg_cmd: list[str] = [
                    "ffmpeg",
                    "-hwaccel",
                    "auto",
                    "-i",
                    chunk_name,
                ]

                # Add SRT inputs and prepare temp files
                if segments_orig:
                    async with aiofiles.tempfile.NamedTemporaryFile(
                        dir=chunk_dir, delete=False, suffix=".orig.srt"
                    ) as srt_orig_file:
                        srt_content_orig = segments_to_srt(segments_orig, start_ts)
                        await srt_orig_file.write(bytes(srt_content_orig, "utf-8"))
                        await srt_orig_file.close()
                        srt_orig_name = cast(str, srt_orig_file.name)
                        srt_files.append(srt_orig_name)
                        ffmpeg_cmd.extend(["-f", "srt", "-i", srt_orig_name])

                if segments_trans:
                    async with aiofiles.tempfile.NamedTemporaryFile(
                        dir=chunk_dir, delete=False, suffix=".trans.srt"
                    ) as srt_trans_file:
                        srt_content_trans = segments_to_srt(segments_trans, start_ts)
                        await srt_trans_file.write(bytes(srt_content_trans, "utf-8"))
                        await srt_trans_file.close()
                        srt_trans_name = cast(str, srt_trans_file.name)
                        srt_files.append(srt_trans_name)
                        ffmpeg_cmd.extend(["-f", "srt", "-i", srt_trans_name])

                # Build mapping - map video and audio from input 0
                ffmpeg_cmd.extend(["-map", "0:v:0"])  # Video stream
                ffmpeg_cmd.extend(["-map", "0:a:0"])  # Audio stream

                # Map subtitle streams from SRT inputs
                subtitle_input_idx = 1  # Start from input 1 (first SRT file)
                subtitle_stream_idx = 0  # For metadata indexing

                if segments_orig:
                    ffmpeg_cmd.extend(["-map", f"{subtitle_input_idx}:0"])
                    subtitle_input_idx += 1

                if segments_trans:
                    ffmpeg_cmd.extend(["-map", f"{subtitle_input_idx}:0"])

                # Encoding options for subtitle stream
                if args.mp4_container:
                    ffmpeg_cmd.extend(
                        ["-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text"]
                    )
                else:
                    ffmpeg_cmd.extend(
                        ["-c:v", "copy", "-c:a", "copy", "-c:s", "dvb_subtitle"]
                    )

                # Add language metadata and subtitle disposition
                if segments_orig:
                    orig_lang = args.language or "rus"
                    ffmpeg_cmd.extend(
                        [
                            "-metadata:s:s:" + str(subtitle_stream_idx),
                            f"language={orig_lang}",
                        ]
                    )
                    ffmpeg_cmd.extend(
                        [
                            "-metadata:s:s:" + str(subtitle_stream_idx),
                            f"title=Original ({orig_lang.upper()})",
                        ]
                    )
                    subtitle_stream_idx += 1
                if segments_trans:
                    ffmpeg_cmd.extend(
                        ["-metadata:s:s:" + str(subtitle_stream_idx), "language=eng"]
                    )
                    ffmpeg_cmd.extend(
                        ["-metadata:s:s:" + str(subtitle_stream_idx), "title=English"]
                    )

                # Output options with TS-specific parameters for live streaming
                chunk_fp_name_split = os.path.splitext(chunk_name)
                if args.mp4_container:
                    embedded_chunk_name = chunk_fp_name_split[0] + "_embedded.mp4"
                    ffmpeg_cmd.extend(
                        [
                            "-bsf:a",
                            "aac_adtstoasc",
                            "-copyts",
                            "-muxpreload",
                            "0",
                            "-muxdelay",
                            "0",
                            "-movflags",
                            "+faststart+frag_keyframe+empty_moov+omit_tfhd_offset",
                            "-f",
                            "mp4",
                            "-loglevel",
                            "quiet",
                            embedded_chunk_name,
                        ]
                    )
                else:
                    embedded_chunk_name = (
                        chunk_fp_name_split[0] + "_embedded" + chunk_fp_name_split[1]
                    )
                    ffmpeg_cmd.extend(
                        [
                            "-bsf:a",
                            "aac_adtstoasc",
                            "-copyts",
                            "-muxpreload",
                            "0",
                            "-muxdelay",
                            "0",
                            "-movflags",
                            "+faststart+frag_keyframe+empty_moov+omit_tfhd_offset",
                            "-f",
                            "mpegts",
                            "-copyts",
                            "-muxpreload",
                            "0",
                            "-muxdelay",
                            "0",
                            "-mpegts_service_type",
                            "digital_tv",  # Help Wowza recognize service type
                            "-mpegts_pmt_start_pid",
                            "0x1000",  # Explicit PMT PID
                            "-loglevel",
                            "quiet",
                            embedded_chunk_name,
                        ]
                    )

                # Execute FFmpeg command
                if args.debug:
                    logger.debug(f"Full FFmpeg command: {' '.join(ffmpeg_cmd)}")
                else:
                    logger.info(
                        f"Executing FFmpeg for embedded subtitles: {' '.join(ffmpeg_cmd[:10])}..."
                    )
                ffmpeg_proc = await asyncio.create_subprocess_exec(
                    *ffmpeg_cmd, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await ffmpeg_proc.communicate()
                if ffmpeg_proc.returncode != 0:
                    logger.error(
                        f"FFmpeg failed for {segment_uri} with return code {ffmpeg_proc.returncode}"
                    )
                    if stderr:
                        logger.error(f"FFmpeg stderr: {stderr.decode()}")
                else:
                    logger.info(f"FFmpeg completed for {segment_uri}")
                    # Generate init.mp4 only once when using fragmented MP4 segments
                    if args.mp4_container:
                        if not init_segment_created:
                            try:
                                init_segment_path = os.path.join(chunk_dir, "init.mp4")
                                init_cmd: list[str] = [
                                    "ffmpeg",
                                    "-i",
                                    embedded_chunk_name,
                                    "-c",
                                    "copy",
                                    "-map",
                                    "0",
                                    "-movflags",
                                    "+faststart+empty_moov",
                                    "-f",
                                    "mp4",
                                    "-t",
                                    "0",
                                    init_segment_path,
                                    "-y",
                                    "-loglevel",
                                    "quiet",
                                ]
                                if args.debug:
                                    logger.debug(
                                        f"Generating init.mp4: {' '.join(init_cmd)}"
                                    )
                                init_proc = await asyncio.create_subprocess_exec(
                                    *init_cmd
                                )
                                await init_proc.communicate()
                                if init_proc.returncode == 0 and init_segment_path:
                                    if os.path.exists(init_segment_path):
                                        init_segment_created = True
                                        logger.info(
                                            "init.mp4 generated and ready to serve"
                                        )
                            except Exception as e:
                                logger.error(f"Failed to generate init.mp4: {e}")
                    # Verify the output file has subtitle streams
                    if args.debug:
                        verify_cmd: list[str] = [
                            "ffprobe",
                            "-v",
                            "quiet",
                            "-print_format",
                            "json",
                            "-show_streams",
                            embedded_chunk_name,
                        ]
                        try:
                            verify_proc = await asyncio.create_subprocess_exec(
                                *verify_cmd, stdout=asyncio.subprocess.PIPE
                            )
                            stdout, _ = await verify_proc.communicate()
                            if verify_proc.returncode == 0:
                                import json

                                probe_data = json.loads(stdout.decode())
                                subtitle_streams = [
                                    s
                                    for s in probe_data.get("streams", [])
                                    if s.get("codec_type") == "subtitle"
                                ]
                                logger.debug(
                                    f"Embedded file has {len(subtitle_streams)} subtitle streams: {[s.get('tags', {}).get('language', 'unknown') for s in subtitle_streams]}"
                                )
                        except Exception as e:
                            logger.debug(f"Failed to verify embedded subtitles: {e}")

                # Cleanup SRT files
                for srt_file in srt_files:
                    try:
                        os.unlink(srt_file)
                    except OSError:
                        pass

                os.unlink(chunk_name)
                return segment_uri, embedded_chunk_name
        else:
            logger.info(f"Single track mode: segments={len(segments)}")
            # Single track mode: embed one subtitle track
            if segments:
                async with aiofiles.tempfile.NamedTemporaryFile(
                    dir=chunk_dir, delete=False, suffix=".srt"
                ) as srt_file:
                    srt_content = segments_to_srt(segments, start_ts)
                    await srt_file.write(bytes(srt_content, "utf-8"))
                    await srt_file.close()
                    srt_file_name = cast(str, srt_file.name)

                    chunk_fp_name_split = os.path.splitext(chunk_name)
                    embedded_chunk_name = (
                        chunk_fp_name_split[0] + "_embedded" + chunk_fp_name_split[1]
                    )

                    # Determine language for metadata
                    lang_code = (
                        "eng" if not args.transcribe else (args.language or "eng")
                    )

                    ffmpeg_cmd_embedded: list[str] = [
                        "ffmpeg",
                        "-hwaccel",
                        "auto",
                        "-i",
                        chunk_name,
                        "-f",
                        "srt",
                        "-i",
                        srt_file_name,
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a:0",
                        "-map",
                        "1:0",
                        "-c:v",
                        "copy",
                        "-c:a",
                        "copy",
                        "-c:s",
                        "mov_text" if args.mp4_container else "dvb_subtitle",
                        "-metadata:s:s:0",
                        f"language={lang_code}",
                        "-metadata:s:s:0",
                        f"title=Subtitles ({lang_code.upper()})",
                        # Container/flags depending on mp4_container
                        *(
                            [
                                "-bsf:a",
                                "aac_adtstoasc",
                                "-copyts",
                                "-muxpreload",
                                "0",
                                "-muxdelay",
                                "0",
                                "-movflags",
                                "+faststart+frag_keyframe+empty_moov+omit_tfhd_offset",
                                "-f",
                                "mp4",
                                "-loglevel",
                                "quiet",
                            ]
                            if args.mp4_container
                            else [
                                "-f",
                                "mpegts",
                                "-copyts",
                                "-muxpreload",
                                "0",
                                "-muxdelay",
                                "0",
                                "-mpegts_service_type",
                                "digital_tv",
                                "-mpegts_pmt_start_pid",
                                "0x1000",
                                "-loglevel",
                                "quiet",
                            ]
                        ),
                        embedded_chunk_name,
                    ]

                    if args.debug:
                        logger.debug(
                            f"🔧 Full single track FFmpeg command: {' '.join(ffmpeg_cmd_embedded)}"
                        )
                    else:
                        logger.info(
                            f"🔧 Executing single track FFmpeg: {' '.join(ffmpeg_cmd_embedded[:8])}..."
                        )
                    ffmpeg_proc = await asyncio.create_subprocess_exec(
                        *ffmpeg_cmd_embedded, stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await ffmpeg_proc.communicate()
                    if ffmpeg_proc.returncode != 0:
                        logger.error(
                            f"Single track FFmpeg failed for {segment_uri} with return code {ffmpeg_proc.returncode}"
                        )
                        if stderr:
                            logger.error(
                                f"Single track FFmpeg stderr: {stderr.decode()}"
                            )
                    else:
                        logger.info(f"Single track FFmpeg completed for {segment_uri}")
                        # Generate init.mp4 only once when using fragmented MP4 segments
                        if args.mp4_container:
                            if not init_segment_created:
                                try:
                                    init_segment_path = os.path.join(
                                        chunk_dir, "init.mp4"
                                    )
                                    init_cmd_embedded: list[str] = [
                                        "ffmpeg",
                                        "-i",
                                        embedded_chunk_name,
                                        "-c",
                                        "copy",
                                        "-map",
                                        "0",
                                        "-movflags",
                                        "+faststart+empty_moov",
                                        "-f",
                                        "mp4",
                                        "-t",
                                        "0",
                                        init_segment_path,
                                        "-y",
                                        "-loglevel",
                                        "quiet",
                                    ]
                                    if args.debug:
                                        logger.debug(
                                            f"Generating init.mp4: {' '.join(init_cmd_embedded)}"
                                        )
                                    init_proc = await asyncio.create_subprocess_exec(
                                        *init_cmd_embedded
                                    )
                                    await init_proc.communicate()
                                    if init_proc.returncode == 0 and init_segment_path:
                                        if os.path.exists(init_segment_path):
                                            init_segment_created = True
                                            logger.info(
                                                "init.mp4 generated and ready to serve"
                                            )
                                except Exception as e:
                                    logger.error(f"Failed to generate init.mp4: {e}")

                    # Cleanup
                    try:
                        os.unlink(srt_file_name)
                    except OSError:
                        pass

                    os.unlink(chunk_name)
                    return segment_uri, embedded_chunk_name

        return segment_uri, chunk_name

    if args.hard_subs:
        # Original hard subs logic with filtering
        async with aiofiles.tempfile.NamedTemporaryFile(
            dir=chunk_dir, delete=False, suffix=".srt"
        ) as srt_file:
            segments_to_use = segments if not args.both_tracks else segments_trans
            segments_to_use = [
                seg for seg in segments_to_use if not should_filter_segment(seg.text)
            ]

            srt_content = segments_to_srt(segments_to_use, start_ts)
            if not srt_content:
                return segment_uri, chunk_name

            await srt_file.write(bytes(srt_content, "utf-8"))
            await srt_file.close()
            srt_file_name = cast(str, srt_file.name)
            chunk_fp_name_split = os.path.splitext(chunk_name)
            translated_chunk_name = (
                chunk_fp_name_split[0] + "_trans" + chunk_fp_name_split[1]
            )

            ffmpeg_sub_proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hwaccel",
                "auto",
                "-i",
                chunk_name,
                "-copyts",
                "-muxpreload",
                "0",
                "-muxdelay",
                "0",
                "-preset",
                "ultrafast",
                "-c:a",
                "copy",
                "-loglevel",
                "quiet",
                "-vf",
                f"subtitles={os.path.basename(srt_file_name)}",
                translated_chunk_name,
            )
            await ffmpeg_sub_proc.communicate()

            os.unlink(chunk_name)
            return segment_uri, translated_chunk_name

    return segment_uri, chunk_name


async def cleanup(
    session: aiohttp.ClientSession,
    chunk_dir: str,
    prev_cwd: str,
    stop_event: threading.Event,
):
    logger.info("Cleaning up resources...")
    await session.close()
    os.chdir(prev_cwd)
    try:
        # Clean up any remaining temporary files
        for chunk_path in list(translated_chunk_paths.values()):
            try:
                if os.path.exists(chunk_path):
                    os.unlink(chunk_path)
            except OSError as e:
                logger.warning(f"Failed to remove temporary file {chunk_path}: {e}")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    finally:
        stop_event.set()


def get_local_ip():
    try:
        # Get the local IP by creating a temporary socket connection
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Doesn't actually send any data
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


async def main():
    check_bindeps_present()

    parser = argparse.ArgumentParser(prog="livevtt")
    parser.add_argument(
        "-u",
        "--url",
        default="https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8",
        help="URL of the HLS stream (defaults to TVRain stream)",
    )
    parser.add_argument(
        "-s",
        "--hard-subs",
        action="store_true",
        help="Set if you want the subtitles to be baked into the stream itself",
    )
    parser.add_argument(
        "-e",
        "--embedded-subs",
        action="store_true",
        help="Embed subtitles as metadata streams within TS segments (experimental)",
    )
    parser.add_argument(
        "-l",
        "--bind-address",
        type=str,
        help="The IP address to bind to " "(defaults to 127.0.0.1)",
        default="127.0.0.1",
    )
    parser.add_argument(
        "-p",
        "--bind-port",
        type=int,
        help="The port to bind to (defaults to 8000)",
        default=8000,
    )
    parser.add_argument(
        "-pl",
        "--public-address",
        type=str,
        help="The public IP address to use in URLs " "(defaults to bind-address)",
        default=None,
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        help="Whisper model to use (defaults to large)",
        default="large",
        choices=available_models(),
    )
    parser.add_argument(
        "-b",
        "--beam-size",
        type=int,
        help="Beam size to use (defaults to 5)",
        default=5,
    )
    parser.add_argument(
        "-c",
        "--use-cuda",
        type=lambda x: str(x).lower() in ["true", "1", "yes"],
        help="Use CUDA where available. Defaults to true",
        default=True,
    )
    parser.add_argument(
        "-t",
        "--transcribe",
        action="store_true",
        help="If set, transcribes rather than translates the given stream.",
    )
    parser.add_argument(
        "-vf",
        "--vad-filter",
        type=lambda x: str(x).lower() in ["true", "1", "yes"],
        help="Whether to utilise the Silero VAD model to try and filter out silences. Defaults to false.",
        default=False,
    )
    parser.add_argument(
        "-la",
        "--language",
        type=str,
        help="The original language of the stream, "
        "if known/not multi-lingual. Can be left unset.",
    )
    parser.add_argument(
        "-ua",
        "--user-agent",
        type=str,
        help="User agent to use to retrieve playlists / " "stream chunks.",
        default="VLC/3.0.18 LibVLC/3.0.18",
    )
    parser.add_argument(
        "-bt",
        "--both-tracks",
        action="store_true",
        help="Enable both transcription and translation tracks",
    )
    parser.add_argument(
        "-f",
        "--filter-file",
        type=str,
        help="Path to JSON file containing words to filter out",
        default="config/filter.json",
    )
    parser.add_argument(
        "-v",
        "--vocabulary-file",
        type=str,
        help="Path to JSON file containing custom vocabulary for better transcription accuracy",
        default="config/vocabulary.json",
    )
    parser.add_argument(
        "-cv",
        "--custom-vocabulary",
        type=lambda x: str(x).lower() in ["true", "1", "yes"],
        help="Enable custom vocabulary to improve transcription accuracy for specific terms. Defaults to true.",
        default=True,
    )

    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )

    # New: option to embed subtitles in fragmented MP4 with mov_text codec
    parser.add_argument(
        "--mp4-container",
        action="store_true",
        help="(experimental, with --embedded-subs) Output each processed segment as fragmented MP4 containing mov_text subtitles instead of MPEG-TS.",
    )

    args = parser.parse_args()

    # Apply CLI-provided config paths before loading filters
    global filter_file_path, vocabulary_file_path
    filter_file_path = args.filter_file
    vocabulary_file_path = args.vocabulary_file
    load_filter_dict()  # Load filter dictionary at startup

    # Validate subtitle mode options
    subtitle_modes = sum([args.hard_subs, args.embedded_subs])
    if subtitle_modes > 1:
        logger.error(
            "Cannot use multiple subtitle modes simultaneously. Choose only one of: --hard-subs, --embedded-subs, or default (WebVTT sidecar)"
        )
        sys.exit(1)

    # Validate mp4 container usage
    if args.mp4_container and not args.embedded_subs:
        logger.error(
            "--mp4-container can only be used together with --embedded-subs mode"
        )
        sys.exit(1)

    # Set logging level based on debug flag
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    # Log subtitle mode
    if args.hard_subs:
        logger.info("Using hard-burned subtitles mode")
    elif args.embedded_subs:
        logger.info("Using embedded subtitles mode (experimental)")
    else:
        logger.info("Using WebVTT sidecar subtitles mode (default)")

    # If custom vocabulary is disabled, clear the initial prompt
    if not args.custom_vocabulary:
        global initial_prompt_text
        initial_prompt_text = ""
        logger.info("Custom vocabulary disabled via command line argument")
    else:
        # Load language-specific custom vocabulary
        load_custom_vocabulary(args.language or "en", args.vocabulary_file)

    # Determine container extension for segment files
    global container_ext
    container_ext = ".mp4" if args.mp4_container else ".ts"

    stop_event = threading.Event()
    session = aiohttp.ClientSession(headers={"User-Agent": args.user_agent})
    loop = asyncio.get_running_loop()

    device = "cuda" if args.use_cuda else "cpu"
    # Set compute_type explicitly for CUDA - 'auto' often fails to use GPU
    if device == "cuda":
        compute_type = "float16"
    else:
        compute_type = "int8"

    logger.info(
        f"Using {device} as the device type for the model with compute_type={compute_type}"
    )

    model = WhisperModel(args.model, device=device, compute_type=compute_type)

    # Log which device the model actually loaded on
    try:
        # This is a simple check - if model creation doesn't fail, log success
        logger.info(f'Whisper model "{args.model}" loaded successfully on {device}')
    except Exception as e:
        logger.error(f"Failed to load model on {device}: {e}")
        raise

    base_playlist = m3u8.load(args.url)

    # Handle both master playlists (with multiple streams) and media playlists (direct stream)
    if base_playlist.playlists:
        # Master playlist - select highest bitrate stream
        highest_bitrate_stream = sorted(
            base_playlist.playlists,
            key=lambda x: x.stream_info.bandwidth or 0,
            reverse=True,
        )[0]
        base_playlist.playlists = PlaylistList([cast(Any, highest_bitrate_stream)])
        stream_uri = (
            cast(Optional[str], highest_bitrate_stream.absolute_uri) or args.url
        )
    else:
        # Media playlist - use it directly
        logger.info("Direct media playlist detected, using stream directly")
        stream_uri = args.url

    modified_base_playlist = copy.deepcopy(base_playlist)

    # Ensure HLS version is high enough for fMP4 / EXT-X-MAP when mp4 container is used
    if args.mp4_container:
        modified_base_playlist.version = str(
            max(7, parse_m3u8_version(modified_base_playlist.version))
        )
    else:
        # Keep at least version 5 for subtitle support in TS mode
        modified_base_playlist.version = str(
            max(5, parse_m3u8_version(modified_base_playlist.version))
        )

    # Only modify playlist URI if it's a master playlist
    if modified_base_playlist.playlists:
        modified_base_playlist.playlists[0].uri = "chunklist.m3u8"  # Removed path join

    # If mp4 container, append tx3g to CODECS attribute of variant
    if args.mp4_container and modified_base_playlist.playlists:
        variant = modified_base_playlist.playlists[0]
        codecs_value = variant.stream_info.codecs or ""
        # Only append tx3g if codecs are already specified
        if codecs_value and "tx3g" not in codecs_value:
            variant.stream_info.codecs = f"{codecs_value},tx3g"

    if (
        not args.hard_subs
        and not args.embedded_subs
        and modified_base_playlist.playlists
    ):
        # Only add subtitle tracks for master playlists when using WebVTT sidecar mode
        if args.both_tracks:
            # Add both subtitle tracks with language-specific URI naming
            subtitle_trans = m3u8.Media(
                uri="subs_en.m3u8",
                type="SUBTITLES",
                group_id="Subtitle",
                language="en",
                name="English",
                autoselect="NO",
            )

            orig_lang = args.language or "ru"
            subtitle_orig = m3u8.Media(
                uri=f"subs_{orig_lang}.m3u8",
                type="SUBTITLES",
                group_id="Subtitle",
                language=orig_lang,
                name={"en": "English", "ru": "Russian"}.get(orig_lang, "Original"),
                autoselect="NO",
            )

            modified_base_playlist.add_media(subtitle_trans)
            modified_base_playlist.add_media(subtitle_orig)
            modified_base_playlist.playlists[0].media += [subtitle_trans, subtitle_orig]
        else:
            # Original single subtitle track logic with language-specific URI naming
            if not args.transcribe:
                subtitle_lang = "en"
                subtitle_name = "English"
            else:
                subtitle_lang = args.language or "en"
            subtitle_name = {
                "en": "English",
                "ru": "Russian",
                "nl": "Dutch",
            }.get(subtitle_lang.lower(), subtitle_lang.capitalize())

            subtitle_list = m3u8.Media(
                uri=f"subs_{subtitle_lang}.m3u8",
                type="SUBTITLES",
                group_id="Subtitle",
                language=subtitle_lang,
                name=subtitle_name,
                autoselect="NO",
            )
            modified_base_playlist.add_media(subtitle_list)
            modified_base_playlist.playlists[0].media += [subtitle_list]

    global base_playlist_ser
    base_playlist_ser = bytes(modified_base_playlist.dumps(), "ascii")

    http_thread = threading.Thread(
        target=http_listener,
        daemon=True,
        args=((args.bind_address, args.bind_port), stop_event),
    )
    http_thread.start()

    async with aiofiles.tempfile.TemporaryDirectory() as chunk_dir:
        prev_cwd = os.getcwd()
        os.chdir(chunk_dir)

        cleanup_task: Optional[asyncio.Task[None]] = None

        def schedule_cleanup() -> None:
            nonlocal cleanup_task
            if cleanup_task is not None and not cleanup_task.done():
                return
            cleanup_task = asyncio.create_task(
                cleanup(session, chunk_dir, prev_cwd, stop_event)
            )

        # Set up signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, schedule_cleanup)

        try:
            while not stop_event.is_set():
                chunk_list = m3u8.load(stream_uri)

                sleep_duration = chunk_list.target_duration or 10

                if chunk_list.target_duration:
                    if int(MAX_TARGET_BUFFER_SECS / chunk_list.target_duration) < len(
                        chunk_list.segments
                    ):
                        chunk_list.segments = SegmentList(
                            chunk_list.segments[
                                -int(TARGET_BUFFER_SECS / chunk_list.target_duration) :
                            ]
                        )
                        chunk_list.media_sequence = chunk_list.segments[
                            0
                        ].media_sequence

                        if chunk_list.program_date_time:
                            chunk_list.program_date_time = chunk_list.segments[
                                0
                            ].current_program_date_time

                current_segments = [
                    normalise_chunk_uri(ensure_segment_uri(segment.uri))
                    for segment in chunk_list.segments
                ]

                for translated_chunk_name, translated_chunk_path in dict(
                    translated_chunk_paths
                ).items():
                    if translated_chunk_name not in current_segments:
                        os.unlink(translated_chunk_path)
                        del translated_chunk_paths[translated_chunk_name]

                if not args.hard_subs:
                    for translated_uri, translated_chunk_path in dict(
                        chunk_to_vtt
                    ).items():
                        if (
                            os.path.splitext(translated_uri)[0] + container_ext
                            not in current_segments
                        ):
                            del chunk_to_vtt[translated_uri]

                chunks_to_translate: dict[str, str] = {}

                for i, chunk_name in enumerate(
                    await asyncio.gather(
                        *[
                            download_chunk(
                                session, chunk_list.base_uri, segment, chunk_dir
                            )
                            for segment in chunk_list.segments
                        ],
                        return_exceptions=True,
                    )
                ):
                    if isinstance(chunk_name, Exception):
                        continue

                    chunk_name_str = cast(str, chunk_name)

                    normalised_segment_uri = current_segments[i]
                    if normalised_segment_uri not in translated_chunk_paths:
                        chunks_to_translate[normalised_segment_uri] = chunk_name_str

                for segment_uri, chunk_name in await asyncio.gather(
                    *[
                        transcribe_chunk(
                            args, model, chunk_dir, segment_uri, chunk_name
                        )
                        for segment_uri, chunk_name in chunks_to_translate.items()
                    ]
                ):
                    chunks_to_translate[segment_uri] = chunk_name

                for segment in chunk_list.segments:
                    segment_uri = ensure_segment_uri(segment.uri)
                    segment_name = normalise_chunk_uri(segment_uri)
                    segment.uri = segment_name.lstrip(
                        "/"
                    )  # Remove leading slash for relative path

                global chunk_list_ser

                # Ensure media playlist version supports EXT-X-MAP when using fMP4
                if args.mp4_container:
                    chunk_list.version = str(
                        max(7, parse_m3u8_version(chunk_list.version))
                    )
                else:
                    # HLS with WebVTT requires at least version 4
                    chunk_list.version = str(
                        max(4, parse_m3u8_version(chunk_list.version))
                    )

                playlist_str = chunk_list.dumps()
                # Inject EXT-X-MAP for mp4 container
                if args.mp4_container and init_segment_created:
                    lines = playlist_str.split("\n")
                    # HLS spec requires EXT-X-MAP to appear before any media segments
                    insert_idx = -1
                    for idx, line in enumerate(lines):
                        if line.startswith("#EXTINF"):
                            insert_idx = idx
                            break

                    if insert_idx != -1:
                        map_uri = INIT_SEGMENT_URI.lstrip("/")
                        lines.insert(insert_idx, f'#EXT-X-MAP:URI="{map_uri}"')
                        # Also ensure version is at least 7 for EXT-X-MAP
                        for idx, line in enumerate(lines):
                            if line.startswith("#EXT-X-VERSION"):
                                current_ver = int(line.split(":")[1])
                                if current_ver < 7:
                                    lines[idx] = "#EXT-X-VERSION:7"
                                break
                        playlist_str = "\n".join(lines)

                chunk_list_ser = bytes(playlist_str, "ascii")

                if not args.hard_subs and not args.embedded_subs:
                    # Only create WebVTT playlists when using sidecar subtitle mode
                    if args.both_tracks:
                        # Create two separate subtitle playlists
                        trans_chunk_list = copy.deepcopy(chunk_list)
                        orig_chunk_list = copy.deepcopy(chunk_list)

                        for segment in trans_chunk_list.segments:
                            segment_uri = ensure_segment_uri(segment.uri)
                            subtitle_name = (
                                os.path.splitext(segment_uri)[0] + ".trans.vtt"
                            )
                            segment.uri = subtitle_name

                        for segment in orig_chunk_list.segments:
                            segment_uri = ensure_segment_uri(segment.uri)
                            subtitle_name = (
                                os.path.splitext(segment_uri)[0] + ".orig.vtt"
                            )
                            segment.uri = subtitle_name

                        global sub_list_trans_ser, sub_list_orig_ser
                        sub_list_trans_ser = bytes(trans_chunk_list.dumps(), "ascii")
                        sub_list_orig_ser = bytes(orig_chunk_list.dumps(), "ascii")
                    else:
                        # Original single subtitle playlist logic
                        for segment in chunk_list.segments:
                            segment_uri = ensure_segment_uri(segment.uri)
                            subtitle_name = os.path.splitext(segment_uri)[0] + ".vtt"
                            segment.uri = subtitle_name

                        global sub_list_ser
                        sub_list_ser = bytes(chunk_list.dumps(), "ascii")

                translated_chunk_paths.update(chunks_to_translate)

                await asyncio.sleep(sleep_duration)
        except asyncio.CancelledError:
            logger.info("Received termination signal")
        finally:
            if cleanup_task is not None:
                await cleanup_task
            else:
                await cleanup(session, chunk_dir, prev_cwd, stop_event)
            http_thread.join(timeout=5)  # Wait for HTTP server to stop


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
