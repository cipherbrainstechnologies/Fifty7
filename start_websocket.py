"""
Standalone WebSocket server startup script for Railway deployment.
Use this when deploying WebSocket as a separate Railway service.
"""

import os
import time
from engine.websocket_server import start_websocket_server

if __name__ == "__main__":
    # Get port from Railway environment variable
    port = int(os.getenv("PORT", "8765"))
    host = os.getenv("WEBSOCKET_HOST", "0.0.0.0")
    
    print(f"Starting WebSocket server on {host}:{port}")
    
    # Start WebSocket server
    start_websocket_server(host=host, port=port)
    
    # Keep the script running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down WebSocket server...")
        from engine.websocket_server import stop_websocket_server
        stop_websocket_server()

