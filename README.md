# Valhalla Home Optimizer

This project is a Python application that leverages the Valhalla API and Nominatim to analyze and visualize optimal home locations based on weighted distances to various destinations. It generates a heatmap to help users choose the best home option according to their preferences.

## Project Structure

```
valhalla_home_optimizer/
├── src/
│   ├── main.py
│   ├── valhalla_client.py
│   └── nominatim_client.py
├── home_options.json
├── destinations.json
├── requirements.txt
└── README.md
```

## Installation

1. Clone the repository.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Place your home options in `home_options.json` and your destinations (with weights) in `destinations.json`.
2. Run the main application from the `src` directory:
   ```bash
   cd src
   python main.py
   ```
3. The script will generate a `weighted_distance_heatmap.html` file in the project root, which you can open in your browser to view the results.

## Data Files

- **home_options.json**: List of possible home locations (by name).
- **destinations.json**: List of destinations with associated weights.

## Components

- **main.py**: Orchestrates the workflow, loads data, computes routes, and generates the heatmap.
- **valhalla_client.py**: Handles routing requests to the Valhalla API.
- **nominatim_client.py**: Handles geocoding using the Nominatim API.

## Requirements

- Python 3.7+
- See `requirements.txt` for Python dependencies.

## Contributing

Feel free to submit issues or pull requests for improvements and bug fixes.