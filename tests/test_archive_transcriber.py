#!/usr/bin/env python3
"""Unit tests for archive_transcriber.py core functionality."""

import importlib
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional
from unittest import mock

# Mock faster_whisper before importing archive_transcriber
sys.modules["faster_whisper"] = mock.MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

archive_transcriber = importlib.import_module("archive_transcriber")


segments_to_webvtt: Callable[..., str] = archive_transcriber.segments_to_webvtt
extract_resolution: Callable[[str], Optional[int]] = (
    archive_transcriber.extract_resolution
)
normalise_variant_name: Callable[[Path], str] = (
    archive_transcriber.normalise_variant_name
)
select_best_variant: Callable[[list[Path]], Optional[Path]] = (
    archive_transcriber.select_best_variant
)
build_output_artifacts: Callable[
    [Path, str, Path, Optional[Path]], tuple[Path, Path, Path, Path]
] = archive_transcriber.build_output_artifacts
atomic_write: Callable[[Path, str], None] = archive_transcriber.atomic_write
translation_output_suspect: Callable[..., bool] = (
    archive_transcriber.translation_output_suspect
)

Manifest = archive_transcriber.Manifest  # type: ignore[assignment]
VideoJob = archive_transcriber.VideoJob  # type: ignore[assignment]
VideoMetadata = archive_transcriber.VideoMetadata  # type: ignore[assignment]


class MockSegment:
    """Mock Whisper segment for testing."""

    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


class TestSegmentsToWebVTT:
    """Tests for WebVTT generation from segments."""

    def test_empty_segments(self):
        """Test with empty segments list."""
        result = segments_to_webvtt([])
        # Should have WEBVTT header and at least one newline
        assert result.startswith("WEBVTT")
        assert result.endswith("\n")
        print("✓ test_empty_segments passed")

    def test_single_segment(self):
        """Test with a single segment."""
        segments = [MockSegment(5.0, 7.5, "Hello, world!")]
        result = segments_to_webvtt(segments)

        assert "WEBVTT" in result
        assert "00:00:05.000 --> 00:00:07.500" in result
        assert "Hello, world!" in result
        print("✓ test_single_segment passed")

    def test_multiple_segments(self):
        """Test with multiple segments."""
        segments = [
            MockSegment(0.0, 2.0, "First"),
            MockSegment(2.5, 5.0, "Second"),
            MockSegment(6.0, 8.5, "Third"),
        ]
        result = segments_to_webvtt(segments)

        assert "First" in result
        assert "Second" in result
        assert "Third" in result
        assert result.count("\n\n") >= 3  # At least 3 empty lines (header + segments)
        print("✓ test_multiple_segments passed")

    def test_empty_text_segments_skipped(self):
        """Test that segments with empty text are skipped."""
        segments = [
            MockSegment(0.0, 2.0, "Valid"),
            MockSegment(2.0, 4.0, "   "),  # Only whitespace
            MockSegment(4.0, 6.0, ""),  # Empty
            MockSegment(6.0, 8.0, "Also valid"),
        ]
        result = segments_to_webvtt(segments)

        assert "Valid" in result
        assert "Also valid" in result

        timestamp_lines = re.findall(
            r"^\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}$",
            result,
            flags=re.MULTILINE,
        )
        assert len(timestamp_lines) == 2
        print("✓ test_empty_text_segments_skipped passed")

    def test_timestamp_formatting(self):
        """Test correct timestamp formatting."""
        segments = [MockSegment(3661.123, 3665.456, "Test")]
        result = segments_to_webvtt(segments)

        # 3661.123 seconds = 01:01:01.123
        assert "01:01:01.123 --> 01:01:05.456" in result
        print("✓ test_timestamp_formatting passed")

    def test_no_header_option(self):
        """Test without WEBVTT header."""
        segments = [MockSegment(0.0, 2.0, "Test")]
        result = segments_to_webvtt(segments, prepend_header=False)

        assert not result.startswith("WEBVTT")
        assert "Test" in result
        print("✓ test_no_header_option passed")


class TestTranslationOutputSuspect:
    """Tests for translation output sanity checks."""

    def test_cyrillic_detected_for_english_label(self):
        # Arrange
        source_segments = [MockSegment(0.0, 1.0, "source")]
        translated_segments = [
            MockSegment(0.0, 1.0, "Привет"),
            MockSegment(1.0, 2.0, "Hello"),
        ]

        # Act
        result = translation_output_suspect(
            source_segments, translated_segments, "english"
        )

        # Assert
        assert result is True
        print("✓ test_cyrillic_detected_for_english_label passed")

    def test_cyrillic_detected_for_en_us(self):
        # Arrange
        source_segments = [MockSegment(0.0, 1.0, "source")]
        translated_segments = [
            MockSegment(0.0, 1.0, "Здравствуйте"),
            MockSegment(1.0, 2.0, "Good morning"),
        ]

        # Act
        result = translation_output_suspect(
            source_segments, translated_segments, "en-US"
        )

        # Assert
        assert result is True
        print("✓ test_cyrillic_detected_for_en_us passed")


