#!/usr/bin/env python3
"""Unit tests for TTML generation and conversion utilities."""

import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

from ttml_utils import (
    SubtitleCue,
    format_ttml_timestamp,
    parse_vtt_timestamp,
    parse_vtt_file,
    align_bilingual_cues,
    create_ttml_document,
    segments_to_ttml,
    vtt_files_to_ttml,
)


class TestTimestampFormatting:
    """Tests for timestamp formatting functions."""

    def test_format_ttml_timestamp_zero(self):
        """Test formatting zero seconds."""
        result = format_ttml_timestamp(0.0)
        assert result == "00:00:00.000"

    def test_format_ttml_timestamp_simple(self):
        """Test formatting simple timestamp."""
        result = format_ttml_timestamp(65.5)
        assert result == "00:01:05.500"

    def test_format_ttml_timestamp_hours(self):
        """Test formatting timestamp with hours."""
        result = format_ttml_timestamp(3661.123)
        assert result == "01:01:01.123"

    def test_format_ttml_timestamp_long(self):
        """Test formatting long timestamp."""
        result = format_ttml_timestamp(7384.456)
        assert result == "02:03:04.456"


class TestTimestampParsing:
    """Tests for VTT timestamp parsing."""

    def test_parse_vtt_timestamp_short_format(self):
        """Test parsing short format (MM:SS.mmm)."""
        result = parse_vtt_timestamp("01:23.456")
        assert abs(result - 83.456) < 0.001

    def test_parse_vtt_timestamp_long_format(self):
        """Test parsing long format (HH:MM:SS.mmm)."""
        result = parse_vtt_timestamp("01:02:03.456")
        assert abs(result - 3723.456) < 0.001

    def test_parse_vtt_timestamp_no_milliseconds(self):
        """Test parsing timestamp without milliseconds."""
        result = parse_vtt_timestamp("01:30")
        assert abs(result - 90.0) < 0.001

    def test_parse_vtt_timestamp_zero(self):
        """Test parsing zero timestamp."""
        result = parse_vtt_timestamp("00:00.000")
        assert abs(result - 0.0) < 0.001

    def test_parse_vtt_timestamp_with_spaces(self):
        """Test parsing timestamp with spaces."""
        result = parse_vtt_timestamp("  01:23.456  ")
        assert abs(result - 83.456) < 0.001


class TestVTTFileParsing:
    """Tests for VTT file parsing."""

    def test_parse_simple_vtt_file(self):
        """Test parsing a simple VTT file."""
        vtt_content = """WEBVTT

1
00:00:05.000 --> 00:00:07.000
Hello, world!

2
00:00:10.000 --> 00:00:12.500
Second subtitle
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False, encoding="utf-8") as f:
            f.write(vtt_content)
            vtt_path = f.name

        try:
            cues = parse_vtt_file(vtt_path)
            assert len(cues) == 2

            assert abs(cues[0].start - 5.0) < 0.001
            assert abs(cues[0].end - 7.0) < 0.001
            assert cues[0].text == "Hello, world!"

            assert abs(cues[1].start - 10.0) < 0.001
            assert abs(cues[1].end - 12.5) < 0.001
            assert cues[1].text == "Second subtitle"
        finally:
            Path(vtt_path).unlink()

    def test_parse_vtt_file_multiline_text(self):
        """Test parsing VTT with multiline text."""
        vtt_content = """WEBVTT

