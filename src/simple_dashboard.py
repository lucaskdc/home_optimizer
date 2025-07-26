import json
import webbrowser
import os
from datetime import datetime
from main import setup_routing_client, load_json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
load_dotenv('.env.local', override=True)

class SimpleHTMLDashboard:
    def __init__(self):
        self.routing_client = setup_routing_client()
        
    def load_and_process_data(self, costing="auto"):
        """Load destinations and origins, calculate routes"""
        try:
            destinations = load_json("destinations.json")
            origins = load_json("home_options.json")
        except FileNotFoundError as e:
            print(f"Error loading JSON files: {e}")
            return [], [], []
        
        # Geocode locations
        for dest in destinations:
            try:
                dest["coords"] = self.routing_client.geocode(dest["name"])
            except Exception as e:
                print(f"Failed to geocode destination {dest['name']}: {e}")
                dest["coords"] = [0, 0]
        
        for origin in origins:
            try:
                origin["coords"] = self.routing_client.geocode(origin["name"])
            except Exception as e:
                print(f"Failed to geocode origin {origin['name']}: {e}")
                origin["coords"] = [0, 0]
        
        # Calculate routes and scores
        route_data = []
        origin_scores = []
        
        for origin in origins:
            total_score = 0
            valid_routes = 0
            origin_routes = []
            
            for dest in destinations:
                try:
                    response = self.routing_client.get_route(
                        origin["coords"], dest["coords"], costing=costing
                    )
                    
                    if "trip" in response and "summary" in response["trip"]:
                        time_min = response["trip"]["summary"].get("time")
                        if time_min is not None:
                            weighted_time = time_min * dest.get("weight", 1.0)
                            total_score += weighted_time
                            valid_routes += 1
                            
                            route_info = {
                                "destination": dest["name"],
                                "travel_time": round(time_min, 2),
                                "weight": dest.get("weight", 1.0),
                                "weighted_time": round(weighted_time, 2)
                            }
                            origin_routes.append(route_info)
                            route_data.append({
                                "origin": origin["name"],
                                **route_info,
                                "origin_coords": origin["coords"],
                                "dest_coords": dest["coords"]
                            })
                except Exception as e:
                    print(f"Route calculation failed: {origin['name']} -> {dest['name']}: {e}")
            
            if valid_routes > 0:
                avg_score = total_score / valid_routes
                origin_scores.append({
                    "name": origin["name"],
                    "total_score": round(total_score, 2),
                    "avg_score": round(avg_score, 2),
                    "valid_routes": valid_routes,
                    "coords": origin["coords"],
                    "routes": origin_routes
                })
        
        # Sort origins by average score (best first)
        origin_scores.sort(key=lambda x: x["avg_score"])
        
        return route_data, origin_scores, destinations
    
    def generate_html_dashboard(self, route_data, origin_scores, destinations, costing="auto"):
        """Generate HTML dashboard"""
        
        # Calculate statistics
        total_origins = len(origin_scores)
        total_destinations = len(destinations)
        total_routes = len(route_data)
        best_avg_time = origin_scores[0]["avg_score"] if origin_scores else "N/A"
        
        # Generate map data for JavaScript
        map_data = {
            "origins": [{
                "name": origin["name"],
                "coords": origin["coords"],
                "avg_score": origin["avg_score"]
            } for origin in origin_scores],
            "destinations": [{
                "name": dest["name"],
                "coords": dest["coords"],
                "weight": dest.get("weight", 1.0)
            } for dest in destinations]
        }
        
        # Generate transportation mode display
        transport_modes = {
            "auto": "🚗 Car/Auto",
            "bicycle": "🚲 Bicycle", 
            "pedestrian": "🚶 Walking",
            "bus": "🚌 Public Transit",
            "motor_scooter": "🛵 Motor Scooter",
            "truck": "🚛 Truck"
        }
        current_mode = transport_modes.get(costing, f"🚗 {costing}")
        
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Home Location Optimizer Dashboard</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f5f5;
            color: #333;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        h1 {{
            text-align: center;
            margin-bottom: 30px;
            color: #2c3e50;
            font-size: 2.5em;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9em;
        }}
        
        .blue {{ color: #3498db; }}
        .red {{ color: #e74c3c; }}
        .green {{ color: #27ae60; }}
        .orange {{ color: #f39c12; }}
        
        .content-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .card h3 {{
            margin-bottom: 15px;
            color: #2c3e50;
        }}
        
        #map {{
            height: 400px;
            width: 100%;
            border-radius: 5px;
        }}
        
        #barChart {{
            height: 400px;
        }}
        
        .full-width {{
            grid-column: 1 / -1;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        
        th {{
            background-color: #f8f9fa;
            font-weight: 600;
        }}
        
        tr:hover {{
            background-color: #f5f5f5;
        }}
        
        .ranking-list {{
            max-height: 400px;
            overflow-y: auto;
        }}
        
        .ranking-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            margin-bottom: 10px;
            background: #f8f9fa;
            border-radius: 5px;
            border-left: 4px solid #3498db;
        }}
        
        .ranking-item.best {{
            border-left-color: #27ae60;
            background: #d5f4e6;
        }}
        
        .ranking-position {{
            font-weight: bold;
            font-size: 1.2em;
            color: #666;
            min-width: 30px;
        }}
        
        .ranking-details {{
            flex-grow: 1;
            margin-left: 15px;
        }}
        
        .ranking-name {{
            font-weight: 600;
            margin-bottom: 5px;
        }}
        
        .ranking-score {{
            font-size: 0.9em;
            color: #666;
        }}
        
        .mode-indicator {{
            background: #3498db;
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            display: inline-block;
            margin-bottom: 20px;
            font-weight: 500;
        }}
        
        .refresh-note {{
            text-align: center;
            margin-top: 20px;
            padding: 15px;
            background: #e8f4fd;
            border-radius: 5px;
            color: #2c3e50;
        }}
        
        @media (max-width: 768px) {{
            .content-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏠 Home Location Optimizer Dashboard</h1>
        
        <div class="mode-indicator">
            Transportation Mode: {current_mode}
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number blue">{total_origins}</div>
                <div class="stat-label">Potential Locations</div>
            </div>
            <div class="stat-card">
                <div class="stat-number red">{total_destinations}</div>
                <div class="stat-label">Destinations</div>
            </div>
            <div class="stat-card">
                <div class="stat-number green">{total_routes}</div>
                <div class="stat-label">Calculated Routes</div>
            </div>
            <div class="stat-card">
                <div class="stat-number orange">{best_avg_time} min</div>
                <div class="stat-label">Best Average Time</div>
            </div>
        </div>
        
        <div class="content-grid">
            <div class="card">
                <h3>📍 Interactive Map</h3>
                <div id="map"></div>
            </div>
            
            <div class="card">
                <h3>🏆 Location Rankings</h3>
                <div class="ranking-list">
"""
        
        # Add rankings
        for i, origin in enumerate(origin_scores):
            best_class = "best" if i == 0 else ""
            html_content += f"""
                    <div class="ranking-item {best_class}">
                        <div class="ranking-position">#{i+1}</div>
                        <div class="ranking-details">
                            <div class="ranking-name">{origin['name']}</div>
                            <div class="ranking-score">{origin['avg_score']} min average • {origin['valid_routes']} routes</div>
                        </div>
                    </div>
"""
        
        html_content += f"""
                </div>
            </div>
        </div>
        
        <div class="card full-width">
            <h3>📊 Detailed Route Data</h3>
            <table>
                <thead>
                    <tr>
                        <th>Origin</th>
                        <th>Destination</th>
                        <th>Travel Time (min)</th>
                        <th>Weight</th>
                        <th>Weighted Time</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        # Add route data table
        for route in route_data:
            html_content += f"""
                    <tr>
                        <td>{route['origin']}</td>
                        <td>{route['destination']}</td>
                        <td>{route['travel_time']}</td>
                        <td>{route['weight']}</td>
                        <td>{route['weighted_time']}</td>
                    </tr>
"""
        
        html_content += f"""
                </tbody>
            </table>
        </div>
        
        <div class="refresh-note">
            📝 <strong>Note:</strong> Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 
            To update data with different transportation mode, modify the costing parameter in your script and regenerate.
        </div>
    </div>

    <script>
        // Initialize map
        const mapData = {json.dumps(map_data)};
        
        if (mapData.origins.length > 0) {{
            const centerLat = mapData.origins.reduce((sum, o) => sum + o.coords[0], 0) / mapData.origins.length;
            const centerLng = mapData.origins.reduce((sum, o) => sum + o.coords[1], 0) / mapData.origins.length;
            
            const map = L.map('map').setView([centerLat, centerLng], 11);
            
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© OpenStreetMap contributors'
            }}).addTo(map);
            
            // Add origin markers
            mapData.origins.forEach((origin, index) => {{
                const marker = L.marker(origin.coords)
                    .addTo(map)
                    .bindPopup(`
                        <strong>${{origin.name}}</strong><br>
                        Rank: #${{index + 1}}<br>
                        Avg Time: ${{origin.avg_score}} min
                    `);
                
                // Color the best location differently
                if (index === 0) {{
                    marker.setIcon(L.icon({{
                        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
                        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                        iconSize: [25, 41],
                        iconAnchor: [12, 41],
                        popupAnchor: [1, -34],
                        shadowSize: [41, 41]
                    }}));
                }}
            }});
            
            // Add destination markers
            mapData.destinations.forEach(dest => {{
                L.marker(dest.coords)
                    .addTo(map)
                    .bindPopup(`
                        <strong>${{dest.name}}</strong><br>
                        Weight: ${{dest.weight}}
                    `)
                    .setIcon(L.icon({{
                        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
                        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                        iconSize: [25, 41],
                        iconAnchor: [12, 41],
                        popupAnchor: [1, -34],
                        shadowSize: [41, 41]
                    }}));
            }});
        }}
    </script>
</body>
</html>
"""
        
        return html_content
    
    def create_dashboard(self, costing="auto", output_file="dashboard.html"):
        """Create and save HTML dashboard"""
        print(f"Generating dashboard with {costing} transportation mode...")
        
        route_data, origin_scores, destinations = self.load_and_process_data(costing)
        
        if not origin_scores:
            print("No valid data found. Please check your JSON files and routing configuration.")
            return
        
        html_content = self.generate_html_dashboard(route_data, origin_scores, destinations, costing)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Dashboard saved as {output_file}")
        webbrowser.open(f"file://{os.path.abspath(output_file)}")

if __name__ == "__main__":
    dashboard = SimpleHTMLDashboard()
    # You can change the costing parameter here
    dashboard.create_dashboard(costing="auto", output_file="dashboard.html")
