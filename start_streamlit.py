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
    
    # Verify Streamlit is installed
    try:
        import streamlit
        print(f"Streamlit version: {streamlit.__version__}")
    except ImportError:
        print("ERROR: Streamlit is not installed!")
        print("Attempting to install Streamlit...")
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "streamlit>=1.28.0", "streamlit-authenticator>=0.2.3"],
                check=True,
                capture_output=True,
                text=True
            )
            print("Streamlit installed successfully")
            import streamlit  # Import again after installation
        except Exception as e:
            print(f"ERROR: Failed to install Streamlit: {e}")
            print("Please ensure Streamlit is in requirements.txt and build completed successfully")
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
    print(f"Python executable: {sys.executable}")
    
    # Start Streamlit (this will block)
    try:
        sys.exit(subprocess.run(streamlit_args).returncode)
    except KeyboardInterrupt:
        print("\nShutting down Streamlit...")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: Failed to start Streamlit: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

