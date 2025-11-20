#!/usr/bin/env python3
"""Mistral LLM VTT Translation Utility for LiveVTT.

Scans a directory for Russian WebVTT files (*.ru.vtt), translates the text content
using Mistral LLM (cloud API or local inference), and generates English VTT files
(*.mistral.en.vtt) with preserved timestamps.

This tool allows for quality comparison between Whisper, NLLB, LibreTranslate,
and Mistral LLM translations without modifying the original workflow.
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

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# Import VTT parsing utilities
from ttml_utils import SubtitleCue, load_filter_words, parse_vtt_file, should_filter_cue

LOGGER = logging.getLogger("mistral_vtt_translator")

# Default API endpoints
DEFAULT_MISTRAL_API = "https://api.mistral.ai/v1/chat/completions"
DEFAULT_OPENAI_COMPATIBLE_API = "http://localhost:8000/v1/chat/completions"


@dataclass
class TranslationJob:
    """Represents a VTT file to be translated."""

    ru_vtt_path: Path
    mistral_en_vtt_path: Path


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


def translate_with_llm(
    text: str,
    api_url: str,
    api_key: str | None,
    model: str,
    system_prompt: str,
    temperature: float = 0.3,
) -> str:
    """
    Translate text using Mistral or OpenAI-compatible API.

    Args:
        text: Text to translate
        api_url: API endpoint URL
        api_key: API key for authentication
        model: Model name to use
        system_prompt: System prompt for translation instructions
        temperature: Sampling temperature (lower = more deterministic)

    Returns:
        Translated text

    Raises:
        Exception: If API request fails
    """
    # Prepare request data (OpenAI/Mistral chat completions format)
    data = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
        "temperature": temperature,
        "max_tokens": 1000,
    }

    # Encode data
    encoded_data = json.dumps(data).encode("utf-8")

    # Create request
    headers = {
        "Content-Type": "application/json",
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(api_url, data=encoded_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))

            # Extract message content from response
            if "choices" in result and len(result["choices"]) > 0:
                message = result["choices"][0].get("message", {})
                content: str = message.get("content", "")
                return content.strip()
            else:
                raise Exception(f"Unexpected API response format: {result}")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        raise Exception(f"LLM API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error: {e.reason}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON response: {e}")


def translate_batch(
    texts: list[str],
    api_url: str,
    api_key: str | None,
    model: str,
    system_prompt: str,
    temperature: float = 0.3,
    delay: float = 0.0,
) -> list[str]:
    """
    Translate a batch of texts using LLM API.

    Args:
        texts: List of texts to translate
        api_url: LLM API endpoint URL
        api_key: Optional API key
        model: Model name
        system_prompt: System prompt for translation
        temperature: Sampling temperature
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
            translated = translate_with_llm(text, api_url, api_key, model, system_prompt, temperature)
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
    Translate a single VTT file from Russian to English using Mistral LLM.

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
            api_key=args.api_key,
            model=args.model,
            system_prompt=args.system_prompt,
            temperature=args.temperature,
            delay=args.delay,
        )

        # Create English cues with translated text but same timestamps
        en_cues = []
        for ru_cue, en_text in zip(ru_cues, translated_texts):
            en_cues.append(SubtitleCue(start=ru_cue.start, end=ru_cue.end, text=en_text))

        # Generate WebVTT content
        en_vtt_content = cues_to_webvtt(en_cues, filter_words=filter_words)

        # Write output file
        job.mistral_en_vtt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(job.mistral_en_vtt_path, en_vtt_content)

        processing_time = round(time.time() - start_time, 2)
        LOGGER.info("Completed %s in %.2f seconds", job.ru_vtt_path.name, processing_time)

        return {
            "status": "success",
            "ru_vtt": str(job.ru_vtt_path),
            "mistral_en_vtt": str(job.mistral_en_vtt_path),
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
        # Generate output path: replace .ru.vtt with .mistral.en.vtt
        mistral_en_vtt_path = ru_vtt_path.with_name(ru_vtt_path.name.replace(".ru.vtt", ".mistral.en.vtt"))

        # Skip if already exists (unless force)
        if mistral_en_vtt_path.exists() and not force:
            LOGGER.debug("Skipping %s (output exists)", ru_vtt_path)
            continue

        jobs.append(
            TranslationJob(
                ru_vtt_path=ru_vtt_path,
                mistral_en_vtt_path=mistral_en_vtt_path,
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
    parser = argparse.ArgumentParser(description="Translate Russian VTT files to English using Mistral LLM")
    parser.add_argument(
        "input_root",
        type=Path,
        help="Root directory containing *.ru.vtt files",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=DEFAULT_OPENAI_COMPATIBLE_API,
        help=f"LLM API endpoint URL (default: {DEFAULT_OPENAI_COMPATIBLE_API})",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="API key for LLM service (required for Mistral API, optional for local)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="mistral-small-latest",
        help="Model name (default: mistral-small-latest for Mistral API, or your local model name)",
    )
    parser.add_argument(
        "--system-prompt",
        type=str,
        default="You are a professional translator. Translate the following Russian text to natural, fluent English. Provide only the translation, without any explanations or additional text.",
        help="System prompt for the LLM",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="Sampling temperature (0.0-1.0, lower = more deterministic, default: 0.3)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between API requests in seconds (default: 0.5, for rate limiting)",
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
    LOGGER.info("Testing LLM API at %s with model %s", args.api_url, args.model)
    try:
        test_result = translate_with_llm(
            "Привет", args.api_url, args.api_key, args.model, args.system_prompt, args.temperature
        )
        LOGGER.info("API test successful. 'Привет' -> '%s'", test_result)
    except Exception as exc:
        LOGGER.error("LLM API test failed: %s", exc)
        LOGGER.error("Please check your API URL, API key, and network connectivity")
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
