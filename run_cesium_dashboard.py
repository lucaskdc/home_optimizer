#!/usr/bin/env python3
"""
Launcher script for the Cesium 3D Dashboard
"""

import os
import sys
import webbrowser
import time
import threading
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
load_dotenv('.env.local', override=True)

# Add src directory to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

def launch_dashboard():
    """Launch the Cesium dashboard"""
    try:
        # Change to src directory
        os.chdir(src_dir)
        
        # Import and run the dashboard
        from cesium_dashboard import app
        
        # Set environment variables if not set
        if not os.getenv('CESIUM_ACCESS_TOKEN'):
            print("Warning: CESIUM_ACCESS_TOKEN not found in environment variables.")
            print("   The dashboard will work with basic terrain, but for better")
            print("   visualizations, get a free token from https://cesium.com/")
            print("   and set it in your .env file: CESIUM_ACCESS_TOKEN=your_token_here")
            print()
        
        port = int(os.getenv('CESIUM_DASHBOARD_PORT', 5000))
        
        # Open browser after a short delay
        def open_browser():
            time.sleep(2)  # Wait for server to start
            webbrowser.open(f'http://localhost:{port}')
        
        threading.Thread(target=open_browser, daemon=True).start()
        
        print(f"Starting Cesium 3D Dashboard...")
        print(f"URL: http://localhost:{port}")
        print(f"Press Ctrl+C to stop the server")
        print()
        
        # Run the Flask app
        app.run(debug=False, host='0.0.0.0', port=port)
        
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    except Exception as e:
        print(f"Error starting dashboard: {e}")
        print("\nMake sure you have:")
        print("1. MongoDB running (for caching)")
        print("2. destinations.json and home_options.json files")
        print("3. Required environment variables in .env file")

if __name__ == "__main__":
    launch_dashboard()
