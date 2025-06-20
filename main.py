import argparse
import asyncio
import logging
import signal
import socket
import json
import os.path

import aiofiles.tempfile
import aiohttp
import faster_whisper
import m3u8
import os
import sys
import shutil
import copy
import threading

from datetime import timedelta, datetime
from typing import Iterable, Tuple, Optional, List
from faster_whisper import WhisperModel
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from faster_whisper.utils import available_models
from m3u8 import PlaylistList, SegmentList

translated_chunk_paths = {}
chunk_to_vtt = {}
chunk_to_vtt_trans = {}  # Dictionary for translated subtitles
chunk_to_vtt_orig = {}   # Dictionary for transcribed subtitles

CHUNK_LIST_BASE_URI = None
BASE_PLAYLIST_SER = None
CHUNK_LIST_SER = None
SUB_LIST_SER = None
SUB_LIST_TRANS_SER = None  # Global for translated subtitles playlist
SUB_LIST_ORIG_SER = None   # Global for transcribed subtitles playlist

TARGET_BUFFER_SECS = 60
MAX_TARGET_BUFFER_SECS = 120

FILTER_DICT = {}  # Dictionary of strings to filter out
FILTER_FILE = 'config/filter.json'  # File to store filter words
VOCABULARY_FILE = 'config/vocabulary.json'  # File to store custom vocabulary

# New global variables for custom vocabulary
CUSTOM_VOCABULARY = {}  # Dictionary of custom vocabulary
INITIAL_PROMPT = ""    # Initial prompt for Whisper model

# New global variables for RTMP streaming
RTMP_ENABLED = False
RTMP_URL = None
RTMP_QUEUE = None

if sys.version_info < (3, 10):
    print(f'This script needs to be ran under Python 3.10 at minimum.')
    sys.exit(1)

logger = logging.getLogger('livevtt')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
                    handlers=[logging.StreamHandler()])


def segments_to_srt(segments: Iterable[faster_whisper.transcribe.Segment], ts_offset: timedelta) -> str:
    base_ts = datetime(1970, 1, 1, 0, 0, 0) + ts_offset
    segment_chunks = [
        f"{i + 1}\n{(base_ts + timedelta(seconds=segment.start)).strftime('%H:%M:%S,%f')[:-3]} --> {(base_ts + timedelta(seconds=segment.end)).strftime('%H:%M:%S,%f')[:-3]}\n{segment.text}"
        for i, segment in enumerate(segments)]
    return '\n\n'.join(segment_chunks)


def segments_to_webvtt(segments: Iterable[faster_whisper.transcribe.Segment], ts_offset: timedelta) -> str:
    base_ts = datetime(1970, 1, 1, 0, 0, 0) + ts_offset
    segment_chunks = [
        f"{i + 1}\n{(base_ts + timedelta(seconds=segment.start)).strftime('%H:%M:%S.%f')[:-3]} --> {(base_ts + timedelta(seconds=segment.end)).strftime('%H:%M:%S.%f')[:-3]}\n{segment.text}"
        for i, segment in enumerate(segments)]
    return 'WEBVTT\n\n' + '\n\n'.join(segment_chunks)


class HTTPHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        # Handle HEAD requests by calling GET but without sending body
        self._handle_request(send_body=False)
    
    def do_GET(self):
        # Handle GET requests normally
        self._handle_request(send_body=True)
    
    def _handle_request(self, send_body=True):
        response_content = None
        if self.path == '/playlist.m3u8':
            response_content = BASE_PLAYLIST_SER
        elif self.path == '/chunklist.m3u8':
            response_content = CHUNK_LIST_SER
        elif self.path == '/subs.m3u8':
            response_content = SUB_LIST_SER
        elif self.path.startswith('/subs_') and self.path.endswith('.m3u8'):
            # Handle language-specific subtitle playlists like /subs_en.m3u8, /subs_ru.m3u8
            if self.path == '/subs_en.m3u8':
                response_content = SUB_LIST_TRANS_SER
            else:
                response_content = SUB_LIST_ORIG_SER
        elif self.path == '/subs.trans.m3u8':
            response_content = SUB_LIST_TRANS_SER
        elif self.path == '/subs.orig.m3u8':
            response_content = SUB_LIST_ORIG_SER
        elif self.path in translated_chunk_paths:
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp2t')
            self.send_header('Content-Length', str(os.path.getsize(translated_chunk_paths[self.path])))
            self.end_headers()

            with open(translated_chunk_paths[self.path], 'rb') as f:
                shutil.copyfileobj(f, self.wfile)

            return
        elif self.path in chunk_to_vtt or self.path in chunk_to_vtt_trans or self.path in chunk_to_vtt_orig:
            vtt_content = chunk_to_vtt.get(self.path) or chunk_to_vtt_trans.get(self.path) or chunk_to_vtt_orig.get(self.path)
            response_content = bytes(vtt_content, 'utf-8')

        self.send_response(200 if response_content else 404)

        if self.path.endswith('.m3u8'):
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8')
        elif self.path.endswith('.vtt'):
            self.send_header('Content-Type', 'text/vtt; charset=utf-8')

        if response_content:
            self.send_header('Content-Length', str(len(response_content)))

        self.end_headers()
        if response_content and send_body:
            self.wfile.write(response_content)


