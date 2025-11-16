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


# Global filter words cache: (path, filter_words)
_FILTER_CACHE: Optional[Tuple[Optional[Path], List[str]]] = None


def load_filter_words(filter_json_path: Optional[Path] = None) -> List[str]:
    """
    Load and return the list of filter words from a filter.json file.
    
    If filter_json_path is None the function searches standard locations relative to the package for a filter.json file. The result is cached per-resolved path; if the file is missing or contains invalid JSON, an empty list is returned and cached.
    
    Parameters:
        filter_json_path (Optional[Path]): Optional path to a filter.json file. If omitted, standard locations are searched.
    
    Returns:
        List[str]: The list of filter words; an empty list if no valid file is found or loading fails.
    """
    global _FILTER_CACHE

    # Resolve the path to use
    resolved_path = filter_json_path
    if resolved_path is None:
        # Try standard locations relative to this file
        script_dir = Path(__file__).parent.parent.parent.parent
        possible_paths = [
            script_dir / "config" / "filter.json",
            script_dir / "filter.json",
        ]

        for path in possible_paths:
            if path.exists():
                resolved_path = path
                break

    # Check if we have a cached result for this path
    if _FILTER_CACHE is not None:
        cached_path, cached_words = _FILTER_CACHE
        if cached_path == resolved_path:
            return cached_words

    # Load filter words from the resolved path
    if resolved_path is None or not resolved_path.exists():
        _FILTER_CACHE = (resolved_path, [])
        return []

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            filter_words = data.get("filter_words", [])
            _FILTER_CACHE = (resolved_path, filter_words)
            return filter_words
    except (json.JSONDecodeError, OSError):
        _FILTER_CACHE = (resolved_path, [])
        return []


def should_filter_cue(text: str, filter_words: List[str]) -> bool:
    """
    Determine whether a cue's text contains any of the provided filter words.
    
    Parameters:
        text (str): Cue text to inspect.
        filter_words (List[str]): Substrings to search for; matching is case-insensitive.
    
    Returns:
        `True` if any filter word appears in `text`, `False` otherwise.
    """
    if not filter_words or not text:
        return False

    for word in filter_words:
        # Check if the word appears in the text (case-insensitive)
        if re.search(re.escape(word), text, flags=re.IGNORECASE):
            return True

    return False


