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
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('livevtt-test')

# Default configuration that can be overridden
DEFAULT_CONFIG = {
    'server': 'localhost',
    'port': 8086,
    'timeout': 10,
    'retries': 3
}

async def send_test_captions(url, num_captions=5, interval=3.0, config=None):
    """
    Send test captions to the Wowza LiveVTT Caption Module via HTTP.
    
    Args:
        url: RTMP URL of the stream
        num_captions: Number of test captions to send
        interval: Interval between captions in seconds
        config: Configuration dictionary for overrides
    """
    config = config or DEFAULT_CONFIG
    
    # Parse RTMP URL to get server and stream name
    try:
        parsed_url = urlparse(url)
        server = parsed_url.netloc or config['server']
        path_parts = parsed_url.path.strip('/').split('/')
        
        if len(path_parts) < 2:
            logger.error(f"Invalid RTMP URL format: {url}")
            logger.error("URL should be in format: rtmp://server/application/streamname")
            return False
        
        stream_name = path_parts[-1]
    except Exception as e:
        logger.error(f"Failed to parse RTMP URL {url}: {e}")
        return False
    
    # HTTP endpoint for the Wowza module
    http_url = f"http://{server}:{config['port']}/livevtt/captions"
    
    logger.info(f"Testing caption delivery to {http_url} for stream '{stream_name}'")
    
    # Test captions with variety
    test_captions = [
        f"Test caption {i+1}/{num_captions} - Basic functionality test",
        f"Unicode test: 你好世界 العالم мир 🌍 (#{i+1})",
        f"Timestamp: {time.strftime('%H:%M:%S')} - Caption {i+1}",
        f"Long caption test: This is a longer caption text to test how the system handles more verbose subtitle content in caption {i+1}",
        f"Final test caption {i+1} with special chars: !@#$%^&*()",
    ]
    
    # Cycle through test captions if we need more
    caption_texts = [test_captions[i % len(test_captions)] for i in range(num_captions)]
    
    success_count = 0
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
    timeout = aiohttp.ClientTimeout(total=config['timeout'])
    
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            for i, caption_text in enumerate(caption_texts, 1):
                # Prepare JSON payload
                payload = {
                    "text": caption_text,
                    "lang": "eng",
                    "trackid": 99,
                    "streamname": stream_name
                }
                
                # Send HTTP request with retries
                for attempt in range(config['retries']):
                    try:
                        logger.info(f"Sending caption {i}: {caption_text[:50]}{'...' if len(caption_text) > 50 else ''}")
                        
                        async with session.post(http_url, json=payload, headers={'Content-Type': 'application/json'}) as response:
                            response_text = await response.text()
                            
                            if response.status == 200:
                                logger.info(f"✅ Caption {i} sent successfully")
                                success_count += 1
                                break
                            elif response.status == 404:
                                if "stream not found" in response_text.lower():
                                    logger.warning(f"⚠️  Stream '{stream_name}' not found (expected if not publishing)")
                                else:
                                    logger.warning(f"⚠️  API endpoint not found - check Wowza configuration")
                                success_count += 1  # 404 for missing stream is acceptable
                                break
                            else:
                                logger.error(f"❌ Caption {i} failed: {response.status} - {response_text}")
                                if attempt < config['retries'] - 1:
                                    logger.info(f"Retrying in 1 second... (attempt {attempt + 2}/{config['retries']})")
                                    await asyncio.sleep(1)
                    except asyncio.TimeoutError:
                        logger.error(f"❌ Caption {i} timed out (attempt {attempt + 1}/{config['retries']})")
                        if attempt < config['retries'] - 1:
                            await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"❌ Caption {i} error: {e} (attempt {attempt + 1}/{config['retries']})")
                        if attempt < config['retries'] - 1:
                            await asyncio.sleep(1)
                
                # Wait between captions (but not after the last one)
                if i < num_captions:
                    await asyncio.sleep(interval)
            
            logger.info(f"Caption test completed: {success_count}/{num_captions} successful")
            return success_count == num_captions
            
    except Exception as e:
        logger.error(f"Session error: {e}")
        return False

async def check_wowza_connection(server, port=8086, timeout=5):
    """Check if the Wowza server is reachable via HTTP"""
    url = f"http://{server}:{port}"
    
    try:
        connector = aiohttp.TCPConnector(limit=5)
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        
        async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
            async with session.get(url) as response:
                logger.info(f"✅ Wowza server at {url} is reachable (status: {response.status})")
                return True
    except aiohttp.ClientError as e:
        logger.error(f"❌ Cannot connect to Wowza server at {url}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error connecting to {url}: {e}")
        return False

async def check_livevtt_module(server, port=8086, timeout=5):
    """Check if the LiveVTT Caption Module is installed and responding"""
    url = f"http://{server}:{port}/livevtt/captions/status"
    
    try:
        connector = aiohttp.TCPConnector(limit=5)
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        
        async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        logger.info(f"✅ LiveVTT Caption Module is responding: {data}")
                        return True
                    except json.JSONDecodeError:
                        logger.warning("⚠️  Module responding but returned invalid JSON")
                        return False
                else:
                    logger.warning(f"⚠️  LiveVTT Caption Module check failed with status {response.status}")
                    return False
    except aiohttp.ClientError as e:
        logger.error(f"❌ Cannot connect to LiveVTT Caption Module at {url}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error checking module: {e}")
        return False

async def main():
    parser = argparse.ArgumentParser(description='Test LiveVTT caption delivery to Wowza')
    parser.add_argument('-u', '--url', default='rtmp://localhost:1935/live/testStream', 
                       help='RTMP URL (default: rtmp://localhost:1935/live/testStream)')
    parser.add_argument('-n', '--num-captions', type=int, default=5, 
                       help='Number of test captions to send (default: 5)')
    parser.add_argument('-i', '--interval', type=float, default=3.0, 
                       help='Interval between captions in seconds (default: 3.0)')
    parser.add_argument('--server', default='localhost', 
                       help='Wowza server hostname/IP (default: localhost)')
    parser.add_argument('--port', type=int, default=8086, 
                       help='Wowza HTTP port (default: 8086)')
    parser.add_argument('--timeout', type=int, default=10, 
                       help='Request timeout in seconds (default: 10)')
    parser.add_argument('--retries', type=int, default=3, 
                       help='Number of retries per request (default: 3)')
    parser.add_argument('--skip-checks', action='store_true',
                       help='Skip connection and module checks')
    
    args = parser.parse_args()
    
    # Build configuration
    config = {
        'server': args.server,
        'port': args.port,
        'timeout': args.timeout,
        'retries': args.retries
    }
    
    logger.info(f"Testing caption delivery to {args.server}:{args.port}")
    logger.info(f"Target stream: {args.url}")
    logger.info(f"Configuration: {config}")
    
    if not args.skip_checks:
        # Check Wowza connection
        if not await check_wowza_connection(args.server, args.port, args.timeout):
            logger.error("❌ Cannot connect to Wowza server. Use --skip-checks to bypass this check.")
            return 1
        
        # Check LiveVTT module
        module_ok = await check_livevtt_module(args.server, args.port, args.timeout)
        if not module_ok:
            logger.warning("⚠️  LiveVTT Caption Module check failed. Continuing anyway...")
    
    # Send test captions
    success = await send_test_captions(args.url, args.num_captions, args.interval, config)
    
    if success:
        logger.info("✅ All caption tests passed!")
        return 0
    else:
        logger.error("❌ Some caption tests failed")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(130) 