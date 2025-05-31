# Testing LiveVTT with Wowza Integration

This document provides instructions for testing the LiveVTT and Wowza integration with a focus on reliable, non-brittle testing approaches.

## Recommended Testing Strategy

### 🎯 Core Testing Tools (Reliable)

**Primary Tests - Use These:**

1. **`test_simple_integration.py`** ⭐ - Simple, focused integration test
   - Tests API endpoints without external dependencies
   - Automatically uses mock Wowza if real server not available
   - Includes concurrent request testing
   - **Usage:** `python test_simple_integration.py`

2. **`test_caption.py`** ⭐ - Manual caption testing CLI
   - Flexible command-line tool for testing specific scenarios
   - Perfect for development and debugging
   - **Usage:** `python test_caption.py --server localhost --port 8086 --stream myStream`

3. **`test_caption_generator.py`** ⭐ - Continuous caption generator
   - Great for load testing and demonstrations
   - Simple and reliable
   - **Usage:** `python test_caption_generator.py`

4. **`test_final_integration.py`** ⭐ - Production readiness verification
   - Comprehensive health checks for production deployments
   - Tests memory stability and real Wowza configuration
   - **Usage:** `python test_final_integration.py`

### 🔧 Specialized Tools

5. **`test_rtmp.py`** - RTMP-specific testing (improved)
   - Now includes better error handling and retries
   - Configurable timeouts and server settings
   - **Usage:** `python test_rtmp.py --server localhost --port 8086`

6. **`test_wowza_api.py`** - Direct API testing
   - Tests Wowza API endpoints directly
   - Good for API-specific debugging
   - **Usage:** `python test_wowza_api.py -u http://localhost:8086`

### ❌ Deprecated/Brittle Tests

**Avoid These (Too Brittle):**

- ~~`test_integration.py`~~ - **REMOVED** - Too complex and dependent on external streams
  - Issues: Hard-coded TVRain stream, complex subprocess management, timing assumptions
  - Replacement: Use `test_simple_integration.py` instead

## Quick Start Testing Guide

### 1. **Basic Functionality Test**
```bash
# Test if everything is working
python test_simple_integration.py
```

### 2. **Manual Caption Testing**
```bash
# Send a single test caption
python test_caption.py --server localhost --port 8086 --stream myStream --text "Hello World"

# Send multiple captions with custom interval
python test_caption.py --server localhost --port 8086 --stream myStream --count 5 --interval 2
```

### 3. **Load Testing**
```bash
# Generate continuous captions for load testing
python test_caption_generator.py
```

### 4. **Production Verification**
```bash
# Verify production readiness
python test_final_integration.py
```

## Testing with Mock Wowza Server

The mock Wowza server simulates the HTTP endpoints without requiring a real Wowza installation:

```bash
# Start mock server (in separate terminal)
python mock_wowza.py

# Run tests against mock server
python test_simple_integration.py --port 8086
python test_wowza_api.py -u http://localhost:8086
```

## Testing with Real Wowza Server

### Prerequisites
- Wowza Streaming Engine running
- LiveVTT Caption Module installed
- HTTP Provider configured on port 8086

### Verification Steps

1. **Check Wowza Configuration:**
   ```bash
   python check_wowza.py -u http://your-wowza-server:8086
   ```

2. **Test Caption API:**
   ```bash
   python test_simple_integration.py --host your-wowza-server --port 8086
   ```

3. **Send Test Captions to Active Stream:**
   ```bash
   python test_caption.py --server your-wowza-server --port 8086 --stream your-stream-name
   ```

## Automated Testing Best Practices

### Following AAA Pattern

Our tests follow the **Arrange, Act, Assert** pattern:

```python
# ✅ Good example from test_simple_integration.py
async def test_caption_submission(self) -> bool:
    # ARRANGE
    test_captions = [
        {"text": "Basic test caption", "lang": "eng", "trackid": 99, "streamname": "testStream"}
    ]
    
    # ACT
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=caption) as response:
            
    # ASSERT
    if response.status in [200, 404]:
        return True
```

### Non-Brittle Test Characteristics

**✅ What Makes Tests Robust:**
- Configurable parameters (hosts, ports, timeouts)
- Graceful fallbacks (mock server if real one unavailable)
- Acceptable failure modes (404 for missing streams is OK)
- Retry logic with reasonable timeouts
- Clear error messages
- Isolated test cases

**❌ What Makes Tests Brittle:**
- Hard-coded external URLs
- Fixed timing assumptions
- Complex subprocess management
- Network dependencies without fallbacks
- Overly specific assertions

## Continuous Integration

### Recommended CI Pipeline
```yaml
# .github/workflows/test.yml example
test:
  runs-on: ubuntu-latest
  steps:
    - name: Basic Integration Test
      run: python test_simple_integration.py
      
    - name: API Test
      run: python test_wowza_api.py -u http://localhost:8086
      
    # Skip tests that require external dependencies in CI
```

### Local Development Testing
```bash
# Full test suite for local development
python test_simple_integration.py
python test_caption.py --server localhost --port 8086 --stream testStream --count 3
python test_final_integration.py  # Only if real Wowza is running
```

## Troubleshooting Tests

### Common Issues

**Test Timeouts:**
```bash
# Increase timeouts for slow systems
python test_simple_integration.py --timeout 30
python test_rtmp.py --timeout 15 --retries 5
```

**Port Conflicts:**
```bash
# Use different ports
python test_simple_integration.py --port 8087
```

**Mock Server Issues:**
```bash
# Start mock server manually first
python mock_wowza.py &
python test_simple_integration.py --skip-mock
```

### Debug Mode

Enable verbose logging:
```bash
# Most tests support debug output
python test_simple_integration.py --debug
python test_caption.py --debug --server localhost --port 8086 --stream test
```

## Test Output Interpretation

**✅ Success Indicators:**
- Green checkmarks (✅)
- "PASSED" status
- HTTP 200 responses
- HTTP 404 for missing streams (expected)

**⚠️ Warning Indicators:**
- Yellow warnings (⚠️)
- "Module not found" (if using mock server)
- Timeout warnings (may indicate slow system)

**❌ Failure Indicators:**
- Red X marks (❌)
- "FAILED" status
- Connection refused errors
- Repeated timeouts

---

**The improved test suite focuses on reliability and usefulness while avoiding brittle dependencies that can break CI/CD pipelines.** 