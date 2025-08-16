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
    def get_route(self, origin: List[float], destination: List[float], costing: str = "auto", 
                  departure_time: Optional[str] = None, day_of_week: Optional[str] = None) -> Dict:
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

    def get_route(self, origin: List[float], destination: List[float], costing: str = "auto", 
                  departure_time: Optional[str] = None, day_of_week: Optional[str] = None) -> Dict:
        # Note: Valhalla client doesn't currently support departure time/day parameters
        # This could be extended in the future to pass timing information to Valhalla
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

    def get_route(self, origin: List[float], destination: List[float], costing: str = "auto", 
                  departure_time: Optional[str] = None, day_of_week: Optional[str] = None) -> Dict:
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
            "key": self.api_key,
            "units": "metric"
        }
        
        # Add departure time if provided
        if departure_time and day_of_week:
            departure_timestamp = self._convert_to_timestamp(departure_time, day_of_week)
            if departure_timestamp:
                # Google API supports departure_time for driving and transit modes
                if params["mode"] in ["driving", "transit"]:
                    params["departure_time"] = str(departure_timestamp)
                    # Enable traffic-aware routing for driving mode
                    if params["mode"] == "driving":
                        params["traffic_model"] = "best_guess"  # Enable traffic modeling
                    logger.info(f"Using departure time: {departure_time} on {day_of_week} (timestamp: {departure_timestamp})")
                else:
                    logger.info(f"Departure time not supported for mode: {params['mode']}")
        
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        if not data["routes"]:
            logger.warning(f"No routes found from {origin} to {destination}")
            return {}
            
        summary = data["routes"][0]["legs"][0]
        
        # Extract basic timing information
        result = {
            "trip": {
                "summary": {
                    "time": summary["duration"]["value"] / 60,  # seconds to minutes
                    "distance": summary["distance"]["value"] / 1000  # meters to km
                }
            }
        }
        
        # Add traffic-aware duration if available (for driving mode with departure time)
        if "duration_in_traffic" in summary:
            traffic_time = summary["duration_in_traffic"]["value"] / 60
            result["trip"]["summary"]["traffic_time"] = traffic_time
            
            # Calculate traffic impact
            normal_time = result["trip"]["summary"]["time"]
            traffic_impact = ((traffic_time - normal_time) / normal_time) * 100
            result["trip"]["summary"]["traffic_impact_percent"] = round(traffic_impact, 1)
            
            logger.info(f"Traffic-aware duration: {traffic_time:.2f} min vs normal: {normal_time:.2f} min (impact: {traffic_impact:+.1f}%)")
        
        # Add additional route information if available
        if "overview_polyline" in data["routes"][0]:
            result["trip"]["geometry"] = data["routes"][0]["overview_polyline"]["points"]
        
        # Log detailed route information
        logger.info(f"Route {origin} -> {destination}: {result['trip']['summary']['time']:.2f} min, {result['trip']['summary']['distance']:.2f} km")
        
        return result
    
    def _convert_to_timestamp(self, departure_time: str, day_of_week: str) -> Optional[int]:
        """Convert departure time and day of week to Unix timestamp.
        
        Args:
            departure_time: Time in HH:MM format (e.g., "08:30")
            day_of_week: Day name (e.g., "Monday")
            
        Returns:
            Unix timestamp for the next occurrence of that day/time, or None if invalid
        """
        try:
            from datetime import datetime, timedelta
            import calendar
            
            # Parse the time
            time_parts = departure_time.split(":")
            if len(time_parts) != 2:
                logger.warning(f"Invalid time format: {departure_time}")
                return None
                
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            # Map day names to weekday numbers (Monday=0, Sunday=6)
            day_map = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6
            }
            
            target_weekday = day_map.get(day_of_week.lower())
            if target_weekday is None:
                logger.warning(f"Invalid day of week: {day_of_week}")
                return None
            
            # Get current time
            now = datetime.now()
            current_weekday = now.weekday()
            
            # Calculate days until target day
            days_ahead = target_weekday - current_weekday
            if days_ahead < 0:  # Target day already happened this week
                days_ahead += 7
            elif days_ahead == 0:  # Same day
                # Check if the time has already passed today
                target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target_time <= now:
                    days_ahead = 7  # Use next week
            
            # Create target datetime
            target_date = now + timedelta(days=days_ahead)
            target_datetime = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Convert to Unix timestamp
            timestamp = int(target_datetime.timestamp())
            
            logger.info(f"Converted {departure_time} on {day_of_week} to timestamp {timestamp} ({target_datetime})")
            return timestamp
            
        except Exception as e:
            logger.error(f"Error converting time to timestamp: {e}")
            return None

    @property
    def name(self) -> str:
        return "Google"

