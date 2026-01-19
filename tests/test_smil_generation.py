#!/usr/bin/env python3
"""Unit tests for SMIL manifest generation."""

import importlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

# Mock dependencies
sys.modules['faster_whisper'] = mock.MagicMock()

archive_transcriber = importlib.import_module("archive_transcriber")

write_smil = archive_transcriber.write_smil
VideoJob = archive_transcriber.VideoJob
VideoMetadata = archive_transcriber.VideoMetadata


class MockArgs:
    """Mock command-line arguments."""

    def __init__(
        self,
        smil_only: bool = False,
        vtt_in_smil: bool = False,
        no_ttml: bool = False,
    ) -> None:
        self.smil_only = smil_only
        self.vtt_in_smil = vtt_in_smil
        self.no_ttml = no_ttml


@pytest.fixture
def tmpdir_with_vtts(tmp_path):
    (tmp_path / "video.ru.vtt").write_text("WEBVTT\n")
    (tmp_path / "video.en.vtt").write_text("WEBVTT\n")
    return tmp_path


@pytest.fixture
def video_job(tmpdir_with_vtts):
    return VideoJob(
        video_path=tmpdir_with_vtts / "video.ts",
        normalized_name="video.ts",
        ru_vtt=tmpdir_with_vtts / "video.ru.vtt",
        en_vtt=tmpdir_with_vtts / "video.en.vtt",
        ttml=tmpdir_with_vtts / "video.ttml",
        smil=tmpdir_with_vtts / "video.smil",
    )


@pytest.fixture
def metadata():
    return VideoMetadata(
        duration=120.0,
        width=1920,
        height=1080,
        video_codec_id="h264",
        audio_codec_id="aac",
        bitrate=5000000,
    )


@pytest.fixture
def args():
    return MockArgs(vtt_in_smil=True)


@pytest.fixture
def video_job_missing_vtts(tmp_path):
    return VideoJob(
        video_path=tmp_path / "video.ts",
        normalized_name="video.ts",
        ru_vtt=tmp_path / "video.ru.vtt",
        en_vtt=tmp_path / "video.en.vtt",
        ttml=tmp_path / "video.ttml",
        smil=tmp_path / "video.smil",
    )


