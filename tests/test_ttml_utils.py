#!/usr/bin/env python3
"""Unit tests for TTML generation and conversion utilities."""

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple, cast
from unittest import mock

import pytest

from src.python.tools.ttml_utils import (
    SegmentLike,
    SubtitleCue,
    align_bilingual_cues,
    create_ttml_document,
    format_ttml_timestamp,
    parse_vtt_file,
    parse_vtt_timestamp,
    segments_to_ttml,
    vtt_files_to_ttml,
)


class TestTimestampFormatting:
    """Tests for timestamp formatting functions."""

    def test_format_ttml_timestamp_zero(self) -> None:
        """Test formatting zero seconds."""
        result = format_ttml_timestamp(0.0)
        assert result == "00:00:00.000"

    def test_format_ttml_timestamp_simple(self) -> None:
        """Test formatting simple timestamp."""
        result = format_ttml_timestamp(65.5)
        assert result == "00:01:05.500"

    def test_format_ttml_timestamp_hours(self) -> None:
        """Test formatting timestamp with hours."""
        result = format_ttml_timestamp(3661.123)
        assert result == "01:01:01.123"

    def test_format_ttml_timestamp_long(self) -> None:
        """Test formatting long timestamp."""
        result = format_ttml_timestamp(7384.456)
        assert result == "02:03:04.456"


class TestTimestampParsing:
    """Tests for VTT timestamp parsing."""

    def test_parse_vtt_timestamp_short_format(self) -> None:
        """Test parsing short format (MM:SS.mmm)."""
        result = parse_vtt_timestamp("01:23.456")
        assert abs(result - 83.456) < 0.001

    def test_parse_vtt_timestamp_long_format(self) -> None:
        """Test parsing long format (HH:MM:SS.mmm)."""
        result = parse_vtt_timestamp("01:02:03.456")
        assert abs(result - 3723.456) < 0.001

    def test_parse_vtt_timestamp_no_milliseconds(self) -> None:
        """Test parsing timestamp without milliseconds."""
        result = parse_vtt_timestamp("01:30")
        assert abs(result - 90.0) < 0.001

    def test_parse_vtt_timestamp_zero(self) -> None:
        """Test parsing zero timestamp."""
        result = parse_vtt_timestamp("00:00.000")
        assert abs(result - 0.0) < 0.001

    def test_parse_vtt_timestamp_with_spaces(self) -> None:
        """Test parsing timestamp with spaces."""
        result = parse_vtt_timestamp("  01:23.456  ")
        assert abs(result - 83.456) < 0.001


class TestVTTFileParsing:
    """Tests for VTT file parsing."""

    def test_parse_simple_vtt_file(self) -> None:
        """Test parsing a simple VTT file."""
        vtt_content = """WEBVTT

1
00:00:05.000 --> 00:00:07.000
Hello, world!

2
00:00:10.000 --> 00:00:12.500
Second subtitle
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".vtt", delete=False, encoding="utf-8"
        ) as f:
            f.write(vtt_content)
            vtt_path = f.name

        try:
            cues: List[SubtitleCue] = parse_vtt_file(vtt_path)
            assert len(cues) == 2

            assert abs(cues[0].start - 5.0) < 0.001
            assert abs(cues[0].end - 7.0) < 0.001
            assert cues[0].text == "Hello, world!"

            assert abs(cues[1].start - 10.0) < 0.001
            assert abs(cues[1].end - 12.5) < 0.001
            assert cues[1].text == "Second subtitle"
        finally:
            Path(vtt_path).unlink()

    def test_parse_vtt_file_multiline_text(self) -> None:
        """Test parsing VTT with multiline text."""
        vtt_content = """WEBVTT

