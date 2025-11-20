#!/usr/bin/env python3
"""LibreTranslate VTT Translation Utility for LiveVTT.

Scans a directory for Russian WebVTT files (*.ru.vtt), translates the text content
using LibreTranslate API (self-hosted or public), and generates English VTT files
(*.libretranslate.en.vtt) with preserved timestamps.

This tool allows for quality comparison between Whisper, NLLB, and LibreTranslate
translations without modifying the original workflow.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# Import VTT parsing utilities
from ttml_utils import SubtitleCue, load_filter_words, parse_vtt_file, should_filter_cue

# Load environment variables from .env file
load_dotenv()

LOGGER = logging.getLogger("libretranslate_vtt_translator")

# Default LibreTranslate instances
DEFAULT_API_URL = "https://libretranslate.com/translate"


@dataclass
class TranslationJob:
    """Represents a VTT file to be translated."""

    ru_vtt_path: Path
    libre_en_vtt_path: Path


def format_vtt_timestamp(seconds: float) -> str:
    """
    Format a time value in seconds into a WebVTT-style timestamp "HH:MM:SS.mmm".

    Args:
        seconds: Time value in seconds

    Returns:
        Timestamp string in WebVTT format
    """
    total_ms = int(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def cues_to_webvtt(cues: list[SubtitleCue], filter_words: list[str] | None = None) -> str:
    """
    Convert a list of SubtitleCue objects into WebVTT content.

    Args:
        cues: List of subtitle cues with start, end, and text
        filter_words: Optional list of filter words to skip cues

    Returns:
        WebVTT-formatted string
    """
    lines: list[str] = ["WEBVTT", ""]

    cue_idx = 1
    for cue in cues:
        text = cue.text.strip()

        if not text:
            continue

        # Skip entire cue if it contains any filter words
        if filter_words and should_filter_cue(text, filter_words):
            continue

        start = format_vtt_timestamp(cue.start)
        end = format_vtt_timestamp(cue.end)

        lines.append(str(cue_idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
        cue_idx += 1

    return "\n".join(lines).rstrip() + "\n"


def atomic_write(path: Path, content: str) -> None:
    """
    Atomically write content to a file using a temporary file and rename.

    Args:
        path: Target file path
        content: Content to write
    """
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp_name)
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
        tmp_file.write(content)
    tmp_path.replace(path)


def translate_text_libretranslate(
    text: str,
    api_url: str,
    source_lang: str = "ru",
    target_lang: str = "en",
    api_key: str | None = None,
) -> str:
    """
    Translate a single text using LibreTranslate API.

    Args:
        text: Text to translate
        api_url: LibreTranslate API endpoint URL
        source_lang: Source language code (ISO 639-1)
        target_lang: Target language code (ISO 639-1)
        api_key: Optional API key for authentication

    Returns:
        Translated text

    Raises:
        Exception: If API request fails
    """
    data = {
        "q": text,
        "source": source_lang,
        "target": target_lang,
        "format": "text",
    }

    if api_key:
        data["api_key"] = api_key

    # Encode data
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")

    # Create request
    req = urllib.request.Request(
        api_url, data=encoded_data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            translated_text: str = result.get("translatedText", "")
            return translated_text
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        raise Exception(f"LibreTranslate API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error: {e.reason}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON response: {e}")


def translate_batch(
    texts: list[str],
    api_url: str,
    source_lang: str = "ru",
    target_lang: str = "en",
    api_key: str | None = None,
    batch_size: int = 1,
    delay: float = 0.0,
) -> list[str]:
    """
    Translate a batch of texts using LibreTranslate API.

    Args:
        texts: List of texts to translate
        api_url: LibreTranslate API endpoint URL
        source_lang: Source language code
        target_lang: Target language code
        api_key: Optional API key
        batch_size: Number of texts per request (currently always 1 for LibreTranslate)
        delay: Delay between requests in seconds (for rate limiting)

    Returns:
        List of translated texts
    """
    if not texts:
        return []

    translations = []
    for i, text in enumerate(texts):
        if delay > 0 and i > 0:
            time.sleep(delay)

        try:
            translated = translate_text_libretranslate(text, api_url, source_lang, target_lang, api_key)
            translations.append(translated)
        except Exception as e:
            LOGGER.warning("Failed to translate text %d: %s. Using original.", i, e)
            translations.append(text)

    return translations


def translate_vtt_file(
    job: TranslationJob,
    args: argparse.Namespace,
    filter_words: list[str] | None = None,
) -> dict:
    """
    Translate a single VTT file from Russian to English using LibreTranslate.

    Args:
        job: TranslationJob with input and output paths
        args: Command-line arguments
        filter_words: Optional list of filter words

    Returns:
        Dictionary with processing results
    """
    start_time = time.time()
    LOGGER.info("Translating %s", job.ru_vtt_path)

    try:
        # Parse Russian VTT file
        ru_cues = parse_vtt_file(str(job.ru_vtt_path))

        if not ru_cues:
            LOGGER.warning("No cues found in %s", job.ru_vtt_path)
            return {
                "status": "error",
                "error": "No cues found in input file",
                "ru_vtt": str(job.ru_vtt_path),
                "processing_time_sec": round(time.time() - start_time, 2),
            }

        # Extract texts for translation
        texts_to_translate = [cue.text for cue in ru_cues]

        # Translate all texts
        LOGGER.debug("Translating %d cues from %s", len(texts_to_translate), job.ru_vtt_path)
        translated_texts = translate_batch(
            texts_to_translate,
            api_url=args.api_url,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            api_key=args.api_key,
            delay=args.delay,
        )

        # Create English cues with translated text but same timestamps
        en_cues = []
        for ru_cue, en_text in zip(ru_cues, translated_texts):
            en_cues.append(SubtitleCue(start=ru_cue.start, end=ru_cue.end, text=en_text))

        # Generate WebVTT content
        en_vtt_content = cues_to_webvtt(en_cues, filter_words=filter_words)

        # Write output file
        job.libre_en_vtt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(job.libre_en_vtt_path, en_vtt_content)

        processing_time = round(time.time() - start_time, 2)
        LOGGER.info("Completed %s in %.2f seconds", job.ru_vtt_path.name, processing_time)

        return {
            "status": "success",
            "ru_vtt": str(job.ru_vtt_path),
            "libre_en_vtt": str(job.libre_en_vtt_path),
            "cue_count": len(en_cues),
            "processing_time_sec": processing_time,
        }

    except Exception as exc:
        LOGGER.error("Failed to translate %s: %s", job.ru_vtt_path, exc, exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "ru_vtt": str(job.ru_vtt_path),
            "processing_time_sec": round(time.time() - start_time, 2),
        }


def discover_vtt_files(
    input_root: Path,
    force: bool,
) -> list[TranslationJob]:
    """
    Scan directory for *.ru.vtt files and prepare translation jobs.

    Args:
        input_root: Root directory to scan
        force: If True, retranslate even if output exists

    Returns:
        List of TranslationJob objects
    """
    LOGGER.info("Scanning for *.ru.vtt files in %s", input_root)

    jobs: list[TranslationJob] = []

    for ru_vtt_path in input_root.rglob("*.ru.vtt"):
        # Generate output path: replace .ru.vtt with .libretranslate.en.vtt
        libre_en_vtt_path = ru_vtt_path.with_name(ru_vtt_path.name.replace(".ru.vtt", ".libretranslate.en.vtt"))

        # Skip if already exists (unless force)
        if libre_en_vtt_path.exists() and not force:
            LOGGER.debug("Skipping %s (output exists)", ru_vtt_path)
            continue

        jobs.append(
            TranslationJob(
                ru_vtt_path=ru_vtt_path,
                libre_en_vtt_path=libre_en_vtt_path,
            )
        )

    LOGGER.info("Found %d VTT files to translate", len(jobs))
    return jobs


def configure_logging(args: argparse.Namespace) -> None:
    """Configure logging based on command-line arguments."""
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=handlers,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Translate Russian VTT files to English using LibreTranslate API")
    parser.add_argument(
        "input_root",
        type=Path,
        help="Root directory containing *.ru.vtt files",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=os.getenv("LIBRETRANSLATE_API_URL", DEFAULT_API_URL),
        help=f"LibreTranslate API endpoint URL (default: env LIBRETRANSLATE_API_URL or {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("LIBRETRANSLATE_API_KEY"),
        help="API key for LibreTranslate (default: env LIBRETRANSLATE_API_KEY)",
    )
    parser.add_argument(
        "--source-lang",
        type=str,
        default="ru",
        help="Source language code in ISO 639-1 format (default: ru)",
    )
    parser.add_argument(
        "--target-lang",
        type=str,
        default="en",
        help="Target language code in ISO 639-1 format (default: en)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay between API requests in seconds (default: 0.1, for rate limiting)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        help="Limit the number of files to translate (for testing)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retranslate even if output file exists",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Display progress bar (requires tqdm)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Optional log file path",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    """Main entry point for the translator."""
    args = parse_args(argv)
    configure_logging(args)

    input_root = args.input_root.resolve()

    if not input_root.exists():
        LOGGER.error("Input root %s does not exist", input_root)
        return 2

    # Load filter words
    filter_words = load_filter_words()
    if filter_words:
        LOGGER.info("Loaded %d filter words", len(filter_words))

    # Discover VTT files to translate
    jobs = discover_vtt_files(input_root, args.force)

    if args.max_files is not None:
        if args.max_files <= 0:
            LOGGER.warning("--max-files must be greater than zero; no work will be performed")
            jobs = []
        else:
            jobs = jobs[: args.max_files]

    if not jobs:
        LOGGER.info("No VTT files to translate. Exiting.")
        return 0

    # Test API connectivity
    LOGGER.info("Testing LibreTranslate API at %s", args.api_url)
    try:
        test_result = translate_text_libretranslate(
            "Привет", args.api_url, args.source_lang, args.target_lang, args.api_key
        )
        LOGGER.info("API test successful. 'Привет' -> '%s'", test_result)
    except Exception as exc:
        LOGGER.error("LibreTranslate API test failed: %s", exc)
        LOGGER.error("Please check your API URL and network connectivity")
        return 1

    # Process files
    LOGGER.info("Processing %d VTT files", len(jobs))

    successes = 0
    failures = 0

    progress_bar = None
    if args.progress and tqdm is not None:
        progress_bar = tqdm(total=len(jobs), desc="Translating", unit="file")
    elif args.progress and tqdm is None:
        LOGGER.warning("tqdm is not installed; progress bar disabled")

    try:
        for job in jobs:
            result = translate_vtt_file(job, args, filter_words)

            if result.get("status") == "success":
                successes += 1
            else:
                failures += 1

            if progress_bar is not None:
                progress_bar.update(1)

    except KeyboardInterrupt:
        if progress_bar is not None:
            progress_bar.close()
        LOGGER.warning("Translation aborted via Ctrl+C")
        return 130

    if progress_bar is not None:
        progress_bar.close()

    LOGGER.info(
        "Completed translation: %d success, %d failures, %d total",
        successes,
        failures,
        len(jobs),
    )

    return 0 if failures == 0 else 1


def main() -> None:
    """CLI entry point."""
    sys.exit(run())


if __name__ == "__main__":
    main()
