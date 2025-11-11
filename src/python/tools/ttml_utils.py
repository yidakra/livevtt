#!/usr/bin/env python3
"""TTML (Timed Text Markup Language) generation and conversion utilities.

This module provides functions for converting WebVTT subtitle segments into
TTML format with support for multilingual content aligned by timestamp.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol, Tuple


@dataclass
class SubtitleCue:
    """Represents a single subtitle cue with timing and text."""
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str


class SegmentLike(Protocol):
    """Structural typing for segment objects used in TTML conversion."""

    start: float
    end: float
    text: Optional[str]


# Global filter words cache
_FILTER_WORDS: Optional[List[str]] = None


def load_filter_words(filter_json_path: Optional[Path] = None) -> List[str]:
    """Load filter words from filter.json file.

    Args:
        filter_json_path: Optional path to filter.json. If not provided, searches for it
                         in standard locations (config/filter.json or filter.json)

    Returns:
        List of strings to filter from subtitles
    """
    global _FILTER_WORDS

    if _FILTER_WORDS is not None:
        return _FILTER_WORDS

    if filter_json_path is None:
        # Try standard locations relative to this file
        script_dir = Path(__file__).parent.parent.parent.parent
        possible_paths = [
            script_dir / "config" / "filter.json",
            script_dir / "filter.json",
        ]

        for path in possible_paths:
            if path.exists():
                filter_json_path = path
                break

    if filter_json_path is None or not filter_json_path.exists():
        _FILTER_WORDS = []
        return _FILTER_WORDS

    try:
        with open(filter_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _FILTER_WORDS = data.get("filter_words", [])
            return _FILTER_WORDS
    except (json.JSONDecodeError, OSError):
        _FILTER_WORDS = []
        return _FILTER_WORDS


def apply_text_filter(text: str, filter_words: List[str]) -> str:
    """Remove filter words from text.

    Args:
        text: Original text
        filter_words: List of strings to filter out

    Returns:
        Filtered text with filter words removed
    """
    if not filter_words or not text:
        return text

    filtered_text = text
    for word in filter_words:
        # Remove the word (case-insensitive) and clean up extra whitespace
        filtered_text = re.sub(re.escape(word), "", filtered_text, flags=re.IGNORECASE)

    # Clean up multiple spaces and leading/trailing whitespace
    filtered_text = re.sub(r"\s+", " ", filtered_text).strip()

    return filtered_text


def format_ttml_timestamp(seconds: float) -> str:
    """Convert seconds to TTML timestamp format (HH:MM:SS.mmm).

    Args:
        seconds: Time in seconds (float)

    Returns:
        Formatted timestamp string (e.g., "00:01:23.456")
    """
    if seconds < 0:
        raise ValueError(f"Timestamp cannot be negative: {seconds}")
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
    if "." in seconds_str:
        secs, ms = seconds_str.split(".")
        seconds = int(secs)
        # Normalize fractional part to milliseconds (pad or truncate to 3 digits)
        ms_normalized = (ms + "000")[:3]
        milliseconds = int(ms_normalized)
    else:
        seconds = int(seconds_str)
        milliseconds = 0

    total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
    return total_seconds


def _parse_vtt_lines(lines: List[str], start_index: int = 0) -> List[SubtitleCue]:
    """Parse subtitle cues from a list of VTT lines starting at the given index."""

    cues: List[SubtitleCue] = []
    i = start_index

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if re.match(r"^\d+\s*$", line):
            i += 1
            if i >= len(lines):
                break
            line = lines[i].strip()

        timing_match = re.match(r"([\d:\.]+)\s*-->\s*([\d:\.]+)", line)
        if timing_match:
            start_str = timing_match.group(1)
            end_str = timing_match.group(2)
            start = parse_vtt_timestamp(start_str)
            end = parse_vtt_timestamp(end_str)

            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].rstrip())
                i += 1

            text = "\n".join(text_lines).strip()
            if text:
                cues.append(SubtitleCue(start=start, end=end, text=text))
        else:
            i += 1

    return cues


def parse_vtt_file(vtt_path: str) -> List[SubtitleCue]:
    """Parse a WebVTT file and extract all cues.

    Args:
        vtt_path: Path to the WebVTT file

    Returns:
        List of SubtitleCue objects
    """
    with open(vtt_path, "r", encoding="utf-8") as vtt_file:
        content = vtt_file.read()

    return parse_vtt_content(content)


def parse_vtt_content(vtt_content: str) -> List[SubtitleCue]:
    """Parse WebVTT content (string) into cues."""

    lines = vtt_content.splitlines()

    start_index = 0
    # Skip header lines until numeric identifier or timing line
    while (
        start_index < len(lines)
        and not re.match(r"^\d+\s*$", lines[start_index].strip())
        and "-->" not in lines[start_index]
    ):
        start_index += 1

    return _parse_vtt_lines(lines, start_index)


def align_bilingual_cues(
    cues_lang1: List[SubtitleCue],
    cues_lang2: List[SubtitleCue],
    tolerance: float = 2.5
) -> List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]:
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
    aligned: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]] = []
    en_index = 0
    total_en = len(cues_lang2)

    for idx, cue1 in enumerate(cues_lang1):
        # emit lang2 cues that finish well before this lang1 cue
        while en_index < total_en and cues_lang2[en_index].end + tolerance < cue1.start:
            aligned.append((None, [cues_lang2[en_index]]))
            en_index += 1

        next_start = (
            cues_lang1[idx + 1].start if idx + 1 < len(cues_lang1) else float("inf")
        )
        limit = (
            (cue1.start + next_start) / 2.0 if next_start != float("inf") else float("inf")
        )

        matched: List[SubtitleCue] = []
        while en_index < total_en:
            candidate = cues_lang2[en_index]
            if candidate.end + tolerance < cue1.start - tolerance:
                aligned.append((None, [candidate]))
                en_index += 1
                continue
            if candidate.start <= cue1.end + tolerance:
                matched.append(candidate)
                en_index += 1
            else:
                break

        aligned.append((cue1, matched))

    # remaining English cues (no matching Russian counterpart)
    while en_index < total_en:
        aligned.append((None, [cues_lang2[en_index]]))
        en_index += 1

    return aligned


def create_ttml_document(
    aligned_cues: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]],
    lang1: str = "ru",
    lang2: str = "en",
    default_lang: str = "ru",
    filter_words: Optional[List[str]] = None
) -> ET.Element:
    """Create a TTML XML document from aligned bilingual cues.

    Args:
        aligned_cues: List of aligned cue pairs (lang1, lang2)
        lang1: Language code for first language (default: "ru")
        lang2: Language code for second language (default: "en")
        default_lang: Default document language (default: "ru")
        filter_words: Optional list of strings to filter from text

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

    lang_attr = "{http://www.w3.org/XML/1998/namespace}lang"

    for cue1, cue2_list in aligned_cues:
        if cue1 is not None:
            text1 = cue1.text
            if filter_words:
                text1 = apply_text_filter(text1, filter_words)

            # Only add cue if text is not empty after filtering
            if text1:
                p = ET.SubElement(div, "p")
                p.set("begin", format_ttml_timestamp(cue1.start))
                p.set("end", format_ttml_timestamp(cue1.end))
                span1 = ET.SubElement(p, "span")
                span1.set(lang_attr, lang1)
                span1.text = text1

        for cue2 in cue2_list:
            text2 = cue2.text
            if filter_words:
                text2 = apply_text_filter(text2, filter_words)

            # Only add cue if text is not empty after filtering
            if text2:
                p_en = ET.SubElement(div, "p")
                p_en.set("begin", format_ttml_timestamp(cue2.start))
                p_en.set("end", format_ttml_timestamp(cue2.end))
                span2 = ET.SubElement(p_en, "span")
                span2.set(lang_attr, lang2)
                span2.text = text2

    return tt


