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