class TestResolutionExtraction:
    """Tests for resolution extraction from filenames."""

    def test_extract_1080p(self):
        """Test extracting 1080p resolution."""
        assert extract_resolution("video_1080p.ts") == 1080
        assert extract_resolution("video.1080p.ts") == 1080
        assert extract_resolution("video-1080p.ts") == 1080
        print("✓ test_extract_1080p passed")

    def test_extract_720p(self):
        """Test extracting 720p resolution."""
        assert extract_resolution("video_720p.mp4") == 720
        print("✓ test_extract_720p passed")

    def test_extract_480p(self):
        """Test extracting 480p resolution."""
        assert extract_resolution("chunk_480p_final.ts") == 480
        print("✓ test_extract_480p passed")

    def test_no_resolution(self):
        """Test files without resolution tags."""
        assert extract_resolution("video.ts") is None
        assert extract_resolution("video_hd.mp4") is None
        assert extract_resolution("chunk.mkv") is None
        print("✓ test_no_resolution passed")

    def test_edge_cases(self):
        """Test edge cases for resolution extraction."""
        # The regex requires 3-4 digits, so 180p should work if it has delimiter
        assert extract_resolution("video_180p.ts") == 180  # 3 digits with delimiter
        assert extract_resolution("video_2160p.ts") == 2160  # 4K
        assert extract_resolution("video_1080px.ts") is None  # Extra char
        print("✓ test_edge_cases passed")


class TestVariantNameNormalization:
    """Tests for variant name normalization."""

    def test_remove_resolution(self):
        """Test removing resolution tokens."""
        path = Path("video_1080p.ts")
        assert normalise_variant_name(path) == "video.ts"
        print("✓ test_remove_resolution passed")

    def test_multiple_resolutions(self):
        """Test with multiple resolution-like patterns."""
        path = Path("video_720p_1080p.ts")
        # Should remove both
        normalized = normalise_variant_name(path)
        assert "720p" not in normalized
        assert "1080p" not in normalized
        print("✓ test_multiple_resolutions passed")

    def test_preserve_extension(self):
        """Test that file extension is preserved."""
        path = Path("chunk_1080p.mp4")
        assert normalise_variant_name(path).endswith(".mp4")
        print("✓ test_preserve_extension passed")

    def test_no_change_needed(self):
        """Test files that don't need normalization."""
        path = Path("video.ts")
        assert normalise_variant_name(path) == "video.ts"
        print("✓ test_no_change_needed passed")


class TestVariantSelection:
    """Tests for selecting best video variant."""

    def test_select_highest_resolution(self):
        """Test selecting highest resolution variant."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create test files with different resolutions
            (tmpdir_path / "video_480p.ts").write_text("small")
            (tmpdir_path / "video_720p.ts").write_text("medium content")
            (tmpdir_path / "video_1080p.ts").write_text("large")

            candidates = [
                tmpdir_path / "video_480p.ts",
                tmpdir_path / "video_720p.ts",
                tmpdir_path / "video_1080p.ts",
            ]

            best = select_best_variant(candidates)
            assert best is not None
            assert best.name == "video_1080p.ts"
            print("✓ test_select_highest_resolution passed")

    def test_select_by_size_when_same_resolution(self):
        """Test selecting larger file when resolution is same."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            (tmpdir_path / "video_1080p_v1.ts").write_text("x" * 100)
            (tmpdir_path / "video_1080p_v2.ts").write_text("x" * 200)

            candidates = [
                tmpdir_path / "video_1080p_v1.ts",
                tmpdir_path / "video_1080p_v2.ts",
            ]

            best = select_best_variant(candidates)
            assert best is not None
            assert best.name == "video_1080p_v2.ts"
            print("✓ test_select_by_size_when_same_resolution passed")

    def test_empty_candidates(self):
        """Test with empty candidates list."""
        assert select_best_variant([]) is None
        print("✓ test_empty_candidates passed")

    def test_no_resolution_info(self):
        """Test files without resolution info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            (tmpdir_path / "video1.ts").write_text("x" * 50)
            (tmpdir_path / "video2.ts").write_text("x" * 150)

            candidates = [
                tmpdir_path / "video1.ts",
                tmpdir_path / "video2.ts",
            ]

            # Should select by size
            best = select_best_variant(candidates)
            assert best is not None
            assert best.name == "video2.ts"
            print("✓ test_no_resolution_info passed")


class TestBuildOutputArtifacts:
    """Tests for building output artifact paths."""

    def test_basic_output_paths(self):
        """Test basic output path generation."""
        video_path = Path("/archive/2024/01/video_1080p.ts")
        input_root = Path("/archive")

        ru_vtt, en_vtt, ttml, smil = build_output_artifacts(
            video_path, "video.ts", input_root, None
        )

        assert ru_vtt.name == "video.ru.vtt"
        assert en_vtt.name == "video.en.vtt"
        assert ttml.name == "video.ttml"
        assert smil.name == "video.smil"
        assert ru_vtt.parent == video_path.parent
        print("✓ test_basic_output_paths passed")

    def test_with_output_root(self):
        """Test output paths with custom output root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_root = Path(tmpdir) / "input"
            output_root = Path(tmpdir) / "output"
            input_root.mkdir()

            video_path = input_root / "subdir" / "video.ts"
            video_path.parent.mkdir()
            video_path.write_text("test")

            ru_vtt, _en_vtt, _ttml, _smil = build_output_artifacts(
                video_path, "video.ts", input_root, output_root
            )

            # Should mirror directory structure
            assert output_root in ru_vtt.parents
            assert "subdir" in str(ru_vtt)
            print("✓ test_with_output_root passed")


