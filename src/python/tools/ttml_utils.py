#!/usr/bin/env python3
"""TTML (Timed Text Markup Language) generation and conversion utilities.

This module provides functions for converting WebVTT subtitle segments into
TTML format with support for multilingual content aligned by timestamp.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class SubtitleCue:
    """Represents a single subtitle cue with timing and text."""
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str


def format_ttml_timestamp(seconds: float) -> str:
    """Convert seconds to TTML timestamp format (HH:MM:SS.mmm).

    Args:
        seconds: Time in seconds (float)

    Returns:
        Formatted timestamp string (e.g., "00:01:23.456")
    """
    total_ms = int(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def parse_vtt_timestamp(timestamp: str) -> float:
    """Parse a WebVTT timestamp to seconds.

    Args:
        timestamp: VTT timestamp (e.g., "00:01:23.456" or "01:23.456")

    Returns:
        Time in seconds as a float
    """
    # VTT format: [HH:]MM:SS.mmm
    parts = timestamp.strip().split(":")

    if len(parts) == 3:  # HH:MM:SS.mmm
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_str = parts[2]
    elif len(parts) == 2:  # MM:SS.mmm
        hours = 0
        minutes = int(parts[0])
        seconds_str = parts[1]
    else:
        raise ValueError(f"Invalid VTT timestamp format: {timestamp}")

    # Parse seconds and milliseconds
    if "." in seconds_str:
        secs, ms = seconds_str.split(".")
        seconds = int(secs)
        milliseconds = int(ms)
    else:
        seconds = int(seconds_str)
        milliseconds = 0

    total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
    return total_seconds


def parse_vtt_file(vtt_path: str) -> List[SubtitleCue]:
    """Parse a WebVTT file and extract all cues.

    Args:
        vtt_path: Path to the WebVTT file

    Returns:
        List of SubtitleCue objects
    """
    cues: List[SubtitleCue] = []

    with open(vtt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Skip WEBVTT header and any metadata
    i = 0
    while i < len(lines) and not re.match(r"^\d+\s*$", lines[i].strip()):
        i += 1

    # Parse cues
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines
        if not line:
            i += 1
            continue

        # Skip cue identifier (optional number)
        if re.match(r"^\d+\s*$", line):
            i += 1
            if i >= len(lines):
                break
            line = lines[i].strip()

        # Parse timing line (e.g., "00:00:05.000 --> 00:00:07.000")
        timing_match = re.match(r"([\d:\.]+)\s*-->\s*([\d:\.]+)", line)
        if timing_match:
            start_str = timing_match.group(1)
            end_str = timing_match.group(2)
            start = parse_vtt_timestamp(start_str)
            end = parse_vtt_timestamp(end_str)

            # Read text lines until empty line or end of file
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].rstrip())
                i += 1

            text = "\n".join(text_lines)
            if text:
                cues.append(SubtitleCue(start=start, end=end, text=text))
        else:
            i += 1

    return cues


def align_bilingual_cues(
    cues_lang1: List[SubtitleCue],
    cues_lang2: List[SubtitleCue],
    tolerance: float = 1.0
) -> List[Tuple[Optional[SubtitleCue], Optional[SubtitleCue]]]:
    """Align two lists of subtitle cues by timestamp.

    Attempts to match cues with similar timestamps (within tolerance).

    Args:
        cues_lang1: First language cues
        cues_lang2: Second language cues
        tolerance: Maximum time difference (in seconds) to consider cues aligned

    Returns:
        List of tuples (cue1, cue2) where cues are aligned. Either element may be None
        if no matching cue was found within tolerance.
    """
    aligned: List[Tuple[Optional[SubtitleCue], Optional[SubtitleCue]]] = []
    used_lang2: set[int] = set()

    for cue1 in cues_lang1:
        best_match_idx: Optional[int] = None
        best_match_diff = float("inf")

        # Find the closest matching cue in lang2
        for idx, cue2 in enumerate(cues_lang2):
            if idx in used_lang2:
                continue

            # Calculate time difference using the start times
            time_diff = abs(cue1.start - cue2.start)

            if time_diff <= tolerance and time_diff < best_match_diff:
                best_match_diff = time_diff
                best_match_idx = idx

        if best_match_idx is not None:
            aligned.append((cue1, cues_lang2[best_match_idx]))
            used_lang2.add(best_match_idx)
        else:
            aligned.append((cue1, None))

    # Add any unmatched lang2 cues
    for idx, cue2 in enumerate(cues_lang2):
        if idx not in used_lang2:
            aligned.append((None, cue2))

    return aligned


def create_ttml_document(
    aligned_cues: List[Tuple[Optional[SubtitleCue], Optional[SubtitleCue]]],
    lang1: str = "ru",
    lang2: str = "en",
    default_lang: str = "ru"
) -> ET.Element:
    """Create a TTML XML document from aligned bilingual cues.

    Args:
        aligned_cues: List of aligned cue pairs (lang1, lang2)
        lang1: Language code for first language (default: "ru")
        lang2: Language code for second language (default: "en")
        default_lang: Default document language (default: "ru")

    Returns:
        XML Element representing the TTML document root
    """
    # Create root element with TTML namespace
    tt = ET.Element("tt")
    tt.set("xmlns", "http://www.w3.org/ns/ttml")
    tt.set("{http://www.w3.org/XML/1998/namespace}lang", default_lang)

    # Create body and div
    body = ET.SubElement(tt, "body")
    div = ET.SubElement(body, "div")

    # Add cues as paragraph elements
    for cue1, cue2 in aligned_cues:
        # Use the timing from whichever cue exists
        # If both exist, use lang1's timing
        if cue1:
            start = format_ttml_timestamp(cue1.start)
            end = format_ttml_timestamp(cue1.end)
        elif cue2:
            start = format_ttml_timestamp(cue2.start)
            end = format_ttml_timestamp(cue2.end)
        else:
            continue  # Skip if both are None

        p = ET.SubElement(div, "p")
        p.set("begin", start)
        p.set("end", end)

        # Add spans for each language
        if cue1:
            span1 = ET.SubElement(p, "span")
            span1.set("{http://www.w3.org/XML/1998/namespace}lang", lang1)
            span1.text = cue1.text

        if cue2:
            span2 = ET.SubElement(p, "span")
            span2.set("{http://www.w3.org/XML/1998/namespace}lang", lang2)
            span2.text = cue2.text

    return tt


def segments_to_ttml(
    segments_lang1,
    segments_lang2,
    lang1: str = "ru",
    lang2: str = "en"
) -> str:
    """Convert two sets of Faster-Whisper segments to TTML content.

    Args:
        segments_lang1: First language segments (Faster-Whisper format)
        segments_lang2: Second language segments (Faster-Whisper format)
        lang1: Language code for first language
        lang2: Language code for second language

    Returns:
        TTML XML content as a string
    """
    # Convert segments to SubtitleCue objects
    cues_lang1 = [
        SubtitleCue(start=seg.start, end=seg.end, text=(seg.text or "").strip())
        for seg in segments_lang1
        if (seg.text or "").strip()
    ]

    cues_lang2 = [
        SubtitleCue(start=seg.start, end=seg.end, text=(seg.text or "").strip())
        for seg in segments_lang2
        if (seg.text or "").strip()
    ]

    # Align cues by timestamp
    aligned = align_bilingual_cues(cues_lang1, cues_lang2)

    # Create TTML document
    tt = create_ttml_document(aligned, lang1=lang1, lang2=lang2)

    # Convert to string with proper formatting
    if hasattr(ET, "indent"):
        ET.indent(tt, space="  ")

    # Generate XML string
    xml_str = ET.tostring(tt, encoding="unicode", method="xml")

    # Add XML declaration
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


def vtt_files_to_ttml(
    vtt_path_lang1: str,
    vtt_path_lang2: str,
    lang1: str = "ru",
    lang2: str = "en"
) -> str:
    """Convert two WebVTT files to a single TTML file with aligned content.

    Args:
        vtt_path_lang1: Path to first language VTT file
        vtt_path_lang2: Path to second language VTT file
        lang1: Language code for first language
        lang2: Language code for second language

    Returns:
        TTML XML content as a string
    """
    # Parse both VTT files
    cues_lang1 = parse_vtt_file(vtt_path_lang1)
    cues_lang2 = parse_vtt_file(vtt_path_lang2)

    # Align cues by timestamp
    aligned = align_bilingual_cues(cues_lang1, cues_lang2)

    # Create TTML document
    tt = create_ttml_document(aligned, lang1=lang1, lang2=lang2)

    # Convert to string with proper formatting
    if hasattr(ET, "indent"):
        ET.indent(tt, space="  ")

    # Generate XML string
    xml_str = ET.tostring(tt, encoding="unicode", method="xml")

    # Add XML declaration
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'
