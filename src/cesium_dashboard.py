import json
import os
import numpy as np
from scipy.interpolate import griddata
from flask import Flask, render_template, jsonify, request
from main import setup_routing_client, load_and_process_routing_data
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()
load_dotenv('.env.local', override=True)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

class CesiumDashboard:
    def __init__(self):
        self.routing_client = setup_routing_client()
        
    def load_and_process_data(self, costing="auto"):
        """Load destinations and origins, calculate routes"""
        try:
            # Use the centralized function from main.py
            route_data, origin_scores, destinations = load_and_process_routing_data(self.routing_client, costing)
            
            logger.info(f"Processed {len(origin_scores)} origins and {len(destinations)} destinations")
            return route_data, origin_scores, destinations
            
        except FileNotFoundError:
            logger.error("destinations.json or home_options.json not found")
            return [], [], []
        except Exception as e:
            logger.error(f"Error processing routing data: {e}")
            return [], [], []
    
    def create_interpolated_grid(self, origin_scores, grid_size=50, expand_factor=0.1):
        """Create an interpolated grid for the colored overlay"""
        if len(origin_scores) < 3:
            return None
            
        # Extract coordinates and scores
        lats = np.array([score['coords'][0] for score in origin_scores])
        lons = np.array([score['coords'][1] for score in origin_scores])
        scores = np.array([score['total_score'] for score in origin_scores])
        
        # Create bounds with expansion
        lat_min, lat_max = lats.min(), lats.max()
        lon_min, lon_max = lons.min(), lons.max()
        
        lat_margin = (lat_max - lat_min) * expand_factor
        lon_margin = (lon_max - lon_min) * expand_factor
        
        lat_min -= lat_margin
        lat_max += lat_margin
        lon_min -= lon_margin
        lon_max += lon_margin
        
        # Create grid
        lat_grid = np.linspace(lat_min, lat_max, grid_size)
        lon_grid = np.linspace(lon_min, lon_max, grid_size)
        lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)
        
        # Interpolate using griddata
        points = np.column_stack((lats, lons))
        grid_points = np.column_stack((lat_mesh.ravel(), lon_mesh.ravel()))
        
        # Use cubic interpolation for smooth results
        interpolated_scores = griddata(
            points, scores, grid_points, 
            method='cubic', fill_value=scores.mean()
        )
        
        # Reshape back to grid
        score_grid = interpolated_scores.reshape(grid_size, grid_size)
        
        # Convert to list format for JSON serialization
        grid_data = []
        for i in range(grid_size):
            for j in range(grid_size):
                if not np.isnan(score_grid[i, j]):
                    grid_data.append({
                        'lat': lat_mesh[i, j],
                        'lon': lon_mesh[i, j],
                        'value': float(score_grid[i, j])
                    })
        
        return {
            'grid_data': grid_data,
            'bounds': {
                'north': lat_max,
                'south': lat_min,
                'east': lon_max,
                'west': lon_min
            },
            'value_range': {
                'min': float(scores.min()),
                'max': float(scores.max())
            }
        }

# Initialize dashboard
dashboard = CesiumDashboard()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('cesium_dashboard.html')

@app.route('/api/data')
def get_data():
    """API endpoint to get routing data"""
    costing = request.args.get('costing', 'auto')
    
    route_data, origin_scores, destinations = dashboard.load_and_process_data(costing)
    
    if not origin_scores:
        return jsonify({'error': 'No data available'})
    
    # Create interpolated grid
    grid_data = dashboard.create_interpolated_grid(origin_scores)
    
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

@app.route('/api/cesium_token')
def get_cesium_token():
    """Get Cesium access token from environment"""
    token = os.getenv('CESIUM_ACCESS_TOKEN', '')
    return jsonify({'token': token})

if __name__ == '__main__':
    port = int(os.getenv('CESIUM_DASHBOARD_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    print(f"Starting Cesium dashboard at http://localhost:{port}")
    print("Make sure to set CESIUM_ACCESS_TOKEN in your environment variables")
    
    app.run(debug=debug, host='0.0.0.0', port=port)