def http_listener(server_address: Tuple[str, int], stop_event: threading.Event):
    logger.info(f'Web server now listening on {server_address}...')
    server = ThreadingHTTPServer(server_address, HTTPHandler)
    server.timeout = 1  # Set timeout to allow checking stop_event
    while not stop_event.is_set():
        server.handle_request()
    server.server_close()
    logger.info("HTTP server stopped")


def normalise_chunk_uri(chunk_uri: str) -> str:
    chunk_uri = os.path.splitext(chunk_uri)[0] + '.ts'
    chunk_uri = chunk_uri.replace('../', '').replace('./', '')
    return '/' + chunk_uri


def check_bindeps_present():
    required_binaries = ('ffmpeg', 'ffprobe')
    for required_binary in required_binaries:
        if not shutil.which(required_binary):
            logger.error(
                f"{required_binary} binary not found. Check your platform PATH and ensure that you've installed the required packages.")
            sys.exit(1)


async def download_chunk(session: aiohttp.ClientSession, base_uri: str, segment: m3u8.Segment, chunk_dir: str):
    chunk_url = os.path.join(base_uri, segment.uri)
    chunk_uri = normalise_chunk_uri(segment.uri)
    if chunk_uri not in translated_chunk_paths:
        logger.info(f'Downloading segment {chunk_uri}...')
        try:
            async with aiofiles.tempfile.NamedTemporaryFile(dir=chunk_dir, delete=False, suffix='.ts') as chunk_fp:
                async with session.get(chunk_url, raise_for_status=True) as response:
                    async for chunk in response.content.iter_chunked(16384):
                        await chunk_fp.write(chunk)

                    await chunk_fp.close()
        except aiohttp.ClientError as e:
            logger.error(f'Failed to download chunk {chunk_uri}, stream may skip...', exc_info=e)
            raise e
        else:
            logger.info(f'Downloaded segment {chunk_uri}')
            return chunk_fp.name
    else:
        # Chunk already exists, return the existing path
        return translated_chunk_paths[chunk_uri]