1
00:00:05.000 --> 00:00:08.000
First line
Second line
Third line
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False, encoding="utf-8") as f:
            f.write(vtt_content)
            vtt_path = f.name

        try:
            cues = parse_vtt_file(vtt_path)
            assert len(cues) == 1
            assert cues[0].text == "First line\nSecond line\nThird line"
        finally:
            Path(vtt_path).unlink()

    def test_parse_vtt_file_empty_lines(self):
        """Test parsing VTT with empty lines."""
        vtt_content = """WEBVTT


1
00:00:05.000 --> 00:00:07.000
Hello


2
00:00:10.000 --> 00:00:12.000
World

"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False, encoding="utf-8") as f:
            f.write(vtt_content)
            vtt_path = f.name

        try:
            cues = parse_vtt_file(vtt_path)
            assert len(cues) == 2
        finally:
            Path(vtt_path).unlink()


class TestBilingualCueAlignment:
    """Tests for bilingual cue alignment."""

    def test_align_perfect_match(self):
        """Test alignment with perfect timestamp matches."""
        cues_lang1 = [
            SubtitleCue(start=5.0, end=7.0, text="Привет"),
            SubtitleCue(start=10.0, end=12.0, text="Мир"),
        ]
        cues_lang2 = [
            SubtitleCue(start=5.0, end=7.0, text="Hello"),
            SubtitleCue(start=10.0, end=12.0, text="World"),
        ]

        aligned = align_bilingual_cues(cues_lang1, cues_lang2, tolerance=1.0)

        assert len(aligned) == 2
        assert aligned[0][0].text == "Привет"
        assert len(aligned[0][1]) == 1
        assert aligned[0][1][0].text == "Hello"
        assert aligned[1][0].text == "Мир"
        assert len(aligned[1][1]) == 1
        assert aligned[1][1][0].text == "World"

    def test_align_with_tolerance(self):
        """Test alignment with slight timestamp differences."""
        cues_lang1 = [
            SubtitleCue(start=5.0, end=7.0, text="Привет"),
        ]
        cues_lang2 = [
            SubtitleCue(start=5.5, end=7.5, text="Hello"),
        ]

        aligned = align_bilingual_cues(cues_lang1, cues_lang2, tolerance=1.0)

        assert len(aligned) == 1
        assert aligned[0][0].text == "Привет"
        assert len(aligned[0][1]) == 1
        assert aligned[0][1][0].text == "Hello"

    def test_align_unmatched_cues(self):
        """Test alignment with unmatched cues."""
        cues_lang1 = [
            SubtitleCue(start=5.0, end=7.0, text="Привет"),
            SubtitleCue(start=15.0, end=17.0, text="Пока"),
        ]
        cues_lang2 = [
            SubtitleCue(start=5.5, end=7.5, text="Hello"),
        ]

        aligned = align_bilingual_cues(cues_lang1, cues_lang2, tolerance=1.0)

        assert len(aligned) == 2
        assert aligned[0][0].text == "Привет"
        assert len(aligned[0][1]) == 1
        assert aligned[0][1][0].text == "Hello"
        assert aligned[1][0].text == "Пока"
        assert aligned[1][1] == []

    def test_align_extra_lang2_cues(self):
        """Test alignment when lang2 has extra cues."""
        cues_lang1 = [
            SubtitleCue(start=5.0, end=7.0, text="Привет"),
        ]
        cues_lang2 = [
            SubtitleCue(start=5.0, end=7.0, text="Hello"),
            SubtitleCue(start=10.0, end=12.0, text="Extra"),
        ]

        aligned = align_bilingual_cues(cues_lang1, cues_lang2, tolerance=1.0)

        assert len(aligned) == 2
        assert aligned[0][0].text == "Привет"
        assert len(aligned[0][1]) == 1
        assert aligned[0][1][0].text == "Hello"
        assert aligned[1][0] is None
        assert len(aligned[1][1]) == 1
        assert aligned[1][1][0].text == "Extra"


class TestTTMLDocumentCreation:
    """Tests for TTML document creation."""

    def test_create_simple_ttml_document(self):
        """Test creating a simple TTML document."""
        aligned_cues = [
            (
                SubtitleCue(start=5.0, end=7.0, text="Привет"),
                [SubtitleCue(start=5.0, end=7.0, text="Hello")],
            ),
        ]

        root = create_ttml_document(aligned_cues, lang1="ru", lang2="en")

        assert root.tag == "tt"
        assert root.get("xmlns") == "http://www.w3.org/ns/ttml"
        assert root.get("{http://www.w3.org/XML/1998/namespace}lang") == "ru"

        body = root.find("body")
        assert body is not None

        div = body.find("div")
        assert div is not None

        paragraphs = div.findall("p")
        assert len(paragraphs) == 2

        p_ru = paragraphs[0]
        assert p_ru.get("begin") == "00:00:05.000"
        assert p_ru.get("end") == "00:00:07.000"
        spans_ru = p_ru.findall("span")
        assert len(spans_ru) == 1
        assert spans_ru[0].get("{http://www.w3.org/XML/1998/namespace}lang") == "ru"
        assert spans_ru[0].text == "Привет"

        p_en = paragraphs[1]
        assert p_en.get("begin") == "00:00:05.000"
        assert p_en.get("end") == "00:00:07.000"
        spans_en = p_en.findall("span")
        assert len(spans_en) == 1
        assert spans_en[0].get("{http://www.w3.org/XML/1998/namespace}lang") == "en"
        assert spans_en[0].text == "Hello"

    def test_create_ttml_document_with_unmatched_cues(self):
        """Test creating TTML with unmatched cues."""
        aligned_cues = [
            (
                SubtitleCue(start=5.0, end=7.0, text="Привет"),
                [],
            ),
            (
                None,
                [SubtitleCue(start=10.0, end=12.0, text="Hello")],
            ),
        ]

        root = create_ttml_document(aligned_cues, lang1="ru", lang2="en")

        div = root.find("body/div")
        paragraphs = div.findall("p")
        assert len(paragraphs) == 2

        # First paragraph should have only Russian
        spans1 = paragraphs[0].findall("span")
        assert len(spans1) == 1
        assert spans1[0].get("{http://www.w3.org/XML/1998/namespace}lang") == "ru"

        # Second paragraph should have only English
        spans2 = paragraphs[1].findall("span")
        assert len(spans2) == 1
        assert spans2[0].get("{http://www.w3.org/XML/1998/namespace}lang") == "en"


class TestSegmentsToTTML:
    """Tests for converting Whisper segments to TTML."""

    def test_segments_to_ttml_basic(self):
        """Test basic segment conversion."""
        # Mock Whisper segment objects
        class MockSegment:
            def __init__(self, start, end, text):
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

        ttml_content = segments_to_ttml(segments_ru, segments_en, lang1="ru", lang2="en")

        assert '<?xml version="1.0" encoding="UTF-8"?>' in ttml_content
        assert '<tt xmlns="http://www.w3.org/ns/ttml"' in ttml_content
        assert 'xml:lang="ru"' in ttml_content
        assert '<p begin="00:00:05.000" end="00:00:07.000">' in ttml_content
        assert '<span xml:lang="ru">Привет, мир!</span>' in ttml_content
        assert '<span xml:lang="en">Hello, world!</span>' in ttml_content


class TestVTTFilesToTTML:
    """Tests for converting VTT files to TTML."""

    def test_vtt_files_to_ttml_integration(self):
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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ru.vtt", delete=False, encoding="utf-8") as f_ru:
            f_ru.write(vtt_ru_content)
            vtt_ru_path = f_ru.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".en.vtt", delete=False, encoding="utf-8") as f_en:
            f_en.write(vtt_en_content)
            vtt_en_path = f_en.name

        try:
            ttml_content = vtt_files_to_ttml(vtt_ru_path, vtt_en_path, lang1="ru", lang2="en")

            # Validate XML structure
            assert '<?xml version="1.0" encoding="UTF-8"?>' in ttml_content

            # Parse XML to validate structure
            xml_content = ttml_content.split("\n", 1)[1]  # Skip XML declaration
            root = ET.fromstring(xml_content)

            assert root.tag.endswith("tt")
            ns = {"tt": "http://www.w3.org/ns/ttml"}
            body = root.find("tt:body", ns)
            div = body.find("tt:div", ns)
            paragraphs = div.findall("tt:p", ns)

            # Expect two languages per cue (overlapping paragraphs)
            assert len(paragraphs) == 4

            lang_attr = "{http://www.w3.org/XML/1998/namespace}lang"
            ru_paragraphs = []
            en_paragraphs = []
            for p in paragraphs:
                spans = p.findall("tt:span", ns)
                assert len(spans) == 1
                lang = spans[0].get(lang_attr)
                if lang == "ru":
                    ru_paragraphs.append(p)
                elif lang == "en":
                    en_paragraphs.append(p)
                else:
                    raise AssertionError(f"Unexpected language span: {lang}")

            assert len(ru_paragraphs) == 2
            assert len(en_paragraphs) == 2

            assert ru_paragraphs[0].get("begin") == "00:00:05.000"
            assert en_paragraphs[0].get("begin") == "00:00:05.000"
            first_en_span = en_paragraphs[0].findall("tt:span", ns)[0]
            assert first_en_span.text == "Hello, world!"

        finally:
            Path(vtt_ru_path).unlink()
            Path(vtt_en_path).unlink()

    def test_vtt_files_to_ttml_uses_pre_aligned_cues(self):
        """Ensure pre-aligned cues are used without re-parsing files."""
        cue_lang1 = SubtitleCue(start=5.0, end=7.0, text="Привет, мир!")
        cue_lang2 = SubtitleCue(start=5.0, end=7.0, text="Hello, world!")
        aligned = [(cue_lang1, [cue_lang2])]

        with mock.patch("ttml_utils.parse_vtt_file") as mock_parse:
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
