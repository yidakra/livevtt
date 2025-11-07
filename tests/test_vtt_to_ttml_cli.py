#!/usr/bin/env python3
"""Tests for vtt_to_ttml.py CLI converter."""

import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

from src.python.tools.vtt_to_ttml import (
    validate_vtt_file,
    convert_vtt_to_ttml,
    parse_args,
)


class TestVTTValidation:
    """Tests for VTT file validation."""

    def test_validate_existing_vtt(self):
        """Test validating an existing VTT file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False) as f:
            f.write("WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nTest\n")
            f.flush()
            vtt_path = Path(f.name)

        try:
            assert validate_vtt_file(vtt_path)
            print("✓ test_validate_existing_vtt passed")
        finally:
            vtt_path.unlink()

    def test_validate_nonexistent_file(self):
        """Test validating a non-existent file."""
        assert not validate_vtt_file(Path("/nonexistent/file.vtt"))
        print("✓ test_validate_nonexistent_file passed")

    def test_validate_directory_not_file(self):
        """Test validating a directory instead of file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert not validate_vtt_file(Path(tmpdir))
            print("✓ test_validate_directory_not_file passed")

    def test_validate_missing_webvtt_header(self):
        """Test file without WEBVTT header (should warn but pass)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vtt", delete=False) as f:
            f.write("1\n00:00:00.000 --> 00:00:02.000\nTest\n")
            f.flush()
            vtt_path = Path(f.name)

        try:
            # Should still validate (warning is logged)
            with mock.patch("src.python.tools.vtt_to_ttml.logging.warning") as mock_warning:
                result = validate_vtt_file(vtt_path)
            assert result  # File is readable even without WEBVTT header
            mock_warning.assert_called_once()
            print("✓ test_validate_missing_webvtt_header passed")
        finally:
            vtt_path.unlink()


class TestConvertVTTtoTTML:
    """Tests for VTT to TTML conversion."""

    def test_successful_conversion(self):
        """Test successful conversion of two VTT files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create test VTT files
            ru_vtt = tmpdir / "test.ru.vtt"
            en_vtt = tmpdir / "test.en.vtt"
            output = tmpdir / "test.ttml"

            ru_vtt.write_text("""WEBVTT

1
00:00:05.000 --> 00:00:07.000
Привет
""")

            en_vtt.write_text("""WEBVTT

1
00:00:05.000 --> 00:00:07.000
Hello
""")

            # Convert
            success = convert_vtt_to_ttml(
                ru_vtt,
                en_vtt,
                output,
                lang1="ru",
                lang2="en",
                tolerance=1.0,
            )

            assert success
            assert output.exists()

            # Verify output content
            content = output.read_text()
            assert '<?xml version="1.0" encoding="UTF-8"?>' in content
            assert 'xml:lang="ru"' in content
            assert "Привет" in content
            assert "Hello" in content

            print("✓ test_successful_conversion passed")

    def test_conversion_missing_input(self):
        """Test conversion with missing input file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            ru_vtt = tmpdir / "missing.ru.vtt"
            en_vtt = tmpdir / "test.en.vtt"
            output = tmpdir / "test.ttml"

            en_vtt.write_text("WEBVTT\n")

            # Should fail validation
            success = convert_vtt_to_ttml(
                ru_vtt,  # Missing file
                en_vtt,
                output,
                lang1="ru",
                lang2="en",
                tolerance=1.0,
            )

            assert not success
            print("✓ test_conversion_missing_input passed")

    def test_conversion_creates_output_directory(self):
        """Test that conversion creates output directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            ru_vtt = tmpdir / "test.ru.vtt"
            en_vtt = tmpdir / "test.en.vtt"
            output = tmpdir / "subdir" / "nested" / "test.ttml"

            ru_vtt.write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nRU\n")
            en_vtt.write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nEN\n")

            success = convert_vtt_to_ttml(
                ru_vtt,
                en_vtt,
                output,
                lang1="ru",
                lang2="en",
                tolerance=1.0,
            )

            assert success
            assert output.exists()
            assert output.parent.exists()

            print("✓ test_conversion_creates_output_directory passed")

    def test_conversion_with_custom_tolerance(self):
        """Test conversion with custom timestamp tolerance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            ru_vtt = tmpdir / "test.ru.vtt"
            en_vtt = tmpdir / "test.en.vtt"
            output = tmpdir / "test.ttml"

            # Different timestamps within 2 seconds
            ru_vtt.write_text("""WEBVTT

