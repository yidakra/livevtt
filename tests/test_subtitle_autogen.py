#!/usr/bin/env python3
"""Tests for subtitle_autogen.py background service."""

import argparse
import sys
from pathlib import Path
from unittest import mock

# Mock archive_transcriber before import
sys.modules["src.python.tools.archive_transcriber"] = mock.MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.python.services import subtitle_autogen


class TestArgumentParsing:
    """Tests for command-line argument parsing."""

    def test_parse_args_minimal_required(self):
        """Test parsing with only required argument."""
        with mock.patch("sys.argv", ["subtitle_autogen.py", "/archive/path"]):
            args = subtitle_autogen.parse_args()
            assert args.root == Path("/archive/path")
            assert args.interval == 300  # Default
            assert args.batch_size == 5  # Default
            assert args.smil_only is False
            assert args.force is False
            assert args.one_shot is False
        print("✓ test_parse_args_minimal_required passed")

    def test_parse_args_with_all_options(self):
        """Test parsing with all optional arguments."""
        test_args = [
            "subtitle_autogen.py",
            "/archive/path",
            "--output-root",
            "/output/path",
            "--manifest",
            "/custom/manifest.jsonl",
            "--interval",
            "600",
            "--batch-size",
            "10",
            "--smil-only",
            "--force",
            "--one-shot",
            "--log-file",
            "/logs/service.log",
            "--verbose",
        ]
        with mock.patch("sys.argv", test_args):
            args = subtitle_autogen.parse_args()
            assert args.root == Path("/archive/path")
            assert args.output_root == Path("/output/path")
            assert args.manifest == Path("/custom/manifest.jsonl")
            assert args.interval == 600
            assert args.batch_size == 10
            assert args.smil_only is True
            assert args.force is True
            assert args.one_shot is True
            assert args.log_file == Path("/logs/service.log")
            assert args.verbose is True
        print("✓ test_parse_args_with_all_options passed")

    def test_parse_args_defaults(self):
        """Test default values for optional arguments."""
        with mock.patch("sys.argv", ["subtitle_autogen.py", "/test"]):
            args = subtitle_autogen.parse_args()
            assert args.output_root is None
            assert args.manifest == Path("logs/archive_transcriber_manifest.jsonl")
            assert args.interval == 300
            assert args.batch_size == 5
            assert args.log_file is None
            assert args.verbose is False
        print("✓ test_parse_args_defaults passed")


class TestTranscriberArgsBuilder:
    """Tests for building archive_transcriber arguments."""

    def test_build_transcriber_args_minimal(self):
        """Test building args with minimal configuration."""
        args = argparse.Namespace(
            root=Path("/archive"),
            output_root=None,
            manifest=Path("manifest.jsonl"),
            batch_size=5,
            smil_only=False,
            force=False,
        )
        result = subtitle_autogen.build_transcriber_args(args)
        assert "/archive" in result[0]
        assert "--manifest" in result
        assert "--max-files" in result
        assert "5" in result
        print("✓ test_build_transcriber_args_minimal passed")

    def test_build_transcriber_args_with_output_root(self):
        """Test building args with output root specified."""
        args = argparse.Namespace(
            root=Path("/archive"),
            output_root=Path("/output"),
            manifest=Path("manifest.jsonl"),
            batch_size=10,
            smil_only=False,
            force=False,
        )
        result = subtitle_autogen.build_transcriber_args(args)
        assert "--output-root" in result
        assert "/output" in result[result.index("--output-root") + 1]
        assert "--max-files" in result
        assert "10" in result
        print("✓ test_build_transcriber_args_with_output_root passed")

    def test_build_transcriber_args_smil_only(self):
        """Test building args with smil-only flag."""
        args = argparse.Namespace(
            root=Path("/archive"),
            output_root=None,
            manifest=Path("manifest.jsonl"),
            batch_size=5,
            smil_only=True,
            force=False,
        )
        result = subtitle_autogen.build_transcriber_args(args)
        assert "--smil-only" in result
        print("✓ test_build_transcriber_args_smil_only passed")

    def test_build_transcriber_args_force(self):
        """Test building args with force flag."""
        args = argparse.Namespace(
            root=Path("/archive"),
            output_root=None,
            manifest=Path("manifest.jsonl"),
            batch_size=5,
            smil_only=False,
            force=True,
        )
        result = subtitle_autogen.build_transcriber_args(args)
        assert "--force" in result
        print("✓ test_build_transcriber_args_force passed")


class TestRunCycle:
    """Tests for the run cycle functionality."""

    def test_run_cycle_success(self):
        """Test successful cycle run."""
        mock_transcriber = mock.MagicMock()
        mock_transcriber.run.return_value = 0

        with mock.patch("src.python.services.subtitle_autogen.archive_transcriber", mock_transcriber):
            result = subtitle_autogen.run_cycle(["--help"])
            assert result == 0
            mock_transcriber.run.assert_called_once()
        print("✓ test_run_cycle_success passed")

    def test_run_cycle_failure(self):
        """Test cycle run with failure."""
        mock_transcriber = mock.MagicMock()
        mock_transcriber.run.return_value = 1

        with mock.patch("src.python.services.subtitle_autogen.archive_transcriber", mock_transcriber):
            result = subtitle_autogen.run_cycle(["--help"])
            assert result == 1
            mock_transcriber.run.assert_called_once()
        print("✓ test_run_cycle_failure passed")


class TestLoggingConfiguration:
    """Tests for logging configuration."""

    def test_configure_logging_default_level(self):
        """Test logging configuration with default level."""
        args = argparse.Namespace(verbose=False, log_file=None)
        subtitle_autogen.configure_logging(args)
        # Just verify it doesn't crash
        print("✓ test_configure_logging_default_level passed")

    def test_configure_logging_verbose(self):
        """Test logging configuration with verbose mode."""
        args = argparse.Namespace(verbose=True, log_file=None)
        subtitle_autogen.configure_logging(args)
        # Just verify it doesn't crash
        print("✓ test_configure_logging_verbose passed")


def run_all_tests():
    """
    Execute the module's test suite across the predefined test classes and report results.

    Discovers and runs test methods whose names start with "test_" on each test class, prints per-test progress and failure tracebacks, and prints a summary of passed/failed counts.

    Returns:
        bool: `True` if all tests passed, `False` otherwise.
    """
    test_classes = [TestArgumentParsing, TestTranscriberArgsBuilder, TestRunCycle, TestLoggingConfiguration]

    passed = 0
    failed = 0

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        print("-" * 60)

        test_methods = [method for method in dir(test_class) if method.startswith("test_")]

        for method_name in test_methods:
            try:
                instance = test_class()
                method = getattr(instance, method_name)
                method()
                passed += 1
            except Exception as e:
                print(f"✗ {method_name} failed: {e}")
                import traceback

                traceback.print_exc()
                failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    import sys

    success = run_all_tests()
    sys.exit(0 if success else 1)
