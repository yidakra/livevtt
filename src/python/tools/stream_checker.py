#!/usr/bin/env python3
"""
Stream Checker Utility for LiveVTT Testing
Checks for active streams and provides guidance for testing
"""

import requests
import json
import sys
import argparse

def check_basic_stream_status(host="localhost"):
    """Basic check using LiveVTT Caption API"""
    print(f"🔍 Checking stream status via LiveVTT Caption API")
    print("=" * 50)
    
    try:
        url = f"http://{host}:8086/livevtt/captions"
        test_payload = {"text": "stream check", "lang": "eng", "trackid": 99, "streamname": "test"}
        
        response = requests.post(url, json=test_payload, timeout=5)
        
        if response.status_code == 200:
            print("✅ LiveVTT Caption API is working and found active streams")
            print("💡 Test with your actual stream names")
        elif response.status_code == 404:
            print("⚠️  LiveVTT Caption API is working but no active streams found")
            print("\n💡 To test with live streams, publish RTMP first:")
            print("   # Using FFmpeg with a video file:")
            print("   ffmpeg -re -i your_video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream")
            print("\n   # Using OBS Studio:")
            print("   Server: rtmp://localhost:1935/live")
            print("   Stream Key: testStream")
            print(f"\n   Then test captions with:")
            print(f"   python test_caption.py --stream testStream")
        else:
            print(f"❌ LiveVTT Caption API returned unexpected status: {response.status_code}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Cannot connect to LiveVTT Caption API: {e}")
        return False

def check_wowza_streams(host="localhost", port=8088):
    """Check for active streams using Wowza REST API"""
    try:
        # Get applications
        apps_url = f"http://{host}:{port}/v2/servers/_defaultServer_/applications"
        response = requests.get(apps_url, timeout=5)
        
        if response.status_code != 200:
            print(f"❌ Cannot access Wowza REST API at {host}:{port} (Status: {response.status_code})")
            print("   Wowza Manager might not be running or REST API disabled")
            print("   Falling back to basic stream status check...")
            return check_basic_stream_status(host)
            
        try:
            apps_data = response.json()
        except json.JSONDecodeError:
            print(f"⚠️  Wowza REST API returned invalid JSON at {host}:{port}")
            print("   Falling back to basic stream status check...")
            return check_basic_stream_status(host)
        
        print(f"🔍 Checking for active streams on {host}:{port}")
        print("=" * 50)
        
        active_streams = []
        
        for app in apps_data.get('applications', []):
            app_name = app.get('name', 'unknown')
            
            # Check instances for this application
            instances_url = f"http://{host}:{port}/v2/servers/_defaultServer_/applications/{app_name}/instances"
            try:
                inst_response = requests.get(instances_url, timeout=5)
                if inst_response.status_code == 200:
                    instances = inst_response.json()
                    
                    for instance in instances.get('instances', []):
                        inst_name = instance.get('name', '_definst_')
                        
                        # Check streams for this instance
                        streams_url = f"http://{host}:{port}/v2/servers/_defaultServer_/applications/{app_name}/instances/{inst_name}/incomingstreams"
                        try:
                            streams_response = requests.get(streams_url, timeout=5)
                            if streams_response.status_code == 200:
                                streams = streams_response.json()
                                
                                for stream in streams.get('incomingStreams', []):
                                    stream_name = stream.get('name', 'unknown')
                                    stream_info = {
                                        'app': app_name,
                                        'instance': inst_name,
                                        'name': stream_name,
                                        'url': f"rtmp://{host}:1935/{app_name}/{stream_name}"
                                    }
                                    active_streams.append(stream_info)
                        except:
                            continue
            except:
                continue
        
        if active_streams:
            print(f"✅ Found {len(active_streams)} active stream(s):")
            for i, stream in enumerate(active_streams, 1):
                print(f"   {i}. {stream['name']} (app: {stream['app']})")
                print(f"      RTMP URL: {stream['url']}")
            
            print(f"\n💡 Test captions with these streams:")
            for stream in active_streams:
                print(f"   python test_caption.py --stream {stream['name']}")
        else:
            print("⚠️  No active streams found")
            print("\n💡 To test with live streams, publish RTMP first:")
            print("   # Using FFmpeg with a video file:")
            print("   ffmpeg -re -i your_video.mp4 -c copy -f flv rtmp://localhost:1935/live/testStream")
            print("\n   # Using FFmpeg with webcam (Linux):")
            print("   ffmpeg -f v4l2 -i /dev/video0 -c:v libx264 -f flv rtmp://localhost:1935/live/webcam")
            print("\n   # Using OBS Studio:")
            print("   Set Server: rtmp://localhost:1935/live")
            print("   Set Stream Key: myStream")
            
            print(f"\n   Then test captions with:")
            print(f"   python test_caption.py --stream testStream")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to Wowza at {host}:{port}: {e}")
        print("   Make sure Wowza Streaming Engine is running")
        return False
    except Exception as e:
        print(f"❌ Error checking streams: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Check for active Wowza streams")
    parser.add_argument("--host", default="localhost", help="Wowza host (default: localhost)")
    parser.add_argument("--port", type=int, default=8088, help="Wowza Manager port (default: 8088)")
    args = parser.parse_args()
    
    success = check_wowza_streams(args.host, args.port)
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 