def load_filter_dict():
    global FILTER_DICT
    try:
        if os.path.exists(FILTER_FILE):
            with open(FILTER_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                FILTER_DICT = data
    except Exception as e:
        logger.error(f"Failed to load filter dictionary: {e}")


def load_custom_vocabulary(language: str, vocabulary_file: str = None):
    """Load language-specific custom vocabulary"""
    global CUSTOM_VOCABULARY, INITIAL_PROMPT
    
    # Use provided file path or fall back to global
    vocab_file_path = vocabulary_file or VOCABULARY_FILE
    
    try:
        if os.path.exists(vocab_file_path):
            with open(vocab_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Process custom vocabulary if it exists
                if 'custom_vocabulary' in data and isinstance(data['custom_vocabulary'], dict):
                    vocab_dict = data['custom_vocabulary']
                    
                    if language in vocab_dict and isinstance(vocab_dict[language], list):
                        CUSTOM_VOCABULARY = vocab_dict[language]
                        
                        # Generate initial prompt for Whisper with the vocabulary words
                        quoted_terms = [f'"{term}"' for term in CUSTOM_VOCABULARY]
                        INITIAL_PROMPT = "The following terms may appear in this audio: " + ", ".join(quoted_terms) + "."
                        logger.info(f"Custom vocabulary loaded for language '{language}' with {len(CUSTOM_VOCABULARY)} terms: {', '.join(CUSTOM_VOCABULARY)}")
                        logger.debug(f"Initial prompt: {INITIAL_PROMPT}")
                    else:
                        # No vocabulary for this language - disable custom vocabulary
                        CUSTOM_VOCABULARY = []
                        INITIAL_PROMPT = ""
                        logger.info(f"No custom vocabulary found for language '{language}' - custom vocabulary disabled")
                else:
                    # No custom vocabulary section - disable
                    CUSTOM_VOCABULARY = []
                    INITIAL_PROMPT = ""
                    logger.info("No custom vocabulary configuration found")
        else:
            # No vocabulary file - disable
            CUSTOM_VOCABULARY = []
            INITIAL_PROMPT = ""
            logger.info(f"Vocabulary file '{vocab_file_path}' not found - custom vocabulary disabled")
    except Exception as e:
        logger.error(f"Failed to load custom vocabulary: {e}")
        CUSTOM_VOCABULARY = []
        INITIAL_PROMPT = ""


def should_filter_segment(text: str) -> bool:
    """Return True if segment should be filtered out based on content."""
    if not FILTER_DICT:
        return False
    text = text.lower()
    return any(word.lower() in text for word in FILTER_DICT.get('filter_words', []))


async def publish_to_rtmp(text: str, language: str = "eng", track_id: int = 99, http_port: int = 8086, 
                          username: str = "admin", password: str = "password"):
    """
    Publish subtitle text to Wowza Streaming Engine via HTTP as onTextData events.
    
    Args:
        text: The subtitle text to send
        language: Language code (default: "eng")
        track_id: Track identifier (default: 99)
        http_port: HTTP port for Wowza caption API (default: 8086)
        username: Username for Wowza authentication (default: admin)
        password: Password for Wowza authentication (default: password)
    """
    global RTMP_ENABLED, RTMP_URL
    if RTMP_ENABLED and RTMP_URL is not None:
        try:
            # Extract server and application name from RTMP URL
            # Example: rtmp://localhost:1935/live/stream -> extract only localhost
            parts = RTMP_URL.split('/')
            if len(parts) >= 3:
                # Extract hostname without port from the server part
                server_part = parts[2]
                if ':' in server_part:
                    server = server_part.split(':')[0]  # Extract only hostname
                else:
                    server = server_part
                stream_name = parts[-1]
                
                # Prepare HTTP request to Wowza module using configured port
                # Fixed URL format to match what the HTTP Provider expects
                url = f"http://{server}:{http_port}/livevtt/captions"
                headers = {'Content-Type': 'application/json'}
                data = {
                    "text": text,
                    "lang": language,
                    "trackid": track_id,
                    "streamname": stream_name
                }
                
                # Setup auth parameters if credentials are provided
                auth = aiohttp.BasicAuth(username, password) if username and password else None
                
                # Enhanced debug logging
                logger.info(f"Sending caption to {url} with auth: {username if username else 'None'}")
                logger.info(f"Caption data: {data}")
                
                # Send HTTP request to Wowza module
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=data, headers=headers, auth=auth) as response:
                        response_text = await response.text()
                        if response.status != 200:
                            logger.error(f"Failed to send caption to Wowza: {response.status} - {response_text}")
                        else:
                            logger.info(f"Caption sent to Wowza successfully: {response_text}")
            else:
                logger.error(f"Invalid RTMP URL format: {RTMP_URL}")
        except Exception as e:
            logger.error(f"Error sending caption to Wowza: {e}")

async def rtmp_publisher(rtmp_url: str, queue: asyncio.Queue):
    """
    Process for publishing onTextData events to an RTMP server using Wowza module.
    This function is kept for backward compatibility but is no longer used.
    All caption publishing is now done directly in publish_to_rtmp.
    """
    logger.info(f"RTMP publishing is now handled directly via HTTP to Wowza module")
    
    # Just consume the queue items to prevent queue from filling up
    # in case old code is still putting items in the queue
    try:
        while True:
            item = await queue.get()
            if item is None:  # None used as sentinel to stop
                break
            queue.task_done()
    except asyncio.CancelledError:
        logger.info("RTMP publisher task cancelled")
    except Exception as e:
        logger.error(f"Error in RTMP publisher: {e}")

async def transcribe_chunk(args: argparse.Namespace, model: WhisperModel, chunk_dir: str, segment_uri: str,
                           chunk_name: str) -> Tuple[str, str]:
    ts_probe_proc = await asyncio.create_subprocess_exec('ffprobe', '-i', chunk_name, '-show_entries',
                                                         'stream=start_time', '-loglevel', 'quiet',
                                                         '-select_streams', 'a:0', '-of',
                                                         'csv=p=0', stdout=asyncio.subprocess.PIPE)
    ts_probe_stdout, _ = await ts_probe_proc.communicate()
    start_ts = timedelta(seconds=float(ts_probe_stdout.splitlines()[0]))

    loop = asyncio.get_running_loop()
    
    # Add custom vocabulary initial prompt if available
    initial_prompt = INITIAL_PROMPT if INITIAL_PROMPT and not args.debug else None
    if initial_prompt:
        logger.debug(f"Using initial prompt for transcription: {initial_prompt}")
    
    # Run transcription and translation in parallel if both_tracks is enabled
    if args.both_tracks:
        # Transcribe in source language
        segments_orig, _ = await loop.run_in_executor(None,
                                                     lambda: model.transcribe(chunk_name, beam_size=args.beam_size,
                                                                           vad_filter=args.vad_filter,
                                                                           language=args.language,
                                                                           task='transcribe',
                                                                           initial_prompt=initial_prompt))
        # Translate to English
        segments_trans, _ = await loop.run_in_executor(None,
                                                      lambda: model.transcribe(chunk_name, beam_size=args.beam_size,
                                                                            vad_filter=args.vad_filter,
                                                                            language=args.language,
                                                                            task='translate',
                                                                            initial_prompt=initial_prompt))
        
        # Filter segments
        segments_orig = [seg for seg in segments_orig if not should_filter_segment(seg.text)]
        segments_trans = [seg for seg in segments_trans if not should_filter_segment(seg.text)]
        
        # Send to RTMP if enabled
        if RTMP_ENABLED:
            segments_to_use = segments_trans if args.rtmp_use_translated else segments_orig
            for segment in segments_to_use:
                if segment.text.strip():
                    await publish_to_rtmp(segment.text, 
                                         language=args.rtmp_language or (args.language if args.rtmp_use_translated else "eng"), 
                                         track_id=args.rtmp_track_id,
                                         http_port=args.rtmp_http_port,
                                         username=args.rtmp_username if args.rtmp_username else "admin",
                                         password=args.rtmp_password if args.rtmp_password else "password")
        
        if not args.hard_subs and not args.embedded_subs:
            vtt_uri = os.path.splitext(segment_uri)[0]
            if segments_orig:  # Only add if there are segments after filtering
                chunk_to_vtt_orig[vtt_uri + '.orig.vtt'] = segments_to_webvtt(segments_orig, start_ts)
            if segments_trans:  # Only add if there are segments after filtering
                chunk_to_vtt_trans[vtt_uri + '.trans.vtt'] = segments_to_webvtt(segments_trans, start_ts)
            return segment_uri, chunk_name
    else:
        # Original behavior with filtering
        segments, _ = await loop.run_in_executor(None,
                                             lambda: model.transcribe(chunk_name, beam_size=args.beam_size,
                                                                      vad_filter=args.vad_filter,
                                                                      language=args.language,
                                                                      task='transcribe' if args.transcribe else 'translate',
                                                                      initial_prompt=initial_prompt))
        
        # Filter segments
        segments = [seg for seg in segments if not should_filter_segment(seg.text)]
        
        # Send to RTMP if enabled
        if RTMP_ENABLED:
            for segment in segments:
                if segment.text.strip():
                    await publish_to_rtmp(segment.text, 
                                         language=args.rtmp_language or args.language, 
                                         track_id=args.rtmp_track_id,
                                         http_port=args.rtmp_http_port,
                                         username=args.rtmp_username if args.rtmp_username else "admin",
                                         password=args.rtmp_password if args.rtmp_password else "password")
        
        if not args.hard_subs and not args.embedded_subs:
            vtt_uri = os.path.splitext(segment_uri)[0] + '.vtt'
            if segments:  # Only add if there are segments after filtering
                chunk_to_vtt[vtt_uri] = segments_to_webvtt(segments, start_ts)
            return segment_uri, chunk_name

    if args.embedded_subs:
        logger.info(f"Starting embedded subtitles processing for {segment_uri}")
        # Embedded subtitles logic
        if args.both_tracks:
            logger.info(f"Both tracks mode: orig={len(segments_orig) if 'segments_orig' in locals() else 0}, trans={len(segments_trans) if 'segments_trans' in locals() else 0}")
            # Both tracks mode: embed both original and translated subtitles
            if segments_orig or segments_trans:
                srt_files = []
                ffmpeg_cmd = ['ffmpeg', '-hwaccel', 'auto', '-i', chunk_name]
                
                # Add SRT inputs and prepare temp files
                if segments_orig:
                    async with aiofiles.tempfile.NamedTemporaryFile(dir=chunk_dir, delete=False, suffix='.orig.srt') as srt_orig_file:
                        srt_content_orig = segments_to_srt(segments_orig, start_ts)
                        await srt_orig_file.write(bytes(srt_content_orig, 'utf-8'))
                        await srt_orig_file.close()
                        srt_files.append(srt_orig_file.name)
                        ffmpeg_cmd.extend(['-f', 'srt', '-i', srt_orig_file.name])
                
                if segments_trans:
                    async with aiofiles.tempfile.NamedTemporaryFile(dir=chunk_dir, delete=False, suffix='.trans.srt') as srt_trans_file:
                        srt_content_trans = segments_to_srt(segments_trans, start_ts)
                        await srt_trans_file.write(bytes(srt_content_trans, 'utf-8'))
                        await srt_trans_file.close()
                        srt_files.append(srt_trans_file.name)
                        ffmpeg_cmd.extend(['-f', 'srt', '-i', srt_trans_file.name])
                
                # Build mapping - map video and audio from input 0
                ffmpeg_cmd.extend(['-map', '0:v:0'])  # Video stream
                ffmpeg_cmd.extend(['-map', '0:a:0'])  # Audio stream
                
                # Map subtitle streams from SRT inputs
                subtitle_input_idx = 1  # Start from input 1 (first SRT file)
                subtitle_stream_idx = 0  # For metadata indexing
                
                if segments_orig:
                    ffmpeg_cmd.extend(['-map', f'{subtitle_input_idx}:0'])
                    subtitle_input_idx += 1
                    
                if segments_trans:
                    ffmpeg_cmd.extend(['-map', f'{subtitle_input_idx}:0'])
                
                # Add encoding options
                ffmpeg_cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'cea_608'])
                
                # Add language metadata and subtitle disposition
                if segments_orig:
                    orig_lang = args.language or 'rus'
                    ffmpeg_cmd.extend(['-metadata:s:s:' + str(subtitle_stream_idx), f'language={orig_lang}'])
                    ffmpeg_cmd.extend(['-metadata:s:s:' + str(subtitle_stream_idx), f'title=Original ({orig_lang.upper()})'])
                    subtitle_stream_idx += 1
                if segments_trans:
                    ffmpeg_cmd.extend(['-metadata:s:s:' + str(subtitle_stream_idx), 'language=eng'])
                    ffmpeg_cmd.extend(['-metadata:s:s:' + str(subtitle_stream_idx), 'title=English'])
                
                # Output options with TS-specific parameters for live streaming
                chunk_fp_name_split = os.path.splitext(chunk_name)
                embedded_chunk_name = chunk_fp_name_split[0] + '_embedded' + chunk_fp_name_split[1]
                ffmpeg_cmd.extend([
                    '-f', 'mpegts', 
                    '-copyts', 
                    '-muxpreload', '0', 
                    '-muxdelay', '0',
                    '-mpegts_service_type', 'digital_tv',  # Help Wowza recognize service type
                    '-mpegts_pmt_start_pid', '0x1000',     # Explicit PMT PID
                    '-loglevel', 'quiet', 
                    embedded_chunk_name
                ])
                
                # Execute FFmpeg command
                if args.debug:
                    logger.debug(f"Full FFmpeg command: {' '.join(ffmpeg_cmd)}")
                else:
                    logger.info(f"Executing FFmpeg for embedded subtitles: {' '.join(ffmpeg_cmd[:10])}...")
                ffmpeg_proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stderr=asyncio.subprocess.PIPE)
                _, stderr = await ffmpeg_proc.communicate()
                if ffmpeg_proc.returncode != 0:
                    logger.error(f"FFmpeg failed for {segment_uri} with return code {ffmpeg_proc.returncode}")
                    if stderr:
                        logger.error(f"FFmpeg stderr: {stderr.decode()}")
                else:
                    logger.info(f"FFmpeg completed for {segment_uri}")
                    # Verify the output file has subtitle streams
                    if args.debug:
                        verify_cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', embedded_chunk_name]
                        try:
                            verify_proc = await asyncio.create_subprocess_exec(*verify_cmd, stdout=asyncio.subprocess.PIPE)
                            stdout, _ = await verify_proc.communicate()
                            if verify_proc.returncode == 0:
                                import json
                                probe_data = json.loads(stdout.decode())
                                subtitle_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'subtitle']
                                logger.debug(f"Embedded file has {len(subtitle_streams)} subtitle streams: {[s.get('tags', {}).get('language', 'unknown') for s in subtitle_streams]}")
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
            logger.info(f"Single track mode: segments={len(segments) if 'segments' in locals() else 0}")
            # Single track mode: embed one subtitle track
            if segments:
                async with aiofiles.tempfile.NamedTemporaryFile(dir=chunk_dir, delete=False, suffix='.srt') as srt_file:
                    srt_content = segments_to_srt(segments, start_ts)
                    await srt_file.write(bytes(srt_content, 'utf-8'))
                    await srt_file.close()
                    
                    chunk_fp_name_split = os.path.splitext(chunk_name)
                    embedded_chunk_name = chunk_fp_name_split[0] + '_embedded' + chunk_fp_name_split[1]
                    
                    # Determine language for metadata
                    lang_code = 'eng' if not args.transcribe else (args.language or 'eng')
                    
                    ffmpeg_cmd = [
                        'ffmpeg', '-hwaccel', 'auto', '-i', chunk_name,
                        '-f', 'srt', '-i', srt_file.name,
                        '-map', '0:v:0', '-map', '0:a:0', '-map', '1:0',
                        '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'cea_608',
                        '-metadata:s:s:0', f'language={lang_code}',
                        '-metadata:s:s:0', f'title=Subtitles ({lang_code.upper()})',
                        '-f', 'mpegts', '-copyts', '-muxpreload', '0', '-muxdelay', '0',
                        '-mpegts_service_type', 'digital_tv',  # Help Wowza recognize service type
                        '-mpegts_pmt_start_pid', '0x1000',     # Explicit PMT PID
                        '-loglevel', 'quiet', embedded_chunk_name
                    ]
                    
                    if args.debug:
                        logger.debug(f"🔧 Full single track FFmpeg command: {' '.join(ffmpeg_cmd)}")
                    else:
                        logger.info(f"🔧 Executing single track FFmpeg: {' '.join(ffmpeg_cmd[:8])}...")
                    ffmpeg_proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stderr=asyncio.subprocess.PIPE)
                    _, stderr = await ffmpeg_proc.communicate()
                    if ffmpeg_proc.returncode != 0:
                        logger.error(f"Single track FFmpeg failed for {segment_uri} with return code {ffmpeg_proc.returncode}")
                        if stderr:
                            logger.error(f"Single track FFmpeg stderr: {stderr.decode()}")
                    else:
                        logger.info(f"Single track FFmpeg completed for {segment_uri}")
                        # Verify the output file has subtitle streams
                        if args.debug:
                            verify_cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', embedded_chunk_name]
                            try:
                                verify_proc = await asyncio.create_subprocess_exec(*verify_cmd, stdout=asyncio.subprocess.PIPE)
                                stdout, _ = await verify_proc.communicate()
                                if verify_proc.returncode == 0:
                                    import json
                                    probe_data = json.loads(stdout.decode())
                                    subtitle_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'subtitle']
                                    logger.debug(f"Single track embedded file has {len(subtitle_streams)} subtitle streams: {[s.get('tags', {}).get('language', 'unknown') for s in subtitle_streams]}")
                            except Exception as e:
                                logger.debug(f"Failed to verify single track embedded subtitles: {e}")
                    
                    # Cleanup
                    try:
                        os.unlink(srt_file.name)
                    except OSError:
                        pass
                    
                    os.unlink(chunk_name)
                    return segment_uri, embedded_chunk_name
        
        return segment_uri, chunk_name

    if args.hard_subs:
        # Original hard subs logic with filtering
        async with aiofiles.tempfile.NamedTemporaryFile(dir=chunk_dir, delete=False, suffix='.srt') as srt_file:
            segments_to_use = segments if not args.both_tracks else segments_trans
            segments_to_use = [seg for seg in segments_to_use if not should_filter_segment(seg.text)]
            
            srt_content = segments_to_srt(segments_to_use, start_ts)
            if not srt_content:
                return segment_uri, chunk_name

            await srt_file.write(bytes(srt_content, 'utf-8'))
            await srt_file.close()
            chunk_fp_name_split = os.path.splitext(chunk_name)
            translated_chunk_name = chunk_fp_name_split[0] + '_trans' + chunk_fp_name_split[1]

            ffmpeg_sub_proc = await asyncio.create_subprocess_exec('ffmpeg', '-hwaccel', 'auto', '-i', chunk_name,
                                                                   '-copyts',
                                                                   '-muxpreload', '0', '-muxdelay', '0', '-preset',
                                                                   'ultrafast', '-c:a',
                                                                   'copy',
                                                                   '-loglevel', 'quiet', '-vf',
                                                                   f'subtitles={os.path.basename(srt_file.name)}',
                                                                   translated_chunk_name)
            await ffmpeg_sub_proc.communicate()

            os.unlink(chunk_name)
            return segment_uri, translated_chunk_name

    return segment_uri, chunk_name


