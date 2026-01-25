#!/usr/bin/env python3
"""
Remote Whisper inference server for cloud GPU deployment.

Receives audio files via HTTP, runs Faster-Whisper inference,
returns VTT transcriptions and translations.
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
import uvicorn

app = FastAPI()

# Global model cache
models = {}


def get_model(
    model_name: str = "large-v3-turbo",
    device: str = "cuda",
    compute_type: str = "float16",
) -> WhisperModel:
    """Get or load Whisper model (cached)."""
    key = f"{model_name}_{device}_{compute_type}"
    if key not in models:
        models[key] = WhisperModel(model_name, device=device, compute_type=compute_type)
    return models[key]


def segments_to_vtt(segments, prepend_header: bool = True) -> str:
    """Convert segments to WebVTT format."""

    def format_timestamp(seconds: float) -> str:
        total_ms = int(seconds * 1000)
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"

    lines = []
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

        lines.append(str(cue_idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
        cue_idx += 1

    return "\n".join(lines).rstrip() + "\n"


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    model_name: str = Form("large-v3-turbo"),
    translation_model: str = Form("large-v3"),
    source_language: str = Form("ru"),
    beam_size: int = Form(5),
    compute_type: str = Form("float16"),
    vad_filter: bool = Form(False),
):
    """
    Transcribe and translate audio file.

    Returns JSON with:
    - ru_vtt: Russian transcription (WebVTT)
    - en_vtt: English translation (WebVTT)
    - duration: Audio duration in seconds
    """
    try:
        # Save uploaded audio to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            content = await audio.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Transcription (Russian)
        model = get_model(model_name, compute_type=compute_type)
        ru_iter, ru_info = model.transcribe(
            tmp_path,
            beam_size=beam_size,
            language=source_language,
            vad_filter=vad_filter,
            task="transcribe",
        )
        ru_segments = list(ru_iter)
        ru_vtt = segments_to_vtt(ru_segments)

        # Translation (English)
        translation_model_obj = get_model(translation_model, compute_type=compute_type)
        en_iter, en_info = translation_model_obj.transcribe(
            tmp_path,
            beam_size=beam_size,
            language=source_language,
            vad_filter=vad_filter,
            task="translate",
        )
        en_segments = list(en_iter)
        en_vtt = segments_to_vtt(en_segments)

        # Cleanup
        Path(tmp_path).unlink()

        duration = max(
            ru_info.duration if ru_info else 0.0, en_info.duration if en_info else 0.0
        )

        return JSONResponse(
            {
                "status": "success",
                "ru_vtt": ru_vtt,
                "en_vtt": en_vtt,
                "duration": duration,
            }
        )

    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "models_loaded": len(models)}


if __name__ == "__main__":
    # Load models on startup
    print("Loading models...")
    get_model("large-v3-turbo")
    get_model("large-v3")
    print("Models loaded. Starting server...")

    uvicorn.run(app, host="0.0.0.0", port=8000)
