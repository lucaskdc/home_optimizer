# Cesium 3D Dashboard

This is a 3D interactive dashboard using Cesium.js that visualizes home location optimization data with interpolated color overlays showing total weighted travel times.

## Features

- **3D Interactive Map**: Full 3D globe with terrain using Cesium.js
- **Interpolated Color Overlay**: Smooth color gradients showing travel time patterns across geographic areas
- **Interactive Markers**: Click on home options and destinations to see details
- **Real-time Controls**: Switch transportation modes, toggle overlays, and refresh data
- **Traffic-Aware Routing**: Uses Google Maps API with traffic modeling for accurate timing
- **Group-Based Analysis**: Handles grouped destinations (gyms, churches) with shortest-time calculations

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables** (create `.env` file):
   ```
   # Required for Google routing (recommended)
   USE_GOOGLE=true
   GOOGLE_API_KEY=your_google_api_key_here
   
   # Optional: Cesium access token for enhanced terrain
   CESIUM_ACCESS_TOKEN=your_cesium_token_here
   
   # MongoDB for caching
   MONGO_URL=mongodb://localhost:27017
   
   # Optional: Custom port
   CESIUM_DASHBOARD_PORT=5000
   ```

3. **Get API Keys**:
   - **Google Maps API**: Required for routing. Enable Directions API and Geocoding API
   - **Cesium Access Token** (optional): Free at https://cesium.com/ for enhanced terrain and imagery

4. **Data Files**: Ensure you have:
   - `destinations.json`: Your destinations with coordinates, weights, and timing
   - `home_options.json`: Potential home locations to evaluate

## Running the Dashboard

### Quick Start:
```bash
python run_cesium_dashboard.py
```

### Manual Start:
```bash
cd src
python cesium_dashboard.py
```

The dashboard will open automatically in your browser at `http://localhost:5000`

## Usage

### Controls
- **Transportation Mode**: Switch between auto, bicycle, walking, transit, etc.
- **Toggle Overlay**: Show/hide the interpolated color overlay
- **Show/Hide Markers**: Control visibility of home options and destinations
- **Reset View**: Return to default camera position

### Visualization
- **Green Areas**: Lower total weighted travel times (better locations)
- **Red Areas**: Higher total weighted travel times (worse locations)
- **Blue Markers (H)**: Home location options
- **Red Markers (D)**: Destinations

### Interaction
- **Click Markers**: See detailed information about locations
- **Mouse/Touch**: Navigate the 3D map (rotate, zoom, pan)
- **Real-time Updates**: Changes in transportation mode trigger automatic recalculation

## Data Processing

The dashboard uses the same routing engine as the main application:

1. **Geocoding**: Converts addresses to coordinates
2. **Route Calculation**: Computes travel times with traffic awareness
3. **Group Analysis**: Finds shortest time to any destination within groups
4. **Interpolation**: Creates smooth color overlays using scipy cubic interpolation
5. **Caching**: Stores results in MongoDB for performance

## Technical Details

- **Frontend**: Cesium.js for 3D visualization, Bootstrap for UI
- **Backend**: Flask API serving routing data
- **Interpolation**: Scipy griddata with cubic method for smooth overlays
- **Routing**: Google Directions API with traffic modeling
- **Caching**: MongoDB for route and geocoding cache

## Troubleshooting

### Common Issues:

1. **"No Cesium token" warning**: Optional - dashboard works without it
2. **MongoDB connection error**: Start MongoDB service
3. **Google API quota exceeded**: Check your API usage limits
4. **Empty map**: Verify data files exist and contain valid coordinates

### Performance Tips:

- Use MongoDB caching to avoid repeated API calls
- Set appropriate grid size for interpolation (default: 50x50)
- Enable traffic modeling only when needed (adds API costs)

## Comparison with Other Dashboards

- **Cesium vs Plotly**: 3D globe vs 2D maps, more immersive visualization
- **Cesium vs Folium**: Real-time controls vs static HTML output
- **Interactive**: Live updates vs pre-generated visualizations
