#!/usr/bin/env python3
"""Compare Whisper, NLLB, LibreTranslate, and Mistral translations side-by-side.

This script takes a directory containing:
- *.ru.vtt (Russian source)
- *.en.vtt (Whisper translation)
- *.nllb.en.vtt (NLLB translation)
- *.libretranslate.en.vtt (LibreTranslate translation)
- *.mistral.en.vtt (Mistral LLM translation)

And displays them side-by-side for quality comparison.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from python.tools.ttml_utils import SubtitleCue, parse_vtt_file


def print_comparison(
    ru_cue: SubtitleCue,
    whisper_cue: SubtitleCue | None,
    nllb_cue: SubtitleCue | None,
    libre_cue: SubtitleCue | None,
    mistral_cue: SubtitleCue | None,
    index: int,
):
    """Print a side-by-side comparison of all available translations."""
    print(f"\n{'='*80}")
    print(f"Cue #{index} [{ru_cue.start:.1f}s - {ru_cue.end:.1f}s]")
    print(f"{'='*80}")

    print("\n🇷🇺 Russian (source):")
    print(f"   {ru_cue.text}")

    print("\n🤖 Whisper translation:")
    if whisper_cue:
        print(f"   {whisper_cue.text}")
    else:
        print("   [NOT FOUND]")

    print("\n🌍 NLLB-200 translation:")
    if nllb_cue:
        print(f"   {nllb_cue.text}")
    else:
        print("   [NOT FOUND]")

    print("\n🔄 LibreTranslate translation:")
    if libre_cue:
        print(f"   {libre_cue.text}")
    else:
        print("   [NOT FOUND]")

    print("\n🧠 Mistral LLM translation:")
    if mistral_cue:
        print(f"   {mistral_cue.text}")
    else:
        print("   [NOT FOUND]")


def find_matching_cue(cues: list[SubtitleCue], target_start: float, tolerance: float = 0.5) -> SubtitleCue | None:
    """Find a cue with matching start time."""
    for cue in cues:
        if abs(cue.start - target_start) < tolerance:
            return cue
    return None


def compare_translations(directory: Path, max_cues: int = 20):
    """Compare translations in a directory."""
    # Find files
    ru_files = list(directory.glob("*.ru.vtt"))
    if not ru_files:
        print(f"❌ No *.ru.vtt files found in {directory}")
        return

    # Process first file (or you could loop through all)
    ru_vtt = ru_files[0]
    base_name = ru_vtt.name.replace(".ru.vtt", "")

    whisper_vtt = directory / f"{base_name}.en.vtt"
    nllb_vtt = directory / f"{base_name}.nllb.en.vtt"
    libre_vtt = directory / f"{base_name}.libretranslate.en.vtt"
    mistral_vtt = directory / f"{base_name}.mistral.en.vtt"

    print(f"📁 Comparing translations for: {base_name}")
    print(f"   Russian source: {ru_vtt.name}")
    print(f"   Whisper: {whisper_vtt.name} {'✅' if whisper_vtt.exists() else '❌ MISSING'}")
    print(f"   NLLB-200: {nllb_vtt.name} {'✅' if nllb_vtt.exists() else '❌ MISSING'}")
    print(f"   LibreTranslate: {libre_vtt.name} {'✅' if libre_vtt.exists() else '❌ MISSING'}")
    print(f"   Mistral LLM: {mistral_vtt.name} {'✅' if mistral_vtt.exists() else '❌ MISSING'}")

    # Parse files
    ru_cues = parse_vtt_file(str(ru_vtt))
    whisper_cues = parse_vtt_file(str(whisper_vtt)) if whisper_vtt.exists() else []
    nllb_cues = parse_vtt_file(str(nllb_vtt)) if nllb_vtt.exists() else []
    libre_cues = parse_vtt_file(str(libre_vtt)) if libre_vtt.exists() else []
    mistral_cues = parse_vtt_file(str(mistral_vtt)) if mistral_vtt.exists() else []

    print("\n📊 Cue counts:")
    print(f"   Russian: {len(ru_cues)} cues")
    print(f"   Whisper: {len(whisper_cues)} cues")
    print(f"   NLLB-200: {len(nllb_cues)} cues")
    print(f"   LibreTranslate: {len(libre_cues)} cues")
    print(f"   Mistral LLM: {len(mistral_cues)} cues")

    # Compare side-by-side
    num_to_show = min(len(ru_cues), max_cues)
    print(f"\n🔍 Showing first {num_to_show} cues:\n")

    for i, ru_cue in enumerate(ru_cues[:num_to_show], 1):
        whisper_cue = find_matching_cue(whisper_cues, ru_cue.start)
        nllb_cue = find_matching_cue(nllb_cues, ru_cue.start)
        libre_cue = find_matching_cue(libre_cues, ru_cue.start)
        mistral_cue = find_matching_cue(mistral_cues, ru_cue.start)

        print_comparison(ru_cue, whisper_cue, nllb_cue, libre_cue, mistral_cue, i)

    if len(ru_cues) > max_cues:
        print(f"\n... and {len(ru_cues) - max_cues} more cues (use --max-cues to see more)")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compare Whisper, NLLB, LibreTranslate, and Mistral translations side-by-side"
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing .ru.vtt, .en.vtt, .nllb.en.vtt, .libretranslate.en.vtt, and .mistral.en.vtt files",
    )
    parser.add_argument("--max-cues", type=int, default=20, help="Maximum number of cues to display (default: 20)")

    args = parser.parse_args()

    if not args.directory.exists():
        print(f"❌ Directory not found: {args.directory}")
        return 1

    print("🔬 Translation Quality Comparison")
    print("=" * 80)

    compare_translations(args.directory, args.max_cues)

    print("\n" + "=" * 80)
    print("✅ Comparison complete!")
    print("\n💡 Tips for quality assessment:")
    print("  • Check for naturalness and fluency")
    print("  • Look for proper handling of idioms and expressions")
    print("  • Verify technical terms are correctly translated")
    print("  • Check if context is preserved across sentences")


if __name__ == "__main__":
    sys.exit(main())
