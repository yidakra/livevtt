# LiveVTT Caption API Reference

This document provides complete reference for the LiveVTT Caption API integration with Wowza Streaming Engine.

## 📡 API Overview

The LiveVTT Caption API allows sending real-time captions to live RTMP streams via HTTP requests. The integration runs as a Wowza module and accepts caption data through a RESTful endpoint.

**Base URL**: `http://localhost:8086/livevtt/captions`
**Method**: `POST`
**Content-Type**: `application/json`

## 🔧 Request Format

### Required Headers
```http
Content-Type: application/json
```

### Optional Headers (Authentication)
```http
Authorization: Basic <base64(username:password)>
```

### Request Body
```json
{
  "text": "Caption text to display",
  "lang": "eng",
  "trackid": 99,
  "streamname": "your_stream_name"
}
```

### Field Descriptions

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `text` | string | ✅ | Caption text content | `"Hello, this is a test caption"` |
| `lang` | string | ✅ | ISO 639-2 language code | `"eng"`, `"spa"`, `"fra"` |
| `trackid` | integer | ✅ | Caption track identifier | `99` |
| `streamname` | string | ✅ | Target RTMP stream name | `"liveShow"`, `"news_stream"` |

## 📊 Response Formats

### Success Response (200 OK)
```json
{
  "status": "success",
  "message": "Caption sent successfully"
}
```

### Stream Not Found (404 Not Found)
```json
{
  "status": "error",
  "error": "Stream not found",
  "message": "No active stream with name 'streamname'"
}
```

### Bad Request (400 Bad Request)
```json
{
  "status": "error",
  "error": "Invalid request",
  "message": "Missing required field: text"
}
```

### Server Error (500 Internal Server Error)
```json
{
  "status": "error",
  "error": "Internal server error",
  "message": "Caption processing failed"
}
```

## 🌍 Language Codes

Supported ISO 639-2 language codes:

| Language | Code | Language | Code |
|----------|------|----------|------|
| English | `eng` | Spanish | `spa` |
| French | `fra` | German | `deu` |
| Italian | `ita` | Portuguese | `por` |
| Dutch | `nld` | Russian | `rus` |
| Chinese | `chi` | Japanese | `jpn` |
| Korean | `kor` | Arabic | `ara` |

## 📝 Usage Examples

### cURL Examples

**Basic Caption**:
```bash
curl -X POST http://localhost:8086/livevtt/captions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "This is a test caption",
    "lang": "eng",
    "trackid": 99,
    "streamname": "testStream"
  }'
```

**With Authentication**:
```bash
curl -X POST http://localhost:8086/livevtt/captions \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'username:password' | base64)" \
  -d '{
    "text": "Authenticated caption",
    "lang": "eng",
    "trackid": 99,
    "streamname": "secureStream"
  }'
```

**Multiple Languages**:
```bash
# English
curl -X POST http://localhost:8086/livevtt/captions \
  -H "Content-Type: application/json" \
  -d '{"text": "English caption", "lang": "eng", "trackid": 1, "streamname": "multiLang"}'

# Spanish  
curl -X POST http://localhost:8086/livevtt/captions \
  -H "Content-Type: application/json" \
  -d '{"text": "Subtítulo en español", "lang": "spa", "trackid": 2, "streamname": "multiLang"}'
```

### Python Examples

**Basic Request**:
```python
import requests
import json

url = "http://localhost:8086/livevtt/captions"
data = {
    "text": "Python test caption",
    "lang": "eng", 
    "trackid": 99,
    "streamname": "pythonStream"
}

response = requests.post(url, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

**With Error Handling**:
```python
import requests
from requests.auth import HTTPBasicAuth

def send_caption(text, stream, lang="eng", track_id=99, username=None, password=None):
    url = "http://localhost:8086/livevtt/captions"
    data = {
        "text": text,
        "lang": lang,
        "trackid": track_id,
        "streamname": stream
    }
    
    auth = HTTPBasicAuth(username, password) if username else None
    
    try:
        response = requests.post(url, json=data, auth=auth, timeout=10)
        
        if response.status_code == 200:
            return {"success": True, "message": "Caption sent successfully"}
        elif response.status_code == 404:
            return {"success": False, "error": "Stream not found", "suggest_check": True}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
            
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Connection error: {e}"}

