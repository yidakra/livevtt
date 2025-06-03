# LiveVTT Tools Guide

This document covers the essential tools for testing and using the LiveVTT Caption integration with Wowza.

## 🛠️ Available Tools

### 1. Caption Sender (`caption_sender.py`)

**Purpose**: Send captions to live streams with full configuration control.

**Usage**:
```bash
# Basic usage
python caption_sender.py --stream myStream

# Advanced usage
python caption_sender.py \
  --stream myStream \
  --server localhost \
  --port 8086 \
  --text "Custom caption text" \
  --language eng \
  --track-id 99 \
  --count 10 \
  --interval 2.0
```

**Options**:
- `--stream` (required): Target stream name
- `--server`: Wowza server hostname/IP (default: localhost)
- `--port`: Wowza HTTP port (default: 8086)
- `--text`: Caption text template (default: "This is a test caption")
- `--language`: Caption language code (default: eng)
- `--track-id`: Caption track ID (default: 99)
- `--username`: Username for authentication (optional)
- `--password`: Password for authentication (optional)
- `--count`: Number of captions to send (default: 1)
- `--interval`: Interval between captions in seconds (default: 1.0)

**Examples**:
```bash
# Send 5 captions to a live stream
python caption_sender.py --stream liveShow --count 5 --interval 3

# Send captions with authentication
python caption_sender.py --stream secureStream --username admin --password secret

# Send multilingual captions
python caption_sender.py --stream newsStream --language spa --text "Subtítulo en español"
```

### 2. Stream Checker (`stream_checker.py`)

**Purpose**: Check for active streams and get setup guidance.

**Usage**:
```bash
# Check default Wowza instance
python stream_checker.py

# Check remote Wowza
python stream_checker.py --host wowza.example.com --port 8088
```

**Features**:
- Detects active RTMP streams
- Provides RTMP publishing guidance
- Shows FFmpeg and OBS Studio setup examples
- Fallback detection via LiveVTT Caption API

**Sample Output**:
```
🔍 Checking stream status via LiveVTT Caption API
==================================================
⚠️  LiveVTT Caption API is working but no active streams found

💡 To test with live streams, publish RTMP first:
   # Using FFmpeg with a video file:
   ffmpeg -re -i your_video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream

   # Using OBS Studio:
   Server: rtmp://localhost:1935/live
   Stream Key: testStream

   Then test captions with:
   python caption_sender.py --stream testStream
```

### 3. Integration Test (`test_final_integration.py`)

**Purpose**: Comprehensive system health check and integration testing.

**Usage**:
```bash
# Run full integration test
python test_final_integration.py
```

**Tests Performed**:
1. **Wowza Status**: Process running, memory usage
2. **Module Loaded**: LiveVTT Caption Module responding
3. **Memory Stability**: Memory usage over time
4. **Caption API**: API endpoints working correctly

**Sample Output**:
```
🚀 Starting LiveVTT Integration Test
==================================================

📋 Running test: Wowza Status
✅ Wowza process found, memory usage: 0.5%

📋 Running test: Module Loaded
✅ LiveVTT Caption Module loaded

📋 Running test: Memory Stability
✅ Memory usage stable: avg=0.5%, range=0.5%-0.5%

📋 Running test: Caption API
✅ Caption API responding correctly

🎯 Overall: 4/4 tests passed
🎉 ALL TESTS PASSED! LiveVTT integration is working correctly.
```

## 🎯 Common Workflows

### Testing Without Live Streams

1. **Check System Health**:
   ```bash
   python test_final_integration.py
   ```

2. **Verify API Connectivity**:
   ```bash
   python caption_sender.py --stream testStream --count 1
   # Should show: ⚠️ Stream 'testStream' not found (API working)
   ```

### Testing With Live Streams

1. **Check for Active Streams**:
   ```bash
   python stream_checker.py
   ```

2. **Start a Test Stream** (if none active):
   ```bash
   # Using FFmpeg
   ffmpeg -re -i your_video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream
   
   # Or use OBS Studio with:
   # Server: rtmp://localhost:1935/live
   # Stream Key: testStream
   ```

3. **Send Test Captions**:
   ```bash
   python caption_sender.py --stream testStream --count 10 --interval 2
   # Should show: ✅ Caption sent successfully to live stream
   ```

### Continuous Caption Testing

For continuous caption testing during development:

```bash
# Method 1: Loop with different texts
while true; do 
  python caption_sender.py --stream myStream --text "Caption $(date +%H:%M:%S)"
  sleep 5
done

# Method 2: Multiple captions with interval
python caption_sender.py --stream myStream --count 100 --interval 5
```

## 🔧 Troubleshooting

### Common Issues

**"Stream not found" errors**:
- Check if RTMP stream is actively publishing
- Use `./stream_checker` to verify active streams
- Ensure stream name matches exactly

**Connection errors**:
- Verify Wowza is running: `ps aux | grep -i wowza`
- Check if port 8086 is listening: `netstat -tlnp | grep :8086`
- Run integration test: `./test_integration`

**Memory issues**:
- Integration test monitors memory usage
- Check Wowza configuration if memory usage is high
- Review logs: `/usr/local/WowzaStreamingEngine/logs/`

### Getting Help

1. **System Status**: `./test_integration`
2. **Stream Status**: `./stream_checker`  
3. **API Test**: `./caption_sender --stream test --count 1`

All tools provide helpful error messages and guidance for resolving issues.

## 📚 Reference Materials

### Wowza onTextData Reference Implementation

The `PublishOnTextData/` directory contains official Wowza reference code showing how to implement onTextData caption injection:

- **`src/ModulePublishOnTextData.java`**: Complete Wowza module implementation
- **`README.html`**: Detailed documentation and setup instructions  
- **`content/ontextdata.txt`**: Sample caption text file
- **Configuration examples**: Properties and module setup

This reference implementation demonstrates the same core functionality that LiveVTT provides, serving as valuable documentation for understanding how caption injection works at the Wowza level. 