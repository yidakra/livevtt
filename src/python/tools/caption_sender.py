import requests
import argparse
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_caption')

def send_caption(server, port, stream_name, text, language="eng", track_id=99, username=None, password=None):
    """Send a caption to the Wowza server."""
    url = f"http://{server}:{port}/livevtt/captions"
    payload = {
        "text": text,
        "lang": language,
        "trackid": track_id,
        "streamname": stream_name
    }
    headers = {"Content-Type": "application/json"}
    auth = None
    if username and password:
        auth = (username, password)
    
    try:
        logger.info(f"Sending caption to {url}: {payload}")
        response = requests.post(url, json=payload, headers=headers, auth=auth)
        
        if response.status_code == 200:
            logger.info(f"✅ Caption sent successfully to live stream: {response.text}")
            return True
        elif response.status_code == 404:
            logger.warning(f"⚠️  Stream '{stream_name}' not found: {response.text}")
            return True  # Still successful API test, just no active stream
        else:
            logger.error(f"❌ Failed to send caption: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending caption: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test sending captions to Wowza")
    parser.add_argument("--server", "-s", default="localhost", help="Wowza server hostname/IP")
    parser.add_argument("--port", "-p", type=int, default=8086, help="Wowza HTTP port")
    parser.add_argument("--stream", required=True, help="Stream name to send captions to")
    parser.add_argument("--text", "-t", default="This is a test caption", help="Caption text to send")
    parser.add_argument("--language", "-l", default="eng", help="Caption language code")
    parser.add_argument("--track-id", type=int, default=99, help="Caption track ID")
    parser.add_argument("--username", "-u", help="Username for authentication")
    parser.add_argument("--password", "-pw", help="Password for authentication")
    parser.add_argument("--count", "-c", type=int, default=1, help="Number of captions to send")
    parser.add_argument("--interval", "-i", type=float, default=1.0, help="Interval between captions in seconds")
    
    args = parser.parse_args()
    
    logger.info(f"Testing caption delivery to {args.server}:{args.port} for stream '{args.stream}'")
    logger.info("💡 To test with live streams, first publish RTMP: ffmpeg -re -i video.mp4 -c copy -f flv rtmp://localhost:1935/live/yourStreamName")
    
    success_count = 0
    for i in range(args.count):
        caption_text = f"{args.text} #{i+1}"
        if send_caption(args.server, args.port, args.stream, caption_text, 
                        args.language, args.track_id, args.username, args.password):
            success_count += 1
        
        if i < args.count - 1:  # Don't sleep after the last caption
            time.sleep(args.interval)
    
    logger.info(f"Test complete. Successfully sent {success_count}/{args.count} captions.")
    return 0 if success_count == args.count else 1

if __name__ == "__main__":
    main() 