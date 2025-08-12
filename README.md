# Home Optimizer

A powerful Python application that helps you find the optimal home location based on your daily travel patterns. The tool analyzes weighted distances to various destinations (work, gym, shopping, etc.) and generates interactive visualizations to help you make data-driven housing decisions.

## 🌟 Features

- **Multiple Routing Providers**: Support for both Valhalla (open-source) and Google Maps API with traffic modeling
- **Interactive Visualizations**: 
  - 2D heatmaps using Folium
  - Interactive web dashboards with Dash/Plotly
  - 3D globe visualization with Cesium.js
- **Smart Destination Analysis**: Configure destinations with weights, preferred times, and transport modes
- **Traffic-Aware Routing**: Account for real-world traffic patterns and departure times
- **Caching System**: MongoDB integration for efficient API usage and faster processing
- **Flexible Configuration**: Easy-to-configure JSON files for homes and destinations

## 🚀 Quick Start

### Prerequisites

- Python 3.7 or higher
- MongoDB (optional, for caching)
- API access to routing services (see Configuration section)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/lucaskdc/home_optimizer.git
   cd home_optimizer
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables** (copy `.env.example` to `.env`):
   ```bash
   cp .env.example .env
   ```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Routing Provider Selection
USE_GOOGLE=false  # Set to true for Google Maps API, false for Valhalla

# Google Maps API (required if USE_GOOGLE=true)
GOOGLE_API_KEY=your_google_api_key_here

# Valhalla Configuration (required if USE_GOOGLE=false)
VALHALLA_URL=http://localhost:8002/route
NOMINATIM_URL=http://localhost:8080/nominatim

# Optional: Cesium Access Token for 3D visualization
CESIUM_ACCESS_TOKEN=your_cesium_token_here

# Optional: MongoDB for caching
MONGO_URL=mongodb://localhost:27017

# Optional: Dashboard port
CESIUM_DASHBOARD_PORT=5000
```

### API Keys Setup

#### Google Maps API (Recommended)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the following APIs:
   - Directions API
   - Geocoding API
   - Places API (optional)
3. Create an API key and add it to your `.env` file

#### Valhalla (Open Source Alternative)
1. Follow the [Valhalla installation guide](https://valhalla.readthedocs.io/)
2. Set up a local Valhalla server
3. Configure `VALHALLA_URL` and `NOMINATIM_URL` in your `.env` file

#### Cesium Access Token (Optional)
1. Sign up at [Cesium.com](https://cesium.com/) (free tier available)
2. Get your access token from the dashboard
3. Add it to your `.env` file for enhanced 3D terrain

## 📊 Usage

### 1. Configure Your Data

#### Home Options (`home_options.json`)
List potential home locations:

```json
[
    {"name": "Downtown Apartment, City, State"},
    {"name": "Suburban House, City, State"},
    {"name": "Riverside Condo, City, State"}
]
```

#### Destinations (`destinations.json`)
Configure your regular destinations with weights and timing:

```json
[
    {
        "name": "Main Office, City, State",
        "weight": 5.0,
        "departure_time_to": "08:00",
        "departure_time_from": "17:00",
        "day_of_week": "Monday",
        "transport_mode": "auto",
        "group": "work"
    },
    {
        "name": "Grocery Store, City, State",
        "weight": 2.0,
        "departure_time_to": "10:00",
        "departure_time_from": "11:00",
        "day_of_week": "Saturday",
        "transport_mode": "auto",
        "group": "shopping"
    }
]
```

**Field Descriptions:**
- `weight`: Importance multiplier (higher = more important)
- `departure_time_to/from`: Time preferences for travel
- `day_of_week`: Day for traffic modeling
- `transport_mode`: `auto`, `walking`, `bicycle`, `transit`
- `group`: Category for organizing destinations

### 2. Run Analysis

#### Basic Heatmap Generation
```bash
cd src
python main.py
```
This generates `weighted_distance_heatmap.html` in the project root.

#### Interactive Web Dashboard
```bash
cd src
python dashboard.py
```
Opens an interactive dashboard at `http://localhost:8050`

