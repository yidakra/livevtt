#!/usr/bin/env python3
"""
Integration test for LiveVTT and Wowza caption integration.
This script tests the end-to-end flow from LiveVTT to Wowza.
"""

import asyncio
import argparse
import logging
import subprocess
import time
import sys
import aiohttp
import json
import os
import signal
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('livevtt-integration-test')

# Global variables
MOCK_WOWZA_PROCESS = None
LIVEVTT_PROCESS = None

async def start_mock_wowza():
    """Start the mock Wowza server"""
    global MOCK_WOWZA_PROCESS
    
    logger.info("Starting mock Wowza server...")
    try:
        MOCK_WOWZA_PROCESS = subprocess.Popen(
            ["python", "mock_wowza.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for server to start
        await asyncio.sleep(2)
        
        # Check if server is running
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("http://localhost:8087/livevtt/captions/status", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Mock Wowza server started: {data}")
                        return True
                    else:
                        logger.error(f"Mock Wowza server returned unexpected status: {response.status}")
                        return False
            except Exception as e:
                logger.error(f"Failed to connect to mock Wowza server: {e}")
                return False
    except Exception as e:
        logger.error(f"Failed to start mock Wowza server: {e}")
        return False

async def start_livevtt(rtmp_url="rtmp://localhost/live/stream"):
    """Start the LiveVTT application with RTMP output"""
    global LIVEVTT_PROCESS
    
    logger.info(f"Starting LiveVTT with RTMP output to {rtmp_url}...")
    try:
        cmd = [
            "python", "main.py",
            "-u", "https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8",  # TVRain stream
            "-la", "ru",                                                     # Russian language
            "-bt",                                                           # Both tracks
            "-l", "127.0.0.1",                                               # Bind to localhost
            "-p", "8000",                                                    # Port 8000
            "-m", "tiny",                                                    # Small model for quick testing
            "-c", "false",                                                   # No CUDA
            "-rtmp", rtmp_url,                                               # RTMP URL
            "-rtmp-trans"                                                    # Use translated captions
        ]
        
        LIVEVTT_PROCESS = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for LiveVTT to start
        await asyncio.sleep(10)
        
        # Check if LiveVTT is running
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8000/playlist.m3u8", timeout=5) as response:
                    if response.status == 200:
                        logger.info("LiveVTT started successfully")
                        return True
                    else:
                        logger.error(f"LiveVTT returned unexpected status: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to connect to LiveVTT: {e}")
            return False
    except Exception as e:
        logger.error(f"Failed to start LiveVTT: {e}")
        return False

async def check_captions_received(timeout=60):
    """Check if captions are being received by the mock Wowza server"""
    logger.info(f"Waiting for captions (timeout: {timeout} seconds)...")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8087/livevtt/captions/list", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        caption_count = data.get("count", 0)
                        
                        if caption_count > 0:
                            logger.info(f"✅ Success! Received {caption_count} captions")
                            # Print the first few captions
                            for i, caption in enumerate(data.get("captions", [])[:5]):
                                logger.info(f"Caption {i+1}: {caption.get('text')}")
                            return True
                        else:
                            logger.info(f"Waiting for captions... ({int(time.time() - start_time)}s)")
                    else:
                        logger.warning(f"Unexpected response from mock Wowza: {response.status}")
        except Exception as e:
            logger.warning(f"Error checking captions: {e}")
        
        await asyncio.sleep(5)
    
    logger.error("❌ No captions received within timeout period")
    return False

async def cleanup():
    """Clean up processes"""
    global MOCK_WOWZA_PROCESS, LIVEVTT_PROCESS
    
    logger.info("Cleaning up processes...")
    
    if LIVEVTT_PROCESS:
        logger.info("Terminating LiveVTT process...")
        try:
            LIVEVTT_PROCESS.terminate()
            LIVEVTT_PROCESS.wait(timeout=5)
        except Exception as e:
            logger.warning(f"Error terminating LiveVTT process: {e}")
            try:
                os.kill(LIVEVTT_PROCESS.pid, signal.SIGKILL)
            except:
                pass
    
    if MOCK_WOWZA_PROCESS:
        logger.info("Terminating mock Wowza server...")
        try:
            MOCK_WOWZA_PROCESS.terminate()
            MOCK_WOWZA_PROCESS.wait(timeout=5)
        except Exception as e:
            logger.warning(f"Error terminating mock Wowza process: {e}")
            try:
                os.kill(MOCK_WOWZA_PROCESS.pid, signal.SIGKILL)
            except:
                pass

async def run_test():
    """Run the integration test"""
    try:
        # Start mock Wowza server
        if not await start_mock_wowza():
            logger.error("Failed to start mock Wowza server. Aborting test.")
            await cleanup()
            return False
        
        # Start LiveVTT
        if not await start_livevtt("rtmp://localhost/live/stream"):
            logger.error("Failed to start LiveVTT. Aborting test.")
            await cleanup()
            return False
        
        # Check if captions are being received
        success = await check_captions_received(timeout=120)
        
        return success
    finally:
        await cleanup()

async def main():
    parser = argparse.ArgumentParser(description="Test LiveVTT to Wowza integration")
    parser.add_argument("--timeout", "-t", type=int, default=120, help="Test timeout in seconds")
    args = parser.parse_args()
    
    logger.info("Starting LiveVTT to Wowza integration test")
    
    success = await run_test()
    
    if success:
        logger.info("✅ Integration test PASSED")
        return 0
    else:
        logger.error("❌ Integration test FAILED")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        asyncio.run(cleanup())
        sys.exit(130) 