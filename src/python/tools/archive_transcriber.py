#!/usr/bin/env python3
"""Archive transcription utility for LiveVTT.

Recursively scans an archive of broadcast chunks, selects the highest
resolution variant of each chunk, extracts audio with FFmpeg, and generates
parallel Russian (transcription) and English (translation) WebVTT files using
Faster-Whisper.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from concurrent.futures import ThreadPoolExecutor, as_completed

try:  # Optional progress feedback
    from tqdm import tqdm  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None

from faster_whisper import WhisperModel  # type: ignore


VIDEO_EXTENSIONS = {
    ".ts",
    ".mp4",
    ".mkv",
    ".mov",
    ".m4v",
    ".flv",
}

# Matches resolution tokens like _1080p, .720p, -480p, _180p
RESOLUTION_TOKEN_PATTERN = re.compile(r"([_.-])(\d{3,4})p(?=([_.-]|$))", re.IGNORECASE)


LOGGER = logging.getLogger("archive_transcriber")


def ensure_python_version() -> None:
    if sys.version_info < (3, 10):
        raise RuntimeError("archive_transcriber requires Python 3.10 or newer")


def human_time() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def segments_to_webvtt(segments: Iterable, prepend_header: bool = True) -> str:
    """Convert Faster-Whisper segments to WebVTT content."""

    def format_timestamp(seconds: float) -> str:
        total_ms = int(seconds * 1000)
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"

    lines: List[str] = []
    if prepend_header:
        lines.append("WEBVTT")
        lines.append("")

    for idx, segment in enumerate(segments, start=1):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = (segment.text or "").strip()
        if not text:
            continue
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    # Ensure file ends with newline
    return "\n".join(lines).rstrip() + "\n"


def extract_resolution(value: str) -> Optional[int]:
    match = RESOLUTION_TOKEN_PATTERN.search(value)
    if not match:
        return None
    try:
        return int(match.group(2))
    except ValueError:
        return None


def normalise_variant_name(path: Path) -> str:
    """Normalise filename by removing resolution tokens while keeping extension."""
    return RESOLUTION_TOKEN_PATTERN.sub("", path.name)


def build_output_paths(
    video_path: Path,
    normalized_name: str,
    input_root: Path,
    output_root: Optional[Path],
) -> Tuple[Path, Path]:
    if output_root:
        relative = video_path.relative_to(input_root)
        target_dir = output_root.joinpath(*relative.parts[:-1])
    else:
        target_dir = video_path.parent

    target_dir.mkdir(parents=True, exist_ok=True)
    base_stem = Path(normalized_name).stem
    ru_vtt = target_dir / f"{base_stem}.ru.vtt"
    en_vtt = target_dir / f"{base_stem}.en.vtt"
    return ru_vtt, en_vtt


@dataclass
class VideoJob:
    video_path: Path
    normalized_name: str
    ru_vtt: Path
    en_vtt: Path


class Manifest:
    """Append-only JSONL manifest with in-memory lookup."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.records: Dict[str, Dict] = {}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as manifest_file:
                for line in manifest_file:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    video_path = record.get("video_path")
                    if video_path:
                        self.records[video_path] = record

        # Ensure parent directory exists for future writes
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, video_path: Path) -> Optional[Dict]:
        return self.records.get(str(video_path))

    def append(self, record: Dict) -> None:
        with self.lock:
            with self.path.open("a", encoding="utf-8") as manifest_file:
                manifest_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.records[str(record.get("video_path"))] = record


class WhisperModelHolder(threading.local):
    def __init__(self) -> None:
        super().__init__()
        self.model: Optional[WhisperModel] = None


MODEL_HOLDER = WhisperModelHolder()


def get_model(args: argparse.Namespace) -> WhisperModel:
    if MODEL_HOLDER.model is not None:
        return MODEL_HOLDER.model

    device = "cuda" if args.use_cuda else "cpu"
    compute_type = args.compute_type

    def instantiate(target_device: str, target_compute_type: str) -> WhisperModel:
        LOGGER.debug(
            "Loading Whisper model %s (device=%s, compute_type=%s)",
            args.model,
            target_device,
            target_compute_type,
        )
        return WhisperModel(
            args.model,
            device=target_device,
            compute_type=target_compute_type,
        )

    try:
        MODEL_HOLDER.model = instantiate(device, compute_type)
        return MODEL_HOLDER.model
    except RuntimeError as exc:
        if args.use_cuda:
            LOGGER.warning(
                "CUDA initialisation failed (%s). Falling back to CPU with float32 compute type.",
                exc,
            )
            MODEL_HOLDER.model = instantiate("cpu", "float32")
            return MODEL_HOLDER.model
        raise



