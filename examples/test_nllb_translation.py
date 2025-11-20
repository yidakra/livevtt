#!/usr/bin/env python3
"""Simple test script for NLLB VTT translation.

This script demonstrates how to use the NLLB VTT translator
to translate Russian subtitle files to English.
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from python.tools.ttml_utils import SubtitleCue, cues_to_webvtt


def create_test_vtt_file() -> Path:
    """Create a temporary test VTT file with Russian content."""
    test_cues = [
        SubtitleCue(start=0.0, end=3.0, text="Добрый день!"),
        SubtitleCue(start=3.5, end=7.0, text="Как дела?"),
        SubtitleCue(start=7.5, end=12.0, text="Меня зовут Алексей."),
        SubtitleCue(start=12.5, end=18.0, text="Я работаю программистом в Москве."),
        SubtitleCue(start=18.5, end=23.0, text="Очень приятно познакомиться!"),
    ]

    vtt_content = cues_to_webvtt(test_cues)

    # Create temporary file
    tmp_dir = Path(tempfile.mkdtemp(prefix="nllb_test_"))
    test_vtt = tmp_dir / "test.ru.vtt"

    with open(test_vtt, "w", encoding="utf-8") as f:
        f.write(vtt_content)

    print(f"✅ Created test VTT file: {test_vtt}")
    print("\nOriginal Russian content:")
    print("=" * 60)
    for i, cue in enumerate(test_cues, 1):
        print(f"{i}. [{cue.start:.1f}s - {cue.end:.1f}s] {cue.text}")
    print("=" * 60)

    return test_vtt


def main():
    """Run a simple NLLB translation test."""
    print("🔬 NLLB VTT Translation Test")
    print()

    # Create test file
    test_vtt = create_test_vtt_file()
    test_dir = test_vtt.parent

    print("\n📋 To translate this file, run:")
    print(f"\n  python src/python/tools/nllb_vtt_translator.py {test_dir} --verbose\n")

    print("Expected output file:")
    print(f"  {test_dir / 'test.nllb.en.vtt'}\n")

    print("💡 Tip: Use --max-files 1 to test on a single file")
    print("💡 Tip: Use --device cpu if you don't have a GPU")
    print("💡 Tip: Use --model facebook/nllb-200-distilled-600M for faster translation")

    print(f"\n📁 Test directory: {test_dir}")
    print("🗑️  Delete this directory when done testing")


if __name__ == "__main__":
    main()
