#!/usr/bin/env python3
"""Unit tests for archive_transcriber.py core functionality."""

import importlib
import os
import re
import sys
import tempfile
import threading
import time
import typing as _typing
from pathlib import Path
from typing import Callable, Optional
from unittest import mock

import pytest

# Mock faster_whisper before importing archive_transcriber
sys.modules["faster_whisper"] = mock.MagicMock()
# On 3.11+, typing.Required exists; alias typing_extensions to typing to avoid
# requiring the package in test-only environments. On 3.10, rely on the real
# typing_extensions package that comes from transitive dependencies.
if sys.version_info >= (3, 11):
    sys.modules.setdefault("typing_extensions", _typing)  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

archive_transcriber = importlib.import_module("archive_transcriber")


segments_to_webvtt: Callable[..., str] = archive_transcriber.segments_to_webvtt
extract_resolution: Callable[[str], Optional[int]] = archive_transcriber.extract_resolution
normalise_variant_name: Callable[[Path], str] = archive_transcriber.normalise_variant_name
select_best_variant: Callable[[list[Path]], Optional[Path]] = archive_transcriber.select_best_variant
build_output_artifacts: Callable[[Path, str, Path, Optional[Path]], tuple[Path, Path, Path, Path]] = (
    archive_transcriber.build_output_artifacts
)
atomic_write: Callable[[Path, str], None] = archive_transcriber.atomic_write
translation_output_suspect: Callable[..., bool] = archive_transcriber.translation_output_suspect

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
        result = translation_output_suspect(source_segments, translated_segments, "english")

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
        result = translation_output_suspect(source_segments, translated_segments, "en-US")

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

        ru_vtt, en_vtt, ttml, smil = build_output_artifacts(video_path, "video.ts", input_root, None)

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

            ru_vtt, _en_vtt, _ttml, _smil = build_output_artifacts(video_path, "video.ts", input_root, output_root)

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


