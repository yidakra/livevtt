#!/usr/bin/env python3
"""
Remote archive transcription utility - uses cloud GPU for inference.

Extracts audio locally, sends to remote Whisper API on cloud GPU,
receives VTT results, and manages SMIL/TTML generation locally.
"""

import requests
import sys
import argparse
from pathlib import Path

# Import everything from the original archive_transcriber
from archive_transcriber import (
    configure_logging,
    Manifest,
    discover_video_jobs,
    extract_audio,
    atomic_write,
    write_smil,
    probe_video_metadata,
    parse_vtt_content,
    cues_to_ttml,
    LANG_CODE_2_TO_3,
    load_filter_words,
    human_time,
    VideoJob,
    LOGGER,
)

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


def process_job_remote(
    job: VideoJob,
    args: argparse.Namespace,
    manifest: Manifest,
    remote_url: str,
) -> Dict:
    """
    Process a single job using remote GPU inference.

    1. Extract audio locally (CPU task)
    2. Send audio to remote GPU server
    3. Receive VTT transcriptions
    4. Save VTT files locally
    5. Generate TTML and SMIL locally
    """
    start_time = time.time()
    LOGGER.info("Processing %s (remote GPU)", job.video_path)

    metadata = probe_video_metadata(job.video_path)
    duration = metadata.duration or 0.0

    need_transcription = not args.smil_only and (
        args.force or not (job.ru_vtt.exists() and job.en_vtt.exists())
    )

    audio_path = None

    try:
        if need_transcription:
            # Step 1: Extract audio locally (CPU task)
            LOGGER.debug("Extracting audio from %s", job.video_path)
            audio_path = extract_audio(job.video_path, args.sample_rate)

            # Step 2: Send to remote GPU server
            LOGGER.debug("Sending audio to remote GPU: %s", remote_url)
            with open(audio_path, "rb") as audio_file:
                files = {"audio": audio_file}
                data = {
                    "model_name": args.model,
                    "translation_model": args.translation_model or args.model,
                    "source_language": args.source_language,
                    "beam_size": args.beam_size,
                    "compute_type": args.compute_type,
                    "vad_filter": str(args.vad_filter).lower(),
                }

                response = requests.post(
                    f"{remote_url}/transcribe",
                    files=files,
                    data=data,
                    timeout=600,  # 10 minute timeout
                )
                response.raise_for_status()

            # Step 3: Parse response
            result = response.json()
            if result.get("status") != "success":
                raise RuntimeError(f"Remote transcription failed: {result.get('error')}")

            ru_content = result["ru_vtt"]
            en_content = result["en_vtt"]
            duration = result.get("duration", duration)

            # Step 4: Save VTT files locally
            atomic_write(job.ru_vtt, ru_content)
            atomic_write(job.en_vtt, en_content)

            # Step 5: Generate TTML locally
            if not args.no_ttml:
                filter_words = load_filter_words()
                ru_cues = parse_vtt_content(ru_content)
                en_cues = parse_vtt_content(en_content)
                ttml_lang1 = LANG_CODE_2_TO_3.get(args.source_language, args.source_language)
                ttml_lang2 = LANG_CODE_2_TO_3.get(args.translation_language, args.translation_language)
                ttml_content = cues_to_ttml(
                    ru_cues,
                    en_cues,
                    lang1=ttml_lang1,
                    lang2=ttml_lang2,
                    filter_words=filter_words,
                )
                atomic_write(job.ttml, ttml_content)
                LOGGER.debug("Generated TTML file: %s", job.ttml)

        else:
            if not job.ru_vtt.exists() or not job.en_vtt.exists():
                LOGGER.warning("Expected caption files missing for %s; skipping SMIL update", job.video_path)
                return {
                    "video_path": str(job.video_path),
                    "status": "error",
                    "error": "Missing caption files for SMIL-only run",
                    "processed_at": human_time(),
                }
            LOGGER.info("VTT already present for %s; generating SMIL only.", job.video_path)

        # Step 6: Generate SMIL locally
        write_smil(job, metadata, args)

        record = {
            "video_path": str(job.video_path),
            "ru_vtt": str(job.ru_vtt),
            "en_vtt": str(job.en_vtt),
            "ttml": str(job.ttml) if not args.no_ttml else None,
            "smil": str(job.smil),
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
            "status": "error",
            "error": str(exc),
            "processed_at": human_time(),
        }
        manifest.append(record)
        return record

    finally:
        if audio_path and Path(audio_path).exists():
            try:
                Path(audio_path).unlink()
            except OSError:
                LOGGER.warning("Failed to delete temp audio file %s", audio_path)