1
00:00:05.000 --> 00:00:08.000
First line
Second line
Third line
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".vtt", delete=False, encoding="utf-8"
        ) as f:
            f.write(vtt_content)
            vtt_path = f.name

        try:
            cues: List[SubtitleCue] = parse_vtt_file(vtt_path)
            assert len(cues) == 1
            assert cues[0].text == "First line\nSecond line\nThird line"
        finally:
            Path(vtt_path).unlink()

    def test_parse_vtt_file_empty_lines(self) -> None:
        """Test parsing VTT with empty lines."""
        vtt_content = """WEBVTT


1
00:00:05.000 --> 00:00:07.000
Hello


2
00:00:10.000 --> 00:00:12.000
World

"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".vtt", delete=False, encoding="utf-8"
        ) as f:
            f.write(vtt_content)
            vtt_path = f.name

        try:
            cues: List[SubtitleCue] = parse_vtt_file(vtt_path)
            assert len(cues) == 2
        finally:
            Path(vtt_path).unlink()


class TestBilingualCueAlignment:
    """Tests for bilingual cue alignment."""

    def test_align_perfect_match(self) -> None:
        """Test alignment with perfect timestamp matches."""
        cues_lang1: List[SubtitleCue] = [
            SubtitleCue(start=5.0, end=7.0, text="Привет"),
            SubtitleCue(start=10.0, end=12.0, text="Мир"),
        ]
        cues_lang2: List[SubtitleCue] = [
            SubtitleCue(start=5.0, end=7.0, text="Hello"),
            SubtitleCue(start=10.0, end=12.0, text="World"),
        ]

        aligned: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]] = (
            align_bilingual_cues(cues_lang1, cues_lang2, 1.0)
        )

        assert len(aligned) == 2
        assert aligned[0][0] is not None
        assert aligned[0][0].text == "Привет"
        assert len(aligned[0][1]) == 1
        assert aligned[0][1][0].text == "Hello"
        assert aligned[1][0] is not None
        assert aligned[1][0].text == "Мир"
        assert len(aligned[1][1]) == 1
        assert aligned[1][1][0].text == "World"

    def test_align_with_tolerance(self) -> None:
        """Test alignment with slight timestamp differences."""
        cues_lang1: List[SubtitleCue] = [
            SubtitleCue(start=5.0, end=7.0, text="Привет"),
        ]
        cues_lang2: List[SubtitleCue] = [
            SubtitleCue(start=5.5, end=7.5, text="Hello"),
        ]

        aligned: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]] = (
            align_bilingual_cues(cues_lang1, cues_lang2, 1.0)
        )

        assert len(aligned) == 1
        assert aligned[0][0] is not None
        assert aligned[0][0].text == "Привет"
        assert len(aligned[0][1]) == 1
        assert aligned[0][1][0].text == "Hello"

    def test_align_unmatched_cues(self) -> None:
        """Test alignment with unmatched cues."""
        cues_lang1: List[SubtitleCue] = [
            SubtitleCue(start=5.0, end=7.0, text="Привет"),
            SubtitleCue(start=15.0, end=17.0, text="Пока"),
        ]
        cues_lang2: List[SubtitleCue] = [
            SubtitleCue(start=5.5, end=7.5, text="Hello"),
        ]

        aligned: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]] = (
            align_bilingual_cues(cues_lang1, cues_lang2, 1.0)
        )

        assert len(aligned) == 2
        assert aligned[0][0] is not None
        assert aligned[0][0].text == "Привет"
        assert len(aligned[0][1]) == 1
        assert aligned[0][1][0].text == "Hello"
        assert aligned[1][0] is not None
        assert aligned[1][0].text == "Пока"
        assert aligned[1][1] == []

    def test_align_extra_lang2_cues(self) -> None:
        """Test alignment when lang2 has extra cues."""
        cues_lang1: List[SubtitleCue] = [
            SubtitleCue(start=5.0, end=7.0, text="Привет"),
        ]
        cues_lang2: List[SubtitleCue] = [
            SubtitleCue(start=5.0, end=7.0, text="Hello"),
            SubtitleCue(start=10.0, end=12.0, text="Extra"),
        ]

        aligned: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]] = (
            align_bilingual_cues(cues_lang1, cues_lang2, 1.0)
        )

        assert len(aligned) == 2
        assert aligned[0][0] is not None
        assert aligned[0][0].text == "Привет"
        assert len(aligned[0][1]) == 1
        assert aligned[0][1][0].text == "Hello"
        assert aligned[1][0] is None
        assert len(aligned[1][1]) == 1
        assert aligned[1][1][0].text == "Extra"


class TestTTMLDocumentCreation:
    """Tests for TTML document creation."""

    def test_create_simple_ttml_document(self) -> None:
        """Test creating a simple TTML document with new two-div structure."""
        aligned_cues: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]] = [
            (
                SubtitleCue(start=5.0, end=7.0, text="Привет"),
                [SubtitleCue(start=5.0, end=7.0, text="Hello")],
            ),
        ]

        root = create_ttml_document(aligned_cues, lang1="rus", lang2="eng")

        # Check root element with namespaces
        assert root.tag == "{http://www.w3.org/ns/ttml}tt"
        assert root.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
        assert (
            root.get("{http://www.w3.org/ns/ttml#parameter}profile")
            == "ttml2-presentation"
        )

        # Check head with styling and layout
        head = root.find("{http://www.w3.org/ns/ttml}head")
        assert head is not None

        styling = head.find("{http://www.w3.org/ns/ttml}styling")
        assert styling is not None

        layout = head.find("{http://www.w3.org/ns/ttml}layout")
        assert layout is not None

        # Check body
        body = root.find("{http://www.w3.org/ns/ttml}body")
        assert body is not None
        assert body.get("style") == "s1"
        assert body.get("region") == "r1"

        # Check two div elements (one per language)
        divs = body.findall("{http://www.w3.org/ns/ttml}div")
        assert len(divs) == 2

        # First div should be for lang2 (eng)
        div_eng = divs[0]
        assert div_eng.get("{http://www.w3.org/XML/1998/namespace}lang") == "eng"
        paragraphs_eng = div_eng.findall("{http://www.w3.org/ns/ttml}p")
        assert len(paragraphs_eng) == 1
        p_en = paragraphs_eng[0]
        assert p_en.get("begin") == "00:00:05.000"
        assert p_en.get("end") == "00:00:07.000"
        assert p_en.text == "Hello"

        # Second div should be for lang1 (rus)
        div_rus = divs[1]
        assert div_rus.get("{http://www.w3.org/XML/1998/namespace}lang") == "rus"
        paragraphs_rus = div_rus.findall("{http://www.w3.org/ns/ttml}p")
        assert len(paragraphs_rus) == 1
        p_ru = paragraphs_rus[0]
        assert p_ru.get("begin") == "00:00:05.000"
        assert p_ru.get("end") == "00:00:07.000"
        assert p_ru.text == "Привет"

    def test_create_ttml_document_with_unmatched_cues(self) -> None:
        """Test creating TTML with unmatched cues."""
        aligned_cues: List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]] = [
            (
                SubtitleCue(start=5.0, end=7.0, text="Привет"),
                [],
            ),
            (
                None,
                [SubtitleCue(start=10.0, end=12.0, text="Hello")],
            ),
        ]

        root = create_ttml_document(aligned_cues, lang1="rus", lang2="eng")

        body = root.find("{http://www.w3.org/ns/ttml}body")
        assert body is not None

        divs = body.findall("{http://www.w3.org/ns/ttml}div")
        assert len(divs) == 2

        # First div is for eng - should have one paragraph
        div_eng = divs[0]
        paragraphs_eng = div_eng.findall("{http://www.w3.org/ns/ttml}p")
        assert len(paragraphs_eng) == 1
        assert paragraphs_eng[0].text == "Hello"

        # Second div is for rus - should have one paragraph
        div_rus = divs[1]
        paragraphs_rus = div_rus.findall("{http://www.w3.org/ns/ttml}p")
        assert len(paragraphs_rus) == 1
        assert paragraphs_rus[0].text == "Привет"


class TestSegmentsToTTML:
    """Tests for converting Whisper segments to TTML."""

    def test_segments_to_ttml_basic(self) -> None:
        """
        Verify conversion of parallel speech segments into a bilingual TTML string containing an XML declaration, a TTML root with `xml:lang="en"`, a head section, two language-specific `div` elements (`eng` and `rus`), and `p` elements with correct `begin`/`end` timestamps and texts.
        """

        # Mock Whisper segment objects
        class MockSegment:
            def __init__(self, start: float, end: float, text: str) -> None:
                self.start = start
                self.end = end
                self.text = text

        segments_ru = [
            MockSegment(5.0, 7.0, "Привет, мир!"),
            MockSegment(10.0, 12.0, "Как дела?"),
        ]

        segments_en = [
            MockSegment(5.0, 7.0, "Hello, world!"),
            MockSegment(10.0, 12.0, "How are you?"),
        ]

        ttml_content = segments_to_ttml(
            cast(List[SegmentLike], segments_ru),
            cast(List[SegmentLike], segments_en),
            lang1="rus",
            lang2="eng",
        )

        assert '<?xml version="1.0" encoding="UTF-8"?>' in ttml_content
        assert '<tt xmlns="http://www.w3.org/ns/ttml"' in ttml_content
        assert 'xml:lang="en"' in ttml_content  # Root lang is en
        assert "<head>" in ttml_content
        assert '<div xml:lang="eng">' in ttml_content
        assert '<div xml:lang="rus">' in ttml_content
        assert (
            '<p begin="00:00:05.000" end="00:00:07.000">Привет, мир!</p>'
            in ttml_content
        )
        assert (
            '<p begin="00:00:05.000" end="00:00:07.000">Hello, world!</p>'
            in ttml_content
        )


class TestVTTFilesToTTML:
    """Tests for converting VTT files to TTML."""

    def test_vtt_files_to_ttml_integration(self) -> None:
        """Test full conversion from VTT files to TTML."""
        vtt_ru_content = """WEBVTT

