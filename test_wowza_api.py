#!/usr/bin/env python3
"""
Test the Wowza LiveVTT Caption Module HTTP API directly.
This script sends captions directly to the API without going through the LiveVTT application.
"""

import asyncio
import argparse
import logging
import aiohttp
import json
import sys
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('wowza-api-test')

async def test_wowza_api(url, num_captions=5, interval=2.0):
    """Test the Wowza LiveVTT Caption Module API directly"""
    # Parse URL to get server
    parsed_url = urlparse(url)
    server = parsed_url.netloc
    
    # Check if server is reachable
    status_url = f"http://{server}/livevtt/captions/status"
    logger.info(f"Checking if Wowza server is reachable at {status_url}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(status_url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Wowza server is reachable: {data}")
                else:
                    logger.error(f"Wowza server returned unexpected status: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"Failed to connect to Wowza server: {e}")
        return False
    
    # Send test captions
    captions_url = f"http://{server}/livevtt/captions?streamname=test_stream"
    logger.info(f"Sending {num_captions} test captions to {captions_url}...")
    
    test_captions = [
        "This is a test caption from the API test script.",
        "Testing the Wowza LiveVTT Caption Module API.",
        "Captions should be properly formatted as onTextData events.",
        "The module should inject these captions into the RTMP stream.",
        "This is the final test caption from the API test."
    ]
    
    # Add more captions if needed
    while len(test_captions) < num_captions:
        test_captions.append(f"Additional test caption {len(test_captions) + 1}")
    
    # Use only the requested number of captions
    test_captions = test_captions[:num_captions]
    
    try:
        async with aiohttp.ClientSession() as session:
            for i, caption in enumerate(test_captions):
                # Prepare payload
                payload = {
                    "text": caption,
                    "language": "eng",
                    "trackId": 99
                }
                
                # Send caption
                logger.info(f"Sending caption {i+1}/{num_captions}: {caption}")
                
                async with session.post(captions_url, json=payload, headers={'Content-Type': 'application/json'}) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        logger.info(f"Caption {i+1} sent successfully: {response_data}")
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to send caption {i+1}: {response.status} - {response_text}")
                        return False
                
                # Wait for the specified interval
                await asyncio.sleep(interval)
            
            logger.info("All captions sent successfully")
            return True
    except Exception as e:
        logger.error(f"Error sending captions: {e}")
        return False

async def main():
    parser = argparse.ArgumentParser(description="Test Wowza LiveVTT Caption Module API")
    parser.add_argument("--url", "-u", required=True, help="Wowza server URL (e.g., http://localhost:8087)")
    parser.add_argument("--num-captions", "-n", type=int, default=5, help="Number of test captions to send")
    parser.add_argument("--interval", "-i", type=float, default=2.0, help="Interval between captions in seconds")
    args = parser.parse_args()
    
    logger.info(f"Testing Wowza LiveVTT Caption Module API at {args.url}")
    
    success = await test_wowza_api(args.url, args.num_captions, args.interval)
    
    if success:
        logger.info("✅ API test PASSED")
        return 0
    else:
        logger.error("❌ API test FAILED")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(130) 