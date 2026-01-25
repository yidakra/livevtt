# LiveVTT

Subtitle generation tools for live and archived streams. LiveVTT focuses on producing WebVTT/TTML assets and SMIL manifests for downstream players and packaging workflows.

## 🚀 Quick Start

### Requirements
- Python 3.10+
- FFmpeg + FFprobe: FFprobe is included with FFmpeg. Download from the [official FFmpeg site](https://ffmpeg.org/download.html). Install via `apt install ffmpeg` (Linux), `brew install ffmpeg` (macOS), or `choco install ffmpeg` (Windows).

### Install dependencies
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### Transcribe archived media
```bash
python src/python/tools/archive_transcriber.py /path/to/media --max-files 1 --progress  # Example: transcribe media in directory, process up to 1 file with progress display
```

### Run the polling service
```bash
python src/python/services/subtitle_autogen.py /path/to/watch --batch-size 5 --interval 300  # Example: watch directory for new files, batch size 5, poll every 300 seconds
```

## 🛠️ Core Tools

### `archive_transcriber`
Batch transcription of archived broadcast chunks with bilingual WebVTT output and SMIL manifest generation.

### `subtitle_autogen`
Polling service for automated transcription + SMIL regeneration.

### `test_integration`
System health check for the local toolchain.

## 📁 Project Structure

```
livevtt/
├── docs/                          # Documentation
│   └── DEMO.md                    # Demo instructions
├── src/                           # Source code
│   └── python/                    # Python utilities
│       ├── services/
│       ├── tools/
│       └── utils/
├── config/                        # Configuration files
│   ├── vocabulary.json
│   └── filter.json
├── deploy/                        # Deployment files
├── test_integration
└── main.py                        # Live transcription pipeline
```
