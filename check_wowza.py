#!/usr/bin/env python3
"""
Utility script to check if Wowza Streaming Engine is running and accepting RTMP connections.
"""

import socket
import argparse
import sys
import subprocess
import shlex
import logging
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("wowza-check")

def parse_rtmp_url(url):
    """Parse an RTMP URL to extract host and port."""
    if not url.startswith("rtmp://"):
        raise ValueError("URL must start with rtmp://")
    
    parsed = urlparse(url)
    host = parsed.netloc.split(':')[0]
    port = parsed.port or 1935  # Default RTMP port is 1935
    
    return host, port

def check_port_open(host, port, timeout=5):
    """Check if a TCP port is open on the specified host."""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.shutdown(socket.SHUT_RDWR)
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        s.close()

def test_rtmp_connection(rtmp_url):
    """Test RTMP connection using FFmpeg."""
    try:
        # Run a quick FFmpeg command to validate RTMP connection
        cmd = f"ffmpeg -v warning -f lavfi -i color=black:s=320x240:r=30 -f lavfi -i anullsrc -t 1 -c:v libx264 -c:a aac -f flv -flvflags no_duration_filesize {rtmp_url}_test"
        
        logger.info(f"Testing RTMP connection with command: {cmd}")
        
        process = subprocess.run(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        
        if process.returncode == 0:
            logger.info("RTMP connection test successful")
            return True
        else:
            logger.error(f"RTMP connection test failed with output:\n{process.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("RTMP connection test timed out after 10 seconds")
        return False
    except Exception as e:
        logger.error(f"Error testing RTMP connection: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Check if Wowza Streaming Engine is running and accepting connections")
    parser.add_argument("-u", "--url", required=True, help="RTMP URL (e.g., rtmp://wowza-server:1935/live)")
    parser.add_argument("-t", "--test-stream", action="store_true", help="Attempt to send a test RTMP stream")
    
    args = parser.parse_args()
    
    try:
        host, port = parse_rtmp_url(args.url)
        
        logger.info(f"Checking if Wowza server is running at {host}:{port}...")
        
        if check_port_open(host, port):
            logger.info(f"✅ Wowza server is accepting connections on {host}:{port}")
            
            if args.test_stream:
                logger.info("Testing RTMP streaming capability...")
                if test_rtmp_connection(args.url):
                    logger.info("✅ Wowza server is accepting RTMP streams")
                else:
                    logger.error("❌ Wowza server is not accepting RTMP streams")
                    sys.exit(1)
        else:
            logger.error(f"❌ Cannot connect to Wowza server at {host}:{port}")
            logger.error("Possible issues:")
            logger.error("  - Wowza Streaming Engine is not running")
            logger.error("  - Firewall is blocking the connection")
            logger.error("  - RTMP port is not the default (1935)")
            sys.exit(1)
            
    except ValueError as e:
        logger.error(f"Error parsing RTMP URL: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 