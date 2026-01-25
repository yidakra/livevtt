# LiveVTT Test Suite

Comprehensive unit tests for the LiveVTT subtitle generation system.

## Test Coverage

### Core Functionality Tests

#### `test_archive_transcriber.py` (31 tests)
Tests for archive transcription core utilities:
- **WebVTT Generation**: Converting Whisper segments to WebVTT format
- **Resolution Extraction**: Parsing resolution from filenames (480p, 720p, 1080p, etc.)
- **Variant Selection**: Choosing best quality video variant
- **File Path Management**: Building output artifact paths
- **Atomic Writes**: Thread-safe file writing
- **Manifest Management**: JSONL manifest tracking
- **Data Classes**: VideoJob and VideoMetadata structures

**Run**: `pytest tests/test_archive_transcriber.py -v`

#### `test_ttml_simple.py` (5 tests)
Standalone tests for TTML utilities (no external dependencies):
- Timestamp formatting and parsing
- VTT file parsing
- Bilingual cue alignment
- TTML generation from VTT files

**Run**: `python tests/test_ttml_simple.py`

#### `test_ttml_utils.py` (11 test classes)
Comprehensive pytest-based tests for TTML functionality:
- Timestamp conversion (VTT ↔ TTML)
- VTT parsing with multiline text
- Bilingual alignment with tolerance
- TTML document creation
- Segment-to-TTML conversion
- Full integration tests

**Requires**: pytest
**Run**: `pytest tests/test_ttml_utils.py -v` (when pytest is installed)

#### `test_smil_generation.py` (7 tests)
Tests for SMIL manifest generation:
- Basic SMIL structure creation
- Video element with metadata
- Textstream elements for subtitles
- Update logic (no duplication)
- Missing VTT file handling
- Codec parameter inclusion

**Run**: `python tests/test_smil_generation.py`

#### `test_vtt_to_ttml_cli.py` (14 tests)
Tests for the standalone VTT-to-TTML converter CLI:
- VTT file validation
- Conversion success/failure cases
- Output directory creation
- Custom tolerance handling
- Argument parsing
- Language code customization

**Run**: `python tests/test_vtt_to_ttml_cli.py`

## Running Tests

### Run All Tests
```bash
# With pytest
poetry run pytest tests/ -v

# With coverage report
poetry run pytest tests/ -v --cov=src/python --cov-report=term-missing
```

### Run Individual Test Files
```bash
# Unit tests
pytest tests/test_archive_transcriber.py -v
pytest tests/test_ttml_utils.py -v
pytest tests/test_smil_generation.py -v

# CLI tool tests
pytest tests/test_vtt_to_ttml_cli.py -v

# Service tests
pytest tests/test_subtitle_autogen.py -v
```

#### `test_subtitle_autogen.py` (11 tests)
Tests for the subtitle_autogen background service:
- Argument parsing with all options
- Default value validation
- Transcriber arguments builder
- Run cycle success and failure handling
- Logging configuration

**Run**: `pytest tests/test_subtitle_autogen.py -v`

## Test Results Summary

As of last run:
- **Total tests**: 116
- **Passing**: 116
- **Failing**: 0
- **Coverage**: 65% overall
  - archive_transcriber.py: 46%
  - ttml_utils.py: 92%
  - vtt_to_ttml.py: 68%
  - subtitle_autogen.py: 71%

## Test Structure

Tests are organized by functionality:
- **Unit tests**: Test individual functions in isolation
- **Integration tests**: Test complete workflows (VTT → TTML conversion)
- **CLI tests**: Test command-line interface and argument parsing
- **Data validation tests**: Test error handling and edge cases

## Mocking Strategy

Tests mock external dependencies to avoid requiring:
- `faster-whisper` (Whisper model)
- `ttml_utils` (when testing archive_transcriber)
- Video files and FFmpeg (use temp files)

## Adding New Tests

When adding new functionality:

1. **Create test file**: `tests/test_new_feature.py`
2. **Follow naming convention**:
   - Test file: `test_*.py`
   - Test class: `Test*`
   - Test method: `test_*`
3. **Use standard assertions**: `assert`, not `self.assertEqual()`
4. **Mock dependencies**: Mock external libraries at module level
5. **Clean up**: Use `tempfile` for temporary files
6. **Document**: Add docstrings explaining what each test validates

### Example Test Template

```python
#!/usr/bin/env python3
"""Tests for new_feature.py"""

import sys
from pathlib import Path
from unittest import mock

# Mock dependencies
sys.modules['external_dep'] = mock.MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

from new_feature import some_function


class TestNewFeature:
    """Tests for new feature functionality."""

    def test_basic_case(self):
        """Test basic functionality."""
        result = some_function("input")
        assert result == "expected"
        print("✓ test_basic_case passed")

```python
def test_new_feature_basic_case():
    """Test basic functionality."""
    result = some_function("input")
    assert result == "expected"
```

## Continuous Testing

Recommended workflow:
1. Run tests before committing: `poetry run pytest`
2. Add tests for new features
3. Update tests when changing functionality
4. Keep test coverage above 80%

## Dependencies

### Required (always available)
- Python 3.10+
- Standard library modules

### Optional (for full test suite)
- `pytest` - Test runner
- `pytest-cov` - For coverage reporting
- `pytest-asyncio` - For async tests (future)

Install with Poetry:
```bash
poetry install --with dev
```

Or with pip:
```bash
pip install pytest pytest-cov
```

## Test Data

Example test data is in:
- `examples/sample.ru.vtt` - Russian WebVTT
- `examples/sample.en.vtt` - English WebVTT
- `examples/sample.ttml` - Bilingual TTML

Tests create temporary files in system temp directory and clean up automatically.

## Troubleshooting

### Tests fail with import errors
- Ensure you're running from repo root
- Check that `sys.path` modifications are correct
- Verify mocks are set up before imports

### Tests fail with file permission errors
- Check that temp directory is writable
- On Linux: ensure `/tmp` has proper permissions

### Tests timeout
- Increase timeout in `run_all_tests.py`
- Check for infinite loops in test logic

## Future Improvements

- [ ] Add coverage reporting with pytest-cov
- [ ] Add performance benchmarks
- [ ] Add end-to-end tests with real video files
- [ ] Add async tests for main.py live service
- [ ] Add CI/CD integration (GitHub Actions)
- [ ] Add test fixtures for common data
