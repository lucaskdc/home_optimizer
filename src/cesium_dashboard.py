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
        """Create an interpolated grid using intelligent distance-based weighting"""
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
        
        # Convert to list format for JSON serialization with intelligent interpolation
        grid_data = []
        for i, lat in enumerate(lat_grid):
            for j, lon in enumerate(lon_grid):
                # Calculate distances to all known points
                distances = []
                point_scores = []
                
                for k in range(len(lats)):
                    # Use more accurate distance calculation (Haversine-like)
                    lat_diff = (lats[k] - lat) * 111  # Convert to km
                    lon_diff = (lons[k] - lon) * 111 * np.cos(np.radians(lat))  # Adjust for latitude
                    distance_km = np.sqrt(lat_diff**2 + lon_diff**2)
                    
                    distances.append(distance_km)
                    point_scores.append(scores[k])
                
                distances = np.array(distances)
                point_scores = np.array(point_scores)
                
                # Find nearest point and its distance
                nearest_idx = np.argmin(distances)
                nearest_distance = distances[nearest_idx]
                nearest_score = point_scores[nearest_idx]
                
                # Intelligent interpolation based on distance decay
                if nearest_distance <= 2.0:  # Within 2km - use distance-weighted average
                    # Use inverse distance weighting with exponential decay
                    # All points within 2km contribute, with varying influence based on distance
                    weights = []
                    contributing_scores = []
                    
                    for k in range(len(distances)):
                        if distances[k] <= 2.0:  # Only consider nearby points
                            # Exponential decay: weight = exp(-distance^2 / sigma^2)
                            # Closer points get much higher weight, but always some variation
                            if distances[k] < 0.05:  # Very close (50m) - avoid division by zero
                                sigma = 0.3  # Tight influence for very close points
                            elif distances[k] <= 0.5:  # Close (up to 500m)
                                sigma = 0.4  # Medium influence
                            else:  # Medium distance (500m - 2km)
                                sigma = 0.8  # Broader influence
                            
                            weight = np.exp(-(distances[k]**2) / (2 * sigma**2))
                            weights.append(weight)
                            contributing_scores.append(point_scores[k])
                    
                    weights = np.array(weights)
                    contributing_scores = np.array(contributing_scores)
                    
                    if len(weights) > 0 and np.sum(weights) > 0:
                        # Weighted average with distance-dependent bias
                        interpolated_score = np.sum(weights * contributing_scores) / np.sum(weights)
                        
                        # Add small distance penalty for areas between points
                        if nearest_distance > 0.1:  # Beyond 100m, add small penalty
                            distance_penalty = (nearest_distance - 0.1) * 2  # 2 minutes per km beyond 100m
                            interpolated_score += distance_penalty
                    else:
                        interpolated_score = nearest_score + (nearest_distance * 10)  # Heavy penalty for isolated points
                else:
                    # Beyond 2km - use nearest score with heavy distance penalty
                    distance_penalty = (nearest_distance - 0.5) * 8  # 8 minutes per km penalty
                    interpolated_score = nearest_score + distance_penalty
                
                grid_data.append({
                    'lat': lat,
                    'lon': lon,
                    'value': float(interpolated_score)
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
                'max': float(max(scores.max(), scores.max() + 20))  # Extend range to account for penalties
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
