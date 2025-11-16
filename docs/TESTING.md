# LiveVTT Testing Guide

This document provides comprehensive testing procedures for the LiveVTT Caption integration with Wowza.

## Overview

The LiveVTT testing suite includes both integration tests and comprehensive unit tests:

### Integration Testing Tools
1. **test_final_integration.py** - Comprehensive system health check
2. **caption_sender.py** - Interactive caption testing tool
3. **stream_checker.py** - Stream status and setup verification

All tools provide helpful error messages and guidance for resolving issues.

### Unit Test Coverage
The project maintains **116 unit tests** with **65% code coverage** across all Python modules:
- **archive_transcriber.py**: 46% coverage (33 tests)
- **ttml_utils.py**: 92% coverage (21 tests)
- **vtt_to_ttml.py**: 68% coverage (14 tests)
- **subtitle_autogen.py**: 71% coverage (11 tests)
- **caption_sender.py**: 98% coverage (11 tests)
- **stream_checker.py**: 92% coverage (13 tests)
- **SMIL generation**: 100% coverage (8 tests)

See [tests/README.md](../tests/README.md) for detailed test documentation.

## 🚀 Quick Start Testing

### 1. System Health Check

```bash
# Run comprehensive integration test
python test_final_integration.py
```

**Expected Output**:
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

### 2. Check Stream Status

```bash
# Check for active streams and get setup guidance
python stream_checker.py
```

**Sample Output** (no active streams):
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

### 3. Send Test Captions

```bash
# Send a single test caption
python caption_sender.py --stream testStream

# Send multiple captions with custom settings
python caption_sender.py --stream myShow --count 5 --interval 2 --text "Live caption test"
```

### 4. Run Unit Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all unit tests
pytest tests/ -v

# Run specific test module
pytest tests/test_caption_sender.py -v

# Generate detailed coverage report (requires pytest-cov)
pytest tests/ --cov=src/python --cov-report=html
# Open htmlcov/index.html in browser for interactive report
```

**Expected Output**:
```
============================= test session starts ==============================
collected 116 items

tests/test_archive_transcriber.py ................................. [ 28%]
tests/test_caption_sender.py ........... [ 37%]
tests/test_smil_generation.py ........ [ 44%]
tests/test_stream_checker.py ............. [ 56%]
tests/test_subtitle_autogen.py ........... [ 65%]
tests/test_ttml_simple.py ..... [ 69%]
tests/test_ttml_utils.py ..................... [ 87%]
tests/test_vtt_to_ttml_cli.py .............. [100%]

============================= 116 passed in 0.69s ==============================
```

## 🔧 Testing Workflows

### Testing Without Live Streams

This is useful for API connectivity and configuration verification:

```bash
# 1. Check system health
python test_final_integration.py

# 2. Verify API responds (expect 404 - stream not found)
python caption_sender.py --stream testStream --count 1

# 3. Check stream status
python stream_checker.py
```

### Testing With Live Streams

For full end-to-end testing with actual video streams:

```bash
# 1. Start a test stream
ffmpeg -re -i test_video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream &

# 2. Verify stream is active
python stream_checker.py

# 3. Send test captions (should show success)
python caption_sender.py --stream testStream --count 10 --interval 2

# 4. Verify captions in player
# Browse to: http://localhost:8088/livevtt/testStream/playlist.m3u8
```

### Load Testing

```bash
# Test multiple concurrent caption streams
for i in {1..5}; do
  python caption_sender.py --stream "stream$i" --count 50 --interval 0.5 &
done

# Monitor system resources
python test_final_integration.py
```

### Development Testing Loop

```bash
# Quick development verification cycle
python test_final_integration.py && \
python caption_sender.py --stream dev --text "Development test $(date)" && \
echo "✅ Development tests passed"
```

## 🎯 Test Scenarios

### 1. Fresh Installation Testing

After deploying LiveVTT to a new server:

```bash
# Verify basic functionality
python test_final_integration.py

# Check configuration
python stream_checker.py

# Test API connectivity
python caption_sender.py --stream test --count 1
```

### 2. Production Health Monitoring

For ongoing production monitoring:

```bash
# Health check (can be automated)
python test_final_integration.py --quiet

# Stream availability check
python stream_checker.py --format json

# API response test
timeout 10 python caption_sender.py --stream health-check --count 1
```

### 3. Troubleshooting Workflow

When captions aren't working:

```bash
# 1. Check system status
python test_final_integration.py

# 2. Verify streams are active  
python stream_checker.py

# 3. Test API with detailed output
python caption_sender.py --stream problemStream --count 1 --verbose