# --- MongoDB Cache ---

class MongoCache:
    def __init__(self, mongo_url: str = "mongodb://localhost:27017", db_name: str = "routing_cache", collection_name: str = "cache"):
        # Configure client with shorter timeout for faster failure detection
        self.client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        # Test connection and create index
        self.client.admin.command('ping')  # This will raise an exception if MongoDB is not available
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
            "client_name": self.routing_client.name,
            "method": method,
            "args": args,
            "kwargs": kwargs
        }, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    @property
    def name(self) -> str:
        return "Cached " + self.routing_client.name

    def get_route(self, origin: List[float], destination: List[float], costing: str = "auto", departure_time: Optional[str] = None, day_of_week: Optional[str] = None) -> Dict:
        key = self._generate_key("get_route", origin, destination, costing=costing, departure_time=departure_time, day_of_week=day_of_week)
        cached_result = self.cache.get(key)
        if cached_result is not None:
            logger.info(f"Cache hit for route: {origin} -> {destination}")
            return cached_result

        logger.info(f"Cache miss for route: {origin} -> {destination}")
        result = self.routing_client.get_route(origin, destination, costing=costing, 
                                             departure_time=departure_time, day_of_week=day_of_week)
        metadata = {
            "method": "get_route",
            "origin": origin,
            "destination": destination,
            "costing": costing,
            "departure_time": departure_time,
            "day_of_week": day_of_week,
            "client_name": self.routing_client.name
        }
        self.cache.set(key, result, metadata)
        logger.info(f"Route calculated and cached: {origin} -> {destination}")
        return result

    def geocode(self, address: str) -> List[float]:
        key = self._generate_key("geocode", address=address)
        cached_result = self.cache.get(key)
        if cached_result is not None:
            logger.info(f"Cache hit for geocode: {address}")
            return cached_result

        logger.info(f"Cache miss for geocode: {address}")
        result = self.routing_client.geocode(address)
        metadata = {
            "method": "geocode",
            "address": address,
            "client_name": self.routing_client.name
        }
        self.cache.set(key, result, metadata)
        logger.info(f"Geocode result cached for: {address}")
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

