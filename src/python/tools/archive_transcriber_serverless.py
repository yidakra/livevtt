#!/usr/bin/env python3
"""Archive transcription utility for LiveVTT using RunPod Serverless.

This variant uses RunPod's Serverless Faster-Whisper endpoint instead of local
processing. Processes videos in REVERSE alphabetical order to avoid conflicts
with the local transcriber running in forward order.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    TYPE_CHECKING,
    TypedDict,
    cast,
)

from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

try:
    from tqdm import tqdm  # type: ignore
except ImportError:
    tqdm = None


ManifestRecord = Dict[str, Any]


class ManifestProtocol(Protocol):
    """Protocol for Manifest interface used in this module."""

    def __init__(self, path: Path) -> None: ...

    def get(self, video_path: Path) -> Optional[ManifestRecord]: ...

    def append(self, record: ManifestRecord) -> None: ...


class VideoJobProtocol(Protocol):
    """Protocol for video job objects."""

    def __init__(
        self,
        *,
        video_path: Path,
        normalized_name: str,
        ru_vtt: Path,
        en_vtt: Path,
        ttml: Path,
        smil: Path,
    ) -> None: ...

    video_path: Path
    normalized_name: str
    ru_vtt: Path
    en_vtt: Path
    ttml: Path
    smil: Path


class VideoMetadataProtocol(Protocol):
    """Protocol for video metadata objects."""

    duration: Optional[float]


if TYPE_CHECKING:
    from .archive_transcriber import (
        Manifest as ManifestType,
        VideoJob as VideoJobType,
        VideoMetadata as VideoMetadataType,
        probe_video_metadata,
        write_smil,
        discover_video_jobs,
        atomic_write,
        human_time,
        segments_to_webvtt,
    )
    from .ttml_utils import (
        cues_to_ttml,
        parse_vtt_content,
        load_filter_words,
    )

try:
    _archive_transcriber = importlib.import_module(".archive_transcriber", __package__)
except ImportError:  # pragma: no cover - fallback for script execution
    _archive_transcriber = importlib.import_module("archive_transcriber")

VideoJob = cast(type[VideoJobProtocol], _archive_transcriber.VideoJob)
Manifest = cast(type[ManifestProtocol], _archive_transcriber.Manifest)
probe_video_metadata: Callable[[Path], VideoMetadataProtocol] = (
    _archive_transcriber.probe_video_metadata
)
write_smil = cast(
    Callable[[VideoJobProtocol, VideoMetadataProtocol, argparse.Namespace], None],
    _archive_transcriber.write_smil,
)
discover_video_jobs = cast(
    Callable[..., List[VideoJobProtocol]], _archive_transcriber.discover_video_jobs
)
atomic_write: Callable[[Path, str], None] = _archive_transcriber.atomic_write
human_time = _archive_transcriber.human_time
segments_to_webvtt = _archive_transcriber.segments_to_webvtt
VIDEO_EXTENSIONS: set[str] = _archive_transcriber.VIDEO_EXTENSIONS
LANG_CODE_2_TO_3: Dict[str, str] = _archive_transcriber.LANG_CODE_2_TO_3

# Import TTML utilities (use same module source as archive_transcriber to keep resolution consistent)
cues_to_ttml = _archive_transcriber.cues_to_ttml
parse_vtt_content = _archive_transcriber.parse_vtt_content
load_filter_words = _archive_transcriber.load_filter_words


LOGGER = logging.getLogger("archive_transcriber_serverless")


@dataclass
class WhisperSegment:
    """Compatible segment structure for existing VTT generation"""

    start: float
    end: float
    text: str


class _RunPodInput(TypedDict):
    audio_base_64: str
    model: str
    translate: bool
    language: str
    beam_size: int


class _RunPodPayload(TypedDict):
    input: _RunPodInput


class _RunPodSegment(TypedDict, total=False):
    start: float
    end: float
    text: str


def call_runpod_serverless(
    audio_path: Path,
    task: str,
    language: str,
    model: str,
    endpoint_id: str,
    api_key: str,
    beam_size: int = 5,
    timeout: int = 600,
) -> List[WhisperSegment]:
    """
    Call RunPod Serverless Faster-Whisper endpoint using ASYNC /run endpoint.

    Args:
        audio_path: Path to audio file
        task: "transcribe" or "translate"
        language: Source language code (e.g., "ru")
        model: Model name (e.g., "large-v3-turbo")
        endpoint_id: RunPod endpoint ID
        api_key: RunPod API key
        beam_size: Beam size for decoding
        timeout: Maximum wait time in seconds

    Returns:
        List of WhisperSegment objects
    """
    # Read and encode audio file
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    audio_b64 = base64.b64encode(audio_data).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload: _RunPodPayload = {
        "input": {
            "audio_base_64": audio_b64,
            "model": model,
            "translate": (task == "translate"),
            "language": language,
            "beam_size": beam_size,
        }
    }

    LOGGER.debug(
        "Calling RunPod Async (task=%s, model=%s, audio_size=%d bytes)",
        task,
        model,
        len(audio_data),
    )

    start_time = time.time()

    # Support custom base URL (for H100) or RunPod
    base_url = os.getenv("H100_URL", "https://api.runpod.ai")

    try:
        # Submit job to /run endpoint
        submit_url = f"{base_url}/v2/{endpoint_id}/run"
        # For H100 synchronous mode, use longer timeout to wait for transcription to complete
        http_timeout = 600  # 10 minutes
        response = requests.post(
            submit_url, headers=headers, json=payload, timeout=http_timeout
        )
        response.raise_for_status()
        submit_result = cast(Dict[str, Any], response.json())

        job_id = submit_result.get("id")
        if not job_id:
            raise RuntimeError(f"No job ID in response: {submit_result}")

        LOGGER.debug("Job submitted: %s", job_id)

        # Check if response is already COMPLETED (synchronous mode, e.g., H100)
        if submit_result.get("status") == "COMPLETED":
            LOGGER.debug("Synchronous response received")
            output = cast(Dict[str, Any], submit_result.get("output", {}))
            segments_data = cast(List[_RunPodSegment], output.get("segments", []))

            # Convert to WhisperSegment objects
            segments: List[WhisperSegment] = []
            for seg in segments_data:
                segments.append(
                    WhisperSegment(
                        start=float(seg.get("start", 0.0)),
                        end=float(seg.get("end", 0.0)),
                        text=str(seg.get("text", "")),
                    )
                )

            elapsed = time.time() - start_time
            LOGGER.debug(
                "Job completed synchronously in %.2f seconds with %d segments",
                elapsed,
                len(segments),
            )
            return segments

        # Poll for results using /stream endpoint (for streaming handlers)
        stream_url = f"{base_url}/v2/{endpoint_id}/stream/{job_id}"
        poll_interval = 2  # Start with 2 seconds
        max_poll_interval = 10
        elapsed = 0

        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed = time.time() - start_time

            stream_response = requests.get(stream_url, headers=headers, timeout=30)
            stream_response.raise_for_status()
            result = cast(Dict[str, Any], stream_response.json())

            status = result.get("status")
            LOGGER.debug("Job %s status: %s (%.1fs elapsed)", job_id, status, elapsed)

            if status == "COMPLETED":
                # DEBUG: Log the FULL response structure
                LOGGER.debug(
                    "Full API response: %s", json.dumps(result, indent=2)[:2000]
                )

                # For streaming endpoints, output is in the 'stream' field
                stream_data = cast(List[Dict[str, Any]], result.get("stream", []))
                LOGGER.debug(
                    "Stream data type: %s, length: %d",
                    type(stream_data),
                    len(stream_data),
                )

                # Aggregate stream data - each item should have the output
                output: Dict[str, Any] = {}
                if stream_data:
                    # Get the last (final) output from stream
                    for item in reversed(stream_data):
                        if "output" in item:
                            output = cast(Dict[str, Any], item["output"])
                            break
                LOGGER.debug(
                    "Output type: %s, Output keys: %s",
                    type(output),
                    output.keys(),
                )
                LOGGER.debug("Full output: %s", json.dumps(output, indent=2)[:1000])

                segments_data = cast(List[_RunPodSegment], output.get("segments", []))
                LOGGER.debug(
                    "Segments data type: %s, length: %d",
                    type(segments_data),
                    len(segments_data),
                )

                # Convert to WhisperSegment objects
                segments: List[WhisperSegment] = []
                for seg in segments_data:
                    segments.append(
                        WhisperSegment(
                            start=float(seg.get("start", 0.0)),
                            end=float(seg.get("end", 0.0)),
                            text=str(seg.get("text", "")),
                        )
                    )

                LOGGER.debug(
                    "Job completed in %.2f seconds with %d segments",
                    elapsed,
                    len(segments),
                )
                return segments

            elif status == "FAILED":
                error_msg = result.get("error", "Unknown error")
                raise RuntimeError(f"RunPod job failed: {error_msg}")

            elif status in ("IN_QUEUE", "IN_PROGRESS"):
                # Gradually increase poll interval
                poll_interval = min(poll_interval * 1.2, max_poll_interval)
                continue

            else:
                raise RuntimeError(f"Unknown status: {status}")

        raise RuntimeError(f"Job timed out after {timeout} seconds")

    except requests.exceptions.Timeout:
        raise RuntimeError(f"RunPod API call timed out after {timeout} seconds")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"RunPod API call failed: {exc}")
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse RunPod API response: {exc}")


def extract_audio(video_path: Path, sample_rate: int) -> Path:
    """Extract audio from video using ffmpeg (same as local version)"""
    tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_file_path = Path(tmp_file.name)
    tmp_file.close()

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "wav",
        str(tmp_file_path),
    ]

    LOGGER.debug("Running FFmpeg: %s", " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr_preview = (result.stderr or "").splitlines()[-5:]
        raise RuntimeError(
            f"FFmpeg failed for {video_path}: return code {result.returncode}\n"
            + "\n".join(stderr_preview)
        )

    return tmp_file_path


def process_job_serverless(
    job: VideoJobProtocol, args: argparse.Namespace, manifest: ManifestProtocol
) -> ManifestRecord:
    """
    Process a single VideoJob using RunPod Serverless API.

    Similar to process_job() but uses RunPod Serverless instead of local models.
    """
    start_time = time.time()
    LOGGER.info("Processing %s", job.video_path)

    # Load filter words
    filter_words = load_filter_words()

    metadata = probe_video_metadata(job.video_path)
    duration = metadata.duration or 0.0
    need_transcription = not args.smil_only and (
        args.force or not (job.ru_vtt.exists() and job.en_vtt.exists())
    )

    audio_path: Optional[Path] = None

    try:
        if need_transcription:
            audio_path = extract_audio(job.video_path, args.sample_rate)

            # Transcribe using RunPod Serverless
            LOGGER.debug("Calling RunPod for transcription (Russian)")
            ru_segments = call_runpod_serverless(
                audio_path=audio_path,
                task="transcribe",
                language=args.source_language,
                model=args.model,
                endpoint_id=args.endpoint_id,
                api_key=args.api_key,
                beam_size=args.beam_size,
                timeout=args.api_timeout,
            )

            # Translate using RunPod Serverless
            LOGGER.debug("Calling RunPod for translation (English)")
            translation_model = args.translation_model or args.model
            en_segments = call_runpod_serverless(
                audio_path=audio_path,
                task="translate",
                language=args.source_language,
                model=translation_model,
                endpoint_id=args.endpoint_id,
                api_key=args.api_key,
                beam_size=args.beam_size,
                timeout=args.api_timeout,
            )

            # Validate we got segments
            if not ru_segments:
                raise RuntimeError(
                    f"Russian transcription returned no segments for {job.video_path}"
                )
            if not en_segments:
                raise RuntimeError(
                    f"English translation returned no segments for {job.video_path}"
                )

            # Generate VTT files
            LOGGER.info(
                "Transcription completed: %d RU segments, %d EN segments",
                len(ru_segments),
                len(en_segments),
            )
            ru_content = segments_to_webvtt(ru_segments, filter_words=filter_words)
            en_content = segments_to_webvtt(en_segments, filter_words=filter_words)
            LOGGER.debug(
                "Generated VTT content: %d RU chars, %d EN chars",
                len(ru_content),
                len(en_content),
            )

            atomic_write(job.ru_vtt, ru_content)
            atomic_write(job.en_vtt, en_content)

            # Verify files were written successfully
            if not job.ru_vtt.exists() or not job.en_vtt.exists():
                raise RuntimeError(
                    f"VTT files not created: ru_exists={job.ru_vtt.exists()}, en_exists={job.en_vtt.exists()}"
                )
            LOGGER.info(
                "VTT files written successfully: %s (size: %d), %s (size: %d)",
                job.ru_vtt.name,
                job.ru_vtt.stat().st_size,
                job.en_vtt.name,
                job.en_vtt.stat().st_size,
            )

            # Generate TTML file
            if not args.no_ttml:
                ru_cues = parse_vtt_content(ru_content)
                en_cues = parse_vtt_content(en_content)
                ttml_lang1 = (
                    LANG_CODE_2_TO_3.get(args.source_language, args.source_language)
                    or args.source_language
                )
                ttml_lang2 = (
                    LANG_CODE_2_TO_3.get(
                        args.translation_language, args.translation_language
                    )
                    or args.translation_language
                )
                ttml_content = cues_to_ttml(
                    ru_cues,
                    en_cues,
                    lang1=ttml_lang1,
                    lang2=ttml_lang2,
                    filter_words=filter_words,
                )
                atomic_write(job.ttml, ttml_content)
                LOGGER.debug("Generated TTML file: %s", job.ttml)

            # Calculate duration from segments
            if ru_segments:
                duration = max(seg.end for seg in ru_segments)
        else:
            if not job.ru_vtt.exists() or not job.en_vtt.exists():
                LOGGER.warning(
                    "Expected caption files missing for %s; skipping SMIL update",
                    job.video_path,
                )
                return {
                    "video_path": str(job.video_path),
                    "ru_vtt": str(job.ru_vtt),
                    "en_vtt": str(job.en_vtt),
                    "ttml": str(job.ttml) if not args.no_ttml else None,
                    "smil": str(job.smil),
                    "status": "error",
                    "error": "Missing caption files for SMIL-only run",
                    "processed_at": human_time(),
                    "processing_mode": "serverless",
                }
            LOGGER.info(
                "VTT already present for %s; generating SMIL only.", job.video_path
            )

        write_smil(
            cast("VideoJobType", job),
            cast("VideoMetadataType", metadata),
            args,
        )

        record: ManifestRecord = {
            "video_path": str(job.video_path),
            "ru_vtt": str(job.ru_vtt),
            "en_vtt": str(job.en_vtt),
            "ttml": str(job.ttml) if not args.no_ttml else None,
            "smil": str(job.smil),
            "status": "success",
            "duration": duration,
            "processed_at": human_time(),
            "processing_time_sec": round(time.time() - start_time, 2),
            "processing_mode": "serverless",
        }
        manifest.append(record)
        return record

    except Exception as exc:
        LOGGER.error("Failed to process %s: %s", job.video_path, exc)
        record: ManifestRecord = {
            "video_path": str(job.video_path),
            "ru_vtt": str(job.ru_vtt),
            "en_vtt": str(job.en_vtt),
            "ttml": str(job.ttml) if not args.no_ttml else None,
            "smil": str(job.smil),
            "status": "error",
            "error": str(exc),
            "processed_at": human_time(),
            "processing_mode": "serverless",
        }
        manifest.append(record)
        return record

    finally:
        if audio_path and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                LOGGER.warning("Failed to delete temp audio file %s", audio_path)


def configure_logging(args: argparse.Namespace) -> None:
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=handlers,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch archive transcription using RunPod Serverless (REVERSE alphabetical order)"
    )
    parser.add_argument(
        "input_root",
        nargs="?",
        default=Path("/mnt/vod/srv/storage/transcoded/"),
        type=Path,
        help="Root directory of archived video chunks",
    )
    parser.add_argument(
        "--output-root", type=Path, help="Optional output root for VTT files"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("logs/archive_transcriber_serverless_manifest.jsonl"),
        help="Path to manifest file (different from local transcriber)",
    )
    parser.add_argument(
        "--endpoint-id",
        type=str,
        required=True,
        help="RunPod Serverless endpoint ID",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="RunPod API key (or set RUNPOD_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="large-v3-turbo",
        help="Whisper model (default: large-v3-turbo)",
    )
    parser.add_argument(
        "--translation-model",
        type=str,
        default="large-v3",
        help="Model for translation (default: large-v3)",
    )
    parser.add_argument(
        "--source-language",
        type=str,
        default="ru",
        help="Source language code",
    )
    parser.add_argument(
        "--translation-language",
        type=str,
        default="en",
        help="Target language code",
    )
    parser.add_argument(
        "--beam-size", type=int, default=5, help="Beam size for decoding"
    )
    parser.add_argument(
        "--sample-rate", type=int, default=16000, help="Audio sample rate"
    )
    parser.add_argument(
        "--api-timeout",
        type=int,
        default=600,
        help="API call timeout in seconds (default: 600)",
    )
    parser.add_argument(
        "--extensions",
        type=str,
        default=",".join(sorted(VIDEO_EXTENSIONS)),
        help="Video extensions",
    )
    parser.add_argument(
        "--workers", type=int, default=8, help="Number of parallel workers"
    )
    parser.add_argument(
        "--max-files", type=int, help="Limit number of videos processed"
    )
    parser.add_argument("--smil-only", action="store_true", help="Regenerate SMIL only")
    parser.add_argument("--no-ttml", action="store_true", help="Skip TTML generation")
    parser.add_argument(
        "--vtt-in-smil", action="store_true", help="Use VTT in SMIL instead of TTML"
    )
    parser.add_argument("--log-file", type=Path, help="Log file path")
    parser.add_argument("--progress", action="store_true", help="Show progress bar")
    parser.add_argument("--force", action="store_true", help="Reprocess existing files")
    parser.add_argument(
        "--scan-cache",
        type=Path,
        default=Path("logs/scan_cache.json"),
        help="Scan cache file path",
    )
    parser.add_argument("--force-scan", action="store_true", help="Force fresh scan")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    parser.add_argument(
        "--reverse",
        action="store_true",
        default=True,
        help="Process in reverse alphabetical order (default: True)",
    )
    parser.add_argument(
        "--quick-start",
        action="store_true",
        help="Skip full job discovery, start processing immediately (faster for testing)",
    )
    return parser.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args)

    # Get API key from args or environment
    api_key = args.api_key or os.getenv("RUNPOD_API_KEY")
    if not api_key:
        LOGGER.error(
            "RunPod API key not provided. Use --api-key or set RUNPOD_API_KEY environment variable"
        )
        return 2
    args.api_key = api_key

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve() if args.output_root else None

    if not input_root.exists():
        LOGGER.error("Input root %s does not exist", input_root)
        return 2

    manifest: ManifestProtocol = Manifest(args.manifest.resolve())
    extensions = [
        ext if ext.startswith(".") else f".{ext}"
        for ext in args.extensions.split(",")
        if ext
    ]

    scan_cache_path = args.scan_cache.resolve() if args.scan_cache else None

    # Quick start mode: find first N videos without full scan
    if args.quick_start and args.max_files:
        LOGGER.info(
            "Quick-start mode: finding first %d unprocessed videos", args.max_files
        )
        normalise_variant_name = _archive_transcriber.normalise_variant_name
        build_output_artifacts = _archive_transcriber.build_output_artifacts
        should_skip = _archive_transcriber.should_skip

        jobs: List[VideoJobProtocol] = []
        target_count = args.max_files

        # Quick scan: just get first videos we find (fast!)
        # For reverse order, start from 'ff' subdirectory (near end alphabetically)
        # For forward order, start from '0a' subdirectory (first alphabetically)
        start_dir = input_root / ("ff" if args.reverse else "0a")
        if not start_dir.exists():
            start_dir = input_root

        # Use subprocess without shell=True for safety and slice results in Python
        find_result = subprocess.run(
            ["find", str(start_dir), "-name", "*_1080p.mp4", "-type", "f"],
            capture_output=True,
            text=True,
            check=True,
        )
        all_paths = find_result.stdout.strip().split("\n") if find_result.stdout else []
        video_paths = all_paths[: target_count * 3]

        for video_path_str in video_paths:
            if len(jobs) >= target_count:
                break

            if not video_path_str:
                continue

            video_path = Path(video_path_str)
            normalized_name = normalise_variant_name(video_path)
            ru_vtt, en_vtt, ttml_path, smil_path = build_output_artifacts(
                video_path, normalized_name, input_root, output_root
            )

            # Skip if already processed
            if should_skip(
                video_path,
                ru_vtt,
                en_vtt,
                ttml_path,
                smil_path,
                args.force,
                not args.no_ttml,
            ):
                continue

            jobs.append(
                VideoJob(
                    video_path=video_path,
                    normalized_name=normalized_name,
                    ru_vtt=ru_vtt,
                    en_vtt=en_vtt,
                    ttml=ttml_path,
                    smil=smil_path,
                )
            )

        LOGGER.info("Quick-start found %d videos to process", len(jobs))
    else:
        # Full scan mode
        jobs = cast(
            List[VideoJobProtocol],
            discover_video_jobs(
                input_root,
                output_root,
                cast("ManifestType", manifest),
                args.force or args.smil_only,
                extensions,
                not args.no_ttml,
                scan_cache_path=scan_cache_path,
                force_scan=args.force_scan,
            ),
        )

        # REVERSE ALPHABETICAL ORDER (to avoid conflicts with local transcriber)
        if args.reverse:
            jobs.sort(key=lambda job: job.video_path, reverse=True)
            LOGGER.info(
                "Processing in REVERSE alphabetical order to avoid conflicts with local transcriber"
            )
        else:
            jobs.sort(key=lambda job: job.video_path)

        if args.max_files is not None:
            if args.max_files <= 0:
                LOGGER.warning("--max-files must be greater than zero")
                jobs = []
            else:
                jobs = jobs[: args.max_files]

    if not jobs:
        LOGGER.info("No videos to process. Exiting.")
        return 0

    LOGGER.info("Processing %d videos using RunPod Serverless", len(jobs))

    total = len(jobs)
    successes = 0
    failures = 0

    progress_bar = None
    if args.progress and tqdm is not None:
        progress_bar = tqdm(total=total, desc="Transcribing (Serverless)", unit="video")
    elif args.progress and tqdm is None:
        LOGGER.warning("tqdm not installed; progress bar disabled")

    try:
        if args.workers > 1:
            LOGGER.info("Using %d parallel workers", args.workers)
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [
                    executor.submit(process_job_serverless, job, args, manifest)
                    for job in jobs
                ]
                try:
                    for future in as_completed(futures):
                        record = future.result()
                        if record.get("status") == "success":
                            successes += 1
                        else:
                            failures += 1
                        if progress_bar is not None:
                            progress_bar.update(1)
                except KeyboardInterrupt:
                    LOGGER.warning("Interrupted by user. Cancelling...")
                    for future in futures:
                        future.cancel()
                    raise
        else:
            for job in jobs:
                record = process_job_serverless(job, args, manifest)
                if record.get("status") == "success":
                    successes += 1
                else:
                    failures += 1
                if progress_bar is not None:
                    progress_bar.update(1)
    except KeyboardInterrupt:
        if progress_bar is not None:
            progress_bar.close()
        LOGGER.warning("Processing aborted via Ctrl+C")
        return 130

    if progress_bar is not None:
        progress_bar.close()

    LOGGER.info(
        "Completed: %d success, %d failures, %d total",
        successes,
        failures,
        total,
    )

    return 0 if failures == 0 else 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
