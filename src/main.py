import folium
from folium.plugins import HeatMap
import webbrowser
from enum import Enum
import json
from valhalla_client import ValhallaClient
from nominatim_client import NominatimClient

class Costing(Enum):
    AUTO = "auto"
    BICYCLE = "bicycle"
    PEDESTRIAN = "pedestrian"
    BUS = "bus"
    MOTOR_SCOOTER = "motor_scooter"
    TRUCK = "truck"

def load_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    vallhala = ValhallaClient("http://[::1]:9000/valhalla")
    nominatim = NominatimClient("http://[::1]:9000/nominatim")

    # Load destinations and origins from JSON files
    destinations = load_json("destinations.json")
    origins = load_json("home_options.json")

    destination_points = []
    for dest in destinations:
        dest["coords"] = nominatim.geocode(dest["name"])
        destination_points.append(dest["coords"])

    origins_points = []
    for origin in origins:
        origin["coords"] = nominatim.geocode(origin["name"])
        origins_points.append(origin["coords"])

    costing = Costing.AUTO.value
    heat_data = []

    for origin in origins:
        score = 0
        valid_count = 0
        for dest in destinations:
            try:
                response = vallhala.get_route(origin["coords"], dest["coords"], costing=costing)
                if "trip" in response and "summary" in response["trip"]:
                    distance = response["trip"]["summary"]["length"]  # in km
                    weighted = distance * dest.get("weight", 1.0)
                    score += weighted
                    valid_count += 1
                    print(f"Route from {origin['name']} to {dest['name']}: {distance} km (weight {dest.get('weight', 1.0)})")
                else:
                    print(f"No summary for route from {origin['name']} to {dest['name']}")
            except Exception as e:
                print(f"Error for origin {origin['name']} to {dest['name']}: {e}")
        if valid_count > 0:
            print(f"Total score for origin {origin['name']}: {score} (valid routes: {valid_count})")
            avg_score = score / valid_count
            heat_data.append([origin["coords"][0], origin["coords"][1], avg_score])
        else:
            print(f"No valid routes for origin {origin['name']}")

    # Plot heatmap
    m = folium.Map(location=destination_points[0], zoom_start=13)
    HeatMap(heat_data, radius=20, blur=0, max_zoom=13).add_to(m)
    for dest in destinations:
        folium.Marker(dest["coords"], tooltip=f"Destination: {dest['name']} (weight {dest.get('weight', 1.0)})", icon=folium.Icon(color="red")).add_to(m)
    for origin in origins:
        folium.Marker(
            origin["coords"],
            tooltip=f"Origin: {origin['name']}",
            popup=origin["name"],
            icon=folium.Icon(color="blue")
        ).add_to(m)
    map_file = "weighted_distance_heatmap.html"
    m.save(map_file)
    webbrowser.open(map_file)

if __name__ == "__main__":
    main()
    print("END")