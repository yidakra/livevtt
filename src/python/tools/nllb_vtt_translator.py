#!/usr/bin/env python3
"""NLLB-200 VTT Translation Utility for LiveVTT.

Scans a directory for Russian WebVTT files (*.ru.vtt), translates the text content
using Meta's NLLB-200 translation model, and generates English VTT files (*.nllb.en.vtt)
with preserved timestamps.

This tool allows for quality comparison between Whisper's translation and NLLB-200's
translation without modifying the original workflow.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

try:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
except ImportError:
    print("ERROR: transformers and torch are required for NLLB translation.")
    print("Install with: pip install transformers torch sentencepiece")
    sys.exit(1)

# Import VTT parsing utilities
from ttml_utils import SubtitleCue, load_filter_words, parse_vtt_file, should_filter_cue

LOGGER = logging.getLogger("nllb_vtt_translator")


@dataclass
class TranslationJob:
    """Represents a VTT file to be translated."""

    ru_vtt_path: Path
    nllb_en_vtt_path: Path


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


def load_nllb_model(model_name: str, device: str = "auto") -> tuple:
    """
    Load NLLB-200 model and tokenizer.

    Args:
        model_name: Hugging Face model identifier (e.g., "facebook/nllb-200-distilled-600M")
        device: Device to use ("cuda", "cpu", or "auto")

    Returns:
        Tuple of (model, tokenizer, device_used)
    """
    LOGGER.info("Loading NLLB-200 model: %s", model_name)

    # Determine device
    if device == "auto":
        if torch.cuda.is_available():
            device = "cuda"
            LOGGER.info("CUDA available, using GPU")
        else:
            device = "cpu"
            LOGGER.info("CUDA not available, using CPU")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

    if device == "cuda":
        model = model.to("cuda")

    LOGGER.info("Model loaded successfully on %s", device)
    return model, tokenizer, device


def translate_batch(
    texts: list[str],
    model,
    tokenizer,
    device: str,
    src_lang: str = "rus_Cyrl",
    tgt_lang: str = "eng_Latn",
    max_length: int = 512,
    batch_size: int = 16,
) -> list[str]:
    """
    Translate a batch of texts using NLLB-200.

    Args:
        texts: List of texts to translate
        model: NLLB model
        tokenizer: NLLB tokenizer
        device: Device to use
        src_lang: Source language code (NLLB format)
        tgt_lang: Target language code (NLLB format)
        max_length: Maximum token length
        batch_size: Batch size for translation

    Returns:
        List of translated texts
    """
    if not texts:
        return []

    # Set source language
    tokenizer.src_lang = src_lang

    # Process in batches
    translations = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]

        # Tokenize
        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=max_length)

        if device == "cuda":
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        # Generate translation
        translated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.lang_code_to_id[tgt_lang],
            max_length=max_length,
            num_beams=5,
            early_stopping=True,
        )

        # Decode
        batch_translations = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)
        translations.extend(batch_translations)

    return translations


def translate_vtt_file(
    job: TranslationJob,
    model,
    tokenizer,
    device: str,
    args: argparse.Namespace,
    filter_words: list[str] | None = None,
) -> dict:
    """
    Translate a single VTT file from Russian to English using NLLB-200.

    Args:
        job: TranslationJob with input and output paths
        model: NLLB model
        tokenizer: NLLB tokenizer
        device: Device being used
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
            model,
            tokenizer,
            device,
            src_lang=args.source_lang,
            tgt_lang=args.target_lang,
            batch_size=args.batch_size,
        )

        # Create English cues with translated text but same timestamps
        en_cues = []
        for ru_cue, en_text in zip(ru_cues, translated_texts):
            en_cues.append(SubtitleCue(start=ru_cue.start, end=ru_cue.end, text=en_text))

        # Generate WebVTT content
        en_vtt_content = cues_to_webvtt(en_cues, filter_words=filter_words)

        # Write output file
        job.nllb_en_vtt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(job.nllb_en_vtt_path, en_vtt_content)

        processing_time = round(time.time() - start_time, 2)
        LOGGER.info("Completed %s in %.2f seconds", job.ru_vtt_path.name, processing_time)

        return {
            "status": "success",
            "ru_vtt": str(job.ru_vtt_path),
            "nllb_en_vtt": str(job.nllb_en_vtt_path),
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
        # Generate output path: replace .ru.vtt with .nllb.en.vtt
        nllb_en_vtt_path = ru_vtt_path.with_name(ru_vtt_path.name.replace(".ru.vtt", ".nllb.en.vtt"))

        # Skip if already exists (unless force)
        if nllb_en_vtt_path.exists() and not force:
            LOGGER.debug("Skipping %s (output exists)", ru_vtt_path)
            continue

        jobs.append(
            TranslationJob(
                ru_vtt_path=ru_vtt_path,
                nllb_en_vtt_path=nllb_en_vtt_path,
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
    parser = argparse.ArgumentParser(description="Translate Russian VTT files to English using NLLB-200")
    parser.add_argument(
        "input_root",
        type=Path,
        help="Root directory containing *.ru.vtt files",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="facebook/nllb-200-distilled-600M",
        help="NLLB model name (default: facebook/nllb-200-distilled-600M)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Device to use for translation (default: auto)",
    )
    parser.add_argument(
        "--source-lang",
        type=str,
        default="rus_Cyrl",
        help="Source language code in NLLB format (default: rus_Cyrl)",
    )
    parser.add_argument(
        "--target-lang",
        type=str,
        default="eng_Latn",
        help="Target language code in NLLB format (default: eng_Latn)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Batch size for translation (default: 16)",
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

    # Load NLLB model
    try:
        model, tokenizer, device = load_nllb_model(args.model, args.device)
    except Exception as exc:
        LOGGER.error("Failed to load NLLB model: %s", exc)
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
            result = translate_vtt_file(job, model, tokenizer, device, args, filter_words)

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
