# 🎬 LiveVTT - Real-time Speech-to-Caption Integration

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Wowza](https://img.shields.io/badge/Wowza-4.9.4-orange.svg)](https://www.wowza.com/)
[![Status](https://img.shields.io/badge/Status-Production_Ready-brightgreen.svg)](#)

LiveVTT is a production-ready solution for real-time speech transcription and live caption delivery to Wowza Streaming Engine. It provides seamless integration between automatic speech recognition and live streaming platforms.

## 🚀 Features

- **Real-time Transcription**: Powered by OpenAI Whisper for high-quality speech-to-text
- **Multi-language Support**: Supports 99+ languages including Russian, English, Spanish, etc.
- **Wowza Integration**: Direct HTTP API integration with Wowza Streaming Engine
- **Live Streaming**: Compatible with HLS, RTMP, and other streaming protocols
- **Filter System**: Built-in content filtering for clean captions
- **Production Ready**: Comprehensive error handling and logging

## 📋 Requirements

- Python 3.11+
- Wowza Streaming Engine 4.9.4+
- Java 21+ (for Wowza modules)
- FFmpeg (for audio processing)
- GPU support (optional, for faster transcription)

## 🛠️ Installation

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/livevtt.git
   cd livevtt
   ```

### 2. Install Python Dependencies
   ```bash
   pip install -r requirements.txt
   ```

### 3. Build Wowza Module
```bash
chmod +x java_module_build.sh
./java_module_build.sh
```

### 4. Configure Wowza
Follow the detailed setup in [WOWZA_SETUP.md](WOWZA_SETUP.md)

## 🎯 Quick Start

### Basic Usage
```bash
# Transcribe Russian live stream with RTMP output
python main.py \
  --url "https://example.com/stream/playlist.m3u8" \
  --language ru \
  --rtmp-url "rtmp://localhost:1935/live/myStream" \
  --rtmp-http-port 8086
```

### Real-world Example
```bash
# TVRain stream with Russian captions
python main.py \
  -u "https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8" \
  -la ru \
  --rtmp-url "rtmp://localhost:1935/live/tvrain" \
  --rtmp-http-port 8086 \
  --beam-transcription
```

## 🔧 Configuration

### Command Line Options
```bash
# Core options
--url URL                    # HLS stream URL to transcribe
--language LANG             # Language code (ru, en, es, etc.)
--rtmp-url URL              # Wowza RTMP endpoint
--rtmp-http-port PORT       # HTTP API port (default: 8086)

# Advanced options
--model MODEL               # Whisper model (tiny, base, small, medium, large)
--beam-transcription        # Enable beam search for better accuracy
--use-cuda                  # Enable GPU acceleration
--filter-file FILE          # Content filter configuration
--rtmp-track-id ID          # Caption track ID (default: 99)
--custom-vocab FILE        # Custom vocabulary file (default: custom_vocab.json)
```

### Custom Vocabulary
LiveVTT supports language-specific custom vocabulary to improve transcription accuracy. Create a `custom_vocab.json` file:

```json
{
    "en": {
        "vocabulary": [
            "LiveVTT",
            "Wowza",
            "RTMP",
            "WebVTT",
            "HLS"
        ]
    },
    "ru": {
        "vocabulary": [
            "Прямой эфир",
            "трансляция",
            "субтитры"
        ]
    }
}
```

The vocabulary file is loaded automatically if present. You can specify a different file with `--custom-vocab`.

### Environment Variables
```bash
export LIVEVTT_MODEL="medium"
export LIVEVTT_LANGUAGE="ru"
export LIVEVTT_WOWZA_PORT="8086"
```

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│   HLS Stream    │───▶│   LiveVTT    │───▶│ Wowza Streaming │
│   (Video/Audio) │    │  Transcriber │    │     Engine      │
└─────────────────┘    └──────────────┘    └─────────────────┘
                              │                       │
                              ▼                       ▼
                       ┌──────────────┐    ┌─────────────────┐
                       │   Whisper    │    │  HLS + Captions │
                       │    Model     │    │   (WebVTT)      │
                       └──────────────┘    └─────────────────┘
```

## 🔌 Wowza Integration

### HTTP API Endpoints
   ```bash
# Send caption to stream
curl -X POST "http://localhost:8086/livevtt/captions" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Caption text here",
    "lang": "eng",
    "trackid": 99,
    "streamname": "myStream"
  }'

# Check provider status
curl "http://localhost:8086/livevtt/captions/status"
   ```

### Response Format
   ```json
   {
  "success": true,
  "message": "Caption added successfully"
   }
   ```

## 📊 Performance

### Typical Metrics
- **Latency**: 2-5 seconds for real-time transcription
- **Accuracy**: 95%+ for clear audio (language-dependent)
- **Memory**: 2-8GB RAM (model-dependent)
- **CPU**: 50-80% usage (without GPU)

### Optimization Tips
- Use GPU acceleration with `--use-cuda`
- Choose appropriate model size for your hardware
- Enable beam search for better accuracy
- Use content filtering for cleaner output

## 🧪 Testing

### Manual Testing
   ```bash
# Start test stream
python test_caption_generator.py

# Test caption API
python test_caption.py --server localhost --port 8086

# Full integration test
python test_final_integration.py
```

### Automated Testing
```bash
# Run all tests
python -m pytest tests/

# Integration tests
python test_integration.py
```

## 🔧 Troubleshooting

### Common Issues

#### 404 Errors from Wowza
   ```bash
# Check module is loaded
curl "http://localhost:8086/livevtt/captions/status"

# Verify Wowza configuration
grep -r "LiveVTTCaptionModule" /usr/local/WowzaStreamingEngine/conf/
```

#### Caption Not Appearing
1. Verify stream is publishing: Check Wowza Manager
2. Test caption API directly: Use curl commands above
3. Check Wowza logs: Look for "LiveVTTCaptionHTTPProvider" messages

#### Performance Issues
1. Reduce model size: Use `--model tiny` or `--model base`
2. Enable GPU: Add `--use-cuda` flag
3. Adjust chunk size: Modify HLS segment duration

### Debug Mode
   ```bash
# Enable detailed logging
python main.py --debug --url "stream_url" --language ru
```

## 📖 Documentation

- [Wowza Setup Guide](WOWZA_SETUP.md) - Complete Wowza configuration
- [Testing Guide](TESTING.md) - Comprehensive testing procedures
- [Changelog](CHANGELOG.md) - Version history and updates

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