1
00:00:05.000 --> 00:00:07.000
Привет
""")

            en_vtt.write_text("""WEBVTT

1
00:00:06.500 --> 00:00:08.500
Hello
""")

            # Should align with tolerance of 2.0 seconds
            success = convert_vtt_to_ttml(
                ru_vtt,
                en_vtt,
                output,
                lang1="ru",
                lang2="en",
                tolerance=2.0,
            )

            assert success
            assert output.exists()

            print("✓ test_conversion_with_custom_tolerance passed")


class TestArgumentParsing:
    """Tests for command-line argument parsing."""

    def test_parse_args_required(self):
        """Test parsing required arguments."""
        args = parse_args([
            "--vtt_ru", "test.ru.vtt",
            "--vtt_en", "test.en.vtt",
            "--output", "test.ttml",
        ])

        assert args.vtt_ru == Path("test.ru.vtt")
        assert args.vtt_en == Path("test.en.vtt")
        assert args.output == Path("test.ttml")
        print("✓ test_parse_args_required passed")

    def test_parse_args_defaults(self):
        """Test default values for optional arguments."""
        args = parse_args([
            "--vtt_ru", "test.ru.vtt",
            "--vtt_en", "test.en.vtt",
            "--output", "test.ttml",
        ])

        assert args.lang1 == "ru"
        assert args.lang2 == "en"
        assert args.tolerance == 1.0
        assert not args.verbose
        print("✓ test_parse_args_defaults passed")

    def test_parse_args_custom_languages(self):
        """Test parsing custom language codes."""
        args = parse_args([
            "--vtt_ru", "test.es.vtt",
            "--vtt_en", "test.en.vtt",
            "--output", "test.ttml",
            "--lang1", "es",
            "--lang2", "en",
        ])

        assert args.lang1 == "es"
        assert args.lang2 == "en"
        print("✓ test_parse_args_custom_languages passed")

    def test_parse_args_custom_tolerance(self):
        """Test parsing custom tolerance."""
        args = parse_args([
            "--vtt_ru", "test.ru.vtt",
            "--vtt_en", "test.en.vtt",
            "--output", "test.ttml",
            "--tolerance", "2.5",
        ])

        assert args.tolerance == 2.5
        print("✓ test_parse_args_custom_tolerance passed")

    def test_parse_args_verbose(self):
        """Test verbose flag."""
        args = parse_args([
            "--vtt_ru", "test.ru.vtt",
            "--vtt_en", "test.en.vtt",
            "--output", "test.ttml",
            "--verbose",
        ])

        assert args.verbose
        print("✓ test_parse_args_verbose passed")

    def test_parse_args_alternative_flags(self):
        """Test alternative flag names (with hyphens)."""
        args = parse_args([
            "--vtt-ru", "test.ru.vtt",
            "--vtt-en", "test.en.vtt",
            "-o", "test.ttml",
        ])

        assert args.vtt_ru == Path("test.ru.vtt")
        assert args.vtt_en == Path("test.en.vtt")
        assert args.output == Path("test.ttml")
        print("✓ test_parse_args_alternative_flags passed")


def run_all_tests():
    """Run all vtt_to_ttml CLI tests."""
    print("\nRunning vtt_to_ttml CLI tests...")
    print("=" * 60)

    test_classes = [
        TestVTTValidation,
        TestConvertVTTtoTTML,
        TestArgumentParsing,
    ]

    total_passed = 0
    total_failed = 0

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        print("-" * 60)

        test_methods = [
            method for method in dir(test_class)
            if method.startswith("test_") and callable(getattr(test_class, method))
        ]

        for method_name in test_methods:
            try:
                instance = test_class()
                method = getattr(instance, method_name)
                method()
                total_passed += 1
            except AssertionError as e:
                print(f"✗ {method_name} failed: {e}")
                traceback.print_exc()
                total_failed += 1
            except Exception as e:
                print(f"✗ {method_name} error: {e}")
                traceback.print_exc()
                total_failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {total_passed} passed, {total_failed} failed")
    print("=" * 60)

    return total_failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
