#!/usr/bin/env python3
"""
Unified Home Optimizer Dashboard Service

This service provides access to all dashboard types through a single web interface:
- Simple HTML Dashboard (static generation)
- Interactive Plotly Dashboard (embedded)
- 3D Cesium Dashboard (Flask-based)
- Legacy Folium Map (static generation)

All dashboards are served from different routes with a central navigation menu.
"""

import os
import sys
import json
import tempfile
import webbrowser
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for, send_from_directory
from werkzeug.serving import run_simple
from dotenv import load_dotenv
import logging

# Add src directory to path for imports
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

# Load environment variables
load_dotenv()
load_dotenv('.env.local', override=True)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')

# Import dashboard components
try:
    from main import setup_routing_client, load_and_process_routing_data, main as legacy_main
    from simple_dashboard import SimpleHTMLDashboard
    from cesium_dashboard import CesiumDashboard
    from dashboard import RoutingDashboard
    logger.info("Successfully imported all dashboard components")
except ImportError as e:
    logger.error(f"Failed to import dashboard components: {e}")
    sys.exit(1)

# Global instances
routing_client = None
simple_dashboard = None
cesium_dashboard = None
dash_app = None

def initialize_services():
    """Initialize all dashboard services"""
    global routing_client, simple_dashboard, cesium_dashboard, dash_app
    
    try:
        # Initialize routing client (this may fail gracefully without MongoDB)
        routing_client = setup_routing_client()
        logger.info("Routing client initialized")
        
        # Initialize simple dashboard
        simple_dashboard = SimpleHTMLDashboard()
        logger.info("Simple dashboard initialized")
        
        # Don't initialize cesium dashboard here - it will be initialized when needed
        # This avoids the MongoDB connection issue at startup
        cesium_dashboard = None
        logger.info("Cesium dashboard will be initialized on demand")
        
        logger.info("All dashboard services initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        return False

@app.route('/')
def index():
    """Main navigation page"""
    return render_template('index.html')

@app.route('/simple')
def simple_dashboard_route():
    """Generate and serve simple HTML dashboard"""
    try:
        costing = request.args.get('costing', 'auto')
        
        # Generate the dashboard content
        route_data, origin_scores, destinations = simple_dashboard.load_and_process_data(costing)
        
        if not origin_scores:
            return "No valid data found. Please check your JSON files and routing configuration.", 400
        
        html_content = simple_dashboard.generate_html_dashboard(route_data, origin_scores, destinations, costing)
        
        return html_content
        
    except Exception as e:
        logger.error(f"Error generating simple dashboard: {e}")
        return f"Error generating dashboard: {str(e)}", 500

@app.route('/legacy')
def legacy_dashboard():
    """Generate and serve legacy folium map"""
    try:
        costing = request.args.get('costing', 'auto')
        
        # Generate the legacy map using main.py logic
        route_data, origin_scores, destinations = load_and_process_routing_data(routing_client, costing)
        
        if not origin_scores:
            return "No valid data found. Please check your JSON files and routing configuration.", 400
        
        # Use the legacy main function to generate the map
        legacy_main(routing_client)
        
        # Check if the map file was created
        map_file = "weighted_distance_heatmap.html"
        if os.path.exists(map_file):
            # Read and serve the generated HTML
            with open(map_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Add a back button to the generated HTML
            html_content = html_content.replace(
                '<body>',
                '<body><div style="position:absolute;top:10px;left:10px;z-index:1000;"><a href="/" style="background:#007bff;color:white;padding:10px 15px;border-radius:5px;text-decoration:none;">← Back to Menu</a></div>'
            )
            
            return html_content
        else:
            return "Failed to generate legacy map", 500
            
    except Exception as e:
        logger.error(f"Error generating legacy dashboard: {e}")
        return f"Error generating legacy dashboard: {str(e)}", 500

@app.route('/cesium')
def cesium_dashboard_route():
    """Serve 3D Cesium dashboard"""
    return render_template('cesium_dashboard.html')

@app.route('/interactive')
def interactive_dashboard():
    """Serve a simple redirect page to start the Dash app separately"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Interactive Dashboard - Home Optimizer</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
            .container { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-width: 600px; margin: 0 auto; }
            .btn { display: inline-block; background: #007bff; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; margin: 10px; }
            .btn:hover { background: #0056b3; }
            .back-btn { background: #6c757d; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Interactive Dashboard</h1>
            <p>The interactive Plotly dashboard runs as a separate service on port 8050.</p>
            <p>Click the button below to launch it in a new window:</p>
            
            <a href="http://localhost:8050" target="_blank" class="btn">Launch Interactive Dashboard</a>
            <br>
            <a href="/" class="back-btn btn">← Back to Menu</a>
            
            <div style="margin-top: 30px; padding: 20px; background: #e8f4fd; border-radius: 5px;">
                <h3>Alternative: Run Manually</h3>
                <p>If the button doesn't work, you can start the interactive dashboard manually:</p>
                <code>cd src && python dashboard.py</code>
            </div>
        </div>
        
        <script>
            // Auto-attempt to open the dashboard
            setTimeout(() => {
                window.open('http://localhost:8050', '_blank');
            }, 1000);
        </script>
    </body>
    </html>
    """

# Cesium API endpoints (reused from cesium_dashboard.py)
@app.route('/api/data')
def get_data():
    """API endpoint to get routing data for Cesium dashboard"""
    try:
        costing = request.args.get('costing', 'auto')
        
        # Initialize cesium dashboard on demand
        global cesium_dashboard
        if cesium_dashboard is None:
            from cesium_dashboard import CesiumDashboard
            cesium_dashboard = CesiumDashboard()
        
        route_data, origin_scores, destinations = cesium_dashboard.load_and_process_data(costing)
        
        if not origin_scores:
            return jsonify({'error': 'No data available'})
        
        # Create interpolated grid
        grid_data = cesium_dashboard.create_interpolated_grid(origin_scores)
        
        # Prepare response data
        response_data = {
            'origins': [{
                'name': score['name'],
                'lat': score['coords'][0],
                'lon': score['coords'][1],
                'total_score': score['total_score'],
                'avg_score': score['avg_score'],
                'valid_routes': score['valid_routes']
            } for score in origin_scores],
            
            'destinations': [{
                'name': dest['name'],
                'lat': dest['coords'][0],
                'lon': dest['coords'][1],
                'weight': dest.get('weight', 1.0),
                'group': dest.get('group', 'individual'),
                'transport_mode': dest.get('transport_mode', 'auto')
            } for dest in destinations],
            
            'interpolated_grid': grid_data,
            
            'summary': {
                'origin_count': len(origin_scores),
                'destination_count': len(destinations),
                'route_count': len(route_data),
                'best_score': min(score['total_score'] for score in origin_scores) if origin_scores else 0
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error in /api/data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cesium_token')
def get_cesium_token():
    """Get Cesium access token from environment"""
    token = os.getenv('CESIUM_ACCESS_TOKEN', '')
    return jsonify({'token': token})

def integrate_dash_app():
    """Integrate Dash app with Flask"""
    try:
        # For now, we'll handle Dash separately due to integration complexity
        # The interactive dashboard will be available as a redirect to a separate service
        logger.info("Dash app integration configured for separate service")
        return True
        
    except Exception as e:
        logger.error(f"Failed to integrate Dash app: {e}")
        return False

@app.errorhandler(404)
def not_found(error):
    """Custom 404 handler"""
    return render_template('index.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Custom 500 handler"""
    logger.error(f"Internal server error: {error}")
    return f"Internal server error: {str(error)}", 500

def main():
    """Main function to run the unified dashboard service"""
    print("Home Location Optimizer - Unified Dashboard Service")
    print("=" * 60)
    
    # Initialize services
    print("Initializing dashboard services...")
    if not initialize_services():
        print("Failed to initialize services. Please check your configuration.")
        sys.exit(1)
    
    # Integrate Dash app
    print("Integrating interactive dashboard...")
    if not integrate_dash_app():
        print("Warning: Interactive dashboard integration failed. It will not be available.")
    
    # Configuration
    host = os.getenv('DASHBOARD_HOST', '127.0.0.1')
    port = int(os.getenv('DASHBOARD_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    print("\nStarting unified dashboard service...")
    print(f"URL: http://{host}:{port}")
    print(f"Navigation: http://{host}:{port}/")
    print(f"Simple Dashboard: http://{host}:{port}/simple")
    print(f"Interactive Dashboard: http://{host}:{port}/interactive")
    print(f"3D Cesium Dashboard: http://{host}:{port}/cesium")
    print(f"Legacy Map: http://{host}:{port}/legacy")
    print(f"Press Ctrl+C to stop the server")
    print("=" * 60)
    
    # Open browser
    try:
        import threading
        import time
        
        def open_browser():
            time.sleep(2)  # Wait for server to start
            webbrowser.open(f'http://{host}:{port}')
        
        threading.Thread(target=open_browser, daemon=True).start()
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")
    
    try:
        # Use Werkzeug's development server with better error handling
        run_simple(
            hostname=host,
            port=port,
            application=app,
            use_reloader=debug,
            use_debugger=debug,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\nDashboard service stopped.")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        print(f"Failed to start server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()