def aligned_cues_to_ttml(
    aligned_cues: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]],
    lang1: str = "ru",
    lang2: str = "en",
    filter_words: Optional[List[str]] = None
) -> str:
    """Convert aligned subtitle cues to TTML content.

    Args:
        aligned_cues: List of aligned cue pairs
        lang1: Language code for first language
        lang2: Language code for second language
        filter_words: Optional list of strings to filter from text

    Returns:
        TTML XML content as a string
    """

    tt = create_ttml_document(aligned_cues, lang1=lang1, lang2=lang2, filter_words=filter_words)

    if hasattr(ET, "indent"):
        ET.indent(tt, space="  ")

    xml_str = ET.tostring(tt, encoding="unicode", method="xml")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


def cues_to_ttml(
    cues_lang1: List[SubtitleCue],
    cues_lang2: List[SubtitleCue],
    lang1: str = "ru",
    lang2: str = "en",
    *,
    tolerance: float = 2.5,
    aligned_cues: Optional[List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]] = None,
    filter_words: Optional[List[str]] = None,
) -> str:
    """Convert two sets of cues to TTML content.

    Args:
        cues_lang1: First language cues
        cues_lang2: Second language cues
        lang1: Language code for first language
        lang2: Language code for second language
        tolerance: Maximum time difference for aligning cues
        aligned_cues: Optional pre-aligned cue pairs
        filter_words: Optional list of strings to filter from text

    Returns:
        TTML XML content as a string
    """

    if aligned_cues is None:
        aligned_cues = align_bilingual_cues(cues_lang1, cues_lang2, tolerance=tolerance)

    return aligned_cues_to_ttml(aligned_cues, lang1=lang1, lang2=lang2, filter_words=filter_words)