class TestAtomicWrite:
    """Tests for atomic file writing."""

    def test_atomic_write_creates_file(self):
        """Test that atomic_write creates the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            target = tmpdir_path / "test.txt"
            content = "Test content\nLine 2"

            atomic_write(target, content)

            assert target.exists()
            assert target.read_text() == content
            print("✓ test_atomic_write_creates_file passed")

    def test_atomic_write_overwrites(self):
        """Test that atomic_write can overwrite existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            target = tmpdir_path / "test.txt"
            target.write_text("Old content")

            new_content = "New content"
            atomic_write(target, new_content)

            assert target.read_text() == new_content
            print("✓ test_atomic_write_overwrites passed")

    def test_atomic_write_utf8(self):
        """Test atomic_write with UTF-8 content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            target = tmpdir_path / "test.txt"
            content = "Привет, мир! 你好世界"

            atomic_write(target, content)

            assert target.read_text(encoding="utf-8") == content
            print("✓ test_atomic_write_utf8 passed")


class TestManifest:
    """Tests for Manifest class."""

    def test_manifest_creation(self):
        """Test creating a new manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "logs" / "manifest.jsonl"
            manifest = Manifest(manifest_path)

            assert manifest.path == manifest_path
            assert len(manifest.records) == 0
            print("✓ test_manifest_creation passed")

    def test_manifest_append(self):
        """Test appending records to manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.jsonl"
            manifest = Manifest(manifest_path)

            record = {
                "video_path": "/test/video.ts",
                "status": "success",
                "ru_vtt": "/test/video.ru.vtt",
            }

            manifest.append(record)

            assert manifest.get(Path("/test/video.ts")) == record
            assert manifest_path.exists()
            print("✓ test_manifest_append passed")

    def test_manifest_persistence(self):
        """Test that manifest persists across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.jsonl"

            # First instance
            manifest1 = Manifest(manifest_path)
            record1 = {"video_path": "/test/video1.ts", "status": "success"}
            manifest1.append(record1)

            # Second instance should load existing data
            manifest2 = Manifest(manifest_path)
            assert manifest2.get(Path("/test/video1.ts")) == record1

            # Add more data
            record2 = {"video_path": "/test/video2.ts", "status": "success"}
            manifest2.append(record2)

            # Third instance should have both
            manifest3 = Manifest(manifest_path)
            assert len(manifest3.records) == 2
            print("✓ test_manifest_persistence passed")

    def test_manifest_get_nonexistent(self):
        """Test getting a non-existent record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.jsonl"
            manifest = Manifest(manifest_path)

            assert manifest.get(Path("/nonexistent/video.ts")) is None
            print("✓ test_manifest_get_nonexistent passed")


class TestVideoMetadata:
    """Tests for VideoMetadata dataclass."""

    def test_video_metadata_creation(self):
        """Test creating VideoMetadata instance."""
        metadata = VideoMetadata(
            duration=120.5,
            width=1920,
            height=1080,
            video_codec_id="h264",
            audio_codec_id="aac",
            bitrate=5000000,
        )

        assert metadata.duration == 120.5
        assert metadata.width == 1920
        assert metadata.height == 1080
        print("✓ test_video_metadata_creation passed")

    def test_video_metadata_none_values(self):
        """Test VideoMetadata with None values."""
        metadata = VideoMetadata(
            duration=None,
            width=None,
            height=None,
            video_codec_id=None,
            audio_codec_id=None,
            bitrate=None,
        )

        assert metadata.duration is None
        assert metadata.bitrate is None
        print("✓ test_video_metadata_none_values passed")


class TestVideoJob:
    """Tests for VideoJob dataclass."""

    def test_video_job_creation(self):
        """Test creating VideoJob instance."""
        job = VideoJob(
            video_path=Path("/test/video.ts"),
            normalized_name="video.ts",
            ru_vtt=Path("/test/video.ru.vtt"),
            en_vtt=Path("/test/video.en.vtt"),
            ttml=Path("/test/video.ttml"),
            smil=Path("/test/video.smil"),
        )

        assert job.video_path == Path("/test/video.ts")
        assert job.normalized_name == "video.ts"
        assert job.ttml.name == "video.ttml"
        print("✓ test_video_job_creation passed")
