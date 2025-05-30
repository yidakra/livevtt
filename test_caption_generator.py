#!/usr/bin/env python3
"""
Test Caption Generator for LiveVTT-Wowza Integration
Sends test captions to the running stream at regular intervals
"""
import time
import requests
import json
import sys

def send_caption(text, lang="eng", trackid=99, streamname="myStream"):
    """Send a caption to the Wowza HTTP provider"""
    url = "http://localhost:8086/livevtt/captions"
    headers = {"Content-Type": "application/json"}
    data = {
        "text": text,
        "lang": lang,
        "trackid": trackid,
        "streamname": streamname
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=5)
        print(f"[{time.strftime('%H:%M:%S')}] Caption: '{text}' -> {response.status_code} {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ERROR: {e}")
        return False

def main():
    """Generate test captions continuously"""
    test_captions = [
        "🎬 Welcome to the LiveVTT test stream!",
        "📺 This is an automated caption test",
        "✅ Caption integration is working",
        "🚀 Streaming live with real-time subtitles",
        "🎯 Testing WebVTT subtitle generation",
        "⚡ Caption delivery via HTTP API",
        "🔄 Continuous caption testing active",
        "🎪 Dynamic subtitle generation",
        "📡 Live streaming with subtitles",
        "🌟 End-to-end caption testing"
    ]
    
    print("Starting test caption generator...")
    print("Sending captions every 5 seconds to myStream")
    print("Press Ctrl+C to stop")
    
    caption_index = 0
    
    try:
        while True:
            text = test_captions[caption_index % len(test_captions)]
            send_caption(text)
            caption_index += 1
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping caption generator...")

if __name__ == "__main__":
    main() 