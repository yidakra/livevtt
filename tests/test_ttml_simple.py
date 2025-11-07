#!/usr/bin/env python3
"""Simple tests for TTML utilities (no pytest required)."""

import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

from ttml_utils import (
    SubtitleCue,
    format_ttml_timestamp,
    parse_vtt_timestamp,
    parse_vtt_file,
    align_bilingual_cues,
    vtt_files_to_ttml,
)


def test_format_timestamp():
    """Test timestamp formatting."""
    assert format_ttml_timestamp(0.0) == "00:00:00.000"
    assert format_ttml_timestamp(65.5) == "00:01:05.500"
    assert format_ttml_timestamp(3661.123) == "01:01:01.123"
    print("✓ test_format_timestamp passed")


def test_parse_timestamp():
    """Test timestamp parsing."""
    assert abs(parse_vtt_timestamp("01:23.456") - 83.456) < 0.001
    assert abs(parse_vtt_timestamp("01:02:03.456") - 3723.456) < 0.001
    print("✓ test_parse_timestamp passed")


def test_parse_vtt_file():
    """Test VTT file parsing."""
    vtt_content = """WEBVTT

1
00:00:05.000 --> 00:00:07.000
Hello, world!

2
00:00:10.000 --> 00:00:12.500
Second subtitle
"""
    vtt_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False, encoding="utf-8") as f:
            f.write(vtt_content)
            vtt_path = f.name

        cues = parse_vtt_file(vtt_path)
        assert len(cues) == 2
        assert abs(cues[0].start - 5.0) < 0.001
        assert cues[0].text == "Hello, world!"
        print("✓ test_parse_vtt_file passed")
    finally:
        if vtt_path:
            Path(vtt_path).unlink()


def test_align_cues():
    """Test bilingual cue alignment."""
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
    print("✓ test_align_cues passed")


def test_vtt_to_ttml():
    """Test full VTT to TTML conversion."""
    vtt_ru_content = """WEBVTT

1
00:00:05.000 --> 00:00:07.000
Привет, мир!
"""

    vtt_en_content = """WEBVTT

1
00:00:05.000 --> 00:00:07.000
Hello, world!
"""

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ru.vtt", delete=False, encoding="utf-8") as f_ru:
            f_ru.write(vtt_ru_content)
            vtt_ru_path = f_ru.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".en.vtt", delete=False, encoding="utf-8") as f_en:
            f_en.write(vtt_en_content)
            vtt_en_path = f_en.name

        ttml_content = vtt_files_to_ttml(vtt_ru_path, vtt_en_path, lang1="ru", lang2="en")

        # Validate XML structure
        assert '<?xml version="1.0" encoding="UTF-8"?>' in ttml_content
        assert '<tt xmlns="http://www.w3.org/ns/ttml"' in ttml_content
        assert 'xml:lang="ru"' in ttml_content
        assert 'Привет, мир!' in ttml_content
        assert 'Hello, world!' in ttml_content

        # Parse XML to validate structure
        xml_content = ttml_content.split("\n", 1)[1]
        root = ET.fromstring(xml_content)
        # Tag will include namespace, so check if it ends with 'tt'
        assert root.tag.endswith("tt") or root.tag == "tt"

        print("✓ test_vtt_to_ttml passed")
    finally:
        Path(vtt_ru_path).unlink()
        Path(vtt_en_path).unlink()


def run_all_tests():
    """Run all tests."""
    print("\nRunning TTML utility tests...")
    print("=" * 50)

    tests = [
        test_format_timestamp,
        test_parse_timestamp,
        test_parse_vtt_file,
        test_align_cues,
        test_vtt_to_ttml,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} error: {e}")
            traceback.print_exc()
            failed += 1

    print("=" * 50)
    print(f"\nResults: {passed} passed, {failed} failed")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
