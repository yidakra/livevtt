#!/usr/bin/env python3
"""
Check Wowza Streaming Engine configuration for LiveVTT integration.
This script verifies that Wowza is properly configured to work with the LiveVTT Caption Module.
"""

import argparse
import asyncio
import aiohttp
import socket
import sys
import json
import logging
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('livevtt-check')

class WowzaChecker:
    def __init__(self, url, timeout=5):
        """Initialize the Wowza checker with the server URL."""
        parsed = urlparse(url)
        self.server = parsed.netloc.split(':')[0]  # Extract hostname without port
        self.url = url
        self.timeout = timeout
        self.results = {
            "server_reachable": False,
            "rtmp_port_open": False,
            "http_port_open": False,
            "module_installed": False,
            "module_version": None,
            "streams": []
        }
    
    async def check_server_reachable(self):
        """Check if the Wowza server is reachable."""
        try:
            # Try to resolve the hostname
            socket.gethostbyname(self.server)
            self.results["server_reachable"] = True
            logger.info(f"✓ Server {self.server} is reachable")
            return True
        except socket.gaierror:
            logger.error(f"✗ Server {self.server} is not reachable")
            self.results["server_reachable"] = False
            return False
    
    async def check_port_open(self, port, service_name):
        """Check if a specific port is open on the server."""
        try:
            # Create a socket and try to connect with timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((self.server, port))
            sock.close()
            
            if result == 0:
                logger.info(f"✓ {service_name} port {port} is open")
                return True
            else:
                logger.error(f"✗ {service_name} port {port} is closed")
                return False
        except Exception as e:
            logger.error(f"✗ Error checking {service_name} port {port}: {e}")
            return False
    
    async def check_module_installed(self):
        """Check if the LiveVTT Caption Module is installed."""
        try:
            url = f"{self.url}/livevtt/captions/status"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.results["module_installed"] = True
                        self.results["module_version"] = data.get("version", "unknown")
                        logger.info(f"✓ LiveVTT Caption Module is installed (version: {self.results['module_version']})")
                        return True
                    else:
                        logger.error(f"✗ LiveVTT Caption Module is not installed or not responding (status: {response.status})")
                        return False
        except aiohttp.ClientError as e:
            logger.error(f"✗ Error checking LiveVTT Caption Module: {e}")
            return False
        except json.JSONDecodeError:
            logger.error("✗ Invalid JSON response from LiveVTT Caption Module")
            return False
    
    async def check_active_streams(self):
        """Check for active streams on the Wowza server."""
        try:
            # This endpoint might require authentication on production Wowza servers
            url = f"{self.url}/v2/servers/_defaultServer_/vhosts/_defaultVHost_/applications"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        applications = data.get("applications", [])
                        
                        if applications:
                            logger.info(f"✓ Found {len(applications)} applications on Wowza server")
                            
                            # Check for streams in each application
                            for app in applications:
                                app_name = app.get("name")
                                streams_url = f"{self.url}/v2/servers/_defaultServer_/vhosts/_defaultVHost_/applications/{app_name}/instances/_definst_/streamfiles"
                                
                                try:
                                    async with session.get(streams_url, timeout=self.timeout) as streams_response:
                                        if streams_response.status == 200:
                                            streams_data = await streams_response.json()
                                            streams = streams_data.get("streamfiles", [])
                                            
                                            for stream in streams:
                                                stream_name = stream.get("name")
                                                self.results["streams"].append({
                                                    "application": app_name,
                                                    "name": stream_name
                                                })
                                                logger.info(f"  - Stream: {app_name}/{stream_name}")
                                except Exception as e:
                                    logger.warning(f"  Could not get streams for application {app_name}: {e}")
                        else:
                            logger.warning("✗ No applications found on Wowza server")
                    else:
                        logger.warning(f"✗ Could not retrieve applications (status: {response.status})")
        except Exception as e:
            logger.warning(f"✗ Error checking active streams: {e}")
    
    async def run_all_checks(self):
        """Run all Wowza configuration checks."""
        logger.info(f"Checking Wowza server at {self.server}...")
        
        # Check if server is reachable
        if not await self.check_server_reachable():
            logger.error("Server is not reachable. Stopping checks.")
            return self.results
        
        # Check RTMP port (1935)
        self.results["rtmp_port_open"] = await self.check_port_open(1935, "RTMP")
        
        # Check HTTP port (8087)
        self.results["http_port_open"] = await self.check_port_open(8087, "HTTP")
        
        if self.results["http_port_open"]:
            # Check if LiveVTT Caption Module is installed
            await self.check_module_installed()
            
            # Check for active streams
            await self.check_active_streams()
        
        return self.results

async def main():
    parser = argparse.ArgumentParser(description="Check Wowza Streaming Engine configuration for LiveVTT")
    parser.add_argument("--url", "-u", required=True, help="Wowza Streaming Engine HTTP URL (e.g., http://server:8087)")
    parser.add_argument("--timeout", "-t", type=int, default=5, help="Connection timeout in seconds")
    args = parser.parse_args()
    
    checker = WowzaChecker(args.url, args.timeout)
    results = await checker.run_all_checks()
    
    # Print summary
    print("\n=== Wowza Configuration Check Summary ===")
    print(f"Server: {checker.server}")
    print(f"Server reachable: {'✓' if results['server_reachable'] else '✗'}")
    print(f"RTMP port (1935) open: {'✓' if results['rtmp_port_open'] else '✗'}")
    print(f"HTTP port (8087) open: {'✓' if results['http_port_open'] else '✗'}")
    print(f"LiveVTT Caption Module installed: {'✓' if results['module_installed'] else '✗'}")
    
    if results['module_version']:
        print(f"Module version: {results['module_version']}")
    
    if results['streams']:
        print(f"\nActive streams ({len(results['streams'])}):")
        for stream in results['streams']:
            print(f"  - {stream['application']}/{stream['name']}")
    else:
        print("\nNo active streams found")
    
    # Determine if configuration is valid for LiveVTT
    if (results['server_reachable'] and 
        results['rtmp_port_open'] and 
        results['http_port_open'] and 
        results['module_installed']):
        print("\n✓ Wowza is properly configured for LiveVTT caption integration")
        return 0
    else:
        print("\n✗ Wowza configuration is incomplete for LiveVTT caption integration")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("Check interrupted by user")
        sys.exit(0) 