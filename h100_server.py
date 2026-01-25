#!/usr/bin/env python3
"""
H100 Server for Faster-Whisper Transcription
Runs on RunPod H100 GPU to process audio transcription requests
Compatible with RunPod API format for easy client integration
"""

import base64
import binascii
import os
import tempfile
from typing import Any, Iterable, Optional, Protocol, cast

from flask import Flask, jsonify, request  # type: ignore
from faster_whisper import WhisperModel  # type: ignore


app: Flask = Flask(__name__)  # type: ignore

# Pre-load models to avoid loading on each request
MODELS: dict[str, WhisperModel] = {}
SUPPORTED_MODELS: set[str] = {
    "large-v3-turbo",
    "large-v3",
    "large",
    "medium",
    "small",
    "base",
    "tiny",
}
MIN_BEAM_SIZE = 1
MAX_BEAM_SIZE = 10


class SegmentLike(Protocol):
    start: float
    end: float
    text: str


class TranscriptionInfoLike(Protocol):
    language: str


def get_model(model_name: str = "large-v3-turbo") -> WhisperModel:
    """Get or load a Whisper model"""
    if model_name not in MODELS:
        print(f"Loading model: {model_name}", flush=True)
        MODELS[model_name] = WhisperModel(
            model_name, device="cuda", compute_type="float16"
        )
        print(f"Model loaded: {model_name}", flush=True)
    return MODELS[model_name]


def parse_beam_size(value: Any) -> int:
    try:
        beam_size = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("beam_size must be an integer") from exc
    if beam_size < MIN_BEAM_SIZE or beam_size > MAX_BEAM_SIZE:
        raise ValueError(
            f"beam_size must be between {MIN_BEAM_SIZE} and {MAX_BEAM_SIZE}"
        )
    return beam_size


@app.route("/health", methods=["GET"])  # type: ignore
def health() -> Any:
    """Health check endpoint"""
    return cast(Any, jsonify({"status": "healthy"}))


@app.route("/v2/<endpoint_id>/run", methods=["POST"])  # type: ignore
def transcribe(_endpoint_id: str) -> Any:
    """
    Transcribe audio using faster-whisper
    Compatible with RunPod API format
    """
    try:
        req = cast(Any, request)
        data = cast(dict[str, Any], req.get_json(silent=True) or {})
        input_data = cast(dict[str, Any], data.get("input", {}))

        # Extract parameters
        audio_b64 = cast(Optional[str], input_data.get("audio_base_64"))
        model_raw = input_data.get("model", "large-v3-turbo")
        if not isinstance(model_raw, str):
            return jsonify({"error": "Invalid model type, expected string"}), 400
        translate = bool(input_data.get("translate", False))
        language = cast(str, input_data.get("language", "auto"))
        try:
            beam_size = parse_beam_size(input_data.get("beam_size", 5))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not audio_b64:
            return jsonify({"error": "No audio_base_64 provided"}), 400

        model_name_key = model_raw.strip().lower()
        model_name = model_name_key if model_name_key in SUPPORTED_MODELS else None
        if model_name is None:
            return (
                jsonify(
                    {
                        "error": "Unsupported model",
                        "supported_models": sorted(SUPPORTED_MODELS),
                    }
                ),
                400,
            )

        # Decode audio from base64
        try:
            audio_data = base64.b64decode(audio_b64)
        except (binascii.Error, TypeError):
            return jsonify({"error": "invalid base64 audio payload"}), 400

        # Write to temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            audio_path = f.name

        try:
            # Get model and transcribe
            model = get_model(model_name)
            task = "translate" if translate else "transcribe"

            segments, info = cast(Any, model).transcribe(
                audio_path,
                task=task,
                language=None if language == "auto" else language,
                beam_size=beam_size,
            )

            segments_iter = cast(Iterable[SegmentLike], segments)
            info_data = cast(TranscriptionInfoLike, info)

            # Convert segments to list
            segments_list: list[dict[str, Any]] = []
            for segment in segments_iter:
                segments_list.append(
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text,
                    }
                )

            # Return in RunPod-compatible format (synchronous)
            return cast(
                Any,
                jsonify(
                    {
                        "id": "sync-job",
                        "status": "COMPLETED",
                        "output": {
                            "segments": segments_list,
                            "detected_language": info_data.language,
                        },
                    }
                ),
            )

        finally:
            # Clean up temp file
            if os.path.exists(audio_path):
                os.unlink(audio_path)

    except Exception as e:
        return cast(
            Any,
            jsonify({"id": "error", "status": "FAILED", "error": str(e)}),
        ), 500


if __name__ == "__main__":
    print("Pre-loading models...", flush=True)
    get_model("large-v3-turbo")
    get_model("large-v3")
    print("Models loaded. Starting server...", flush=True)
    app.run(host="0.0.0.0", port=8000, debug=False)  # type: ignore
