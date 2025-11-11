#!/usr/bin/env python3
"""Standalone WebVTT to TTML converter.

Merges two WebVTT subtitle files (typically one Russian, one English) into a
single TTML file with bilingual content aligned by timestamp.

Example usage:
    python vtt_to_ttml.py --vtt1 video.ru.vtt --vtt2 video.en.vtt --output video.ttml

    # With custom tolerance for timestamp matching
    python vtt_to_ttml.py --vtt1 video.ru.vtt --vtt2 video.en.vtt \
        --output video.ttml --tolerance 1.5

    # Specify different language codes
    python vtt_to_ttml.py --vtt1 video.source.vtt --vtt2 video.trans.vtt \
        --output video.ttml --lang1 es --lang2 en
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from ttml_utils import parse_vtt_file, align_bilingual_cues, vtt_files_to_ttml, load_filter_words


LOGGER = logging.getLogger("vtt_to_ttml")


def validate_vtt_file(path: Path) -> bool:
    """Validate that a VTT file exists and is readable.

    Args:
        path: Path to the VTT file

    Returns:
        True if valid, False otherwise
    """
    if not path.exists():
        LOGGER.error("VTT file not found: %s", path)
        return False

    if not path.is_file():
        LOGGER.error("VTT path is not a file: %s", path)
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            if not first_line.startswith("WEBVTT"):
                LOGGER.warning("VTT file is missing WEBVTT header: %s", path)
    except OSError as exc:
        LOGGER.error("Cannot read VTT file %s: %s", path, exc)
        return False

    return True


def convert_vtt_to_ttml(
    vtt_file1: Path,
    vtt_file2: Path,
    output: Path,
    lang1: str = "ru",
    lang2: str = "en",
    tolerance: float = 1.0,
    filter_json_path: Optional[Path] = None,
) -> bool:
    """Convert two VTT files to a single TTML file.

    Args:
        vtt_file1: Path to first language VTT file
        vtt_file2: Path to second language VTT file
        output: Path for output TTML file
        lang1: Language code for first language
        lang2: Language code for second language
        tolerance: Maximum time difference (seconds) for cue alignment
        filter_json_path: Optional path to filter.json file for text filtering

    Returns:
        True if successful, False otherwise
    """
    # Validate input files
    if not validate_vtt_file(vtt_file1):
        return False
    if not validate_vtt_file(vtt_file2):
        return False

    # Load filter words if specified
    filter_words = load_filter_words(filter_json_path) if filter_json_path else []

    if filter_words:
        LOGGER.info("Loaded %d filter words from %s", len(filter_words), filter_json_path)

    try:
        # Parse VTT files
        LOGGER.info("Parsing %s", vtt_file1)
        cues_lang1 = parse_vtt_file(str(vtt_file1))
        LOGGER.info("Found %d cues in %s", len(cues_lang1), vtt_file1)

        LOGGER.info("Parsing %s", vtt_file2)
        cues_lang2 = parse_vtt_file(str(vtt_file2))
        LOGGER.info("Found %d cues in %s", len(cues_lang2), vtt_file2)

        # Align cues
        LOGGER.info("Aligning cues with tolerance of %.1f seconds", tolerance)
        aligned = align_bilingual_cues(cues_lang1, cues_lang2, tolerance=tolerance)

        # Validate alignment
        unaligned_count = sum(1 for c1, c2_list in aligned if c1 is None or not c2_list)
        if unaligned_count > 0:
            LOGGER.warning(
                "Warning: %d/%d cue pairs are unaligned (missing one language)",
                unaligned_count,
                len(aligned),
            )
            LOGGER.warning(
                "Consider adjusting --tolerance if too many cues are unaligned"
            )

        # Generate TTML without re-parsing or re-aligning the cues
        LOGGER.info("Generating TTML file")
        ttml_content = vtt_files_to_ttml(
            str(vtt_file1),
            str(vtt_file2),
            lang1=lang1,
            lang2=lang2,
            tolerance=tolerance,
            aligned_cues=aligned,
            filter_words=filter_words if filter_words else None,
        )

        # Write output
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(ttml_content)

        LOGGER.info("Successfully created TTML file: %s", output)
        LOGGER.info("Total aligned cue pairs: %d", len(aligned))
        return True

    except OSError as exc:
        LOGGER.error(
            "Failed to convert VTT to TTML due to file system error: %s",
            exc,
            exc_info=True,
        )
        return False
    except ValueError as exc:
        LOGGER.error(
            "Failed to convert VTT to TTML due to invalid data: %s",
            exc,
            exc_info=True,
        )
        return False
    except (KeyError, AttributeError) as exc:
        LOGGER.error(
            "Failed to convert VTT to TTML due to missing attribute: %s",
            exc,
            exc_info=True,
        )
        return False
    except Exception:
        LOGGER.exception("Unexpected error while converting VTT to TTML")
        raise


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list (defaults to sys.argv)

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Convert two WebVTT files to a single bilingual TTML file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  %(prog)s --vtt1 video.ru.vtt --vtt2 video.en.vtt --output video.ttml

  # With custom tolerance
  %(prog)s --vtt1 video.ru.vtt --vtt2 video.en.vtt \\
      --output video.ttml --tolerance 1.5

  # Custom language codes
  %(prog)s --vtt1 video.es.vtt --vtt2 video.en.vtt \\
      --output video.ttml --lang1 es --lang2 en
        """,
    )

    parser.add_argument(
        "--vtt_ru",
        "--vtt-ru",
        "--vtt1",
        "--vtt-file1",
        type=Path,
        required=True,
        metavar="PATH",
        dest="vtt_ru",
        help="Path to first WebVTT file",
    )

    parser.add_argument(
        "--vtt_en",
        "--vtt-en",
        "--vtt2",
        "--vtt-file2",
        type=Path,
        required=True,
        metavar="PATH",
        dest="vtt_en",
        help="Path to second WebVTT file",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path for output TTML file",
    )

    parser.add_argument(
        "--lang1",
        type=str,
        default="ru",
        metavar="CODE",
        help="Language code for first VTT file (default: ru)",
    )

    parser.add_argument(
        "--lang2",
        type=str,
        default="en",
        metavar="CODE",
        help="Language code for second VTT file (default: en)",
    )

    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Maximum time difference (seconds) for aligning cues (default: 1.0)",
    )

    parser.add_argument(
        "--filter",
        type=Path,
        metavar="PATH",
        help="Path to filter.json file for text filtering",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    # Provide attribute aliases for backward compatibility
    args.vtt_file1 = args.vtt_ru
    args.vtt_file2 = args.vtt_en

    return args


def configure_logging(verbose: bool) -> None:
    """Configure logging output.

    Args:
        verbose: Enable debug-level logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point.

    Args:
        argv: Optional argument list

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    args = parse_args(argv)
    configure_logging(args.verbose)

    LOGGER.info("VTT to TTML Converter")
    LOGGER.info("Input 1: %s (%s)", args.vtt_ru, args.lang1)
    LOGGER.info("Input 2: %s (%s)", args.vtt_en, args.lang2)
    LOGGER.info("Output: %s", args.output)

    success = convert_vtt_to_ttml(
        args.vtt_ru,
        args.vtt_en,
        args.output,
        lang1=args.lang1,
        lang2=args.lang2,
        tolerance=args.tolerance,
        filter_json_path=args.filter,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
