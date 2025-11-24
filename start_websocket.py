"""
Standalone WebSocket server startup script for Railway deployment.
Use this when deploying WebSocket as a separate Railway service.
"""

import os
import sys
import time
from engine.websocket_server import start_websocket_server

if __name__ == "__main__":
    # Get port from Railway environment variable (Railway requires PORT to be set)
    port_env = os.getenv("PORT")
    if not port_env:
        print("ERROR: PORT environment variable is required but not set")
        print("Railway should provide this automatically. Check your service configuration.")
        sys.exit(1)
    
    try:
        port = int(port_env)
        if not (0 <= port <= 65535):
            print(f"ERROR: PORT must be between 0 and 65535, got {port}")
            sys.exit(1)
    except ValueError:
        print(f"ERROR: PORT must be an integer, got '{port_env}'")
        sys.exit(1)
    
    host = os.getenv("WEBSOCKET_HOST", "0.0.0.0")
    
    print(f"Starting WebSocket server on {host}:{port}")
    print(f"PORT environment variable: {port_env}")
    
    # Start WebSocket server
    try:
        start_websocket_server(host=host, port=port)
        print("WebSocket server started successfully")
    except Exception as e:
        print(f"ERROR: Failed to start WebSocket server: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Keep the script running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down WebSocket server...")
        from engine.websocket_server import stop_websocket_server
        stop_websocket_server()

