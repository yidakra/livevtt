#!/usr/bin/env python3
"""Unit tests for SMIL manifest generation."""

import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

# Mock dependencies
sys.modules['faster_whisper'] = mock.MagicMock()
sys.modules['ttml_utils'] = mock.MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

from archive_transcriber import (
    write_smil,
    VideoJob,
    VideoMetadata,
)


class MockArgs:
    """Mock command-line arguments."""
    def __init__(self, smil_only=False):
        self.smil_only = smil_only


class TestSMILGeneration:
    """Tests for SMIL manifest generation."""

    def test_smil_basic_structure(self):
        """Test basic SMIL structure generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create dummy VTT files
            (tmpdir / "video.ru.vtt").write_text("WEBVTT\n")
            (tmpdir / "video.en.vtt").write_text("WEBVTT\n")

            # Create VideoJob
            job = VideoJob(
                video_path=tmpdir / "video.ts",
                normalized_name="video.ts",
                ru_vtt=tmpdir / "video.ru.vtt",
                en_vtt=tmpdir / "video.en.vtt",
                ttml=tmpdir / "video.ttml",
                smil=tmpdir / "video.smil",
            )

            # Create metadata
            metadata = VideoMetadata(
                duration=120.0,
                width=1920,
                height=1080,
                video_codec_id="h264",
                audio_codec_id="aac",
                bitrate=5000000,
            )

            # Generate SMIL
            args = MockArgs()
            write_smil(job, metadata, args)

            # Verify SMIL was created
            assert job.smil.exists()

            # Parse and validate structure
            tree = ET.parse(job.smil)
            root = tree.getroot()

            assert root.tag == "smil"
            assert root.find("head") is not None
            assert root.find("body") is not None
            assert root.find("body/switch") is not None

            print("✓ test_smil_basic_structure passed")

    def test_smil_video_element(self):
        """Test that SMIL includes video element with metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            (tmpdir / "video.ru.vtt").write_text("WEBVTT\n")
            (tmpdir / "video.en.vtt").write_text("WEBVTT\n")

            job = VideoJob(
                video_path=tmpdir / "video.ts",
                normalized_name="video.ts",
                ru_vtt=tmpdir / "video.ru.vtt",
                en_vtt=tmpdir / "video.en.vtt",
                ttml=tmpdir / "video.ttml",
                smil=tmpdir / "video.smil",
            )

            metadata = VideoMetadata(
                duration=120.0,
                width=1920,
                height=1080,
                video_codec_id="h264",
                audio_codec_id="aac",
                bitrate=5000000,
            )

            args = MockArgs()
            write_smil(job, metadata, args)

            tree = ET.parse(job.smil)
            root = tree.getroot()
            switch = root.find("body/switch")
            video = switch.find("video")

            assert video is not None
            assert video.get("src") == "mp4:video.ts"
            assert video.get("system-bitrate") == "5000000"
            assert video.get("width") == "1920"
            assert video.get("height") == "1080"

            print("✓ test_smil_video_element passed")

    def test_smil_textstream_elements(self):
        """Test that SMIL includes textstream elements for subtitles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            (tmpdir / "video.ru.vtt").write_text("WEBVTT\n")
            (tmpdir / "video.en.vtt").write_text("WEBVTT\n")

            job = VideoJob(
                video_path=tmpdir / "video.ts",
                normalized_name="video.ts",
                ru_vtt=tmpdir / "video.ru.vtt",
                en_vtt=tmpdir / "video.en.vtt",
                ttml=tmpdir / "video.ttml",
                smil=tmpdir / "video.smil",
            )

            metadata = VideoMetadata(
                duration=120.0,
                width=1920,
                height=1080,
                video_codec_id="h264",
                audio_codec_id="aac",
                bitrate=5000000,
            )

            args = MockArgs()
            write_smil(job, metadata, args)

            tree = ET.parse(job.smil)
            root = tree.getroot()
            switch = root.find("body/switch")
            textstreams = switch.findall("textstream")

            # Should have two textstreams (Russian and English)
            assert len(textstreams) >= 2

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
            assert ru_stream.get("src") == "mp4:video.ru.vtt"
            assert en_stream.get("src") == "mp4:video.en.vtt"

            print("✓ test_smil_textstream_elements passed")

    def test_smil_wowza_caption_params(self):
        """Test that textstreams have Wowza caption parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            (tmpdir / "video.ru.vtt").write_text("WEBVTT\n")
            (tmpdir / "video.en.vtt").write_text("WEBVTT\n")

            job = VideoJob(
                video_path=tmpdir / "video.ts",
                normalized_name="video.ts",
                ru_vtt=tmpdir / "video.ru.vtt",
                en_vtt=tmpdir / "video.en.vtt",
                ttml=tmpdir / "video.ttml",
                smil=tmpdir / "video.smil",
            )

            metadata = VideoMetadata(
                duration=None,
                width=None,
                height=None,
                video_codec_id=None,
                audio_codec_id=None,
                bitrate=None,
            )

            args = MockArgs()
            write_smil(job, metadata, args)

            tree = ET.parse(job.smil)
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

            print("✓ test_smil_wowza_caption_params passed")

    def test_smil_update_preserves_structure(self):
        """Test that updating SMIL preserves existing structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            (tmpdir / "video.ru.vtt").write_text("WEBVTT\n")
            (tmpdir / "video.en.vtt").write_text("WEBVTT\n")

            job = VideoJob(
                video_path=tmpdir / "video.ts",
                normalized_name="video.ts",
                ru_vtt=tmpdir / "video.ru.vtt",
                en_vtt=tmpdir / "video.en.vtt",
                ttml=tmpdir / "video.ttml",
                smil=tmpdir / "video.smil",
            )

            metadata = VideoMetadata(
                duration=120.0,
                width=1920,
                height=1080,
                video_codec_id="h264",
                audio_codec_id="aac",
                bitrate=5000000,
            )

            args = MockArgs()

            # Generate SMIL first time
            write_smil(job, metadata, args)
            first_content = job.smil.read_text()

            # Generate SMIL second time (should update, not duplicate)
            write_smil(job, metadata, args)
            second_content = job.smil.read_text()

            # Parse and count elements
            tree = ET.parse(job.smil)
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

            print("✓ test_smil_update_preserves_structure passed")

    def test_smil_missing_vtt_warning(self):
        """Test that SMIL generation handles missing VTT files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Don't create VTT files - they're missing

            job = VideoJob(
                video_path=tmpdir / "video.ts",
                normalized_name="video.ts",
                ru_vtt=tmpdir / "video.ru.vtt",
                en_vtt=tmpdir / "video.en.vtt",
                ttml=tmpdir / "video.ttml",
                smil=tmpdir / "video.smil",
            )

            metadata = VideoMetadata(
                duration=120.0,
                width=1920,
                height=1080,
                video_codec_id="h264",
                audio_codec_id="aac",
                bitrate=5000000,
            )

            args = MockArgs(smil_only=False)

            # Should not crash, just skip missing textstreams
            write_smil(job, metadata, args)

            # SMIL should still be created with video element
            assert job.smil.exists()

            tree = ET.parse(job.smil)
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

            print("✓ test_smil_missing_vtt_warning passed")

    def test_smil_codec_params(self):
        """Test that video codec parameters are included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            (tmpdir / "video.ru.vtt").write_text("WEBVTT\n")
            (tmpdir / "video.en.vtt").write_text("WEBVTT\n")

            job = VideoJob(
                video_path=tmpdir / "video.ts",
                normalized_name="video.ts",
                ru_vtt=tmpdir / "video.ru.vtt",
                en_vtt=tmpdir / "video.en.vtt",
                ttml=tmpdir / "video.ttml",
                smil=tmpdir / "video.smil",
            )

            metadata = VideoMetadata(
                duration=120.0,
                width=1920,
                height=1080,
                video_codec_id="h264",
                audio_codec_id="aac",
                bitrate=5000000,
            )

            args = MockArgs()
            write_smil(job, metadata, args)

            tree = ET.parse(job.smil)
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

            print("✓ test_smil_codec_params passed")


def run_all_tests():
    """Run all SMIL generation tests."""
    print("\nRunning SMIL generation tests...")
    print("=" * 60)

    test_class = TestSMILGeneration

    test_methods = [
        method for method in dir(test_class)
        if method.startswith("test_") and callable(getattr(test_class, method))
    ]

    passed = 0
    failed = 0

    for method_name in test_methods:
        try:
            instance = test_class()
            method = getattr(instance, method_name)
            method()
            passed += 1
        except AssertionError as e:
            print(f"✗ {method_name} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"✗ {method_name} error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