# Usage
result = send_caption("Test caption", "myStream")
if result["success"]:
    print("✅ Caption sent!")
else:
    print(f"❌ Error: {result['error']}")
```

### JavaScript Examples

**Fetch API**:
```javascript
async function sendCaption(text, streamName, lang = 'eng', trackId = 99) {
    const url = 'http://localhost:8086/livevtt/captions';
    const data = {
        text: text,
        lang: lang,
        trackid: trackId,
        streamname: streamName
    };
    
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log('✅ Caption sent successfully');
            return result;
        } else {
            console.error('❌ Error:', result.message);
            return null;
        }
    } catch (error) {
        console.error('❌ Connection error:', error);
        return null;
    }
}

// Usage
sendCaption('JavaScript test caption', 'webStream');
```

## 🔍 Testing and Validation

### Stream Validation

Before sending captions, verify the stream exists:

```bash
# Check via Wowza REST API
curl -X GET "http://localhost:8088/v2/servers/_defaultServer_/applications/live/instances/_definst_/incomingstreams"

# Or test caption API (404 = stream not found, but API working)
curl -X POST http://localhost:8086/livevtt/captions \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "lang": "eng", "trackid": 99, "streamname": "nonexistent"}'
```

### Caption Delivery Testing

1. **Start RTMP Stream**:
   ```bash
   ffmpeg -re -i test_video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream
   ```

2. **Send Test Caption**:
   ```bash
   curl -X POST http://localhost:8086/livevtt/captions \
     -H "Content-Type: application/json" \
     -d '{"text": "Test caption delivery", "lang": "eng", "trackid": 99, "streamname": "testStream"}'
   ```

3. **Monitor Player**: Check caption display in video player consuming the stream

## ⚙️ Configuration

### Wowza Module Configuration

The LiveVTT Caption Module is configured in:
- **Application**: `/usr/local/WowzaStreamingEngine/conf/live/Application.xml`
- **VHost**: `/usr/local/WowzaStreamingEngine/conf/VHost.xml`

### HTTP Port Configuration

Default caption API port (8086) is configured in `VHost.xml`:
```xml
<HTTPProvider>
    <BaseClass>com.wowza.wms.http.HTTProvider2Base</BaseClass>
    <RequestFilters>livevtt*</RequestFilters>
    <AuthenticationMethod>none</AuthenticationMethod>
</HTTPProvider>
```

## 🚨 Error Handling

### Common Error Scenarios

1. **Stream Not Found (404)**:
   - Stream name doesn't match active RTMP stream
   - RTMP stream not published yet
   - Stream disconnected/stopped

2. **Bad Request (400)**:
   - Missing required fields (`text`, `lang`, `trackid`, `streamname`)
   - Invalid JSON format
   - Invalid field types

3. **Internal Server Error (500)**:
   - Wowza module error
   - Memory issues
   - Caption processing failure

4. **Connection Error**:
   - Wowza server not running
   - Port 8086 not accessible
   - Network connectivity issues

### Debugging Tips

1. **Check Wowza Status**:
   ```bash
   ps aux | grep -i wowza
   netstat -tlnp | grep :8086
   ```

2. **Review Logs**:
   ```bash
   tail -f /usr/local/WowzaStreamingEngine/logs/wowzastreamingengine_access.log
   tail -f /usr/local/WowzaStreamingEngine/logs/wowzastreamingengine_error.log
   ```

3. **Test API Connectivity**:
   ```bash
   curl -I http://localhost:8086/livevtt/captions
   ```

## 🔒 Security Considerations

### Authentication
- Optional HTTP Basic Auth support
- Configure in Wowza Manager or `Application.xml`
- Use HTTPS in production environments

### Access Control
- Restrict API access by IP/network
- Use firewall rules for port 8086
- Monitor access logs for unauthorized attempts

### Best Practices
- Validate all input data
- Implement rate limiting
- Use secure credential storage
- Regular security updates 