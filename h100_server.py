#!/usr/bin/env python3
"""
H100 Server for Faster-Whisper Transcription
Runs on RunPod H100 GPU to process audio transcription requests
Compatible with RunPod API format for easy client integration
"""

import base64
import tempfile
import os
from flask import Flask, request, jsonify
from faster_whisper import WhisperModel

app = Flask(__name__)

# Pre-load models to avoid loading on each request
MODELS = {}

def get_model(model_name="large-v3-turbo"):
    """Get or load a Whisper model"""
    if model_name not in MODELS:
        print(f"Loading model: {model_name}", flush=True)
        MODELS[model_name] = WhisperModel(
            model_name,
            device="cuda",
            compute_type="float16"
        )
        print(f"Model loaded: {model_name}", flush=True)
    return MODELS[model_name]

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route('/v2/<endpoint_id>/run', methods=['POST'])
def transcribe(endpoint_id):
    """
    Transcribe audio using faster-whisper
    Compatible with RunPod API format
    """
    try:
        data = request.json
        input_data = data.get("input", {})
        
        # Extract parameters
        audio_b64 = input_data.get("audio_base_64")
        model_name = input_data.get("model", "large-v3-turbo")
        translate = input_data.get("translate", False)
        language = input_data.get("language", "auto")
        beam_size = input_data.get("beam_size", 5)
        
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
            
            segments, info = model.transcribe(
                audio_path,
                task=task,
                language=None if language == "auto" else language,
                beam_size=beam_size,
            )
            
            # Convert segments to list
            segments_list = []
            for segment in segments:
                segments_list.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                })
            
            # Return in RunPod-compatible format (synchronous)
            return jsonify({
                "id": "sync-job",
                "status": "COMPLETED",
                "output": {
                    "segments": segments_list,
                    "detected_language": info.language,
                }
            })
            
        finally:
            # Clean up temp file
            if os.path.exists(audio_path):
                os.unlink(audio_path)
            
    except Exception as e:
        return jsonify({
            "id": "error",
            "status": "FAILED",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    print("Pre-loading models...", flush=True)
    get_model("large-v3-turbo")
    get_model("large-v3")
    print("Models loaded. Starting server...", flush=True)
    app.run(host='0.0.0.0', port=8000, debug=False)
