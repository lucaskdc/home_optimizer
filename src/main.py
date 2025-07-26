import folium
from folium.plugins import HeatMap
import webbrowser
from enum import Enum
import json
import requests
from abc import ABC, abstractmethod
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import hashlib
from datetime import datetime

# Load environment variables
load_dotenv()
load_dotenv('.env.local', override=True)  # loads .env.local and overrides .env values

# --- Interfaces ---

class RoutingClient(ABC):
    @abstractmethod
    def geocode(self, address):
        pass

    @abstractmethod
    def get_route(self, origin, destination, costing="auto"):
        pass

    @property
    @abstractmethod
    def name(self):
        pass

# --- Valhalla Implementation ---

from valhalla_client import ValhallaClient
from nominatim_client import NominatimClient

class ValhallaRoutingClient(RoutingClient):
    def __init__(self, valhalla_url, nominatim_url):
        self.valhalla = ValhallaClient(valhalla_url)
        self.nominatim = NominatimClient(nominatim_url)

    def geocode(self, address):
        return self.nominatim.geocode(address)

    def get_route(self, origin, destination, costing="auto"):
        return self.valhalla.get_route(origin, destination, costing=costing)

    @property
    def name(self):
        return "Valhalla"

# --- Google Implementation ---

class GoogleRoutingClient(RoutingClient):
    def __init__(self, api_key):
        self.api_key = api_key

    def geocode(self, address):
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": address, "key": self.api_key}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        results = resp.json().get("results")
        if not results:
            raise Exception(f"Geocode failed for {address}")
        loc = results[0]["geometry"]["location"]
        return [loc["lat"], loc["lng"]]

    def get_route(self, origin, destination, costing="auto"):
        mode_map = {
            "auto": "driving",
            "bicycle": "bicycling",
            "pedestrian": "walking",
            "bus": "transit",
            "motor_scooter": "driving",
            "truck": "driving"
        }
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "mode": mode_map.get(costing, "driving"),
            "key": self.api_key
        }
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data["routes"]:
            return {}
        summary = data["routes"][0]["legs"][0]
        return {
            "trip": {
                "summary": {
                    "time": summary["duration"]["value"] / 60  # seconds to minutes
                }
            }
        }

    @property
    def name(self):
        return "Google"

# --- MongoDB Cache ---

class MongoCache:
    def __init__(self, mongo_url="mongodb://localhost:27017", db_name="routing_cache", collection_name="cache"):
        self.client = MongoClient(mongo_url)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self.collection.create_index("key", unique=True)

    def get(self, key):
        result = self.collection.find_one({"key": key})
        if result:
            return json.loads(result["value"])
        return None

    def set(self, key, value, metadata=None):
        if metadata is None:
            metadata = {}
        self.collection.update_one(
            {"key": key},
            {"$set": {
                "value": json.dumps(value),
                "metadata": metadata,
                "timestamp": datetime.utcnow()
            }},
            upsert=True
        )

# --- Cached Routing Client ---

class CachedRoutingClient(RoutingClient):
    def __init__(self, routing_client, cache):
        self.routing_client = routing_client
        self.cache = cache

    def _generate_key(self, method, *args, **kwargs):
        key_data = json.dumps({
            "client_name": self.routing_client.get_name(),
            "method": method,
            "args": args,
            "kwargs": kwargs
        }, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def geocode(self, address):
        key = self._generate_key("geocode", address)
        cached_result = self.cache.get(key)
        if cached_result is not None:
            return cached_result

        result = self.routing_client.geocode(address)
        metadata = {"method": "geocode", "address": address, "client_name": self.routing_client.get_name()}
        self.cache.set(key, result, metadata)
        return result

    def get_route(self, origin, destination, costing="auto"):
        key = self._generate_key("get_route", origin, destination, costing=costing)
        cached_result = self.cache.get(key)
        if cached_result is not None:
            return cached_result

        result = self.routing_client.get_route(origin, destination, costing=costing)
        metadata = {
            "method": "get_route",
            "origin": origin,
            "destination": destination,
            "costing": costing,
            "client_name": self.routing_client.get_name()
        }
        self.cache.set(key, result, metadata)
        return result

# --- Main logic ---

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

def calculate_score(origin, destinations, routing_client, costing):
    score = 0
    valid_count = 0
    for dest in destinations:
        try:
            response = routing_client.get_route(origin["coords"], dest["coords"], costing=costing)
            if "trip" in response and "summary" in response["trip"]:
                time_min = response["trip"]["summary"].get("time")
                if time_min is None:
                    print(f"No time for route from {origin['name']} to {dest['name']}")
                    continue
                weighted = time_min * dest.get("weight", 1.0)
                score += weighted
                valid_count += 1
                print(f"Route from {origin['name']} to {dest['name']}: {time_min:.2f} min (weight {dest.get('weight', 1.0)})")
            else:
                print(f"No summary for route from {origin['name']} to {dest['name']}")
        except Exception as e:
            print(f"Error for origin {origin['name']} to {dest['name']}: {e}")
    return score, valid_count

def main(routing_client):
    # Load destinations and origins from JSON files
    destinations = load_json("destinations.json")
    origins = load_json("home_options.json")

    destination_points = []
    for dest in destinations:
        dest["coords"] = routing_client.geocode(dest["name"])
        destination_points.append(dest["coords"])

    origins_points = []
    for origin in origins:
        origin["coords"] = routing_client.geocode(origin["name"])
        origins_points.append(origin["coords"])

    costing = Costing.AUTO.value
    heat_data = []

    for origin in origins:
        score, valid_count = calculate_score(origin, destinations, routing_client, costing)
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
    # Choose the provider here:
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

    # Add caching
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    cache = MongoCache(mongo_url)
    cached_routing_client = CachedRoutingClient(routing_client, cache)

    main(cached_routing_client)
    print("END")