def segments_to_ttml(
    segments_lang1: List[SegmentLike],
    segments_lang2: List[SegmentLike],
    lang1: str = "ru",
    lang2: str = "en",
    *,
    tolerance: float = 2.5,
    filter_words: Optional[List[str]] = None,
) -> str:
    """Backward-compatible helper to convert segments to TTML.

    Args:
        segments_lang1: First language segments
        segments_lang2: Second language segments
        lang1: Language code for first language
        lang2: Language code for second language
        tolerance: Maximum time difference for aligning cues
        filter_words: Optional list of strings to filter from text

    Returns:
        TTML XML content as a string
    """

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

    return cues_to_ttml(
        cues_lang1,
        cues_lang2,
        lang1=lang1,
        lang2=lang2,
        tolerance=tolerance,
        filter_words=filter_words,
    )


def vtt_files_to_ttml(
    vtt_path_lang1: str,
    vtt_path_lang2: str,
    lang1: str = "ru",
    lang2: str = "en",
    *,
    tolerance: float = 2.5,
    cues_lang1: Optional[List[SubtitleCue]] = None,
    cues_lang2: Optional[List[SubtitleCue]] = None,
    aligned_cues: Optional[List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]] = None,
    filter_words: Optional[List[str]] = None,
) -> str:
    """Convert two WebVTT files to a single TTML file with aligned content.

    Args:
        vtt_path_lang1: Path to first language VTT file
        vtt_path_lang2: Path to second language VTT file
        lang1: Language code for first language
        lang2: Language code for second language
        tolerance: Maximum time difference (in seconds) for aligning cues
        cues_lang1: Optional pre-parsed cues for the first language
        cues_lang2: Optional pre-parsed cues for the second language
        aligned_cues: Optional pre-aligned cue pairs to convert directly
        filter_words: Optional list of strings to filter from text

    Returns:
        TTML XML content as a string
    """

    if aligned_cues is not None:
        return aligned_cues_to_ttml(aligned_cues, lang1=lang1, lang2=lang2, filter_words=filter_words)

    if cues_lang1 is None:
        cues_lang1 = parse_vtt_file(str(vtt_path_lang1))

    if cues_lang2 is None:
        cues_lang2 = parse_vtt_file(str(vtt_path_lang2))

    return cues_to_ttml(
        cues_lang1,
        cues_lang2,
        lang1=lang1,
        lang2=lang2,
        tolerance=tolerance,
        filter_words=filter_words,
    )