# 4. Check logs (if needed)
tail -f /usr/local/WowzaStreamingEngine/logs/wowzastreamingengine_error.log
```

## 🌐 Multi-Language Testing

Test caption delivery in different languages:

```bash
# English
python caption_sender.py --stream multilang --language eng --text "English caption"

# Spanish  
python caption_sender.py --stream multilang --language spa --text "Subtítulo en español"

# French
python caption_sender.py --stream multilang --language fra --text "Légende française"
```

## 🔒 Authentication Testing

For secured Wowza configurations:

```bash
# Test with authentication
python caption_sender.py \
  --stream secureStream \
  --username admin \
  --password secret \
  --text "Authenticated caption"
```

## 📊 Performance Testing

### Memory Stability Testing

```bash
# Run extended memory monitoring
python test_final_integration.py --extended-memory-test

# Load test with memory monitoring
python caption_sender.py --stream loadtest --count 1000 --interval 0.1 &
python test_final_integration.py --memory-only
```

### Throughput Testing

```bash
# High-frequency caption testing
python caption_sender.py --stream throughput --count 500 --interval 0.05

# Multiple stream testing
for stream in stream1 stream2 stream3; do
  python caption_sender.py --stream $stream --count 100 --interval 0.1 &
done
```

## 🐛 Debugging and Troubleshooting

### Common Test Failures and Solutions

**Test Failure: "Wowza process not found"**
```bash
# Check if Wowza is running
ps aux | grep -i wowza
sudo service WowzaStreamingEngine status

# Restart if needed
sudo service WowzaStreamingEngine restart
```

**Test Failure: "LiveVTT Caption Module not loaded"**
```bash
# Check module configuration
grep -i livevtt /usr/local/WowzaStreamingEngine/conf/live/Application.xml
grep -i livevtt /usr/local/WowzaStreamingEngine/conf/VHost.xml

# Check JAR file exists
ls -la /usr/local/WowzaStreamingEngine/lib/livevtt-caption-module.jar
```

**Test Failure: "Caption API not responding"**
```bash
# Check port is listening
netstat -tlnp | grep :8086

# Test direct connection
curl -v http://localhost:8086/livevtt/captions

# Check firewall
sudo ufw status | grep 8086
```

**Test Warning: "Stream not found"**
```bash
# Check active streams
python stream_checker.py

# Start test stream
ffmpeg -re -i test_video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream
```

### Verbose Output

All tools support verbose output for debugging:

```bash
# Detailed integration test output
python test_final_integration.py --verbose

# Caption sender with debug info
python caption_sender.py --stream test --verbose

# Stream checker with detailed info
python stream_checker.py --verbose
```

## 🤖 Automated Testing

### CI/CD Pipeline Testing

For continuous integration environments:

```bash
# Basic health check (exit code 0 = success)
python test_final_integration.py --quiet --exit-code

# API connectivity test
python caption_sender.py --stream ci-test --count 1 --exit-on-error
```

### Monitoring Integration

For monitoring systems like Nagios/Zabbix:

```bash
# Return JSON status for monitoring
python test_final_integration.py --format json --quiet

# Health check with timeout
timeout 30 python test_final_integration.py --quick
```

### Shell Script Integration

```bash
#!/bin/bash
# livevtt-health-check.sh

echo "🔍 LiveVTT Health Check"
echo "====================="

if python test_final_integration.py --quiet; then
    echo "✅ System healthy"
    exit 0
else
    echo "❌ System issues detected"
    echo "Running diagnostic..."
    python stream_checker.py
    exit 1
fi
```

## 📈 Test Results Interpretation

### Success Indicators
- ✅ Green checkmarks
- "PASSED" status messages
- HTTP 200 responses for active streams
- HTTP 404 responses for inactive streams (expected)
- Stable memory usage patterns

### Warning Indicators
- ⚠️ Yellow warnings
- "Stream not found" messages (normal when no streams active)
- Memory usage fluctuations (within normal range)

### Error Indicators
- ❌ Red error marks
- "FAILED" status messages
- Connection refused errors
- Module loading failures
- Persistent high memory usage

## 🎯 Best Practices

### Testing Strategy
1. **Start with integration test** - Always run `test_final_integration.py` first
2. **Check streams before caption testing** - Use `stream_checker.py` to verify setup
3. **Test incrementally** - Start with single captions, then increase volume
4. **Monitor resources** - Check memory and CPU usage during tests

### Test Environment Setup
- Use dedicated test streams for consistent results
- Keep test video files small for faster iteration
- Set up monitoring for automated testing
- Document expected vs. actual behavior

### Documentation
- Record test procedures for team members
- Document environment-specific configurations  
- Keep troubleshooting steps updated
- Share successful test patterns

The streamlined LiveVTT testing suite provides reliable, comprehensive verification of the caption integration while avoiding the complexity and brittleness of previous testing approaches. 