#!/usr/bin/env python3
"""
Home Location Optimizer - Single Startup Script

This is the unified entry point for the Home Location Optimizer.
It serves all dashboards through a single web service with multiple routes.

Usage:
    python start.py [--port PORT] [--host HOST] [--debug]

Features:
- Single web service serving all dashboard types
- Main navigation page at /
- Simple HTML dashboard at /simple  
- Interactive Plotly dashboard at /interactive
- 3D Cesium dashboard at /cesium
- Legacy Folium map at /legacy
"""

import sys
import os
import argparse
from pathlib import Path

def main():
    """Main entry point"""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Home Location Optimizer - Unified Dashboard Service')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on (default: 5000)')
    parser.add_argument('--host', default='127.0.0.1', help='Host to run the server on (default: 127.0.0.1)')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    args = parser.parse_args()
    
    # Set environment variables for the app
    os.environ['DASHBOARD_HOST'] = args.host
    os.environ['DASHBOARD_PORT'] = str(args.port)
    if args.debug:
        os.environ['FLASK_DEBUG'] = 'true'
    
    # Ensure we're in the right directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Import and run the main app
    try:
        from app import main as app_main
        app_main()
    except ImportError as e:
        print(f"❌ Failed to import app module: {e}")
        print("Make sure you're running this script from the project root directory.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting the application: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()