def main():
    # Reuse argument parser from original, add remote URL
    from archive_transcriber import parse_args

    parser = argparse.ArgumentParser(
        description="Batch archive transcription using remote GPU",
        parents=[],
    )
    parser.add_argument("--remote-url", type=str, required=True, help="Remote Whisper API URL (e.g., http://gpu.example.com:8000)")

    # Copy all args from original parse_args
    original_args = parse_args([])
    for action in vars(original_args):
        # Skip positional args, we'll add them separately
        continue

    # Add all original arguments
    parser.add_argument("input_root", nargs="?", default=Path("/mnt/vod/srv/storage/transcoded/"), type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("logs/archive_transcriber_manifest.jsonl"))
    parser.add_argument("--model", type=str, default="large-v3-turbo")
    parser.add_argument("--compute-type", type=str, default="float16")
    parser.add_argument("--source-language", type=str, default="ru")
    parser.add_argument("--translation-language", type=str, default="en")
    parser.add_argument("--translation-model", type=str, default="large-v3")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--vad-filter", type=lambda x: str(x).lower() in {"1", "true", "yes"}, default=False)
    parser.add_argument("--extensions", type=str, default=".ts,.mp4,.mkv,.mov,.m4v,.flv")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (recommended: 4-8 for remote GPU)")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--smil-only", action="store_true")
    parser.add_argument("--no-ttml", action="store_true")
    parser.add_argument("--vtt-in-smil", action="store_true")
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--scan-cache", type=Path, default=Path("logs/scan_cache.json"))
    parser.add_argument("--force-scan", action="store_true")
    parser.add_argument("--verbose", action="store_true")

    # Note: --use-cuda not needed since GPU is remote
    args = parser.parse_args()

    configure_logging(args)

    # Validate remote URL
    remote_url = args.remote_url.rstrip("/")
    try:
        response = requests.get(f"{remote_url}/health", timeout=10)
        response.raise_for_status()
        LOGGER.info("Connected to remote GPU server: %s", remote_url)
    except Exception as e:
        LOGGER.error("Failed to connect to remote GPU server %s: %s", remote_url, e)
        return 2

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve() if args.output_root else None

    if not input_root.exists():
        LOGGER.error("Input root %s does not exist", input_root)
        return 2

    manifest = Manifest(args.manifest.resolve())
    extensions = [ext if ext.startswith(".") else f".{ext}" for ext in args.extensions.split(",") if ext]

    jobs = discover_video_jobs(
        input_root,
        output_root,
        manifest,
        args.force or args.smil_only,
        extensions,
        not args.no_ttml,
        scan_cache_path=args.scan_cache.resolve() if args.scan_cache else None,
        force_scan=args.force_scan,
    )

    if args.max_files and args.max_files > 0:
        jobs = jobs[:args.max_files]

    if not jobs:
        LOGGER.info("No videos to process. Exiting.")
        return 0

    LOGGER.info("Processing %d videos with %d workers", len(jobs), args.workers)

    successes = 0
    failures = 0

    progress_bar = None
    if args.progress and tqdm:
        progress_bar = tqdm(total=len(jobs), desc="Transcribing (remote GPU)", unit="video")

    try:
        if args.workers > 1:
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [
                    executor.submit(process_job_remote, job, args, manifest, remote_url)
                    for job in jobs
                ]
                for future in as_completed(futures):
                    record = future.result()
                    if record.get("status") == "success":
                        successes += 1
                    else:
                        failures += 1
                    if progress_bar:
                        progress_bar.update(1)
        else:
            for job in jobs:
                record = process_job_remote(job, args, manifest, remote_url)
                if record.get("status") == "success":
                    successes += 1
                else:
                    failures += 1
                if progress_bar:
                    progress_bar.update(1)

    except KeyboardInterrupt:
        if progress_bar:
            progress_bar.close()
        LOGGER.warning("Processing aborted via Ctrl+C")
        return 130
    finally:
        if progress_bar:
            progress_bar.close()

    LOGGER.info("Completed: %d success, %d failures", successes, failures)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