#### 3D Cesium Dashboard
```bash
python run_cesium_dashboard.py
```
Launches a 3D interactive globe at `http://localhost:5000`

#### Simple HTML Dashboard
```bash
cd src
python simple_dashboard.py
```
Generates a comprehensive HTML report.

### 3. Interpret Results

- **Green areas**: Lower total weighted travel times (better locations)
- **Red areas**: Higher total weighted travel times (worse locations)
- **Markers**: Home options (H) and destinations (D)
- **Interactive controls**: Switch transport modes, toggle overlays

## 📁 Project Structure

```
home_optimizer/
├── src/                          # Source code
│   ├── main.py                   # Core routing logic and heatmap generation
│   ├── dashboard.py              # Interactive Dash web dashboard
│   ├── cesium_dashboard.py       # 3D Cesium globe visualization
│   ├── simple_dashboard.py       # Static HTML dashboard
│   ├── valhalla_client.py        # Valhalla API client
│   └── nominatim_client.py       # Nominatim geocoding client
├── home_options.json             # Home location candidates
├── destinations.json             # Weighted destinations configuration
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variables template
├── run_cesium_dashboard.py       # Cesium dashboard launcher
└── README.md                     # This file
```

## 🔧 Advanced Configuration

### Custom Routing Parameters

Modify routing behavior by editing the configuration in `main.py`:

- **Grid size**: Adjust heatmap resolution
- **Transport modes**: Add custom routing profiles
- **Caching**: Configure MongoDB connection settings
- **API limits**: Set request throttling parameters

### Batch Processing

For multiple scenarios, you can programmatically modify the JSON files and run analyses:

```python
from main import setup_routing_client, load_and_process_routing_data

# Setup
client = setup_routing_client()

# Run analysis
route_data, origin_scores, destinations = load_and_process_routing_data(client, "auto")

# Process results
best_location = min(origin_scores, key=lambda x: x["avg_score"])
print(f"Best location: {best_location['name']}")
```

## 🐛 Troubleshooting

### Common Issues

**MongoDB Connection Error**
```
pymongo.errors.ServerSelectionTimeoutError
```
**Solution**: Install and start MongoDB, or disable caching in the code.

**Google API Quota Exceeded**
```
API quota exceeded
```
**Solution**: Check your Google Cloud Console usage limits and billing.

**Empty Visualization**
```
No routes calculated
```
**Solution**: Verify your data files contain valid addresses and API keys are correct.

**Geocoding Failures**
```
Address not found
```
**Solution**: Use more specific addresses (include city, state, country).

### Performance Tips

1. **Use MongoDB caching** to avoid repeated API calls
2. **Limit grid size** for faster processing (trade-off with resolution)
3. **Use Valhalla** for cost-free routing (requires local setup)
4. **Batch process** multiple scenarios efficiently

### Development Mode

For development and testing:

```bash
# Skip caching and use debug mode
export DEBUG_MODE=true
export SKIP_CACHE=true

# Run with verbose logging
python -c "import logging; logging.basicConfig(level=logging.DEBUG)"
cd src && python main.py
```

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** and add tests
4. **Run the test suite**: `python test_refactoring.py`
5. **Commit your changes**: `git commit -m 'Add amazing feature'`
6. **Push to the branch**: `git push origin feature/amazing-feature`
7. **Open a Pull Request**

### Development Setup

```bash
# Install development dependencies
pip install -r requirements.txt

# Run tests
python test_refactoring.py

# Check code style (if available)
flake8 src/
```

## 📄 License

This project is licensed under the AGPL-3.0 License. Feel free to use, modify, and distribute according to the terms of the AGPL license.

## 🙏 Acknowledgments

- [Valhalla](https://valhalla.readthedocs.io/) for open-source routing
- [OpenStreetMap](https://www.openstreetmap.org/) for mapping data
- [Folium](https://python-visualization.github.io/folium/) for mapping visualizations
- [Cesium](https://cesium.com/) for 3D globe visualization