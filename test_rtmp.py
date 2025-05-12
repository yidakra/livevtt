#!/usr/bin/env python3
"""
Test script for LiveVTT RTMP publishing functionality.
This script tests sending captions to an RTMP server without requiring a full video stream.
"""

import asyncio
import argparse
import logging
import subprocess
import time
import sys
import signal

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rtmp-test")

# Global variables
RTMP_PROCESS = None

async def publish_test_captions(rtmp_url, num_captions=5, delay=5):
    """Publish test captions to the specified RTMP URL."""
    global RTMP_PROCESS
    
    test_captions = [
        "This is a test caption 1",
        "Testing RTMP subtitle functionality",
        "Captions should appear in Wowza",
        "Lorem ipsum dolor sit amet",
        "Final test caption"
    ]
    
    for i in range(min(num_captions, len(test_captions))):
        caption = test_captions[i]
        logger.info(f"Publishing caption {i+1}/{num_captions}: '{caption}'")
        
        # Stop previous process if running
        if RTMP_PROCESS is not None:
            RTMP_PROCESS.terminate()
            await asyncio.sleep(0.1)
            
        # Start FFmpeg process with new caption
        ffmpeg_cmd = [
            'ffmpeg',
            '-re',
            '-f', 'lavfi',
            '-i', 'color=black:s=1280x720',
            '-f', 'lavfi',
            '-i', 'anullsrc',
            '-c:v', 'libx264',
            '-tune', 'zerolatency',
            '-preset', 'ultrafast',
            '-c:a', 'aac',
            '-f', 'flv',
            '-flvflags', '+no_duration_filesize',
            '-metadata', f'onTextData="text={caption}",language=eng,trackid=99',
            rtmp_url
        ]
        
        RTMP_PROCESS = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        logger.info(f"Started RTMP process with PID {RTMP_PROCESS.pid}")
        
        # Wait between captions
        await asyncio.sleep(delay)
    
    logger.info("Caption test complete")
    
    # Cleanup
    if RTMP_PROCESS is not None:
        RTMP_PROCESS.terminate()
        RTMP_PROCESS = None

async def cleanup(sig=None):
    """Clean up resources when terminating."""
    if sig:
        logger.info(f"Received signal {sig}, shutting down...")
    
    global RTMP_PROCESS
    if RTMP_PROCESS is not None:
        RTMP_PROCESS.terminate()
        RTMP_PROCESS = None
    
    logger.info("Cleanup complete")

async def main():
    parser = argparse.ArgumentParser(description='Test RTMP caption publishing')
    parser.add_argument('-u', '--rtmp-url', type=str, required=True,
                        help='RTMP URL to publish captions to (e.g., rtmp://server/app/stream)')
    parser.add_argument('-n', '--num-captions', type=int, default=5,
                        help='Number of test captions to publish (default: 5)')
    parser.add_argument('-d', '--delay', type=int, default=5,
                        help='Delay between captions in seconds (default: 5)')
    
    args = parser.parse_args()
    
    # Set up signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(cleanup(sig)))
    
    try:
        logger.info(f"Starting RTMP test with URL: {args.rtmp_url}")
        await publish_test_captions(args.rtmp_url, args.num_captions, args.delay)
    except Exception as e:
        logger.error(f"Error in RTMP test: {e}")
    finally:
        await cleanup()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1) 