def discover_video_jobs(
    input_root: Path,
    output_root: Optional[Path],
    manifest: Manifest,
    force: bool,
    extensions: Iterable[str],
) -> List[VideoJob]:
    extensions = {ext.lower() for ext in extensions}
    grouped: Dict[Tuple[str, str], List[Path]] = {}

    LOGGER.info("Scanning archive at %s", input_root)
    for dirpath, _, filenames in os.walk(input_root):
        directory = Path(dirpath)
        for filename in filenames:
            path = directory / filename
            if path.suffix.lower() not in extensions:
                continue
            normalized_name = normalise_variant_name(path)
            key = (str(path.parent), normalized_name.lower())
            grouped.setdefault(key, []).append(path)

    jobs: List[VideoJob] = []
    LOGGER.info("Found %d candidate groups", len(grouped))

    for (_, normalized_name_lower), candidates in grouped.items():
        best_path = select_best_variant(candidates)
        if not best_path:
            continue
        normalized_name = normalise_variant_name(best_path)
        ru_vtt, en_vtt = build_output_paths(best_path, normalized_name, input_root, output_root)

        if should_skip(best_path, ru_vtt, en_vtt, manifest, force):
            LOGGER.debug("Skipping already processed %s", best_path)
            continue

        jobs.append(
            VideoJob(
                video_path=best_path,
                normalized_name=normalized_name,
                ru_vtt=ru_vtt,
                en_vtt=en_vtt,
            )
        )

    jobs.sort(key=lambda job: job.video_path)
    return jobs


def select_best_variant(candidates: List[Path]) -> Optional[Path]:
    best_path: Optional[Path] = None
    best_score = (-1, -1)

    for path in candidates:
        resolution = extract_resolution(path.name)
        priority = resolution or 0
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        score = (priority, size)
        if score > best_score:
            best_score = score
            best_path = path

    return best_path


def should_skip(
    video_path: Path,
    ru_vtt: Path,
    en_vtt: Path,
    manifest: Manifest,
    force: bool,
) -> bool:
    if force:
        return False

    video_mtime = video_path.stat().st_mtime
    record = manifest.get(video_path)
    if record and record.get("status") == "success":
        ru_path = Path(record.get("ru_vtt", ru_vtt))
        en_path = Path(record.get("en_vtt", en_vtt))
        if ru_path.exists() and en_path.exists():
            if ru_path.stat().st_mtime >= video_mtime and en_path.stat().st_mtime >= video_mtime:
                return True

    if ru_vtt.exists() and en_vtt.exists():
        if ru_vtt.stat().st_mtime >= video_mtime and en_vtt.stat().st_mtime >= video_mtime:
            return True

    return False


def extract_audio(video_path: Path, sample_rate: int) -> Path:
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
            f"FFmpeg failed for {video_path}: return code {result.returncode}\n" +
            "\n".join(stderr_preview)
        )

    return tmp_file_path


def atomic_write(path: Path, content: str) -> None:
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp_name)
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
        tmp_file.write(content)
    tmp_path.replace(path)


