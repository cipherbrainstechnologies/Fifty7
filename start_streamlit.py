#!/usr/bin/env python3
"""
Streamlit startup script for Railway deployment.
Reads PORT from environment and starts Streamlit with proper configuration.
"""

import os
import sys
import subprocess

if __name__ == "__main__":
    # Get port from Railway environment variable
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
    
    # Set Streamlit environment variables
    os.environ["STREAMLIT_SERVER_PORT"] = str(port)
    os.environ["STREAMLIT_SERVER_ADDRESS"] = "0.0.0.0"
    
    # Build Streamlit command
    streamlit_args = [
        sys.executable, "-m", "streamlit", "run",
        "dashboard/ui_frontend.py",
        "--server.port", str(port),
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    
    print(f"Starting Streamlit on 0.0.0.0:{port}")
    print(f"PORT environment variable: {port_env}")
    
    # Start Streamlit (this will block)
    try:
        sys.exit(subprocess.run(streamlit_args).returncode)
    except KeyboardInterrupt:
        print("\nShutting down Streamlit...")
        sys.exit(0)