def geocode_locations(routing_client: RoutingClient, destinations: List[Dict], origins: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Geocode all destinations and origins."""
    logger.info("Geocoding destinations and origins")
    
    # Geocode destinations
    for dest in destinations:
        try:
            dest["coords"] = routing_client.geocode(dest["name"])
            logger.info(f"Geocoded destination: {dest['name']}")
        except Exception as e:
            logger.error(f"Failed to geocode destination {dest['name']}: {e}")
            dest["coords"] = [0, 0]
    
    # Geocode origins
    for origin in origins:
        try:
            origin["coords"] = routing_client.geocode(origin["name"])
            logger.info(f"Geocoded origin: {origin['name']}")
        except Exception as e:
            logger.error(f"Failed to geocode origin {origin['name']}: {e}")
            origin["coords"] = [0, 0]
    
    return destinations, origins

def calculate_routes_and_scores(routing_client: RoutingClient, origins: List[Dict], destinations: List[Dict], costing: str = "auto") -> Tuple[List[Dict], List[Dict]]:
    """Calculate routes and scores for all origin-destination pairs.
    
    For destinations with groups, calculates the shortest time to any destination within each group.
    For individual destinations, calculates routes from each origin.
    
    Returns:
        Tuple of (route_data, origin_scores)
        - route_data: List of route information dictionaries
        - origin_scores: List of origin summary dictionaries with scores
    """
    logger.info("Calculating routes and scores")
    route_data = []
    origin_scores = []
    
    # Group ALL destinations by their group field, regardless of transport mode
    grouped_destinations = {}
    individual_destinations = []
    
    for dest in destinations:
        group = dest.get("group")
        if group:
            if group not in grouped_destinations:
                grouped_destinations[group] = []
            grouped_destinations[group].append(dest)
        else:
            individual_destinations.append(dest)
    
    logger.info(f"Found {len(grouped_destinations)} groups with {sum(len(dests) for dests in grouped_destinations.values())} destinations")
    logger.info(f"Found {len(individual_destinations)} individual destinations")
    for group, dests in grouped_destinations.items():
        logger.info(f"Group '{group}': {len(dests)} destinations")
    
    # For each origin, calculate the shortest time to each group
    best_routes_by_origin = {}
    for origin in origins:
        best_routes_by_origin[origin["name"]] = {}
        
        for group_name, group_destinations in grouped_destinations.items():
            shortest_time = float('inf')
            best_route = None
            
            logger.info(f"Calculating routes for origin {origin['name']} to group '{group_name}'")
            for dest in group_destinations:
                try:
                    # Use the transport mode specified for this destination
                    transport_mode = dest.get("transport_mode", "auto")
                    route_costing = "pedestrian" if transport_mode == "walking" else costing
                    
                    departure_time_to = dest.get("departure_time_to")
                    departure_time_from = dest.get("departure_time_from")
                    day_of_week = dest.get("day_of_week")
                    
                    response_to = routing_client.get_route(
                        origin["coords"], dest["coords"], costing=route_costing,
                        departure_time=departure_time_to, day_of_week=day_of_week
                    )
                    
                    response_from = routing_client.get_route(
                        origin["coords"], dest["coords"], costing=route_costing,
                        departure_time=departure_time_from, day_of_week=day_of_week
                    )
                    
                    if ("trip" in response_to and "summary" in response_to["trip"]) and \
                       ("trip" in response_from and "summary" in response_to["trip"]):
                        time_min = response_to["trip"]["summary"].get("time") + response_from["trip"]["summary"].get("time")

                        # Use traffic-aware time if available
                        if "traffic_time" in response_to["trip"]["summary"] and \
                            "traffic_time" in response_from["trip"]["summary"]:
                            traffic_time = response_to["trip"]["summary"]["traffic_time"] + response_from["trip"]["summary"]["traffic_time"]
                            logger.info(f"Using traffic-aware time: {traffic_time:.2f} min (normal: {time_min:.2f} min)")
                            time_min = traffic_time

                        if time_min is not None and time_min < shortest_time:
                            shortest_time = time_min
                            best_route = {
                                "origin": origin["name"],
                                "destination": dest["name"],
                                "group": group_name,
                                "travel_time": round(time_min, 2),
                                "weight": group_destinations[0].get("weight", 1.0),  # Use weight from first in group
                                "weighted_time": round(time_min * group_destinations[0].get("weight", 1.0), 2),
                                "departure_time_to": departure_time_to,
                                "departure_time_from": departure_time_from,
                                "day_of_week": day_of_week,
                                "origin_coords": origin["coords"],
                                "dest_coords": dest["coords"],
                                "transport_mode": transport_mode,
                                "is_shortest_in_group": True
                            }

                            # Add traffic information if available
                            if "traffic_time" in response_to["trip"]["summary"]:
                                best_route["traffic_time"] = round(response_to["trip"]["summary"]["traffic_time"], 2)
                                best_route["normal_time"] = round(response_to["trip"]["summary"]["time"], 2)
                                best_route["traffic_impact_percent"] = response_to["trip"]["summary"].get("traffic_impact_percent", 0)
                            
                            logger.info(f"New shortest route for group '{group_name}': {origin['name']} -> {dest['name']} = {time_min:.2f} min ({transport_mode})")
                except Exception as e:
                    logger.error(f"Route calculation failed: {origin['name']} -> {dest['name']}: {e}")
            
            if best_route:
                best_routes_by_origin[origin["name"]][group_name] = best_route
                logger.info(f"Best route for {origin['name']} to group '{group_name}': {best_route['travel_time']:.2f} min to {best_route['destination']}")
    
    # Calculate routes for each origin
    for origin in origins:
        total_score = 0
        valid_routes = 0
        origin_routes = []
        
        # Add individual destinations for this origin
        for dest in individual_destinations:
            try:
                transport_mode = dest.get("transport_mode", "auto")
                route_costing = "pedestrian" if transport_mode == "walking" else costing
                departure_time_to = dest.get("departure_time_to")
                departure_time_from = dest.get("departure_time_from")
                day_of_week = dest.get("day_of_week")

                logger.info(f"Calculating individual route: {origin['name']} -> {dest['name']} ({transport_mode})")
                response_to = routing_client.get_route(
                    origin["coords"], dest["coords"], costing=route_costing,
                    departure_time=departure_time_to, day_of_week=day_of_week
                )

                response_from = routing_client.get_route(
                    origin["coords"], dest["coords"], costing=route_costing,
                    departure_time=departure_time_from, day_of_week=day_of_week
                )

                if ("trip" in response_to and "summary" in response_to["trip"]) and \
                    ("trip" in response_from and "summary" in response_to["trip"]):
                    time_min = response_to["trip"]["summary"].get("time") + response_from["trip"]["summary"].get("time")

                    # Use traffic-aware time if available
                    if "traffic_time" in response_to["trip"]["summary"] and \
                       "traffic_time" in response_from["trip"]["summary"]:
                        traffic_time = response_to["trip"]["summary"]["traffic_time"] + response_from["trip"]["summary"]["traffic_time"]
                        logger.info(f"Using traffic-aware time: {traffic_time:.2f} min (normal: {time_min:.2f} min)")
                        time_min = traffic_time

                    if time_min is not None:
                        weighted_time = time_min * dest.get("weight", 1.0)
                        total_score += weighted_time
                        valid_routes += 1

                        route_info = {
                            "origin": origin["name"],
                            "destination": dest["name"],
                            "group": dest.get("group", "individual"),
                            "travel_time": round(time_min, 2),
                            "weight": dest.get("weight", 1.0),
                            "weighted_time": round(weighted_time, 2),
                            "departure_time_to": departure_time_to,
                            "departure_time_from": departure_time_from,
                            "day_of_week": day_of_week,
                            "origin_coords": origin["coords"],
                            "dest_coords": dest["coords"],
                            "transport_mode": transport_mode
                        }

                        # Add traffic information if available
                        if "traffic_time" in response_to["trip"]["summary"]:
                            route_info["traffic_time"] = round(response_to["trip"]["summary"]["traffic_time"], 2) + round(response_from["trip"]["summary"]["traffic_time"], 2)
                            route_info["normal_time"] = round(response_to["trip"]["summary"]["time"], 2) + round(response_from["trip"]["summary"]["time"], 2)
                            route_info["traffic_impact_percent"] = (response_to["trip"]["summary"].get("traffic_impact_percent", 0) + response_from["trip"]["summary"].get("traffic_impact_percent", 0)) / 2

                        origin_routes.append(route_info)
                        route_data.append(route_info)
                        
                        logger.info(f"Individual route calculated: {origin['name']} -> {dest['name']} = {time_min:.2f} min ({transport_mode})")
                else:
                    logger.warning(f"No route summary for {origin['name']} -> {dest['name']}")
            except Exception as e:
                logger.error(f"Individual route calculation failed: {origin['name']} -> {dest['name']}: {e}")
        
        # Add the best route for each group (shortest time to any destination in that group)
        for group_name, best_route in best_routes_by_origin[origin["name"]].items():
            weighted_time = best_route["travel_time"] * best_route["weight"]
            total_score += weighted_time
            valid_routes += 1
            
            # Add best route to this origin's routes and global route data
            origin_routes.append(best_route)
            route_data.append(best_route)
            
            logger.info(f"Added best route for group '{group_name}' to {origin['name']} score: {best_route['travel_time']:.2f} min to {best_route['destination']}")
        
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
            logger.info(f"Origin {origin['name']}: {valid_routes} routes, avg score: {avg_score:.2f}")
        else:
            logger.warning(f"No valid routes for origin {origin['name']}")
    
    return route_data, origin_scores

def load_and_process_routing_data(routing_client: RoutingClient, costing: str = "auto") -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Load destinations and origins, geocode them, and calculate all routes.
    
    Returns:
        Tuple of (route_data, origin_scores, destinations)
    """
    logger.info("Loading and processing routing data")
    
    # Load data - check for demo mode first
    prj_path = os.path.join(os.path.dirname(__file__), os.path.pardir)
    
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        # Try to load demo data files
        destinations_file = os.path.join(prj_path, "destinations_demo.json")
        origins_file = os.path.join(prj_path, "home_options_demo.json")
        
        if os.path.exists(destinations_file) and os.path.exists(origins_file):
            destinations = load_json(destinations_file)
            origins = load_json(origins_file)
            logger.info("Loaded demo data files")
        else:
            # Fallback to default files
            destinations = load_json(os.path.join(prj_path, "destinations.json"))
            origins = load_json(os.path.join(prj_path, "home_options.json"))
            logger.info("Demo mode enabled but using default data files")
    else:
        destinations = load_json(os.path.join(prj_path, "destinations.json"))
        origins = load_json(os.path.join(prj_path, "home_options.json"))

    # Geocode locations (skip if coords already provided in demo mode)
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        # In demo mode, coordinates should already be provided
        for dest in destinations:
            if "coords" not in dest:
                dest["coords"] = routing_client.geocode(dest["name"])
        for origin in origins:
            if "coords" not in origin:
                origin["coords"] = routing_client.geocode(origin["name"])
        logger.info("Using provided coordinates in demo mode")
    else:
        destinations, origins = geocode_locations(routing_client, destinations, origins)
    
    # Calculate routes and scores
    route_data, origin_scores = calculate_routes_and_scores(routing_client, origins, destinations, costing)
    
    return route_data, origin_scores, destinations

def main(routing_client: RoutingClient):
    logger.info("Starting main function")
    
    # Load and process all routing data
    route_data, origin_scores, destinations = load_and_process_routing_data(routing_client)
    
    # Prepare data for heatmap
    costing = Costing.AUTO.value
    heat_data = []
    destination_points = [dest["coords"] for dest in destinations]
    
    for origin_score in origin_scores:
        heat_data.append([
            origin_score["coords"][0], 
            origin_score["coords"][1], 
            origin_score["avg_score"]
        ])

    logger.info("Generating heatmap")
    m = folium.Map(location=destination_points[0], zoom_start=13)
    HeatMap(heat_data, radius=20, blur=0, max_zoom=13).add_to(m)
    
    for dest in destinations:
        folium.Marker(
            dest["coords"], 
            tooltip=f"Destination: {dest['name']} (weight {dest.get('weight', 1.0)})", 
            icon=folium.Icon(color="red")
        ).add_to(m)
    
    for origin_score in origin_scores:
        folium.Marker(
            origin_score["coords"],
            tooltip=f"Origin: {origin_score['name']}",
            popup=origin_score["name"],
            icon=folium.Icon(color="blue")
        ).add_to(m)
    
    map_file = "weighted_distance_heatmap.html"
    m.save(map_file)
    webbrowser.open(map_file)
    logger.info("Heatmap saved and opened in browser")

def setup_routing_client():
    """Setup the routing client and cache."""
    # Check for demo mode
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        from demo import DemoRoutingClient
        logger.info("Using demo routing client")
        return DemoRoutingClient()
    
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

    # Try to add caching, but continue without it if MongoDB is not available
    try:
        mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
        cache = MongoCache(mongo_url)
        cached_client = CachedRoutingClient(routing_client, cache)
        logger.info("MongoDB cache enabled")
        return cached_client
    except Exception as e:
        logger.warning(f"MongoDB cache not available ({e}), continuing without caching")
        return routing_client

if __name__ == "__main__":
    cached_routing_client = setup_routing_client()
    main(cached_routing_client)
    print("END")
