#!/usr/bin/env python3
"""
Home Location Optimizer - Dashboard Launcher

This script provides options to run different types of dashboards:
1. Simple HTML Dashboard (no additional dependencies)
2. Interactive Plotly Dash Dashboard (requires dash, plotly, pandas)
3. Original Folium Map (minimal dependencies)
"""

import sys
import os
from pathlib import Path

def check_dependencies():
    """Check which dependencies are available"""
    deps = {
        'basic': True,  # Always available (uses standard library)
        'dash': False,
        'plotly': False,
        'pandas': False,
        'folium': False
    }
    
    try:
        import dash
        deps['dash'] = True
    except ImportError:
        pass
    
    try:
        import plotly
        deps['plotly'] = True
    except ImportError:
        pass
    
    try:
        import pandas
        deps['pandas'] = True
    except ImportError:
        pass
    
    try:
        import folium
        deps['folium'] = True
    except ImportError:
        pass
    
    return deps

def run_simple_dashboard():
    """Run the simple HTML dashboard"""
    try:
        from simple_dashboard import SimpleHTMLDashboard
        dashboard = SimpleHTMLDashboard()
        dashboard.create_dashboard(costing="auto", output_file="dashboard.html")
        print("Simple HTML dashboard created successfully!")
    except Exception as e:
        print(f"Error running simple dashboard: {e}")

def run_interactive_dashboard():
    """Run the interactive Plotly Dash dashboard"""
    try:
        from dashboard import RoutingDashboard
        dashboard = RoutingDashboard()
        print("Starting interactive dashboard...")
        print("Dashboard will be available at: http://127.0.0.1:8050")
        print("Press Ctrl+C to stop the server")
        dashboard.run()
    except Exception as e:
        print(f"Error running interactive dashboard: {e}")

def run_original_map():
    """Run the original folium-based map"""
    try:
        from main import main, GoogleRoutingClient, ValhallaRoutingClient
        import os
        from dotenv import load_dotenv
        
        # Load environment variables
        load_dotenv()
        load_dotenv('.env.local', override=True)
        
        # Setup routing client
        USE_GOOGLE = os.getenv("USE_GOOGLE", "false").lower() == "true"
        
        if USE_GOOGLE:
            GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
            if not GOOGLE_API_KEY:
                raise ValueError("GOOGLE_API_KEY not found in environment variables")
            routing_client = GoogleRoutingClient(GOOGLE_API_KEY)
        else:
            VALHALLA_URL = os.getenv("VALHALLA_URL", "http://[::1]:9000/valhalla")
            NOMINATIM_URL = os.getenv("NOMINATIM_URL", "http://[::1]:9000/nominatim")
            routing_client = ValhallaRoutingClient(VALHALLA_URL, NOMINATIM_URL)
        
        main(routing_client)
        print("Original folium map created successfully!")
    except Exception as e:
        print(f"Error running original map: {e}")

def install_dependencies():
    """Guide user to install dependencies"""
    print("\nTo install additional dependencies, run:")
    print("pip install -r requirements.txt")
    print("\nOr install specific packages:")
    print("pip install dash plotly pandas  # For interactive dashboard")
    print("pip install folium              # For original map")

def main_menu():
    """Display main menu and handle user choice"""
    deps = check_dependencies()
    
    print("Home Location Optimizer - Dashboard Launcher")
    print("=" * 50)
    
    print("\nAvailable Options:")
    print("1. Simple HTML Dashboard (Recommended)")
    print("   Always available - creates a beautiful HTML report")
    
    if deps['dash'] and deps['plotly'] and deps['pandas']:
        print("2. Interactive Dashboard (Advanced)")
        print("   Available - runs a live web server with interactive charts")
    else:
        print("2. Interactive Dashboard (Advanced)")
        print("   Not available - missing dependencies")
    
    if deps['folium']:
        print("3. Original Folium Map")
        print("   Available - creates the original heatmap")
    else:
        print("3. Original Folium Map")
        print("   Not available - missing folium")
    
    print("4. Install Dependencies")
    print("5. Exit")
    
    print("\n" + "=" * 50)
    choice = input("Select an option (1-5): ").strip()
    
    if choice == "1":
        print("\nCreating simple HTML dashboard...")
        run_simple_dashboard()
    
    elif choice == "2":
        if deps['dash'] and deps['plotly'] and deps['pandas']:
            print("\nStarting interactive dashboard...")
            run_interactive_dashboard()
        else:
            print("\nInteractive dashboard dependencies not installed.")
            print("Please install them first (option 4)")
    
    elif choice == "3":
        if deps['folium']:
            print("\nCreating original folium map...")
            run_original_map()
        else:
            print("\nFolium not installed.")
            print("Please install it first (option 4)")
    
    elif choice == "4":
        install_dependencies()
    
    elif choice == "5":
        print("\nGoodbye!")
        sys.exit(0)
    
    else:
        print("\nInvalid choice. Please select 1-5.")
    
    # Ask if user wants to continue
    print("\n" + "=" * 50)
    continue_choice = input("Would you like to run another option? (y/n): ").strip().lower()
    if continue_choice in ['y', 'yes']:
        print("\n")
        main_menu()
    else:
        print("\nGoodbye!")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nDashboard launcher stopped by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
