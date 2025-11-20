# LiveVTT Caption Integration

Real-time caption delivery for live video streams using Wowza Streaming Engine.

## 📋 Table of Contents

### 🚀 Quick Start
- [**Installation & Setup**](docs/DEPLOYMENT.md) - Get LiveVTT running quickly
- [**Testing Guide**](docs/TESTING.md) - Verify your installation works
- [**API Reference**](docs/API.md) - Complete API documentation

### 📚 Documentation
- [**Tools Guide**](docs/TOOLS.md) - Essential tools and utilities
- [**Wowza Setup**](docs/WOWZA_SETUP.md) - Detailed Wowza configuration
- [**Demo Guide**](docs/DEMO.md) - Live demonstration instructions

### 🛠️ Essential Tools
- [`test_integration`](#test_integration) - System health check
- [`caption_sender`](#caption_sender) - Send captions to streams  
- [`stream_checker`](#stream_checker) - Check stream status

---

## 🎯 What is LiveVTT?

LiveVTT enables real-time caption delivery to live video streams. It consists of:

- **Wowza Module**: Java module that integrates with Wowza Streaming Engine
- **HTTP API**: RESTful endpoint for caption submission (`/livevtt/captions`)
- **Testing Tools**: Python utilities for testing and monitoring
- **WebVTT Output**: Standards-compliant caption tracks in HLS streams

---

## 🚀 Quick Start

### 1. System Requirements
- Wowza Streaming Engine 4.9.4+
- Java Development Kit 8+
- Python 3.7+ (for testing tools)
- Network access to ports 1935 (RTMP) and 8086 (Caption API)

### 2. Installation (3 commands)
```bash
# Build and deploy the module
./build.sh
cp build/livevtt-caption-module.jar /usr/local/WowzaStreamingEngine/lib/

# Configure Wowza (see deployment guide for details)
# Restart Wowza
sudo service WowzaStreamingEngine restart
```

### 3. Verify Installation
```bash
# Run health check
./test_integration

# Test caption API
./caption_sender --stream testStream --count 1
```

**More details**: See [**Deployment Guide →**](docs/DEPLOYMENT.md)

---

## 🛠️ Essential Tools

### `archive_transcriber`
**Batch transcription of archived broadcast chunks with bilingual WebVTT output**

```bash
# Activate virtual environment (recommended)
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Install system dependencies (Ubuntu example)
sudo apt-get install -y ffmpeg
# Optional GPU acceleration
sudo apt-get install -y nvidia-driver-535 nvidia-cuda-toolkit libcudnn9-cuda-13 libcudnn9-dev-cuda-13

# Transcribe a single unprocessed video
python src/python/tools/archive_transcriber.py --max-files 1 --progress
```

Generates `<hash>.ru.vtt` (source-language transcript), `<hash>.en.vtt` (English translation), and `<hash>.smil` manifest files alongside the source (or under `--output-root`). Uses `/mnt/vod/srv/storage/transcoded/` as the default archive root; pass a path to override.

### `nllb_vtt_translator`
**High-quality translation of existing Russian VTT files using Meta's NLLB-200 model**

```bash
# Install NLLB dependencies (one-time setup)
poetry install -E nllb
# OR with pip:
pip install transformers torch sentencepiece

# Translate all *.ru.vtt files in a directory
python src/python/tools/nllb_vtt_translator.py /path/to/archive --progress

# Limit to first 10 files for testing
python src/python/tools/nllb_vtt_translator.py /path/to/archive --max-files 10 --progress

# Use smaller/faster model (600M parameters)
python src/python/tools/nllb_vtt_translator.py /path/to/archive --model facebook/nllb-200-distilled-600M

# Use larger model for best quality (3.3B parameters, requires ~13GB GPU RAM)
python src/python/tools/nllb_vtt_translator.py /path/to/archive --model facebook/nllb-200-3.3B

# Force CPU (no GPU)
python src/python/tools/nllb_vtt_translator.py /path/to/archive --device cpu
```

Scans for `*.ru.vtt` files and generates `*.nllb.en.vtt` translations using NLLB-200, preserving original timestamps. This allows quality comparison between Whisper's translation (`*.en.vtt`) and NLLB-200's translation (`*.nllb.en.vtt`) without modifying the existing transcription pipeline.

**Why NLLB?** Meta's NLLB-200 (No Language Left Behind) model provides significantly better translation quality than Whisper's translation mode, especially for Russian→English. It's also much faster since it only translates text rather than reprocessing audio.

### `libretranslate_vtt_translator`
**Lightweight translation using LibreTranslate API (self-hosted or cloud)**

```bash
# No dependencies required! Uses HTTP API

# Use public LibreTranslate instance (free, rate-limited)
python src/python/tools/libretranslate_vtt_translator.py /path/to/archive --progress

# Use self-hosted instance
python src/python/tools/libretranslate_vtt_translator.py /path/to/archive \
  --api-url http://localhost:5000/translate \
  --progress

# With API key (if required by your instance)
python src/python/tools/libretranslate_vtt_translator.py /path/to/archive \
  --api-url https://your-instance.com/translate \
  --api-key YOUR_API_KEY \
  --progress

# Limit to first 10 files for testing
python src/python/tools/libretranslate_vtt_translator.py /path/to/archive --max-files 10 --progress

# Adjust delay for rate limiting (default 0.1s between requests)
python src/python/tools/libretranslate_vtt_translator.py /path/to/archive --delay 0.5 --progress
```

Scans for `*.ru.vtt` files and generates `*.libretranslate.en.vtt` translations using LibreTranslate API, preserving original timestamps. This allows quality comparison between Whisper (`*.en.vtt`), NLLB (`*.nllb.en.vtt`), and LibreTranslate (`*.libretranslate.en.vtt`) translations.

**Why LibreTranslate?**
- **No ML dependencies**: Uses HTTP API, no need for transformers/torch
- **Lightweight**: Works on any machine without GPU
- **Self-hostable**: Run your own instance for unlimited, private translations
- **Free tier available**: Public instance at libretranslate.com (rate-limited)
- **Good quality**: Uses Argos Translate models under the hood

**Self-hosting LibreTranslate:**
```bash
# Quick Docker setup
docker run -ti --rm -p 5000:5000 libretranslate/libretranslate

# Then use it:
python src/python/tools/libretranslate_vtt_translator.py /path/to/archive \
  --api-url http://localhost:5000/translate
```

### `mistral_vtt_translator`
**LLM-powered translation using Mistral or compatible APIs**

```bash
# No dependencies required! Uses HTTP API

# Use Mistral API (requires API key) - mistral-large-latest for best quality
python src/python/tools/mistral_vtt_translator.py /path/to/archive \
  --api-url https://api.mistral.ai/v1/chat/completions \
  --api-key YOUR_MISTRAL_API_KEY \
  --model mistral-large-latest \
  --progress

# Use local inference server (vLLM, llama.cpp, Ollama, etc.)
python src/python/tools/mistral_vtt_translator.py /path/to/archive \
  --api-url http://localhost:8000/v1/chat/completions \
  --model mistral-7b \
  --progress

# With custom system prompt for context
python src/python/tools/mistral_vtt_translator.py /path/to/archive \
  --api-url http://localhost:8000/v1/chat/completions \
  --model mistral-7b \
  --system-prompt "You are a professional translator specializing in broadcast subtitles. Translate naturally and fluently." \
  --temperature 0.2 \
  --progress

# Limit to first 10 files for testing
python src/python/tools/mistral_vtt_translator.py /path/to/archive --max-files 10 --progress
```

Scans for `*.ru.vtt` files and generates `*.mistral.en.vtt` translations using Mistral LLM or any OpenAI-compatible API, preserving original timestamps. This allows quality comparison between Whisper (`*.en.vtt`), NLLB (`*.nllb.en.vtt`), LibreTranslate (`*.libretranslate.en.vtt`), and Mistral (`*.mistral.en.vtt`) translations.

**Why Mistral LLM?**
- **State-of-the-art quality**: LLMs excel at nuanced, context-aware translation
- **No ML dependencies**: Uses HTTP API (like LibreTranslate)
- **Flexible**: Works with Mistral API, local vLLM, Ollama, llama.cpp servers
- **Customizable**: Adjust prompts, temperature, and model selection
- **Best for context**: Excellent handling of idioms, cultural references, technical terms

**Local inference options:**
```bash
# Option 1: vLLM (fast, GPU-optimized)
vllm serve mistralai/Mistral-7B-Instruct-v0.2 --host 0.0.0.0 --port 8000

# Option 2: Ollama (easy setup)
ollama pull mistral
ollama serve

# Option 3: llama.cpp (CPU-friendly)
./server -m mistral-7b-instruct-v0.2.Q4_K_M.gguf --port 8000

# Then use local endpoint:
python src/python/tools/mistral_vtt_translator.py /path/to/archive \
  --api-url http://localhost:8000/v1/chat/completions \
  --model mistral
```

### `subtitle_autogen`
**Polling service for automated transcription + SMIL regeneration**

```bash
python src/python/services/subtitle_autogen.py /mnt/vod/srv/storage/transcoded/ --batch-size 5 --interval 300

# SMIL touch-ups only
python src/python/services/subtitle_autogen.py /mnt/vod/srv/storage/transcoded/ --smil-only --batch-size 20 --interval 600
```

### `test_integration`
**Comprehensive system health check and integration testing**

```bash
# Basic health check
./test_integration

# Expected output:
# 🚀 Starting LiveVTT Integration Test
# ✅ Wowza process found, memory usage: 0.5%
# ✅ LiveVTT Caption Module loaded
# ✅ Memory usage stable
# ✅ Caption API responding correctly
# 🎉 ALL TESTS PASSED!
```

### `caption_sender`
**Interactive tool for sending captions to live streams**

```bash
# Send single caption
./caption_sender --stream myStream

# Multiple captions with custom settings
./caption_sender --stream myShow --count 10 --interval 2 --language spa

# With authentication
./caption_sender --stream secure --username admin --password secret
```

### `stream_checker`
**Check for active streams and get setup guidance**

```bash
# Check stream status
./stream_checker

# Provides RTMP setup guidance if no streams found:
# 💡 To test with live streams, publish RTMP first:
#    ffmpeg -re -i video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream
```

**More details**: See [**Tools Guide →**](docs/TOOLS.md)

---

## 📡 API Usage

Send captions via HTTP POST to `http://localhost:8086/livevtt/captions`:

```bash
curl -X POST http://localhost:8086/livevtt/captions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "This is a live caption",
    "lang": "eng", 
    "trackid": 99,
    "streamname": "myLiveStream"
  }'
```

**Response codes**:
- `200` - Caption sent successfully to live stream
- `404` - Stream not found (check if RTMP stream is publishing)
- `400` - Invalid request format
- `500` - Server error

**More details**: See [**API Reference →**](docs/API.md)

---

## 🧪 Testing Workflows

### Development Testing
```bash
# 1. Health check
./test_integration

# 2. Check for active streams  
./stream_checker

# 3. Send test caption
./caption_sender --stream testStream
```

### Production Testing
```bash
# Start live stream
ffmpeg -re -i video.mp4 -c copy -f flv rtmp://localhost:1935/live/productionStream

# Send captions
./caption_sender --stream productionStream --count 5 --interval 3

# Monitor in video player
# HLS: http://localhost:8088/live/productionStream/playlist.m3u8
```

**More details**: See [**Testing Guide →**](docs/TESTING.md)

---

## 🌐 Language Support

LiveVTT supports multiple languages using ISO 639-2 codes:

| Language | Code | Example Usage |
|----------|------|---------------|
| English | `eng` | `./caption_sender --language eng --text "English caption"` |
| Spanish | `spa` | `./caption_sender --language spa --text "Subtítulo en español"` |
| French | `fra` | `./caption_sender --language fra --text "Légende française"` |
| German | `deu` | `./caption_sender --language deu --text "Deutsche Untertitel"` |

**Full language reference**: See [**API Reference →**](docs/API.md#language-codes)

---

## 🚨 Troubleshooting

### Common Issues

**"Wowza process not found"**
```bash
sudo service WowzaStreamingEngine status
sudo service WowzaStreamingEngine restart
```

**"Caption API not responding"**
```bash
netstat -tlnp | grep :8086
curl -v http://localhost:8086/livevtt/captions
```

**"Stream not found"**
```bash
./stream_checker  # Check if streams are active
# Start test stream if needed:
ffmpeg -re -i video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream
```

**More troubleshooting**: See [**Testing Guide →**](docs/TESTING.md#debugging-and-troubleshooting)

---

## 🔧 Configuration Files

| File | Purpose | Documentation |
|------|---------|---------------|
| `config/examples/Application.xml.example` | Wowza module configuration | [Setup Guide →](docs/WOWZA_SETUP.md) |
| `config/examples/VHost.xml.example` | HTTP provider configuration | [Setup Guide →](docs/WOWZA_SETUP.md) |
| `requirements.txt` | Python dependencies | [Tools Guide →](docs/TOOLS.md) |
| `deploy/scripts/java_module_build.sh` | Build script | [Deployment Guide →](docs/DEPLOYMENT.md) |

---

## 📁 Project Structure

```
livevtt/
├── docs/                          # All documentation
│   ├── API.md                     # Complete API reference
│   ├── DEPLOYMENT.md              # Installation & deployment
│   ├── TESTING.md                 # Testing procedures  
│   ├── TOOLS.md                   # Tools documentation
│   ├── WOWZA_SETUP.md            # Detailed Wowza setup
│   └── DEMO.md                    # Demo instructions
├── src/                           # Source code
│   ├── java/                      # Java modules
│   │   ├── LiveVTTCaptionModule.java
│   │   └── LiveVTTCaptionHTTPProvider.java
│   └── python/                    # Python utilities
│       ├── tools/                 # Essential tools
│       │   ├── caption_sender.py
│       │   ├── stream_checker.py
│       │   └── test_final_integration.py
│       └── utils/                 # Supporting utilities
├── config/                        # Configuration files
│   ├── vocabulary.json
│   ├── filter.json
│   └── examples/                  # Configuration examples
├── deploy/                        # Deployment files
│   ├── scripts/
│   │   └── java_module_build.sh
│   ├── Dockerfile
│   └── docker-compose.yml
├── build/                         # Build output
├── caption_sender                 # Convenience scripts
├── stream_checker
├── test_integration
└── build.sh                      # Build convenience script
```

---

## 🎥 Live Demo

Want to see LiveVTT in action? 

**See**: [**Demo Guide →**](docs/DEMO.md) for step-by-step demonstration instructions.

---

## 📚 Reference Implementation

### Wowza onTextData Example

The `PublishOnTextData/` directory contains the official Wowza reference implementation for caption injection. This valuable resource includes:

- **Complete Java module** showing onTextData implementation
- **Detailed documentation** with setup instructions
- **Sample configuration** and caption files
- **Implementation patterns** used by LiveVTT

This reference code demonstrates the same core functionality that LiveVTT provides and serves as excellent documentation for understanding caption delivery at the Wowza level.

---

## 📞 Support

### Getting Help

1. **Start with health check**: `./test_integration`
2. **Check documentation**: Review relevant guide above
3. **Run diagnostics**: `./stream_checker`
4. **Check logs**: `/usr/local/WowzaStreamingEngine/logs/`

### Useful Commands

```bash
# System status
./test_integration

# API connectivity  
curl -v http://localhost:8086/livevtt/captions

# Check Wowza
ps aux | grep -i wowza
netstat -tlnp | grep :8086

# View logs
tail -f /usr/local/WowzaStreamingEngine/logs/wowzastreamingengine_error.log
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
