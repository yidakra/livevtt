#!/usr/bin/env python3
"""Unit tests for SMIL manifest subtitle association.

write_smil is strictly additive: it only adds <textstream> entries to an
existing, valid, transcoder-generated SMIL. It must never create a SMIL from
scratch and never touch <video> nodes (incident of 2026-07-13: transcriber-
created single-variant SMILs broke adaptive playback in production).
"""

from __future__ import annotations

import argparse
import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import pytest
from pytest import LogCaptureFixture

# Mock dependencies
sys.modules["faster_whisper"] = mock.MagicMock()

from src.python.tools.archive_transcriber import (  # noqa: E402
    VideoJob,
    VideoMetadata,
    skip_record_for_invalid_smil,
    smil_precheck,
    write_smil,
)

# A realistic transcoder-generated multi-bitrate SMIL (5 renditions)
TRANSCODER_SMIL = """<?xml version="1.0" encoding="UTF-8"?>
<smil>
 <head/>
 <body>
  <switch>
   <video src="mp4:video_1080p.mp4" system-bitrate="4692000" width="1920" height="1080"/>
   <video src="mp4:video_720p.mp4" system-bitrate="2692000" width="1280" height="720"/>
   <video src="mp4:video_480p.mp4" system-bitrate="1378000" width="704" height="480"/>
   <video src="mp4:video_360p.mp4" system-bitrate="584000" width="640" height="360"/>
   <video src="mp4:video_180p.mp4" system-bitrate="264000" width="320" height="180"/>
  </switch>
 </body>
</smil>
"""


class MockArgs(argparse.Namespace):
    """Mock command-line arguments."""

    def __init__(
        self,
        smil_only: bool = False,
        vtt_in_smil: bool = False,
        no_ttml: bool = False,
    ) -> None:
        super().__init__()
        self.smil_only = smil_only
        self.vtt_in_smil = vtt_in_smil
        self.no_ttml = no_ttml


@pytest.fixture
def tmpdir_with_vtts(tmp_path: Path) -> Path:
    (tmp_path / "video.ru.vtt").write_text("WEBVTT\n")
    (tmp_path / "video.en.vtt").write_text("WEBVTT\n")
    (tmp_path / "video.smil").write_text(TRANSCODER_SMIL)
    return tmp_path


@pytest.fixture
def video_job(tmpdir_with_vtts: Path) -> VideoJob:
    return VideoJob(
        video_path=tmpdir_with_vtts / "video_1080p.mp4",
        normalized_name="video.mp4",
        ru_vtt=tmpdir_with_vtts / "video.ru.vtt",
        en_vtt=tmpdir_with_vtts / "video.en.vtt",
        ttml=tmpdir_with_vtts / "video.ttml",
        smil=tmpdir_with_vtts / "video.smil",
    )


@pytest.fixture
def metadata() -> VideoMetadata:
    return VideoMetadata(
        duration=120.0,
        width=1920,
        height=1080,
        video_codec_id="h264",
        audio_codec_id="aac",
        bitrate=5000000,
    )


@pytest.fixture
def args() -> MockArgs:
    return MockArgs(vtt_in_smil=True)


