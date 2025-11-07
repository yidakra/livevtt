#!/usr/bin/env python3
"""
Master test runner for LiveVTT test suite.

Runs all unit tests and reports overall results.
"""

import re
import sys
import subprocess
from pathlib import Path


RESULT_PATTERN = re.compile(
    r"""(?ix)
    (?:
        (?P<count>\d+)\s*[,;:]?\s*(?P<label>passed|failed)s? |
        (?P<label_alt>passed|failed)s?\s*[,;:]?\s*(?P<count_alt>\d+)
    )
    """
)


def run_test_file(test_file: Path) -> tuple[int, int]:
    """Run a single test file and return (passed, failed) counts."""
    print("\n" + "=" * 70)
    print(f"Running: {test_file.name}")
    print("=" * 70)

    if test_file.name == "test_archive_transcriber.py":
        command = ["pytest", "tests/test_archive_transcriber.py", "-v"]
    else:
        command = [sys.executable, str(test_file)]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Print output
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr, file=sys.stderr)

        # Parse results from output
        passed = None
        failed = None
        for line in result.stdout.splitlines():
            matches = RESULT_PATTERN.finditer(line)
            for match in matches:
                label = (match.group("label") or match.group("label_alt") or "").lower()
                raw_count = match.group("count") or match.group("count_alt")
                if not raw_count:
                    continue
                count = int(raw_count)
                if label.startswith("pass"):
                    passed = count
                elif label.startswith("fail"):
                    failed = count
            if passed is not None and failed is not None:
                return passed, failed
        if passed is not None or failed is not None:
            return (passed or 0, failed or 0)

        # If we can't parse, check return code
        if result.returncode == 0:
            print(f"WARNING: Could not parse test results from {test_file.name}, assuming success based on exit code")
            return (1, 0)  # Assume at least one test passed
        else:
            print(f"WARNING: Could not parse test results from {test_file.name}, assuming failure based on exit code")
            return (0, 1)  # Assume failure

    except subprocess.TimeoutExpired:
        print(f"ERROR: {test_file.name} timed out!")
        return (0, 1)
    except Exception as e:
        print(f"ERROR running {test_file.name}: {e}")
        return (0, 1)


def main():
    """Run all tests and report results."""
    print("=" * 70)
    print("LiveVTT Test Suite")
    print("=" * 70)

    tests_dir = Path(__file__).parent

    # Find all test files
    test_files = sorted(tests_dir.glob("test_*.py"))

    if not test_files:
        print("No test files found!")
        return 1

    print(f"\nFound {len(test_files)} test file(s):")
    for test_file in test_files:
        print(f"  • {test_file.name}")

    # Run all tests
    total_passed = 0
    total_failed = 0
    failed_files = []

    for test_file in test_files:
        passed, failed = run_test_file(test_file)
        total_passed += passed
        total_failed += failed

        if failed > 0:
            failed_files.append(test_file.name)

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL TEST RESULTS")
    print("=" * 70)
    print(f"Total tests passed: {total_passed}")
    print(f"Total tests failed: {total_failed}")
    print(f"Test files run: {len(test_files)}")

    if failed_files:
        print("\nFiles with failures:")
        for fname in failed_files:
            print(f"  ✗ {fname}")
    else:
        print("\n🎉 ALL TESTS PASSED!")

    print("=" * 70)

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