def process_job(job: VideoJob, args: argparse.Namespace, manifest: Manifest) -> Dict:
    start_time = time.time()
    LOGGER.info("Processing %s", job.video_path)

    audio_path = None
    ru_segments = None
    en_segments = None

    try:
        audio_path = extract_audio(job.video_path, args.sample_rate)
        model = get_model(args)

        ru_iter, ru_info = model.transcribe(
            str(audio_path),
            beam_size=args.beam_size,
            language=args.source_language,
            vad_filter=args.vad_filter,
            task="transcribe",
        )
        ru_segments = list(ru_iter)

        en_iter, en_info = model.transcribe(
            str(audio_path),
            beam_size=args.beam_size,
            language=args.source_language,
            vad_filter=args.vad_filter,
            task="translate",
        )
        en_segments = list(en_iter)

        ru_content = segments_to_webvtt(ru_segments)
        en_content = segments_to_webvtt(en_segments)

        atomic_write(job.ru_vtt, ru_content)
        atomic_write(job.en_vtt, en_content)

        duration = max(ru_info.duration if ru_info else 0.0, en_info.duration if en_info else 0.0)

        record = {
            "video_path": str(job.video_path),
            "ru_vtt": str(job.ru_vtt),
            "en_vtt": str(job.en_vtt),
            "status": "success",
            "duration": duration,
            "processed_at": human_time(),
            "processing_time_sec": round(time.time() - start_time, 2),
        }
        manifest.append(record)
        return record

    except Exception as exc:
        LOGGER.error("Failed to process %s: %s", job.video_path, exc)
        record = {
            "video_path": str(job.video_path),
            "ru_vtt": str(job.ru_vtt),
            "en_vtt": str(job.en_vtt),
            "status": "error",
            "error": str(exc),
            "processed_at": human_time(),
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
    parser = argparse.ArgumentParser(description="Batch archive transcription and translation")
    parser.add_argument(
        "input_root",
        nargs="?",
        default=Path("/mnt/vod/srv/storage/transcoded/"),
        type=Path,
        help="Root directory of archived video chunks (default: /mnt/vod/srv/storage/transcoded/)",
    )
    parser.add_argument("--output-root", type=Path, help="Optional output root for VTT files")
    parser.add_argument("--manifest", type=Path, default=Path("logs/archive_transcriber_manifest.jsonl"), help="Path to manifest file (JSONL)")
    parser.add_argument("--model", type=str, default="large-v3", help="Faster-Whisper model to load")
    parser.add_argument("--compute-type", type=str, default="float16", help="Faster-Whisper compute type (e.g., float16, int8_float16)")
    parser.add_argument("--use-cuda", type=lambda x: str(x).lower() in {"1", "true", "yes"}, default=True, help="Use CUDA if available (default: true)")
    parser.add_argument("--source-language", type=str, default="ru", help="Source language code for transcription")
    parser.add_argument("--beam-size", type=int, default=5, help="Beam size for decoding")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Audio sample rate for extraction")
    parser.add_argument("--vad-filter", type=lambda x: str(x).lower() in {"1", "true", "yes"}, default=False, help="Enable Silero VAD filtering")
    parser.add_argument("--extensions", type=str, default=",".join(sorted(VIDEO_EXTENSIONS)), help="Comma-separated list of video extensions to include")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker threads for processing")
    parser.add_argument("--max-files", type=int, help="Limit the number of videos processed in this run")
    parser.add_argument("--log-file", type=Path, help="Optional log file path")
    parser.add_argument("--progress", action="store_true", help="Display progress bar (requires tqdm)")
    parser.add_argument("--force", action="store_true", help="Reprocess files even if outputs exist")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    ensure_python_version()
    args = parse_args(argv)
    configure_logging(args)

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve() if args.output_root else None

    if not input_root.exists():
        LOGGER.error("Input root %s does not exist", input_root)
        return 2

    manifest = Manifest(args.manifest.resolve())
    extensions = [ext if ext.startswith(".") else f".{ext}" for ext in args.extensions.split(",") if ext]
    jobs = discover_video_jobs(input_root, output_root, manifest, args.force, extensions)

    if args.max_files is not None:
        if args.max_files <= 0:
            LOGGER.warning("--max-files must be greater than zero; no work will be performed")
            jobs = []
        else:
            jobs = jobs[:args.max_files]

    if not jobs:
        LOGGER.info("No videos to process. Exiting.")
        return 0

    LOGGER.info("Processing %d videos", len(jobs))

    total = len(jobs)
    successes = 0
    failures = 0

    progress_bar = None
    if args.progress and tqdm is not None:
        progress_bar = tqdm(total=total, desc="Transcribing", unit="video")
    elif args.progress and tqdm is None:
        LOGGER.warning("tqdm is not installed; progress bar disabled")

    if args.workers > 1:
        LOGGER.info("Using %d worker threads", args.workers)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(process_job, job, args, manifest) for job in jobs]
            for future in as_completed(futures):
                record = future.result()
                if record.get("status") == "success":
                    successes += 1
                else:
                    failures += 1
                if progress_bar is not None:
                    progress_bar.update(1)
    else:
        for job in jobs:
            record = process_job(job, args, manifest)
            if record.get("status") == "success":
                successes += 1
            else:
                failures += 1
            if progress_bar is not None:
                progress_bar.update(1)

    if progress_bar is not None:
        progress_bar.close()

    LOGGER.info(
        "Completed processing: %d success, %d failures, %d total",
        successes,
        failures,
        total,
    )

    return 0 if failures == 0 else 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()

