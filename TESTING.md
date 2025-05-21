# Testing LiveVTT with Wowza Integration

This document provides instructions for testing the LiveVTT and Wowza integration without having access to a real Wowza Streaming Engine server.

## Testing Tools

We've created several testing scripts to help verify that the LiveVTT to Wowza integration is working correctly:

1. **mock_wowza.py** - A mock Wowza server that simulates the LiveVTT Caption Module HTTP endpoints
2. **test_wowza_api.py** - A script to test the Wowza module's HTTP API directly
3. **test_integration.py** - A comprehensive test that verifies the end-to-end flow from LiveVTT to Wowza
4. **test_rtmp.py** - A script to test sending captions to a Wowza server (can be used with the mock server)
5. **check_wowza.py** - A script to check if a Wowza server is properly configured for LiveVTT

## Testing with Mock Wowza Server

The mock Wowza server simulates the HTTP endpoints of the LiveVTT Caption Module without requiring a real Wowza Streaming Engine server.

### Starting the Mock Server

```bash
python mock_wowza.py
```

This will start a server on `http://localhost:8087` that responds to the same endpoints as a real Wowza server with the LiveVTT Caption Module installed.

### Testing the API Directly

Once the mock server is running, you can test the API directly:

```bash
python test_wowza_api.py -u http://localhost:8087
```

This will send test captions to the mock server and verify that they are received correctly.

### Running the Integration Test

The integration test verifies the end-to-end flow from LiveVTT to Wowza:

```bash
python test_integration.py
```

This test:
1. Starts the mock Wowza server
2. Starts LiveVTT with RTMP output pointing to the mock server
3. Verifies that captions are being generated and sent to the mock server
4. Cleans up all processes when done

## Testing with a Real Wowza Server

If you have access to a real Wowza Streaming Engine server with the LiveVTT Caption Module installed, you can use these scripts to test it:

### Checking the Wowza Configuration

```bash
python check_wowza.py -u http://your-wowza-server:8087
```

This will check if the server is properly configured for LiveVTT.

### Testing Caption Delivery

```bash
python test_rtmp.py -u rtmp://your-wowza-server/live/stream
```

This will send test captions to the specified RTMP stream.

### Running LiveVTT with RTMP Output

```bash
python main.py -u https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8 -la ru -bt -rtmp rtmp://your-wowza-server/live/stream
```

This will start LiveVTT with RTMP output to your Wowza server.

## Troubleshooting

If you encounter issues during testing, check the following:

1. **Mock server not starting**: Make sure port 8087 is not already in use
2. **LiveVTT not connecting**: Check that the TVRain stream is accessible
3. **Captions not being sent**: Check the LiveVTT logs for errors
4. **API test failing**: Verify that the mock server is running and responding to requests

## Interpreting Test Results

- **Green checkmarks (✅)** indicate that a test passed
- **Red X marks (❌)** indicate that a test failed
- Check the logs for detailed information about what went wrong

If all tests pass, it means that the LiveVTT to Wowza integration is working correctly and should work with a real Wowza server as well. 