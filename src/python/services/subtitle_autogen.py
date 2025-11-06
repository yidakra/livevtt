#!/usr/bin/env python3
"""Background service for automatic transcript + SMIL generation."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List

try:
    from src.python.tools import archive_transcriber  # type: ignore
except ImportError:  # pragma: no cover
    REPO_ROOT = Path(__file__).resolve().parents[3]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from src.python.tools import archive_transcriber  # type: ignore

LOGGER = logging.getLogger("subtitle_service")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatic subtitle generation service")
    parser.add_argument("root", type=Path, help="Root directory to monitor for video chunks")
    parser.add_argument("--output-root", type=Path, help="Optional output root for generated assets")
    parser.add_argument("--manifest", type=Path, default=Path("logs/archive_transcriber_manifest.jsonl"), help="Manifest path shared with archive_transcriber")
    parser.add_argument("--interval", type=int, default=300, help="Polling interval in seconds")
    parser.add_argument("--batch-size", type=int, default=5, help="Number of videos to process per cycle")
    parser.add_argument("--smil-only", action="store_true", help="Regenerate SMIL manifests without modifying VTT files")
    parser.add_argument("--force", action="store_true", help="Force regeneration of assets each cycle")
    parser.add_argument("--one-shot", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--log-file", type=Path, help="Optional log file for service output")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def configure_logging(args: argparse.Namespace) -> None:
    level = logging.DEBUG if args.verbose else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s", handlers=handlers)


def build_transcriber_args(args: argparse.Namespace) -> List[str]:
    cmd: List[str] = [str(args.root.resolve())]
    if args.output_root:
        cmd += ["--output-root", str(args.output_root.resolve())]
    if args.manifest:
        cmd += ["--manifest", str(args.manifest.resolve())]
    if args.batch_size:
        cmd += ["--max-files", str(args.batch_size)]
    if args.smil_only:
        cmd.append("--smil-only")
    if args.force:
        cmd.append("--force")
    return cmd


def run_cycle(transcriber_args: List[str]) -> int:
    LOGGER.debug("Invoking archive_transcriber with args: %s", transcriber_args)
    return archive_transcriber.run(transcriber_args)


def main() -> int:
    args = parse_args()
    configure_logging(args)

    transcriber_args = build_transcriber_args(args)

    try:
        while True:
            exit_code = run_cycle(transcriber_args)
            if exit_code != 0:
                LOGGER.error("archive_transcriber exited with code %s", exit_code)
            else:
                LOGGER.info("Cycle completed successfully")

            if args.one_shot:
                break

            LOGGER.debug("Sleeping for %s seconds", args.interval)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        LOGGER.info("Service interrupted by user")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
