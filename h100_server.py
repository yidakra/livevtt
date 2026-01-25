#!/usr/bin/env python3
"""
H100 Server for Faster-Whisper Transcription
Runs on RunPod H100 GPU to process audio transcription requests
Compatible with RunPod API format for easy client integration
"""

import base64
import os
import tempfile
from typing import Any, Callable, Iterable, Optional, Protocol, cast

from flask import Flask, jsonify, request  # type: ignore
from faster_whisper import WhisperModel  # type: ignore


class FlaskLike(Protocol):
    def route(
        self, rule: str, methods: Optional[list[str]] = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...

    def run(self, host: str, port: int, debug: bool) -> None: ...


app: FlaskLike = cast(FlaskLike, Flask(__name__))

# Pre-load models to avoid loading on each request
MODELS: dict[str, WhisperModel] = {}


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


@app.route("/health", methods=["GET"])
def health() -> Any:
    """Health check endpoint"""
    return cast(Any, jsonify({"status": "healthy"}))


@app.route("/v2/<endpoint_id>/run", methods=["POST"])
def transcribe(endpoint_id: str) -> Any:
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
        model_name = cast(str, input_data.get("model", "large-v3-turbo"))
        translate = bool(input_data.get("translate", False))
        language = cast(str, input_data.get("language", "auto"))
        beam_size = int(input_data.get("beam_size", 5))

        if not audio_b64:
            return jsonify({"error": "No audio_base_64 provided"}), 400

        # Decode audio from base64
        audio_data = base64.b64decode(audio_b64)

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
    app.run(host="0.0.0.0", port=8000, debug=False)