def format_ttml_timestamp(seconds: float) -> str:
    """
    Format a non-negative time value as a TTML timestamp in HH:MM:SS.mmm.
    
    Parameters:
        seconds: Non-negative time value; fractional seconds are supported and are truncated to milliseconds.
    
    Returns:
        TTML timestamp string in the form "HH:MM:SS.mmm".
    
    Raises:
        ValueError: If `seconds` is negative.
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
    lang1: str = "rus",
    lang2: str = "eng",
    default_lang: str = "en",
    filter_words: Optional[List[str]] = None
) -> ET.Element:
    """
    Builds a namespaced TTML <tt> element containing two language-specific <div> sections with styled and regioned subtitle cues.
    
    Parameters:
        aligned_cues (List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]): Sequence of tuples where the first element is an optional cue from the first language and the second element is a list of cues from the second language aligned to it.
        lang1 (str): Language code assigned to the second div (defaults to "rus").
        lang2 (str): Language code assigned to the first div (defaults to "eng").
        default_lang (str): Language code set on the root xml:lang attribute (defaults to "en").
        filter_words (Optional[List[str]]): If provided, cues whose text contains any of these words (case-insensitive) will be omitted.
    
    Returns:
        ET.Element: The root <tt> element of the constructed TTML document.
    """
    # Namespace constants
    TTML_NS = "http://www.w3.org/ns/ttml"
    TTP_NS = "http://www.w3.org/ns/ttml#parameter"
    TTS_NS = "http://www.w3.org/ns/ttml#style"
    XML_NS = "http://www.w3.org/XML/1998/namespace"

    # Register namespaces for proper output
    ET.register_namespace("", TTML_NS)
    ET.register_namespace("ttp", TTP_NS)
    ET.register_namespace("tts", TTS_NS)

    # Create root element with all namespace declarations
    tt = ET.Element("{%s}tt" % TTML_NS)
    tt.set("{%s}lang" % XML_NS, default_lang)
    tt.set("{%s}profile" % TTP_NS, "ttml2-presentation")

    # Create head with styling and layout
    head = ET.SubElement(tt, "{%s}head" % TTML_NS)

    # Styling section
    styling = ET.SubElement(head, "{%s}styling" % TTML_NS)
    style = ET.SubElement(styling, "{%s}style" % TTML_NS)
    style.set("{%s}id" % XML_NS, "s1")
    style.set("{%s}fontSize" % TTS_NS, "10px")
    style.set("{%s}textAlign" % TTS_NS, "center")

    # Layout section
    layout = ET.SubElement(head, "{%s}layout" % TTML_NS)
    region = ET.SubElement(layout, "{%s}region" % TTML_NS)
    region.set("{%s}id" % XML_NS, "r1")
    region.set("{%s}extent" % TTS_NS, "80% 10%")
    region.set("{%s}origin" % TTS_NS, "10% 85%")
    region.set("{%s}displayAlign" % TTS_NS, "after")

    # Create body with style and region references
    body = ET.SubElement(tt, "{%s}body" % TTML_NS)
    body.set("style", "s1")
    body.set("region", "r1")

    # Collect all cues for each language separately
    cues_lang2_all: List[SubtitleCue] = []
    cues_lang1_all: List[SubtitleCue] = []

    for cue1, cue2_list in aligned_cues:
        if cue1 is not None:
            if not (filter_words and should_filter_cue(cue1.text, filter_words)):
                cues_lang1_all.append(cue1)

        for cue2 in cue2_list:
            if not (filter_words and should_filter_cue(cue2.text, filter_words)):
                cues_lang2_all.append(cue2)

    # Create first div for lang2 (English)
    div_lang2 = ET.SubElement(body, "{%s}div" % TTML_NS)
    div_lang2.set("{%s}lang" % XML_NS, lang2)

    for cue in cues_lang2_all:
        p = ET.SubElement(div_lang2, "{%s}p" % TTML_NS)
        p.set("begin", format_ttml_timestamp(cue.start))
        p.set("end", format_ttml_timestamp(cue.end))
        p.text = cue.text

    # Create second div for lang1 (Russian)
    div_lang1 = ET.SubElement(body, "{%s}div" % TTML_NS)
    div_lang1.set("{%s}lang" % XML_NS, lang1)

    for cue in cues_lang1_all:
        p = ET.SubElement(div_lang1, "{%s}p" % TTML_NS)
        p.set("begin", format_ttml_timestamp(cue.start))
        p.set("end", format_ttml_timestamp(cue.end))
        p.text = cue.text

    return tt


def aligned_cues_to_ttml(
    aligned_cues: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]],
    lang1: str = "rus",
    lang2: str = "eng",
    filter_words: Optional[List[str]] = None
) -> str:
    """
    Builds a TTML document string from aligned bilingual subtitle cues.
    
    Converts the provided alignment (pairs of an optional cue from language 1 and a list of cues from language 2) into a complete TTML XML string. If `filter_words` is provided, any cue whose text contains any of those words (case-insensitive) will be omitted from the output.
    
    Parameters:
        aligned_cues (List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]): Alignment where each item is a tuple of an optional cue for language 1 and a list of cues for language 2.
        lang1 (str): Language tag to apply to spans derived from the first-language cues.
        lang2 (str): Language tag to apply to spans derived from the second-language cues.
        filter_words (Optional[List[str]]): Optional list of words; cues containing any of these words (case-insensitive) will be skipped.
    
    Returns:
        str: A TTML XML document as a string, including an XML declaration.
    """

    tt = create_ttml_document(aligned_cues, lang1=lang1, lang2=lang2, filter_words=filter_words)

    if hasattr(ET, "indent"):
        ET.indent(tt, space="  ")

    xml_str = ET.tostring(tt, encoding="unicode", method="xml")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'


def cues_to_ttml(
    cues_lang1: List[SubtitleCue],
    cues_lang2: List[SubtitleCue],
    lang1: str = "rus",
    lang2: str = "eng",
    *,
    tolerance: float = 2.5,
    aligned_cues: Optional[List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]] = None,
    filter_words: Optional[List[str]] = None,
) -> str:
    """
    Convert two lists of SubtitleCue into a TTML document string.
    
    If `aligned_cues` is not provided, cues are aligned using `tolerance` before conversion.
    
    Parameters:
        cues_lang1 (List[SubtitleCue]): Cues for the first language.
        cues_lang2 (List[SubtitleCue]): Cues for the second language.
        lang1 (str): Language code to annotate cues from `cues_lang1`.
        lang2 (str): Language code to annotate cues from `cues_lang2`.
        tolerance (float): Maximum time difference in seconds used when aligning cues.
        aligned_cues (Optional[List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]]): Optional precomputed alignment to use instead of computing it.
        filter_words (Optional[List[str]]): Optional list of words; any cue whose text contains any of these words (case-insensitive) will be omitted from the output.
    
    Returns:
        str: Complete TTML XML document as a string.
    """

    if aligned_cues is None:
        aligned_cues = align_bilingual_cues(cues_lang1, cues_lang2, tolerance=tolerance)

    return aligned_cues_to_ttml(aligned_cues, lang1=lang1, lang2=lang2, filter_words=filter_words)


def segments_to_ttml(
    segments_lang1: List[SegmentLike],
    segments_lang2: List[SegmentLike],
    lang1: str = "rus",
    lang2: str = "eng",
    *,
    tolerance: float = 2.5,
    filter_words: Optional[List[str]] = None,
) -> str:
    """
    Convert segment-like objects for two languages into a TTML document string.
    
    Parameters:
    	segments_lang1 (List[SegmentLike]): Segments for the first language; each item must have `start`, `end`, and `text` attributes.
    	segments_lang2 (List[SegmentLike]): Segments for the second language.
    	lang1 (str): Language code to assign to first-language text.
    	lang2 (str): Language code to assign to second-language text.
    	tolerance (float): Maximum time difference in seconds used when aligning segments into bilingual cues.
    	filter_words (Optional[List[str]]): Optional list of substrings (case-insensitive). Segments whose text contains any of these substrings will be omitted from the output.
    
    Returns:
    	str: TTML XML content as a string.
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
    lang1: str = "rus",
    lang2: str = "eng",
    *,
    tolerance: float = 2.5,
    cues_lang1: Optional[List[SubtitleCue]] = None,
    cues_lang2: Optional[List[SubtitleCue]] = None,
    aligned_cues: Optional[List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]] = None,
    filter_words: Optional[List[str]] = None,
) -> str:
    """
    Convert two WebVTT files (or pre-parsed/aligned cues) into a single TTML document string with aligned subtitles.
    
    Parameters:
        vtt_path_lang1 (str): Path to the first-language VTT file; used only if `cues_lang1` is not provided.
        vtt_path_lang2 (str): Path to the second-language VTT file; used only if `cues_lang2` is not provided.
        lang1 (str): Language code to apply to first-language cues.
        lang2 (str): Language code to apply to second-language cues.
        tolerance (float): Maximum time difference in seconds to consider cues as aligned.
        cues_lang1 (Optional[List[SubtitleCue]]): Pre-parsed cues for the first language; if provided, file at `vtt_path_lang1` is not read.
        cues_lang2 (Optional[List[SubtitleCue]]): Pre-parsed cues for the second language; if provided, file at `vtt_path_lang2` is not read.
        aligned_cues (Optional[List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]]]): Pre-aligned cue groups to convert directly; if provided, parsing and alignment are skipped.
        filter_words (Optional[List[str]]): Optional list of words; cues containing any of these (case-insensitive) will be omitted from the output.
    
    Returns:
        str: The TTML XML document as a string.
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