class TestSMILSubtitleAssociation:
    """Tests for adding subtitle textstreams to existing SMIL manifests."""

    def test_smil_missing_is_never_created(
        self, tmp_path: Path, metadata: VideoMetadata, args: MockArgs, caplog: LogCaptureFixture
    ) -> None:
        """write_smil must never create a SMIL when none exists."""
        job = VideoJob(
            video_path=tmp_path / "video_1080p.mp4",
            normalized_name="video.mp4",
            ru_vtt=tmp_path / "video.ru.vtt",
            en_vtt=tmp_path / "video.en.vtt",
            ttml=tmp_path / "video.ttml",
            smil=tmp_path / "video.smil",
        )
        (tmp_path / "video.ru.vtt").write_text("WEBVTT\n")
        (tmp_path / "video.en.vtt").write_text("WEBVTT\n")

        with caplog.at_level(logging.WARNING):
            result = write_smil(job, metadata, args)

        assert result is False
        assert not job.smil.exists()
        assert any("does not exist" in r.message for r in caplog.records)

    def test_corrupt_smil_is_never_regenerated(
        self, video_job: VideoJob, metadata: VideoMetadata, args: MockArgs, caplog: LogCaptureFixture
    ) -> None:
        """A SMIL that fails XML parsing must be left untouched."""
        video_job.smil.write_text("<smil><body><switch>")  # malformed

        with caplog.at_level(logging.ERROR):
            result = write_smil(video_job, metadata, args)

        assert result is False
        assert video_job.smil.read_text() == "<smil><body><switch>"

    def test_smil_without_video_nodes_is_skipped(
        self, video_job: VideoJob, metadata: VideoMetadata, args: MockArgs
    ) -> None:
        """A SMIL with no <video> entries must not be modified."""
        video_job.smil.write_text("<?xml version='1.0'?><smil><head/><body><switch/></body></smil>")
        before = video_job.smil.read_text()

        result = write_smil(video_job, metadata, args)

        assert result is False
        assert video_job.smil.read_text() == before

    def test_all_video_variants_preserved(self, video_job: VideoJob, metadata: VideoMetadata, args: MockArgs) -> None:
        """All 5 transcoder renditions must survive the subtitle update, unmodified."""
        result = write_smil(video_job, metadata, args)
        assert result is True

        tree = ET.parse(video_job.smil)
        switch = tree.getroot().find("body/switch")
        assert switch is not None
        videos = switch.findall("video")

        assert len(videos) == 5
        srcs = [v.get("src") for v in videos]
        assert "mp4:video_1080p.mp4" in srcs
        assert "mp4:video_180p.mp4" in srcs
        # video nodes must not gain codec params or any children
        for v in videos:
            assert len(list(v)) == 0

    def test_smil_textstream_elements(self, video_job: VideoJob, metadata: VideoMetadata, args: MockArgs) -> None:
        """Russian and English VTT textstreams are added with correct attributes."""
        write_smil(video_job, metadata, args)

        tree = ET.parse(video_job.smil)
        switch = tree.getroot().find("body/switch")
        assert switch is not None
        textstreams = switch.findall("textstream")

        assert len(textstreams) == 2

        ru_stream = None
        en_stream = None
        for ts in textstreams:
            if ts.get("system-language") == "rus":
                ru_stream = ts
            elif ts.get("system-language") == "eng":
                en_stream = ts

        assert ru_stream is not None
        assert en_stream is not None
        # Textstream elements should NOT have mp4: prefix (unlike video sources)
        assert ru_stream.get("src") == "video.ru.vtt"
        assert en_stream.get("src") == "video.en.vtt"

    def test_smil_update_is_idempotent(self, video_job: VideoJob, metadata: VideoMetadata, args: MockArgs) -> None:
        """Running write_smil twice must not duplicate any nodes."""
        write_smil(video_job, metadata, args)
        first_content = video_job.smil.read_text()

        write_smil(video_job, metadata, args)
        second_content = video_job.smil.read_text()
        assert first_content == second_content

        tree = ET.parse(video_job.smil)
        switch = tree.getroot().find("body/switch")
        assert switch is not None
        assert len(switch.findall("video")) == 5
        assert len(switch.findall("textstream")) == 2

    def test_backup_created_before_modification(
        self, video_job: VideoJob, metadata: VideoMetadata, args: MockArgs
    ) -> None:
        """A .bak copy of the original SMIL must exist after an update."""
        original = video_job.smil.read_text()
        write_smil(video_job, metadata, args)

        backups = list(video_job.smil.parent.glob("video.smil.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text() == original

    def test_smil_missing_vtt_warning(
        self,
        video_job: VideoJob,
        metadata: VideoMetadata,
        args: MockArgs,
        caplog: LogCaptureFixture,
    ) -> None:
        """Missing subtitle files are skipped with a warning, videos untouched."""
        video_job.ru_vtt.unlink()
        video_job.en_vtt.unlink()

        with caplog.at_level(logging.WARNING):
            write_smil(video_job, metadata, args)

        assert any("vtt" in r.message.lower() for r in caplog.records)

        tree = ET.parse(video_job.smil)
        switch = tree.getroot().find("body/switch")
        assert switch is not None
        assert len(switch.findall("textstream")) == 0
        assert len(switch.findall("video")) == 5

    def test_precheck_passes_on_valid_smil(self, video_job: VideoJob) -> None:
        """A valid transcoder SMIL passes the pre-flight check."""
        assert smil_precheck(video_job) is None

    def test_precheck_rejects_missing_smil(self, video_job: VideoJob) -> None:
        """A missing SMIL fails the pre-flight check so the video is never processed."""
        video_job.smil.unlink()
        assert smil_precheck(video_job) == "smil_missing"

    def test_precheck_rejects_unparseable_smil(self, video_job: VideoJob) -> None:
        video_job.smil.write_text("<smil><body>")
        reason = smil_precheck(video_job)
        assert reason is not None and reason.startswith("smil_unparseable")

    def test_precheck_rejects_smil_without_videos(self, video_job: VideoJob) -> None:
        video_job.smil.write_text("<?xml version='1.0'?><smil><head/><body><switch/></body></smil>")
        assert smil_precheck(video_job) == "smil_no_video_nodes"

    def test_skip_record_shape(self, video_job: VideoJob) -> None:
        """The skip record is queryable by status and error_type in the manifest."""
        record = skip_record_for_invalid_smil(video_job, "smil_missing", phase="transcription")
        assert record["status"] == "skipped"
        assert record["error_type"] == "invalid_smil"
        assert record["error"] == "smil_missing"
        assert record["phase"] == "transcription"
        assert record["video_path"] == str(video_job.video_path)

    def test_smil_ttml_bilingual_language(self, video_job: VideoJob, metadata: VideoMetadata) -> None:
        """TTML textstream carries both languages in system-language."""
        video_job.ttml.write_text("<?xml version='1.0' encoding='UTF-8'?><tt></tt>")

        args = MockArgs(vtt_in_smil=False)
        write_smil(video_job, metadata, args)

        tree = ET.parse(video_job.smil)
        switch = tree.getroot().find("body/switch")
        assert switch is not None
        textstreams = switch.findall("textstream")

        ttml_stream = None
        for ts in textstreams:
            if "video.ttml" in ts.get("src", ""):
                ttml_stream = ts
                break

        assert ttml_stream is not None, "TTML textstream should be present"
        assert ttml_stream.get("system-language") == "rus,eng", (
            "TTML textstream should have bilingual system-language attribute"
        )
