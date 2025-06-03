#!/usr/bin/env python3
"""
Mock Wowza server for testing LiveVTT caption integration.
This script simulates a Wowza Streaming Engine with the LiveVTT Caption Module installed.
"""

import asyncio
import json
import logging
from aiohttp import web
import aiohttp_cors

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('mock-wowza')

# Store received captions for inspection
captions = []

async def handle_status(request):
    """Simulate the status endpoint of the LiveVTT Caption Module"""
    return web.json_response({
        "module": "LiveVTTCaptionModule",
        "version": "1.0.0",
        "status": "running",
        "captionsReceived": len(captions)
    })

async def handle_captions(request):
    """Handle caption POST requests from the LiveVTT application"""
    try:
        # Get stream name from query parameters
        stream_name = request.query.get('streamname', 'unknown')
        
        # Parse JSON body
        data = await request.json()
        text = data.get('text', '')
        language = data.get('language', 'eng')
        track_id = data.get('trackId', 99)
        
        # Store the caption
        caption_data = {
            "stream": stream_name,
            "text": text,
            "language": language,
            "trackId": track_id,
            "timestamp": asyncio.get_event_loop().time()
        }
        captions.append(caption_data)
        
        # Log the caption
        logger.info(f"Caption received for stream '{stream_name}': {text}")
        
        # Return success response
        return web.json_response({
            "status": "success",
            "message": "Caption received and processed",
            "captionId": len(captions)
        })
    except Exception as e:
        logger.error(f"Error processing caption: {e}")
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def handle_list_captions(request):
    """Return all captions received so far"""
    return web.json_response({
        "captions": captions,
        "count": len(captions)
    })

async def handle_root(request):
    """Simulate the Wowza server root endpoint"""
    return web.json_response({
        "server": "Mock Wowza Streaming Engine",
        "version": "4.8.0",
        "modules": ["LiveVTTCaptionModule"],
        "endpoints": [
            "/livevtt/captions/status",
            "/livevtt/captions",
            "/livevtt/captions/list"
        ]
    })

async def main():
    # Create a mock caption server
    app = web.Application()
    app.add_routes([
        web.get('/livevtt/captions/status', handle_status),
        web.post('/livevtt/captions', handle_captions),
        web.get('/livevtt/captions', handle_list_captions),
        web.get('/', handle_root),
    ])
    
    # Set CORS headers
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["GET", "POST", "OPTIONS"]
        )
    })
    
    # Apply CORS to all routes
    for route in list(app.router.routes()):
        cors.add(route)
    
    # Start the server
    port = 8086
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', port)
    await site.start()
    
    print(f"Mock Wowza server running at http://127.0.0.1:{port}")
    print("Available endpoints:")
    print("  GET /livevtt/captions/status - Check server status")
    print("  POST /livevtt/captions?streamname=name - Add captions to stream")
    
    try:
        while True:
            await asyncio.sleep(3600)  # Keep the server running
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Mock Wowza server stopped") 