#!/usr/bin/env python3
"""Archive transcription utility for LiveVTT.

Recursively scans an archive of broadcast chunks, selects the highest
resolution variant of each chunk, extracts audio with FFmpeg, and generates
parallel Russian (transcription) and English (translation) WebVTT files using
Faster-Whisper.

Also generates TTML (Timed Text Markup Language) files with bilingual subtitles
aligned by timestamp. SMIL manifests include TTML by default; use --vtt-in-smil
to include individual VTT files instead.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from concurrent.futures import ThreadPoolExecutor, as_completed

try:  # Optional progress feedback
    from tqdm import tqdm  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None

from faster_whisper import WhisperModel  # type: ignore

# Import TTML utilities
from ttml_utils import cues_to_ttml, parse_vtt_content, load_filter_words, should_filter_cue


VIDEO_EXTENSIONS = {
    ".ts",
    ".mp4",
    ".mkv",
    ".mov",
    ".m4v",
    ".flv",
}

# Matches resolution tokens like _1080p, .720p, -480p, _180p
RESOLUTION_TOKEN_PATTERN = re.compile(r"([_.-])(\d{3,4})p(?=([_.-]|$))", re.IGNORECASE)


LOGGER = logging.getLogger("archive_transcriber")

# ISO 639-1 (2-letter) to ISO 639-2 (3-letter) language code mapping for TTML
LANG_CODE_2_TO_3 = {
    "en": "eng",
    "ru": "rus",
}


def ensure_python_version() -> None:
    if sys.version_info < (3, 10):
        raise RuntimeError("archive_transcriber requires Python 3.10 or newer")


def human_time() -> str:
    """
    Return the current UTC time formatted as an ISO-like timestamp.
    
    Returns:
        A string in the format `YYYY-MM-DDTHH:MM:SSZ` representing the current time in UTC.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def segments_to_webvtt(segments: Iterable, prepend_header: bool = True, filter_words: Optional[List[str]] = None) -> str:
    """
    Convert an iterable of transcription segments into WebVTT subtitle content.
    
    Parameters:
        segments: Iterable of objects with numeric `start` and `end` (seconds) and string `text` attributes.
        prepend_header: If True, include the leading "WEBVTT" header and a blank line.
        filter_words: Optional list of substrings; any cue whose text matches filtering rules will be omitted.
    
    Notes:
        - Timestamps are formatted as "HH:MM:SS.mmm".
        - Empty texts are skipped. Cue indices are assigned sequentially only to emitted cues.
    
    Returns:
        A WebVTT-formatted string ending with a single newline.
    """

    def format_timestamp(seconds: float) -> str:
        """
        Format a time value in seconds into a WebVTT-style timestamp "HH:MM:SS.mmm".
        
        Returns:
            str: Timestamp in the form "HH:MM:SS.mmm" corresponding to the input seconds; sub-millisecond fractions are truncated.
        """
        total_ms = int(seconds * 1000)
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"

    lines: List[str] = []
    if prepend_header:
        lines.append("WEBVTT")
        lines.append("")

    cue_idx = 1
    for segment in segments:
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = (segment.text or "").strip()

        if not text:
            continue

        # Skip entire cue if it contains any filter words
        if filter_words and should_filter_cue(text, filter_words):
            continue

        lines.append(str(cue_idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
        cue_idx += 1

    # Ensure file ends with newline
    return "\n".join(lines).rstrip() + "\n"


def _normalise_language_code(language: Optional[str]) -> Optional[str]:
    """Normalise language labels to simplified codes for downstream checks."""
    if not language:
        return None

    token = language.strip().lower()
    if not token:
        return None

    if token in {"en", "eng", "english"}:
        return "en"

    normalized = token.replace("_", "-")
    for part in re.split(r"[\s,;]+", normalized):
        part = part.strip("()")
        if not part:
            continue
        if part in {"en", "eng", "english"}:
            return "en"
        if part.startswith("en-"):
            return "en"
        if part.startswith("en") and len(part) > 2:
            return "en"

    if normalized.startswith("en-"):
        return "en"
    if normalized.startswith("en") and len(normalized) > 2:
        return "en"

    return None


def translation_output_suspect(
    source_segments: List,
    translated_segments: List,
    target_language: str,
) -> bool:
    if not translated_segments:
        return True

    target = _normalise_language_code(target_language)

    if target == "en":
        total_chars = 0
        cyrillic_chars = 0
        for seg in translated_segments:
            text = (seg.text or "")
            total_chars += len(text)
            cyrillic_chars += sum("\u0400" <= ch <= "\u04FF" for ch in text)

        if total_chars == 0:
            return True

        if cyrillic_chars / total_chars > 0.2:
            return True

    source_count = len(source_segments)
    translated_count = len(translated_segments)

    if source_count and translated_count < max(1, source_count // 3):
        return True

    return False


def extract_resolution(value: str) -> Optional[int]:
    match = RESOLUTION_TOKEN_PATTERN.search(value)
    if not match:
        return None
    try:
        return int(match.group(2))
    except ValueError:
        return None


def normalise_variant_name(path: Path) -> str:
    """Normalise filename by removing resolution tokens while keeping extension."""
    return RESOLUTION_TOKEN_PATTERN.sub("", path.name)


def build_output_artifacts(
    video_path: Path,
    normalized_name: str,
    input_root: Path,
    output_root: Optional[Path],
) -> Tuple[Path, Path, Path, Path]:
    if output_root:
        relative = video_path.relative_to(input_root)
        target_dir = output_root.joinpath(*relative.parts[:-1])
    else:
        target_dir = video_path.parent

    target_dir.mkdir(parents=True, exist_ok=True)
    base_stem = Path(normalized_name).stem
    ru_vtt = target_dir / f"{base_stem}.ru.vtt"
    en_vtt = target_dir / f"{base_stem}.en.vtt"
    ttml = target_dir / f"{base_stem}.ttml"
    smil = target_dir / f"{base_stem}.smil"
    return ru_vtt, en_vtt, ttml, smil


@dataclass
class VideoJob:
    video_path: Path
    normalized_name: str
    ru_vtt: Path
    en_vtt: Path
    ttml: Path
    smil: Path


class Manifest:
    """Append-only JSONL manifest with in-memory lookup."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.records: Dict[str, Dict] = {}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as manifest_file:
                for line in manifest_file:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    video_path = record.get("video_path")
                    if video_path:
                        self.records[video_path] = record

        # Ensure parent directory exists for future writes
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, video_path: Path) -> Optional[Dict]:
        return self.records.get(str(video_path))

    def append(self, record: Dict) -> None:
        with self.lock:
            with self.path.open("a", encoding="utf-8") as manifest_file:
                manifest_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.records[str(record.get("video_path"))] = record


class WhisperModelHolder(threading.local):
    def __init__(self) -> None:
        super().__init__()
        self.models: Dict[str, WhisperModel] = {}


MODEL_HOLDER = WhisperModelHolder()


def get_model(
    args: argparse.Namespace,
    model_name: Optional[str] = None,
    compute_type: Optional[str] = None,
) -> WhisperModel:
    name = model_name or args.model

    if name in MODEL_HOLDER.models:
        return MODEL_HOLDER.models[name]

    device = "cuda" if args.use_cuda else "cpu"
    selected_compute_type = compute_type or args.compute_type

    def instantiate(target_device: str, target_compute_type: str) -> WhisperModel:
        LOGGER.debug(
            "Loading Whisper model %s (device=%s, compute_type=%s)",
            name,
            target_device,
            target_compute_type,
        )
        return WhisperModel(
            name,
            device=target_device,
            compute_type=target_compute_type,
        )

    try:
        MODEL_HOLDER.models[name] = instantiate(device, selected_compute_type)
    except RuntimeError as exc:
        if args.use_cuda:
            LOGGER.warning(
                "CUDA initialisation failed for %s (%s). Falling back to CPU with float32 compute type.",
                name,
                exc,
            )
            MODEL_HOLDER.models[name] = instantiate("cpu", "float32")
        else:
            raise

    return MODEL_HOLDER.models[name]

@dataclass
class VideoMetadata:
    duration: Optional[float]
    width: Optional[int]
    height: Optional[int]
    video_codec_id: Optional[str]
    audio_codec_id: Optional[str]
    bitrate: Optional[int]


def probe_video_metadata(video_path: Path) -> VideoMetadata:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout or "{}")
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        LOGGER.warning("Failed to probe metadata for %s: %s", video_path, exc)
        return VideoMetadata(duration=None, width=None, height=None, video_codec_id=None, audio_codec_id=None, bitrate=None)

    streams = data.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    format_data = data.get("format", {})

    def _get_int(value: Optional[str]) -> Optional[int]:
        if value in (None, "", "N/A"):
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _get_float(value: Optional[str]) -> Optional[float]:
        if value in (None, "", "N/A"):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    duration = _get_float(format_data.get("duration"))
    width = _get_int(video_stream.get("width"))
    height = _get_int(video_stream.get("height"))
    video_codec_id = video_stream.get("codec_tag_string") or video_stream.get("codec_name")
    audio_codec_id = audio_stream.get("codec_tag_string") or audio_stream.get("codec_name")
    bitrate = _get_int(video_stream.get("bit_rate")) or _get_int(format_data.get("bit_rate"))

    return VideoMetadata(
        duration=duration,
        width=width,
        height=height,
        video_codec_id=video_codec_id,
        audio_codec_id=audio_codec_id,
        bitrate=bitrate,
    )


def write_smil(job: VideoJob, metadata: VideoMetadata, args: argparse.Namespace) -> None:
    """
    Write or update the SMIL manifest for a video job, ensuring a video element and appropriate textstream entries.
    
    Creates the SMIL parent directory if needed, makes a one-time backup of an existing SMIL file, parses an existing SMIL (or creates a minimal one), ensures a single <video> element with available metadata attributes, removes previously managed caption <textstream> nodes, and adds new <textstream> entries for subtitles. By default adds a bilingual TTML textstream (if present); if args.vtt_in_smil is true, adds individual Russian and English VTT textstreams instead. When comparing or deduplicating textstream sources the comparison strips an optional "mp4:" prefix; textstream entries are not added if the referenced subtitle file is missing (a warning is emitted). The final SMIL XML is optionally indented and written with an XML declaration.
    
    Parameters:
        job (VideoJob): Job record containing source video path and target artifact paths (smil, ttml, ru_vtt, en_vtt).
        metadata (VideoMetadata): Probed video metadata used to populate video attributes (bitrate, width, height, codec ids).
        args (argparse.Namespace): Parsed CLI arguments; used flags are at least `vtt_in_smil` and `smil_only`.
    """
    job.smil.parent.mkdir(parents=True, exist_ok=True)

    tree: Optional[ET.ElementTree] = None
    root: Optional[ET.Element] = None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = job.smil.with_suffix(job.smil.suffix + f".bak.{timestamp}")
    if job.smil.exists() and not backup_path.exists():
        try:
            shutil.copy2(job.smil, backup_path)
            LOGGER.debug("Backed up SMIL %s to %s", job.smil, backup_path)
        except OSError as exc:
            LOGGER.warning("Failed to back up %s to %s: %s", job.smil, backup_path, exc)

    if job.smil.exists():
        try:
            tree = ET.parse(job.smil)
            root = tree.getroot()
        except ET.ParseError as exc:
            LOGGER.warning("SMIL parse error for %s (%s); regenerating", job.smil, exc)

    if root is None:
        root = ET.Element("smil")
        ET.SubElement(root, "head")
        tree = ET.ElementTree(root)

    body = root.find("body")
    if body is None:
        body = ET.SubElement(root, "body")

    switch = body.find("switch")
    if switch is None:
        switch = ET.SubElement(body, "switch")

    def ensure_video_node() -> None:
        if any(child.tag == "video" for child in switch):
            return
        video_attrs = {"src": f"mp4:{job.video_path.name}"}
        if metadata.bitrate:
            video_attrs["system-bitrate"] = str(metadata.bitrate)
        if metadata.width:
            video_attrs["width"] = str(metadata.width)
        if metadata.height:
            video_attrs["height"] = str(metadata.height)
        video_elem = ET.SubElement(switch, "video", video_attrs)
        if metadata.video_codec_id:
            ET.SubElement(
                video_elem,
                "param",
                {
                    "name": "videoCodecId",
                    "value": metadata.video_codec_id,
                    "valuetype": "data",
                },
            )
        if metadata.audio_codec_id:
            ET.SubElement(
                video_elem,
                "param",
                {
                    "name": "audioCodecId",
                    "value": metadata.audio_codec_id,
                    "valuetype": "data",
                },
            )

    ensure_video_node()

    # Remove existing LiveVTT-managed textstreams
    for node in list(switch.findall("textstream")):
        if any(child.tag == "param" and child.get("name") == "isWowzaCaptionStream" for child in list(node)):
            switch.remove(node)

    def ensure_textstream(src: str, language: str) -> None:
        # Textstream sources should NOT have mp4: prefix (unlike video sources)
        """
        Ensure a textstream entry for a subtitle file exists in the SMIL switch element.
        
        Removes any existing <textstream> entries that reference the same subtitle source (comparison ignores a leading "mp4:" prefix), then adds a new <textstream> child with the given language and an `isWowzaCaptionStream` parameter. If the referenced subtitle file is missing on disk, logs a warning and does not add an entry.
        
        Parameters:
        	src (str): Subtitle file path as used in the SMIL `src` attribute.
        	language (str): Language code to set on the `system-language` attribute.
        
        Notes:
        	This function mutates the surrounding SMIL `switch` element and reads the job's SMIL directory to check for file existence. It does not return a value.
        """
        target_src = src

        def _normalize(value: Optional[str]) -> str:
            """
            Normalize a subtitle/textstream source string for comparison.
            
            Strips surrounding whitespace and, if present, removes a leading "mp4:" prefix (case-insensitive). Returns an empty string when the input is None or empty.
            
            Parameters:
                value (Optional[str]): The source string to normalize; may be None.
            
            Returns:
                str: The normalized source string (trimmed and without a leading "mp4:"), or an empty string if the input was falsy.
            """
            if not value:
                return ""
            value = value.strip()
            # Remove mp4: prefix if present for comparison
            if value.lower().startswith("mp4:"):
                return value[4:]
            return value

        # Remove existing textstream nodes with the same source
        for node in list(switch.findall("textstream")):
            if _normalize(node.get("src")) == src:
                switch.remove(node)

        if not Path(job.smil.parent, src).exists():
            LOGGER.warning("Expected subtitle file missing for %s when writing SMIL", src)
            return
        ts = ET.SubElement(switch, "textstream", {"src": target_src, "system-language": language})
        ET.SubElement(
            ts,
            "param",
            {
                "name": "isWowzaCaptionStream",
                "value": "true",
                "valuetype": "data",
            },
        )

    # By default, use TTML in SMIL (contains both languages)
    # Use --vtt-in-smil flag to include individual VTT files instead
    if args.vtt_in_smil:
        # Include individual VTT files in SMIL
        if job.ru_vtt.exists():
            ensure_textstream(job.ru_vtt.name, "rus")
        elif not args.smil_only:
            LOGGER.warning("Expected Russian VTT missing for %s when writing SMIL", job.ru_vtt)

        if job.en_vtt.exists():
            ensure_textstream(job.en_vtt.name, "eng")
        elif not args.smil_only:
            LOGGER.warning("Expected English VTT missing for %s when writing SMIL", job.en_vtt)
    else:
        # Use TTML by default (bilingual subtitle file)
        if job.ttml.exists():
            # TTML is bilingual, so we include both languages in system-language
            ensure_textstream(job.ttml.name, "rus,eng")
            LOGGER.debug("Added TTML to SMIL: %s", job.ttml.name)
        elif not args.smil_only:
            LOGGER.warning("Expected TTML file missing for %s when writing SMIL", job.ttml)

    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")  # type: ignore[arg-type]

    tree.write(job.smil, encoding="utf-8", xml_declaration=True)


def discover_video_jobs(
    input_root: Path,
    output_root: Optional[Path],
    manifest: Manifest,
    force: bool,
    extensions: Iterable[str],
    ttml_enabled: bool,
) -> List[VideoJob]:
    extensions = {ext.lower() for ext in extensions}
    grouped: Dict[Tuple[str, str], List[Path]] = {}

    LOGGER.info("Scanning archive at %s", input_root)
    for dirpath, _, filenames in os.walk(input_root):
        directory = Path(dirpath)
        for filename in filenames:
            path = directory / filename
            if path.suffix.lower() not in extensions:
                continue
            normalized_name = normalise_variant_name(path)
            key = (str(path.parent), normalized_name.lower())
            grouped.setdefault(key, []).append(path)

    jobs: List[VideoJob] = []
    LOGGER.info("Found %d candidate groups", len(grouped))

    for (_, normalized_name_lower), candidates in grouped.items():
        best_path = select_best_variant(candidates)
        if not best_path:
            continue
        normalized_name = normalise_variant_name(best_path)
        ru_vtt, en_vtt, ttml_path, smil_path = build_output_artifacts(best_path, normalized_name, input_root, output_root)

        if should_skip(best_path, ru_vtt, en_vtt, ttml_path, smil_path, force, ttml_enabled):
            LOGGER.debug("Skipping already processed %s", best_path)
            continue

        jobs.append(
            VideoJob(
                video_path=best_path,
                normalized_name=normalized_name,
                ru_vtt=ru_vtt,
                en_vtt=en_vtt,
                ttml=ttml_path,
                smil=smil_path,
            )
        )

    jobs.sort(key=lambda job: job.video_path)
    return jobs


def select_best_variant(candidates: List[Path]) -> Optional[Path]:
    best_path: Optional[Path] = None
    best_score = (-1, -1)

    for path in candidates:
        resolution = extract_resolution(path.name)
        priority = resolution or 0
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        score = (priority, size)
        if score > best_score:
            best_score = score
            best_path = path

    return best_path


def should_skip(
    video_path: Path,
    ru_vtt: Path,
    en_vtt: Path,
    ttml_path: Path,
    smil_path: Path,
    force: bool,
    ttml_enabled: bool,
) -> bool:
    if force:
        return False

    required_outputs = [ru_vtt, en_vtt, smil_path]
    if ttml_enabled:
        required_outputs.append(ttml_path)

    if not all(path.exists() for path in required_outputs):
        return False

    video_mtime = video_path.stat().st_mtime
    return all(path.stat().st_mtime >= video_mtime for path in required_outputs)


def extract_audio(video_path: Path, sample_rate: int) -> Path:
    tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_file_path = Path(tmp_file.name)
    tmp_file.close()

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "wav",
        str(tmp_file_path),
    ]

    LOGGER.debug("Running FFmpeg: %s", " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr_preview = (result.stderr or "").splitlines()[-5:]
        raise RuntimeError(
            f"FFmpeg failed for {video_path}: return code {result.returncode}\n" +
            "\n".join(stderr_preview)
        )

    return tmp_file_path


def atomic_write(path: Path, content: str) -> None:
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp_name)
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
        tmp_file.write(content)
    tmp_path.replace(path)


def process_job(job: VideoJob, args: argparse.Namespace, manifest: Manifest) -> Dict:
    """
    Process a single VideoJob: transcribe/translate audio if needed, write VTT/TTML outputs, generate or update the SMIL, and append a manifest record.
    
    Parameters:
        job (VideoJob): Candidate video and target output paths.
        args (argparse.Namespace): CLI options that control processing (sampling rate, models, transcription/translation flags, ttml/vtt behavior, force, etc.).
        manifest (Manifest): Append-only manifest used to record processing results.
    
    Returns:
        dict: A manifest-style record describing the processed video. On success the record has "status": "success" and contains output paths, duration, timestamps, and processing time; on failure the record has "status": "error" and includes an "error" message.
    """
    start_time = time.time()
    LOGGER.info("Processing %s", job.video_path)

    # Load filter words (cached after first call)
    filter_words = load_filter_words()

    metadata = probe_video_metadata(job.video_path)
    duration = metadata.duration or 0.0
    need_transcription = not args.smil_only and (
        args.force or not (job.ru_vtt.exists() and job.en_vtt.exists())
    )

    audio_path: Optional[Path] = None

    try:
        if need_transcription:
            audio_path = extract_audio(job.video_path, args.sample_rate)
            model = get_model(args)

            ru_iter, ru_info = model.transcribe(
                str(audio_path),
                beam_size=args.beam_size,
                language=args.source_language,
                vad_filter=args.vad_filter,
                task="transcribe",
            )
            ru_segments = list(ru_iter)

            translation_model_name = args.translation_model or args.model
            translation_model = get_model(args, model_name=translation_model_name)

            en_iter, en_info = translation_model.transcribe(
                str(audio_path),
                beam_size=args.beam_size,
                language=args.source_language,
                vad_filter=args.vad_filter,
                task="translate",
            )
            en_segments = list(en_iter)

            fallback_name = (args.translation_fallback_model or "").strip()
            if fallback_name.lower() == "none":
                fallback_name = ""

            if (
                fallback_name
                and fallback_name != translation_model_name
                and translation_output_suspect(ru_segments, en_segments, args.translation_language)
            ):
                LOGGER.warning(
                    "Translation model %s produced unexpected output; retrying with %s",
                    translation_model_name,
                    fallback_name,
                )
                translation_model = get_model(args, model_name=fallback_name)
                en_iter, en_info = translation_model.transcribe(
                    str(audio_path),
                    beam_size=args.beam_size,
                    language=args.source_language,
                    vad_filter=args.vad_filter,
                    task="translate",
                )
                en_segments = list(en_iter)
                translation_model_name = fallback_name

            ru_content = segments_to_webvtt(ru_segments, filter_words=filter_words)
            en_content = segments_to_webvtt(en_segments, filter_words=filter_words)

            atomic_write(job.ru_vtt, ru_content)
            atomic_write(job.en_vtt, en_content)

            # Generate TTML file by default (unless --no-ttml is specified)
            if not args.no_ttml:
                ru_cues = parse_vtt_content(ru_content)
                en_cues = parse_vtt_content(en_content)
                # Convert 2-letter language codes to 3-letter for TTML
                ttml_lang1 = LANG_CODE_2_TO_3.get(args.source_language, args.source_language)
                ttml_lang2 = LANG_CODE_2_TO_3.get(args.translation_language, args.translation_language)
                ttml_content = cues_to_ttml(
                    ru_cues,
                    en_cues,
                    lang1=ttml_lang1,
                    lang2=ttml_lang2,
                    filter_words=filter_words,
                )
                atomic_write(job.ttml, ttml_content)
                LOGGER.debug("Generated TTML file: %s", job.ttml)

            duration_from_model = max(ru_info.duration if ru_info else 0.0, en_info.duration if en_info else 0.0)
            if duration_from_model:
                duration = duration_from_model
        else:
            if not job.ru_vtt.exists() or not job.en_vtt.exists():
                LOGGER.warning("Expected caption files missing for %s; skipping SMIL update", job.video_path)
                return {
                    "video_path": str(job.video_path),
                    "ru_vtt": str(job.ru_vtt),
                    "en_vtt": str(job.en_vtt),
                    "ttml": str(job.ttml) if not args.no_ttml else None,
                    "smil": str(job.smil),
                    "status": "error",
                    "error": "Missing caption files for SMIL-only run",
                    "processed_at": human_time(),
                }
            LOGGER.info("VTT already present for %s; generating SMIL only.", job.video_path)

        write_smil(job, metadata, args)

        record = {
            "video_path": str(job.video_path),
            "ru_vtt": str(job.ru_vtt),
            "en_vtt": str(job.en_vtt),
            "ttml": str(job.ttml) if not args.no_ttml else None,
            "smil": str(job.smil),
            "status": "success",
            "duration": duration,
            "processed_at": human_time(),
            "processing_time_sec": round(time.time() - start_time, 2),
        }
        manifest.append(record)
        return record

    except Exception as exc:
        LOGGER.error("Failed to process %s: %s", job.video_path, exc)
        record = {
            "video_path": str(job.video_path),
            "ru_vtt": str(job.ru_vtt),
            "en_vtt": str(job.en_vtt),
            "ttml": str(job.ttml) if not args.no_ttml else None,
            "smil": str(job.smil),
            "status": "error",
            "error": str(exc),
            "processed_at": human_time(),
        }
        manifest.append(record)
        return record

    finally:
        if audio_path and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                LOGGER.warning("Failed to delete temp audio file %s", audio_path)


def configure_logging(args: argparse.Namespace) -> None:
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=handlers,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch archive transcription and translation")
    parser.add_argument(
        "input_root",
        nargs="?",
        default=Path("/mnt/vod/srv/storage/transcoded/"),
        type=Path,
        help="Root directory of archived video chunks (default: /mnt/vod/srv/storage/transcoded/)",
    )
    parser.add_argument("--output-root", type=Path, help="Optional output root for VTT files")
    parser.add_argument("--manifest", type=Path, default=Path("logs/archive_transcriber_manifest.jsonl"), help="Path to manifest file (JSONL)")
    parser.add_argument("--model", type=str, default="large-v3-turbo", help="Faster-Whisper model to load (default: large-v3-turbo)")
    parser.add_argument("--compute-type", type=str, default="float16", help="Faster-Whisper compute type (e.g., float16, int8_float16)")
    parser.add_argument("--use-cuda", type=lambda x: str(x).lower() in {"1", "true", "yes"}, default=True, help="Use CUDA if available (default: true)")
    parser.add_argument("--source-language", type=str, default="ru", help="Source language code for transcription")
    parser.add_argument("--translation-language", type=str, default="en", help="Target language code for translation output")
    parser.add_argument(
        "--translation-model",
        type=str,
        default="large-v3",
        help="Model name to use for translation (default: large-v3; use --model for transcription)",
    )
    parser.add_argument(
        "--translation-fallback-model",
        type=str,
        default="large-v3",
        help="Fallback model for translation if the primary output appears incorrect (set to 'none' to disable)",
    )
    parser.add_argument("--beam-size", type=int, default=5, help="Beam size for decoding")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Audio sample rate for extraction")
    parser.add_argument("--vad-filter", type=lambda x: str(x).lower() in {"1", "true", "yes"}, default=False, help="Enable Silero VAD filtering")
    parser.add_argument("--extensions", type=str, default=",".join(sorted(VIDEO_EXTENSIONS)), help="Comma-separated list of video extensions to include")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker threads for processing")
    parser.add_argument("--max-files", type=int, help="Limit the number of videos processed in this run")
    parser.add_argument("--smil-only", action="store_true", help="Regenerate SMIL manifests without creating or updating VTT files")
    parser.add_argument("--no-ttml", action="store_true", help="Skip TTML file generation (generate only VTT files)")
    parser.add_argument("--vtt-in-smil", action="store_true", help="Include individual VTT files in SMIL manifest instead of TTML")
    parser.add_argument("--log-file", type=Path, help="Optional log file path")
    parser.add_argument("--progress", action="store_true", help="Display progress bar (requires tqdm)")
    parser.add_argument("--force", action="store_true", help="Reprocess files even if outputs exist")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    ensure_python_version()
    args = parse_args(argv)
    configure_logging(args)

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve() if args.output_root else None

    if not input_root.exists():
        LOGGER.error("Input root %s does not exist", input_root)
        return 2

    manifest = Manifest(args.manifest.resolve())
    extensions = [ext if ext.startswith(".") else f".{ext}" for ext in args.extensions.split(",") if ext]
    jobs = discover_video_jobs(
        input_root,
        output_root,
        manifest,
        args.force or args.smil_only,
        extensions,
        not args.no_ttml,
    )

    if args.max_files is not None:
        if args.max_files <= 0:
            LOGGER.warning("--max-files must be greater than zero; no work will be performed")
            jobs = []
        else:
            jobs = jobs[:args.max_files]

    if not jobs:
        LOGGER.info("No videos to process. Exiting.")
        return 0

    LOGGER.info("Processing %d videos", len(jobs))

    total = len(jobs)
    successes = 0
    failures = 0

    progress_bar = None
    if args.progress and tqdm is not None:
        progress_bar = tqdm(total=total, desc="Transcribing", unit="video")
    elif args.progress and tqdm is None:
        LOGGER.warning("tqdm is not installed; progress bar disabled")

    try:
        if args.workers > 1:
            LOGGER.info("Using %d worker threads", args.workers)
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(process_job, job, args, manifest) for job in jobs]
                try:
                    for future in as_completed(futures):
                        record = future.result()
                        if record.get("status") == "success":
                            successes += 1
                        else:
                            failures += 1
                        if progress_bar is not None:
                            progress_bar.update(1)
                except KeyboardInterrupt:
                    LOGGER.warning("Interrupted by user. Cancelling remaining jobs...")
                    for future in futures:
                        future.cancel()
                    raise
        else:
            for job in jobs:
                record = process_job(job, args, manifest)
                if record.get("status") == "success":
                    successes += 1
                else:
                    failures += 1
                if progress_bar is not None:
                    progress_bar.update(1)
    except KeyboardInterrupt:
        if progress_bar is not None:
            progress_bar.close()
        LOGGER.warning("Processing aborted via Ctrl+C")
        return 130

    if progress_bar is not None:
        progress_bar.close()

    LOGGER.info(
        "Completed processing: %d success, %d failures, %d total",
        successes,
        failures,
        total,
    )

    return 0 if failures == 0 else 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()