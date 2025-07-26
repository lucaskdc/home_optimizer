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
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Union, Optional
import logging

# Load environment variables
load_dotenv()
load_dotenv('.env.local', override=True)  # loads .env.local and overrides .env values

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Interfaces ---

class RoutingClient(ABC):
    @abstractmethod
    def geocode(self, address: str) -> List[float]:
        pass

    @abstractmethod
    def get_route(self, origin: List[float], destination: List[float], costing: str = "auto") -> Dict:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

# --- Valhalla Implementation ---

from valhalla_client import ValhallaClient
from nominatim_client import NominatimClient

class ValhallaRoutingClient(RoutingClient):
    def __init__(self, valhalla_url: str, nominatim_url: str):
        self.valhalla = ValhallaClient(valhalla_url)
        self.nominatim = NominatimClient(nominatim_url)

    def geocode(self, address: str) -> List[float]:
        return self.nominatim.geocode(address)

    def get_route(self, origin: List[float], destination: List[float], costing: str = "auto") -> Dict:
        return self.valhalla.get_route(origin, destination, costing=costing)

    @property
    def name(self) -> str:
        return "Valhalla"

# --- Google Implementation ---

class GoogleRoutingClient(RoutingClient):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def geocode(self, address: str) -> List[float]:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": address, "key": self.api_key}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        results = resp.json().get("results")
        if not results:
            raise Exception(f"Geocode failed for {address}")
        loc = results[0]["geometry"]["location"]
        return [loc["lat"], loc["lng"]]

    def get_route(self, origin: List[float], destination: List[float], costing: str = "auto") -> Dict:
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
    def name(self) -> str:
        return "Google"

# --- MongoDB Cache ---

class MongoCache:
    def __init__(self, mongo_url: str = "mongodb://localhost:27017", db_name: str = "routing_cache", collection_name: str = "cache"):
        self.client = MongoClient(mongo_url)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self.collection.create_index("key", unique=True)

    def get(self, key: str) -> Optional[Dict]:
        result = self.collection.find_one({"key": key})
        if result:
            return json.loads(result["value"])
        return None

    def set(self, key: str, value: Dict, metadata: Optional[Dict] = None):
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
    def __init__(self, routing_client: RoutingClient, cache: MongoCache):
        self.routing_client = routing_client
        self.cache = cache

    def _generate_key(self, method: str, *args: Tuple, **kwargs: Dict) -> str:
        key_data = json.dumps({
            "client_name": self.routing_client.get_name(),
            "method": method,
            "args": args,
            "kwargs": kwargs
        }, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get_route(self, origin: List[float], destination: List[float], costing: str = "auto", departure_time: Optional[str] = None, day_of_week: Optional[str] = None) -> Dict:
        key = self._generate_key("get_route", origin, destination, costing=costing, departure_time=departure_time, day_of_week=day_of_week)
        cached_result = self.cache.get(key)
        if cached_result is not None:
            logger.info(f"Cache hit for route: {origin} -> {destination}")
            return cached_result

        logger.info(f"Cache miss for route: {origin} -> {destination}")
        result = self.routing_client.get_route(origin, destination, costing=costing)
        metadata = {
            "method": "get_route",
            "origin": origin,
            "destination": destination,
            "costing": costing,
            "departure_time": departure_time,
            "day_of_week": day_of_week,
            "client_name": self.routing_client.get_name()
        }
        self.cache.set(key, result, metadata)
        logger.info(f"Route calculated and cached: {origin} -> {destination}")
        return result

# --- Main logic ---

class Costing(Enum):
    AUTO = "auto"
    BICYCLE = "bicycle"
    PEDESTRIAN = "pedestrian"
    BUS = "bus"
    MOTOR_SCOOTER = "motor_scooter"
    TRUCK = "truck"

def load_json(filename: str) -> Union[List, Dict]:
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def calculate_score(origin: Dict, destinations: List[Dict], routing_client: RoutingClient, costing: str) -> Tuple[float, int]:
    score = 0
    valid_count = 0
    for dest in destinations:
        try:
            departure_time_to = dest.get("departure_time_to")
            departure_time_from = dest.get("departure_time_from")
            day_of_week = dest.get("day_of_week")

            logger.info(f"Calculating route to destination: {dest['name']}")
            response_to = routing_client.get_route(
                origin["coords"], dest["coords"], costing=costing, 
                departure_time=departure_time_to, day_of_week=day_of_week
            )

            logger.info(f"Calculating route from destination: {dest['name']}")
            response_from = routing_client.get_route(
                dest["coords"], origin["coords"], costing=costing, 
                departure_time=departure_time_from, day_of_week=day_of_week
            )

            if "trip" in response_to and "summary" in response_to["trip"] and \
               "trip" in response_from and "summary" in response_from["trip"]:

                time_to = response_to["trip"]["summary"].get("time")
                time_from = response_from["trip"]["summary"].get("time")

                if time_to is None or time_from is None:
                    logger.warning(f"No time for route from {origin['name']} to {dest['name']} or back")
                    continue

                total_time = time_to + time_from
                weighted = total_time * dest.get("weight", 1.0)
                score += weighted
                valid_count += 1

                logger.info(f"Roundtrip from {origin['name']} to {dest['name']}: {total_time:.2f} min (weight {dest.get('weight', 1.0)})")
            else:
                logger.warning(f"No summary for roundtrip from {origin['name']} to {dest['name']}")
        except Exception as e:
            logger.error(f"Error for roundtrip from {origin['name']} to {dest['name']}: {e}")
    return score, valid_count

def main(routing_client: RoutingClient):
    logger.info("Starting main function")
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
            logger.info(f"Total score for origin {origin['name']}: {score} (valid routes: {valid_count})")
            avg_score = score / valid_count
            heat_data.append([origin["coords"][0], origin["coords"][1], avg_score])
        else:
            logger.warning(f"No valid routes for origin {origin['name']}")

    logger.info("Generating heatmap")
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
    logger.info("Heatmap saved and opened in browser")

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