1
00:00:05.000 --> 00:00:07.000
Привет, мир!

2
00:00:10.000 --> 00:00:12.000
Как дела?
"""

        vtt_en_content = """WEBVTT

1
00:00:05.000 --> 00:00:07.000
Hello, world!

2
00:00:10.000 --> 00:00:12.000
How are you?
"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ru.vtt", delete=False, encoding="utf-8"
        ) as f_ru:
            f_ru.write(vtt_ru_content)
            vtt_ru_path = f_ru.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".en.vtt", delete=False, encoding="utf-8"
        ) as f_en:
            f_en.write(vtt_en_content)
            vtt_en_path = f_en.name

        try:
            ttml_content = vtt_files_to_ttml(
                vtt_ru_path, vtt_en_path, lang1="rus", lang2="eng"
            )

            # Validate XML structure
            assert '<?xml version="1.0" encoding="UTF-8"?>' in ttml_content

            # Parse XML to validate structure
            xml_content = ttml_content.split("\n", 1)[1]  # Skip XML declaration
            root = ET.fromstring(xml_content)

            assert root.tag == "{http://www.w3.org/ns/ttml}tt"
            ns = {"tt": "http://www.w3.org/ns/ttml"}

            # Check for head
            head = root.find("tt:head", ns)
            assert head is not None

            # Check body
            body = root.find("tt:body", ns)
            assert body is not None

            # Should have two divs (one per language)
            divs = body.findall("tt:div", ns)
            assert len(divs) == 2

            lang_attr = "{http://www.w3.org/XML/1998/namespace}lang"

            # First div is for eng
            div_eng = divs[0]
            assert div_eng.get(lang_attr) == "eng"
            paragraphs_eng = div_eng.findall("tt:p", ns)
            assert len(paragraphs_eng) == 2
            assert paragraphs_eng[0].get("begin") == "00:00:05.000"
            assert paragraphs_eng[0].text == "Hello, world!"
            assert paragraphs_eng[1].text == "How are you?"

            # Second div is for rus
            div_rus = divs[1]
            assert div_rus.get(lang_attr) == "rus"
            paragraphs_rus = div_rus.findall("tt:p", ns)
            assert len(paragraphs_rus) == 2
            assert paragraphs_rus[0].get("begin") == "00:00:05.000"
            assert paragraphs_rus[0].text == "Привет, мир!"
            assert paragraphs_rus[1].text == "Как дела?"

        finally:
            Path(vtt_ru_path).unlink()
            Path(vtt_en_path).unlink()

    def test_vtt_files_to_ttml_uses_pre_aligned_cues(self) -> None:
        """Ensure pre-aligned cues are used without re-parsing files."""
        cue_lang1 = SubtitleCue(start=5.0, end=7.0, text="Привет, мир!")
        cue_lang2 = SubtitleCue(start=5.0, end=7.0, text="Hello, world!")
        aligned = cast(
            List[Tuple[Optional[SubtitleCue], List[SubtitleCue]]],
            [(cue_lang1, [cue_lang2])],
        )

        with mock.patch("src.python.tools.ttml_utils.parse_vtt_file") as mock_parse:
            ttml_content = vtt_files_to_ttml(
                "ignored.ru.vtt",
                "ignored.en.vtt",
                lang1="ru",
                lang2="en",
                aligned_cues=aligned,
            )

        mock_parse.assert_not_called()
        assert "Привет, мир!" in ttml_content
        assert "Hello, world!" in ttml_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