class TestSMILGeneration:
    """Tests for SMIL manifest generation."""

    def test_smil_basic_structure(self, video_job, metadata, args):
        """Test basic SMIL structure generation."""
        write_smil(video_job, metadata, args)

        # Verify SMIL was created
        assert video_job.smil.exists()

        # Parse and validate structure
        tree = ET.parse(video_job.smil)
        root = tree.getroot()

        assert root.tag == "smil"
        assert root.find("head") is not None
        assert root.find("body") is not None
        assert root.find("body/switch") is not None


    def test_smil_video_element(self, video_job, metadata, args):
        """Test that SMIL includes video element with metadata."""
        write_smil(video_job, metadata, args)

        tree = ET.parse(video_job.smil)
        root = tree.getroot()
        switch = root.find("body/switch")
        video = switch.find("video")

        assert video is not None
        assert video.get("src") == "mp4:video.ts"
        assert video.get("system-bitrate") == "5000000"
        assert video.get("width") == "1920"
        assert video.get("height") == "1080"


    def test_smil_textstream_elements(self, video_job, metadata, args):
        """
        Verify the SMIL contains two subtitle textstream elements (Russian and English) with correct src and language attributes.
        
        Asserts that exactly two textstream elements appear under body/switch, one with system-language "rus" and one with "eng", and that their src attributes are "video.ru.vtt" and "video.en.vtt" respectively (no "mp4:" prefix).
        """
        write_smil(video_job, metadata, args)

        tree = ET.parse(video_job.smil)
        root = tree.getroot()
        switch = root.find("body/switch")
        textstreams = switch.findall("textstream")

        # Should have two textstreams (Russian and English)
        assert len(textstreams) == 2

        # Check for Russian textstream
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


    def test_smil_wowza_caption_params(self, video_job, args):
        """Test that textstreams have Wowza caption parameters."""
        metadata = VideoMetadata(
            duration=None,
            width=None,
            height=None,
            video_codec_id=None,
            audio_codec_id=None,
            bitrate=None,
        )

        write_smil(video_job, metadata, args)

        tree = ET.parse(video_job.smil)
        root = tree.getroot()
        switch = root.find("body/switch")
        textstreams = switch.findall("textstream")

        for ts in textstreams:
            # Check for Wowza caption parameter
            params = ts.findall("param")
            wowza_param = None
            for param in params:
                if param.get("name") == "isWowzaCaptionStream":
                    wowza_param = param
                    break

            assert wowza_param is not None
            assert wowza_param.get("value") == "true"
            assert wowza_param.get("valuetype") == "data"


    def test_smil_update_preserves_structure(self, video_job, metadata, args):
        """Test that updating SMIL preserves existing structure."""
        # Generate SMIL first time
        write_smil(video_job, metadata, args)
        first_content = video_job.smil.read_text()

        # Generate SMIL second time (should update, not duplicate)
        write_smil(video_job, metadata, args)
        second_content = video_job.smil.read_text()
        assert first_content == second_content

        # Parse and count elements
        tree = ET.parse(video_job.smil)
        root = tree.getroot()
        switch = root.find("body/switch")
        videos = switch.findall("video")
        textstreams = switch.findall("textstream")

        # Should have exactly one video element
        assert len(videos) == 1

        # Should have exactly two textstreams (not duplicated)
        wowza_textstreams = []
        for ts in textstreams:
            params = ts.findall("param")
            for param in params:
                if param.get("name") == "isWowzaCaptionStream":
                    wowza_textstreams.append(ts)
                    break

        assert len(wowza_textstreams) == 2


    def test_smil_missing_vtt_warning(self, video_job_missing_vtts, metadata, args):
        """Test that SMIL generation handles missing VTT files."""
        # Should not crash, just skip missing textstreams
        original_level = archive_transcriber.LOGGER.level
        archive_transcriber.LOGGER.setLevel("ERROR")
        try:
            write_smil(video_job_missing_vtts, metadata, args)
        finally:
            archive_transcriber.LOGGER.setLevel(original_level)

        # SMIL should still be created with video element
        assert video_job_missing_vtts.smil.exists()

        tree = ET.parse(video_job_missing_vtts.smil)
        root = tree.getroot()
        switch = root.find("body/switch")
        video = switch.find("video")

        # Video element should exist
        assert video is not None

        # Textstreams should not exist (files missing)
        textstreams = switch.findall("textstream")
        wowza_textstreams = []
        for ts in textstreams:
            params = ts.findall("param")
            for param in params:
                if param.get("name") == "isWowzaCaptionStream":
                    wowza_textstreams.append(ts)
                    break

        # No textstreams should be added for missing files
        assert len(wowza_textstreams) == 0


    def test_smil_codec_params(self, video_job, metadata, args):
        """Test that video codec parameters are included."""
        write_smil(video_job, metadata, args)

        tree = ET.parse(video_job.smil)
        root = tree.getroot()
        switch = root.find("body/switch")
        video = switch.find("video")
        params = video.findall("param")

        video_codec_param = None
        audio_codec_param = None

        for param in params:
            if param.get("name") == "videoCodecId":
                video_codec_param = param
            elif param.get("name") == "audioCodecId":
                audio_codec_param = param

        assert video_codec_param is not None
        assert video_codec_param.get("value") == "h264"

        assert audio_codec_param is not None
        assert audio_codec_param.get("value") == "aac"


    def test_smil_ttml_bilingual_language(self, video_job, metadata):
        """Test that TTML textstream includes both languages in system-language."""
        # Create TTML file
        video_job.ttml.write_text("<?xml version='1.0' encoding='UTF-8'?><tt></tt>")

        # Use default args (TTML in SMIL, not VTT)
        args = MockArgs(vtt_in_smil=False)
        write_smil(video_job, metadata, args)

        tree = ET.parse(video_job.smil)
        root = tree.getroot()
        switch = root.find("body/switch")
        textstreams = switch.findall("textstream")

        # Find TTML textstream
        ttml_stream = None
        for ts in textstreams:
            if "video.ttml" in ts.get("src", ""):
                ttml_stream = ts
                break

        assert ttml_stream is not None, "TTML textstream should be present"
        assert ttml_stream.get("system-language") == "rus,eng", \
            "TTML textstream should have bilingual system-language attribute"
