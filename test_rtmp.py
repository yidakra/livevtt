#!/usr/bin/env python3
"""
Test script for LiveVTT RTMP publishing functionality.
This script tests sending captions to an RTMP server without requiring a full video stream.
"""

import asyncio
import argparse
import logging
import time
import sys
import aiohttp
import json
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('livevtt-test')

async def send_test_captions(url, num_captions=5, interval=3.0):
    """
    Send test captions to the Wowza LiveVTT Caption Module via HTTP.
    
    Args:
        url: RTMP URL of the stream
        num_captions: Number of test captions to send
        interval: Interval between captions in seconds
    """
    # Parse RTMP URL to get server and stream name
    parsed_url = urlparse(url)
    server = parsed_url.netloc
    path_parts = parsed_url.path.strip('/').split('/')
    
    if len(path_parts) < 2:
        logger.error(f"Invalid RTMP URL format: {url}")
        logger.error("URL should be in format: rtmp://server/application/streamname")
        return False
    
    stream_name = path_parts[-1]
    
    # HTTP endpoint for the Wowza module
    http_url = f"http://{server}:8087/livevtt/captions?streamname={stream_name}"
    
    logger.info(f"Testing caption delivery to Wowza at {http_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            for i in range(1, num_captions + 1):
                caption_text = f"This is test caption {i} of {num_captions} from LiveVTT"
                
                # Prepare JSON payload
                payload = {
                    "text": caption_text,
                    "language": "eng",
                    "trackId": 99
                }
                
                # Send HTTP request
                logger.info(f"Sending caption: {caption_text}")
                async with session.post(http_url, json=payload, headers={'Content-Type': 'application/json'}) as response:
                    if response.status == 200:
                        logger.info(f"Caption {i} sent successfully")
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to send caption {i}: {response.status} - {response_text}")
                
                # Wait for the specified interval
                await asyncio.sleep(interval)
            
            logger.info("Caption test completed")
            return True
    except Exception as e:
        logger.error(f"Error sending captions: {e}")
        return False

async def check_wowza_connection(server, port=8087):
    """Check if the Wowza server is reachable via HTTP"""
    url = f"http://{server}:{port}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    logger.info(f"Wowza server at {url} is reachable")
                    return True
                else:
                    logger.warning(f"Wowza server at {url} returned status {response.status}")
                    return False
    except aiohttp.ClientError as e:
        logger.error(f"Cannot connect to Wowza server at {url}: {e}")
        return False

async def check_livevtt_module(server, port=8087):
    """Check if the LiveVTT Caption Module is installed and responding"""
    url = f"http://{server}:{port}/livevtt/captions/status"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"LiveVTT Caption Module is installed and responding: {data}")
                    return True
                else:
                    logger.warning(f"LiveVTT Caption Module check failed with status {response.status}")
                    return False
    except aiohttp.ClientError as e:
        logger.error(f"Cannot connect to LiveVTT Caption Module at {url}: {e}")
        return False
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON response from LiveVTT Caption Module")
        return False

async def main():
    parser = argparse.ArgumentParser(description='Test LiveVTT caption delivery to Wowza')
    parser.add_argument('-u', '--url', required=True, help='RTMP URL (e.g., rtmp://server/application/streamname)')
    parser.add_argument('-n', '--num-captions', type=int, default=5, help='Number of test captions to send')
    parser.add_argument('-i', '--interval', type=float, default=3.0, help='Interval between captions in seconds')
    args = parser.parse_args()
    
    # Parse server from URL
    parsed_url = urlparse(args.url)
    server = parsed_url.netloc
    
    # Check Wowza connection
    if not await check_wowza_connection(server):
        logger.error("Cannot connect to Wowza server. Please check if it's running.")
        return 1
    
    # Check LiveVTT module
    if not await check_livevtt_module(server):
        logger.warning("LiveVTT Caption Module check failed. Module may not be installed properly.")
    
    # Send test captions
    success = await send_test_captions(args.url, args.num_captions, args.interval)
    
    return 0 if success else 1

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(0) 