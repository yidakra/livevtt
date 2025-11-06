#!/usr/bin/env python3
"""
Master test runner for LiveVTT test suite.

Runs all unit tests and reports overall coverage.
"""

import sys
import subprocess
from pathlib import Path


def run_test_file(test_file: Path) -> tuple[int, int]:
    """Run a single test file and return (passed, failed) counts."""
    print(f"\n{'=' * 70}")
    print(f"Running: {test_file.name}")
    print(f"{'=' * 70}")

    try:
        result = subprocess.run(
            [sys.executable, str(test_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Print output
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr, file=sys.stderr)

        # Parse results from output
        # Look for pattern like "Results: X passed, Y failed"
        lines = result.stdout.split("\n")
        for line in lines:
            if "passed" in line.lower() and "failed" in line.lower():
                # Extract numbers
                parts = line.split()
                passed = 0
                failed = 0
                for i, part in enumerate(parts):
                    if part.isdigit():
                        if i + 1 < len(parts):
                            if "passed" in parts[i + 1].lower():
                                passed = int(part)
                            elif "failed" in parts[i + 1].lower():
                                failed = int(part)
                return passed, failed

        # If we can't parse, check return code
        if result.returncode == 0:
            return (1, 0)  # Assume at least one test passed
        else:
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
    test_files = sorted([
        f for f in tests_dir.glob("test_*.py")
        if f.name != "run_all_tests.py"
    ])

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
        print(f"\nFiles with failures:")
        for fname in failed_files:
            print(f"  ✗ {fname}")
    else:
        print("\n🎉 ALL TESTS PASSED!")

    print("=" * 70)

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