class TestExtractAudio:
    """Tests for audio extraction ffmpeg command construction."""

    def _run_extract_audio(self, video_path: Path, sample_rate: int) -> list:
        """Run extract_audio with mocked subprocess and return the captured command."""
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            result = mock.MagicMock()
            result.returncode = 0
            return result

        with mock.patch("archive_transcriber.subprocess.run", side_effect=fake_run):
            with mock.patch("archive_transcriber.tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp.return_value.__enter__ = mock.MagicMock()
                mock_tmp.return_value.name = "/tmp/fake.wav"
                archive_transcriber.extract_audio(video_path, sample_rate)

        return captured[0] if captured else []

    def test_uses_pan_filter_not_ac_flag(self):
        """extract_audio must use pan=mono|c0=c0 to select channel 0, not -ac 1."""
        cmd = self._run_extract_audio(Path("/test/video.mp4"), 16000)

        assert "-ac" not in cmd, "Should not use -ac flag (mixes channels)"
        assert "pan=mono|c0=c0" in " ".join(cmd), "Should use pan filter to select channel 0"
        print("✓ test_uses_pan_filter_not_ac_flag passed")

    def test_pan_filter_position_in_command(self):
        """The pan filter should be passed via -af flag."""
        cmd = self._run_extract_audio(Path("/test/video.mp4"), 16000)

        assert "-af" in cmd
        af_index = cmd.index("-af")
        assert cmd[af_index + 1] == "pan=mono|c0=c0"
        print("✓ test_pan_filter_position_in_command passed")

    def test_sample_rate_preserved(self):
        """Sample rate argument should still be passed correctly."""
        cmd = self._run_extract_audio(Path("/test/video.mp4"), 22050)

        assert "-ar" in cmd
        ar_index = cmd.index("-ar")
        assert cmd[ar_index + 1] == "22050"
        print("✓ test_sample_rate_preserved passed")


class TestPhaseNeeds:
    """phase_needs must match needs_transcription/needs_translation exactly."""

    def _job(self, tmp: Path):
        return VideoJob(
            video_path=tmp / "video_1080p.mp4",
            normalized_name="video.mp4",
            ru_vtt=tmp / "video.ru.vtt",
            en_vtt=tmp / "video.en.vtt",
            ttml=tmp / "video.ttml",
            smil=tmp / "video.smil",
        )

    def test_matches_separate_checks_across_all_states(self):
        import itertools
        import os

        phase_needs = archive_transcriber.phase_needs
        needs_transcription = archive_transcriber.needs_transcription
        needs_translation = archive_transcriber.needs_translation

        # Every combination of artifact presence, with fresh and stale mtimes
        names = ["video_1080p.mp4", "video.ru.vtt", "video.en.vtt", "video.ttml", "video.smil"]
        for present in itertools.product([False, True], repeat=len(names)):
            for stale_ru in (False, True):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp = Path(tmpdir)
                    for name, exists in zip(names, present):
                        if exists:
                            (tmp / name).write_text("x")
                            os.utime(tmp / name, (2000000, 2000000))
                    ru = tmp / "video.ru.vtt"
                    if stale_ru and ru.exists():
                        os.utime(ru, (1000000, 1000000))  # older than everything
                    job = self._job(tmp)
                    for ttml_enabled in (False, True):
                        expected = (needs_transcription(job), needs_translation(job, ttml_enabled))
                        assert phase_needs(job, ttml_enabled) == expected, (
                            f"mismatch for present={present} stale_ru={stale_ru} ttml={ttml_enabled}"
                        )


def _make_job(tmp: Path, stem: str = "video"):
    return VideoJob(
        video_path=tmp / f"{stem}_1080p.mp4",
        normalized_name=f"{stem}.mp4",
        ru_vtt=tmp / f"{stem}.ru.vtt",
        en_vtt=tmp / f"{stem}.en.vtt",
        ttml=tmp / f"{stem}.ttml",
        smil=tmp / f"{stem}.smil",
    )


class TestKnownPermanentFailure:
    """Videos with recorded permanent errors must not be retried while unchanged."""

    def _manifest(self, tmp: Path):
        return Manifest(tmp / "manifest.jsonl")

    def _error_record(self, job, video_mtime, error_type="audio_extraction", status="error"):
        return {
            "video_path": str(job.video_path),
            "status": status,
            "phase": "transcription",
            "error": "FFmpeg failed: return code 234",
            "error_type": error_type,
            "video_mtime": video_mtime,
            "processed_at": "2026-08-01 00:00:00",
        }

    def test_skips_unchanged_video_with_extraction_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job = _make_job(tmp)
            job.video_path.write_bytes(b"corrupt")
            manifest = self._manifest(tmp)
            manifest.append(self._error_record(job, job.video_path.stat().st_mtime))

            assert archive_transcriber.known_permanent_failure(job, manifest) is True

    def test_retries_when_video_changed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job = _make_job(tmp)
            job.video_path.write_bytes(b"corrupt")
            manifest = self._manifest(tmp)
            manifest.append(self._error_record(job, job.video_path.stat().st_mtime - 100.0))

            assert archive_transcriber.known_permanent_failure(job, manifest) is False

    def test_retries_transient_error_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job = _make_job(tmp)
            job.video_path.write_bytes(b"ok")
            manifest = self._manifest(tmp)
            manifest.append(self._error_record(job, job.video_path.stat().st_mtime, error_type="processing"))

            assert archive_transcriber.known_permanent_failure(job, manifest) is False

    def test_retries_without_record_or_mtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job = _make_job(tmp)
            job.video_path.write_bytes(b"ok")
            manifest = self._manifest(tmp)
            assert archive_transcriber.known_permanent_failure(job, manifest) is False

            manifest.append(self._error_record(job, None))
            assert archive_transcriber.known_permanent_failure(job, manifest) is False

    def test_success_record_never_blocks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job = _make_job(tmp)
            job.video_path.write_bytes(b"ok")
            manifest = self._manifest(tmp)
            manifest.append(
                self._error_record(job, job.video_path.stat().st_mtime, status="success"),
            )
            assert archive_transcriber.known_permanent_failure(job, manifest) is False


class TestSortJobsBySize:
    """Phase queues run smallest video first; unreadable paths sort first and fail fast."""

    def test_orders_smallest_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jobs = []
            for stem, size in (("big", 3000), ("small", 10), ("mid", 500)):
                job = _make_job(tmp, stem)
                job.video_path.write_bytes(b"x" * size)
                jobs.append(job)

            ordered = archive_transcriber.sort_jobs_by_size(jobs)
            assert [j.normalized_name for j in ordered] == ["small.mp4", "mid.mp4", "big.mp4"]

    def test_missing_file_sorts_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            present = _make_job(tmp, "present")
            present.video_path.write_bytes(b"x" * 100)
            missing = _make_job(tmp, "missing")

            ordered = archive_transcriber.sort_jobs_by_size([present, missing])
            assert ordered[0] is missing

    def test_empty_list(self):
        assert archive_transcriber.sort_jobs_by_size([]) == []


class TestAudioMinutesBudget:
    """Admission is bounded by audio-minutes in flight, not by video count."""

    def test_videos_fitting_the_budget_run_concurrently(self):
        budget = archive_transcriber.AudioMinutesBudget(200.0)
        charged = [budget.acquire(50.0) for _ in range(4)]
        # Four 50-minute videos fit; none of the acquires blocked.
        assert charged == [50.0, 50.0, 50.0, 50.0]

    def test_acquire_blocks_once_the_budget_is_spent(self):
        budget = archive_transcriber.AudioMinutesBudget(100.0)
        budget.acquire(80.0)
        admitted = threading.Event()

        def _second() -> None:
            budget.acquire(40.0)
            admitted.set()

        t = threading.Thread(target=_second, daemon=True)
        t.start()
        # 80 + 40 > 100, so the second video waits rather than overcommitting.
        assert admitted.wait(timeout=0.2) is False
        budget.release(80.0)
        assert admitted.wait(timeout=2.0) is True
        t.join(timeout=2.0)

    def test_video_longer_than_budget_is_capped_and_runs_alone(self):
        budget = archive_transcriber.AudioMinutesBudget(200.0)
        # A 6.5-hour video must not deadlock waiting for budget it can never get.
        charged = budget.acquire(389.0)
        assert charged == 200.0

        admitted = threading.Event()

        def _other() -> None:
            budget.acquire(1.0)
            admitted.set()

        t = threading.Thread(target=_other, daemon=True)
        t.start()
        # ...but while it holds the whole budget, nothing else decodes.
        assert admitted.wait(timeout=0.2) is False
        budget.release(charged)
        assert admitted.wait(timeout=2.0) is True
        t.join(timeout=2.0)

    def test_unknown_duration_is_charged_nothing(self):
        budget = archive_transcriber.AudioMinutesBudget(200.0)
        assert budget.acquire(None) == 0.0
        assert budget.acquire(0.0) == 0.0

    def test_admission_is_fifo_so_long_videos_cannot_starve(self):
        budget = archive_transcriber.AudioMinutesBudget(100.0)
        budget.acquire(60.0)

        order: list[str] = []
        big_waiting = threading.Event()
        big_done = threading.Event()
        small_done = threading.Event()

        def _big() -> None:
            big_waiting.set()
            budget.acquire(100.0)
            order.append("big")
            big_done.set()

        def _small() -> None:
            budget.acquire(10.0)
            order.append("small")
            small_done.set()

        big = threading.Thread(target=_big, daemon=True)
        big.start()
        big_waiting.wait(timeout=1.0)
        time.sleep(0.05)  # let the big video take its ticket first

        small = threading.Thread(target=_small, daemon=True)
        small.start()
        # 10 minutes would fit in the 40 still free, but the big video queued
        # first; letting the small one skip ahead is how long videos starve.
        assert small_done.wait(timeout=0.2) is False

        budget.release(60.0)
        assert big_done.wait(timeout=2.0) is True
        budget.release(100.0)
        assert small_done.wait(timeout=2.0) is True
        big.join(timeout=2.0)
        small.join(timeout=2.0)
        assert order == ["big", "small"]

    def test_unbalanced_release_fails_loudly(self):
        # An over-release must raise rather than silently widening the budget.
        budget = archive_transcriber.AudioMinutesBudget(200.0)
        with pytest.raises(ValueError):
            budget.release(1.0)

    def test_failed_release_leaves_the_budget_intact(self):
        budget = archive_transcriber.AudioMinutesBudget(200.0)
        with pytest.raises(ValueError):
            budget.release(1.0)
        # The rejected refund must not have been applied.
        assert budget.acquire(200.0) == 200.0

    def test_rejects_non_positive_budget(self):
        with pytest.raises(ValueError):
            archive_transcriber.AudioMinutesBudget(0)


class TestTwoPhaseQueueing:
    """Phase 2 must pick up newly transcribed videos exactly once, without re-statting everything."""

    def _args(self, tmp: Path):
        import argparse

        return argparse.Namespace(
            max_files=None,
            force_scan=True,
            no_ttml=True,
            workers=1,
            progress=False,
            verbose=False,
            transcribe_minutes_budget=1000.0,
        )

    def _make_video(self, tmp: Path, stem: str, *, ru=False, en=False, smil=False, stale_ru=False):
        video = tmp / f"{stem}_1080p.mp4"
        video.write_bytes(b"x" * 1000)
        stamp = 2000000 if stale_ru else 1000000
        os.utime(video, (stamp, stamp))
        for flag, suffix in ((ru, "ru.vtt"), (en, "en.vtt"), (smil, "smil")):
            if flag:
                artifact = tmp / f"{stem}.{suffix}"
                artifact.write_text("x")
                # stale_ru: artifacts predate the video, so it needs both phases
                os.utime(artifact, (1000000, 1000000))
        return video

    def test_newly_transcribed_video_translated_once(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            archive = tmp / "archive"
            archive.mkdir()

            # A: nothing yet -> transcribe, then translate
            self._make_video(archive, "a")
            # B: fully done -> neither phase
            self._make_video(archive, "b", ru=True, en=True, smil=True)
            # C: transcript only -> translate only
            self._make_video(archive, "c", ru=True, smil=True)
            # D: stale transcript, no en.vtt -> needs BOTH phases. It is already
            # in the Phase 2 queue before Phase 1 runs, so the post-Phase-1
            # re-filter must not queue it a second time.
            self._make_video(archive, "d", ru=True, smil=True, stale_ru=True)

            transcribed: list[str] = []
            translated: list[str] = []

            def fake_transcribe(job, args, quiet=False):
                transcribed.append(job.normalized_name)
                job.ru_vtt.write_text("WEBVTT\n")  # now eligible for translation
                return {
                    "video_path": str(job.video_path),
                    "status": "success",
                    "phase": "transcription",
                    "processed_at": "2026-08-01 00:00:00",
                }

            def fake_translate(job, args, manifest, quiet=False):
                translated.append(job.normalized_name)
                return {
                    "video_path": str(job.video_path),
                    "status": "success",
                    "phase": "translation",
                    "processed_at": "2026-08-01 00:00:00",
                }

            monkeypatch.setattr(archive_transcriber, "process_transcription_only", fake_transcribe)
            monkeypatch.setattr(archive_transcriber, "process_translation_only", fake_translate)

            manifest = Manifest(tmp / "manifest.jsonl")
            rc = archive_transcriber.run_two_phase(
                self._args(tmp),
                archive,
                None,
                manifest,
                [".mp4"],
                tmp / "scan_cache.json",
            )

            assert rc == 0
            assert sorted(transcribed) == ["a.mp4", "d.mp4"]
            # c and d were queued up front, a became eligible after Phase 1 —
            # each exactly once, and d is not duplicated by the re-filter
            assert sorted(translated) == ["a.mp4", "c.mp4", "d.mp4"]
            assert len(translated) == 3


class TestTranscriptionErrorRecord:
    """Extraction failures must be recorded as permanent with the video mtime."""

    def _args(self):
        import argparse

        return argparse.Namespace(
            sample_rate=16000,
            model="large-v3",
            beam_size=5,
            source_language="ru",
            vad_filter=True,
            trim_silence=False,
            verbose=False,
            transcribe_minutes_budget=1000.0,
        )

    def test_ffmpeg_failure_marked_permanent(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job = _make_job(tmp)
            job.video_path.write_bytes(b"corrupt")
            # Valid transcoder SMIL so the precheck passes
            job.smil.write_text(
                "<?xml version='1.0'?><smil><head/><body><switch>"
                "<video src='mp4:video_1080p.mp4'/><video src='mp4:video_720p.mp4'/>"
                "</switch></body></smil>"
            )

            def boom(video_path, sample_rate):
                raise RuntimeError(f"FFmpeg failed for {video_path}: return code 234")

            monkeypatch.setattr(archive_transcriber, "extract_audio", boom)
            record = archive_transcriber.process_transcription_only(job, self._args(), quiet=True)

            assert record["status"] == "error"
            assert record["error_type"] == "audio_extraction"
            assert record["video_mtime"] == job.video_path.stat().st_mtime

    def test_other_failure_not_marked_permanent(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            job = _make_job(tmp)
            job.video_path.write_bytes(b"ok")
            job.smil.write_text(
                "<?xml version='1.0'?><smil><head/><body><switch>"
                "<video src='mp4:video_1080p.mp4'/><video src='mp4:video_720p.mp4'/>"
                "</switch></body></smil>"
            )

            def boom(video_path, sample_rate):
                raise ValueError("CUDA hiccup")

            monkeypatch.setattr(archive_transcriber, "extract_audio", boom)
            record = archive_transcriber.process_transcription_only(job, self._args(), quiet=True)

            assert record["status"] == "error"
            assert record["error_type"] == "processing"