async def cleanup(session: aiohttp.ClientSession, chunk_dir: str, prev_cwd: str, stop_event: threading.Event):
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
                
        # Signal to stop the RTMP queue if it exists
        global RTMP_QUEUE
        if RTMP_QUEUE is not None:
            try:
                await RTMP_QUEUE.put(None)  # Signal to stop the publisher
            except Exception as e:
                logger.warning(f"Failed to stop RTMP queue: {e}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    finally:
        stop_event.set()


def get_local_ip():
    try:
        # Get the local IP by creating a temporary socket connection
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))  # Doesn't actually send any data
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


async def main():
    check_bindeps_present()
    load_filter_dict()  # Load filter dictionary at startup
    
    parser = argparse.ArgumentParser(prog='livevtt')
    parser.add_argument('-u', '--url', default='https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8',
                        help='URL of the HLS stream (defaults to TVRain stream)')
    parser.add_argument('-s', '--hard-subs', action='store_true',
                        help='Set if you want the subtitles to be baked into the stream itself')
    parser.add_argument('-e', '--embedded-subs', action='store_true',
                        help='Embed subtitles as metadata streams within TS segments (experimental)')
    parser.add_argument('-l', '--bind-address', type=str, help='The IP address to bind to '
                                                               '(defaults to 127.0.0.1)', default='127.0.0.1')
    parser.add_argument('-p', '--bind-port', type=int, help='The port to bind to (defaults to 8000)',
                        default=8000)
    parser.add_argument('-pl', '--public-address', type=str, help='The public IP address to use in URLs '
                                                               '(defaults to bind-address)',
                        default=None)
    parser.add_argument('-m', '--model', type=str, help='Whisper model to use (defaults to large)',
                        default='large', choices=available_models())
    parser.add_argument('-b', '--beam-size', type=int, help='Beam size to use (defaults to 5)', default=5)
    parser.add_argument('-c', '--use-cuda', type=lambda x: str(x).lower() in ['true', '1', 'yes'],
                        help='Use CUDA where available. Defaults to true', default=True)
    parser.add_argument('-t', '--transcribe', action='store_true',
                        help='If set, transcribes rather than translates the given stream.')
    parser.add_argument('-vf', '--vad-filter', type=lambda x: str(x).lower() in ['true', '1', 'yes'],
                        help='Whether to utilise the Silero VAD model to try and filter out silences. Defaults to false.',
                        default=False)
    parser.add_argument('-la', '--language', type=str, help='The original language of the stream, '
                                                            'if known/not multi-lingual. Can be left unset.')
    parser.add_argument('-ua', '--user-agent', type=str, help='User agent to use to retrieve playlists / '
                                                              'stream chunks.', default='VLC/3.0.18 LibVLC/3.0.18')
    parser.add_argument('-bt', '--both-tracks', action='store_true',
                        help='Enable both transcription and translation tracks')
    parser.add_argument('-f', '--filter-file', type=str, help='Path to JSON file containing words to filter out',
                        default='config/filter.json')
    parser.add_argument('-v', '--vocabulary-file', type=str, help='Path to JSON file containing custom vocabulary for better transcription accuracy',
                        default='config/vocabulary.json')
    parser.add_argument('-cv', '--custom-vocabulary', type=lambda x: str(x).lower() in ['true', '1', 'yes'],
                        help='Enable custom vocabulary to improve transcription accuracy for specific terms. Defaults to true.',
                        default=True)
    
    # RTMP arguments
    parser.add_argument('-rtmp', '--rtmp-url', type=str, help='RTMP URL to publish captions to (e.g., rtmp://server/app/stream)')
    parser.add_argument('-rtmp-lang', '--rtmp-language', type=str, help='Language code for RTMP subtitles (defaults to stream language or "eng")')
    parser.add_argument('-rtmp-track', '--rtmp-track-id', type=int, help='Track ID for RTMP subtitles', default=99)
    parser.add_argument('-rtmp-trans', '--rtmp-use-translated', action='store_true',
                        help='Use translated (English) text for RTMP instead of original language (only applies with --both-tracks)')
    parser.add_argument('-rtmp-port', '--rtmp-http-port', type=int, help='HTTP port for Wowza caption API (defaults to 8086)', default=8086)
    parser.add_argument('-rtmp-user', '--rtmp-username', type=str, help='Username for Wowza API authentication')
    parser.add_argument('-rtmp-pass', '--rtmp-password', type=str, help='Password for Wowza API authentication')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable debug logging')

    args = parser.parse_args()

    # Validate subtitle mode options
    subtitle_modes = sum([args.hard_subs, args.embedded_subs])
    if subtitle_modes > 1:
        logger.error("Cannot use multiple subtitle modes simultaneously. Choose only one of: --hard-subs, --embedded-subs, or default (WebVTT sidecar)")
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
        global INITIAL_PROMPT
        INITIAL_PROMPT = ""
        logger.info("Custom vocabulary disabled via command line argument")
    else:
        # Load language-specific custom vocabulary
        load_custom_vocabulary(args.language or "en", args.vocabulary_file)

    # Initialize RTMP settings if enabled
    global RTMP_ENABLED, RTMP_URL, RTMP_QUEUE
    if args.rtmp_url:
        RTMP_ENABLED = True
        RTMP_URL = args.rtmp_url
        RTMP_QUEUE = asyncio.Queue()
        # Keep compatibility with old code by starting the queue consumer
        asyncio.create_task(rtmp_publisher(RTMP_URL, RTMP_QUEUE))
        logger.info(f"RTMP caption publishing enabled to {RTMP_URL}")

    stop_event = threading.Event()
    session = aiohttp.ClientSession(headers={'User-Agent': args.user_agent})
    loop = asyncio.get_running_loop()
    
    device = 'cuda' if args.use_cuda else 'cpu'
    # Set compute_type explicitly for CUDA - 'auto' often fails to use GPU
    if device == 'cuda':
        compute_type = 'float16'
    else:
        compute_type = 'int8'

    logger.info(f'Using {device} as the device type for the model with compute_type={compute_type}')

    model = WhisperModel(args.model, device=device, compute_type=compute_type)
    
    # Log which device the model actually loaded on
    try:
        # This is a simple check - if model creation doesn't fail, log success
        logger.info(f'Whisper model "{args.model}" loaded successfully on {device}')
    except Exception as e:
        logger.error(f'Failed to load model on {device}: {e}')
        raise

    base_playlist = m3u8.load(args.url)
    
    # Handle both master playlists (with multiple streams) and media playlists (direct stream)
    if base_playlist.playlists:
        # Master playlist - select highest bitrate stream
        highest_bitrate_stream = sorted(base_playlist.playlists, key=lambda x: x.stream_info.bandwidth, reverse=True)[0]
        base_playlist.playlists = PlaylistList([highest_bitrate_stream])
        stream_uri = highest_bitrate_stream.absolute_uri
    else:
        # Media playlist - use it directly
        logger.info("Direct media playlist detected, using stream directly")
        stream_uri = args.url

    # Use actual IP if binding to all interfaces
    public_address = get_local_ip() if args.bind_address == '0.0.0.0' else args.bind_address
    http_base_url = '' # Changed from absolute to relative path

    modified_base_playlist = copy.deepcopy(base_playlist)
    
    # Set HLS version to 5 for subtitle support
    modified_base_playlist.version = 5
    
    # Only modify playlist URI if it's a master playlist
    if modified_base_playlist.playlists:
        modified_base_playlist.playlists[0].uri = 'chunklist.m3u8' # Removed path join

    if not args.hard_subs and not args.embedded_subs and modified_base_playlist.playlists:
        # Only add subtitle tracks for master playlists when using WebVTT sidecar mode
        if args.both_tracks:
            # Add both subtitle tracks with language-specific URI naming
            subtitle_trans = m3u8.Media(uri='subs_en.m3u8',
                                      type='SUBTITLES', group_id='Subtitle',
                                      language='en', name='English',
                                      autoselect='NO')
            
            orig_lang = args.language or 'ru'
            subtitle_orig = m3u8.Media(uri=f'subs_{orig_lang}.m3u8',
                                     type='SUBTITLES', group_id='Subtitle',
                                     language=orig_lang, 
                                     name={'en': 'English', 'ru': 'Russian'}.get(orig_lang, 'Original'),
                                     autoselect='NO')
            
            modified_base_playlist.add_media(subtitle_trans)
            modified_base_playlist.add_media(subtitle_orig)
            modified_base_playlist.playlists[0].media += [subtitle_trans, subtitle_orig]
        else:
            # Original single subtitle track logic with language-specific URI naming
            if not args.transcribe:
                subtitle_lang = 'en'
                subtitle_name = 'English'
            else:
                subtitle_lang = args.language or 'en'
            subtitle_name = {
                'en': 'English',
                'ru': 'Russian',
                'nl': 'Dutch',
            }.get(subtitle_lang.lower(), subtitle_lang.capitalize())

            subtitle_list = m3u8.Media(uri=f'subs_{subtitle_lang}.m3u8',
                                     type='SUBTITLES', group_id='Subtitle',
                                     language=subtitle_lang, name=subtitle_name,
                                     autoselect='NO')
            modified_base_playlist.add_media(subtitle_list)
            modified_base_playlist.playlists[0].media += [subtitle_list]

    global BASE_PLAYLIST_SER
    BASE_PLAYLIST_SER = bytes(modified_base_playlist.dumps(), 'ascii')

    # Set up signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(cleanup(session, chunk_dir, prev_cwd, stop_event)))

    http_thread = threading.Thread(target=http_listener, daemon=True, args=((args.bind_address, args.bind_port), stop_event))
    http_thread.start()

    async with aiofiles.tempfile.TemporaryDirectory() as chunk_dir:
        prev_cwd = os.getcwd()
        os.chdir(chunk_dir)

        try:
            while not stop_event.is_set():
                chunk_list = m3u8.load(stream_uri)

                sleep_duration = chunk_list.target_duration or 10

                if chunk_list.target_duration:
                    if int(MAX_TARGET_BUFFER_SECS / chunk_list.target_duration) < len(chunk_list.segments):
                        chunk_list.segments = SegmentList(
                            chunk_list.segments[-int(TARGET_BUFFER_SECS / chunk_list.target_duration):])
                        chunk_list.media_sequence = chunk_list.segments[0].media_sequence

                        if chunk_list.program_date_time:
                            chunk_list.program_date_time = chunk_list.segments[0].current_program_date_time

                current_segments = [normalise_chunk_uri(segment.uri) for segment in chunk_list.segments]

                for translated_chunk_name, translated_chunk_path in dict(translated_chunk_paths).items():
                    if translated_chunk_name not in current_segments:
                        os.unlink(translated_chunk_path)
                        del translated_chunk_paths[translated_chunk_name]

                if not args.hard_subs:
                    for translated_uri, translated_chunk_path in dict(chunk_to_vtt).items():
                        if os.path.splitext(translated_uri)[0] + '.ts' not in current_segments:
                            del chunk_to_vtt[translated_uri]

                chunks_to_translate = {}

                for i, chunk_name in enumerate(
                        await asyncio.gather(*[download_chunk(session, chunk_list.base_uri, segment, chunk_dir)
                                               for segment in chunk_list.segments], return_exceptions=True)):
                    if isinstance(chunk_name, Exception):
                        continue

                    normalised_segment_uri = current_segments[i]
                    if normalised_segment_uri not in translated_chunk_paths:
                        chunks_to_translate[normalised_segment_uri] = chunk_name

                for segment_uri, chunk_name in await asyncio.gather(*[transcribe_chunk(args, model, chunk_dir,
                                                                                       segment_uri, chunk_name)
                                                                      for segment_uri, chunk_name in
                                                                      chunks_to_translate.items()]):
                    chunks_to_translate[segment_uri] = chunk_name

                for segment in chunk_list.segments:
                    segment_name = normalise_chunk_uri(segment.uri)
                    segment.uri = segment_name.lstrip('/') # Remove leading slash for relative path

                global CHUNK_LIST_SER
                CHUNK_LIST_SER = bytes(chunk_list.dumps(), 'ascii')

                if not args.hard_subs and not args.embedded_subs:
                    # Only create WebVTT playlists when using sidecar subtitle mode
                    if args.both_tracks:
                        # Create two separate subtitle playlists
                        trans_chunk_list = copy.deepcopy(chunk_list)
                        orig_chunk_list = copy.deepcopy(chunk_list)
                        
                        for segment in trans_chunk_list.segments:
                            subtitle_name = os.path.splitext(segment.uri)[0] + '.trans.vtt'
                            segment.uri = subtitle_name
                            
                        for segment in orig_chunk_list.segments:
                            subtitle_name = os.path.splitext(segment.uri)[0] + '.orig.vtt'
                            segment.uri = subtitle_name

                        global SUB_LIST_TRANS_SER, SUB_LIST_ORIG_SER
                        SUB_LIST_TRANS_SER = bytes(trans_chunk_list.dumps(), 'ascii')
                        SUB_LIST_ORIG_SER = bytes(orig_chunk_list.dumps(), 'ascii')
                    else:
                        # Original single subtitle playlist logic
                        for segment in chunk_list.segments:
                            subtitle_name = os.path.splitext(segment.uri)[0] + '.vtt'
                            segment.uri = subtitle_name

                        global SUB_LIST_SER
                        SUB_LIST_SER = bytes(chunk_list.dumps(), 'ascii')

                translated_chunk_paths.update(chunks_to_translate)

                await asyncio.sleep(sleep_duration)
        except asyncio.CancelledError:
            logger.info("Received termination signal")
        finally:
            await cleanup(session, chunk_dir, prev_cwd, stop_event)
            http_thread.join(timeout=5)  # Wait for HTTP server to stop

    # Update filter file path if provided
    global FILTER_FILE, VOCABULARY_FILE
    FILTER_FILE = args.filter_file
    VOCABULARY_FILE = args.vocabulary_file
    load_filter_dict()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
