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
- [`test_final_integration.py`](#test_final_integrationpy) - System health check
- [`caption_sender.py`](#caption_senderpy) - Send captions to streams  
- [`stream_checker.py`](#stream_checkerpy) - Check stream status

---

## 🎯 What is LiveVTT?

LiveVTT enables real-time caption delivery to live video streams. It consists of:

- **Wowza Module**: Java module that integrates with Wowza Streaming Engine
- **HTTP API**: RESTful endpoint for caption submission (`/livevtt/captions`)
- **Testing Tools**: Python utilities for testing and monitoring
- **WebVTT Output**: Standards-compliant caption tracks in HLS/DASH streams

### Key Features
- ✅ Real-time caption delivery to live streams
- ✅ Multiple language support (ISO 639-2 codes)
- ✅ HTTP-based API for easy integration
- ✅ WebVTT format compatibility
- ✅ HLS and DASH streaming support
- ✅ Memory-efficient processing
- ✅ Production-ready monitoring

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
./java_module_build.sh
cp build/livevtt-caption-module.jar /usr/local/WowzaStreamingEngine/lib/

# Configure Wowza (see deployment guide for details)
# Restart Wowza
sudo service WowzaStreamingEngine restart
```

### 3. Verify Installation
```bash
# Run health check
python test_final_integration.py

# Test caption API
python caption_sender.py --stream testStream --count 1
```

**More details**: See [**Deployment Guide →**](docs/DEPLOYMENT.md)

---

## 🛠️ Essential Tools

### `test_final_integration.py`
**Comprehensive system health check and integration testing**

```bash
# Basic health check
python test_final_integration.py

# Expected output:
# 🚀 Starting LiveVTT Integration Test
# ✅ Wowza process found, memory usage: 0.5%
# ✅ LiveVTT Caption Module loaded
# ✅ Memory usage stable
# ✅ Caption API responding correctly
# 🎉 ALL TESTS PASSED!
```

### `caption_sender.py`
**Interactive tool for sending captions to live streams**

```bash
# Send single caption
python caption_sender.py --stream myStream

# Multiple captions with custom settings
python caption_sender.py --stream myShow --count 10 --interval 2 --language spa

# With authentication
python caption_sender.py --stream secure --username admin --password secret
```

### `stream_checker.py`
**Check for active streams and get setup guidance**

```bash
# Check stream status
python stream_checker.py

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
python test_final_integration.py

# 2. Check for active streams  
python stream_checker.py

# 3. Send test caption
python caption_sender.py --stream testStream
```

### Production Testing
```bash
# Start live stream
ffmpeg -re -i video.mp4 -c copy -f flv rtmp://localhost:1935/live/productionStream

# Send captions
python caption_sender.py --stream productionStream --count 5 --interval 3

# Monitor in video player
# HLS: http://localhost:8088/live/productionStream/playlist.m3u8
```

**More details**: See [**Testing Guide →**](docs/TESTING.md)

---

## 🌐 Language Support

LiveVTT supports multiple languages using ISO 639-2 codes:

| Language | Code | Example Usage |
|----------|------|---------------|
| English | `eng` | `python caption_sender.py --language eng --text "English caption"` |
| Spanish | `spa` | `python caption_sender.py --language spa --text "Subtítulo en español"` |
| French | `fra` | `python caption_sender.py --language fra --text "Légende française"` |
| German | `deu` | `python caption_sender.py --language deu --text "Deutsche Untertitel"` |

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
python stream_checker.py  # Check if streams are active
# Start test stream if needed:
ffmpeg -re -i video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream
```

**More troubleshooting**: See [**Testing Guide →**](docs/TESTING.md#debugging-and-troubleshooting)

---

## 📊 Performance

**Typical metrics on production systems:**
- Memory usage: 0.5-2% of system RAM
- CPU overhead: <1% for caption processing  
- Latency: <100ms caption delivery
- Throughput: 1000+ captions/minute per stream

**Load testing**:
```bash
# Test multiple concurrent streams
for i in {1..10}; do
  python caption_sender.py --stream "stream$i" --count 100 --interval 0.1 &
done
```

---

## 🔧 Configuration Files

| File | Purpose | Documentation |
|------|---------|---------------|
| `Application.xml` | Wowza module configuration | [Setup Guide →](docs/WOWZA_SETUP.md) |
| `VHost.xml` | HTTP provider configuration | [Setup Guide →](docs/WOWZA_SETUP.md) |
| `requirements.txt` | Python dependencies | [Tools Guide →](docs/TOOLS.md) |
| `java_module_build.sh` | Build script | [Deployment Guide →](docs/DEPLOYMENT.md) |

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
├── caption_sender.py              # Interactive caption tool
├── stream_checker.py              # Stream status checker
├── test_final_integration.py      # Integration test suite
├── LiveVTTCaptionModule.java      # Wowza Java module
├── LiveVTTCaptionHTTPProvider.java # HTTP API provider
└── java_module_build.sh           # Build script
```

---

## 🎥 Live Demo

Want to see LiveVTT in action? 

**See**: [**Demo Guide →**](docs/DEMO.md) for step-by-step demonstration instructions.

---

## 📞 Support

### Getting Help

1. **Start with health check**: `python test_final_integration.py`
2. **Check documentation**: Review relevant guide above
3. **Run diagnostics**: `python stream_checker.py`
4. **Check logs**: `/usr/local/WowzaStreamingEngine/logs/`

### Useful Commands

```bash
# System status
python test_final_integration.py

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

---

**Ready to get started?** 👉 [**Deployment Guide →**](docs/DEPLOYMENT.md)
