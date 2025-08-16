#!/usr/bin/env python3
"""
Demo Mode for Home Optimizer - works without external routing services

This creates a version that works with mock data and calculated distances.
"""

import os
import sys
import math
import json
from pathlib import Path

# Add src directory to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from main import RoutingClient

class DemoRoutingClient(RoutingClient):
    """Demo routing client that calculates routes using distance approximations"""
    
    def __init__(self):
        pass
    
    @property
    def name(self) -> str:
        return "Demo (Mock Data)"
    
    def geocode(self, address: str):
        """Return mock coordinates for demo addresses"""
        # This should not be called if coords are already provided
        mock_coords = {
            "Downtown Apartment": [-30.0346, -51.2177],
            "Shopping Mall": [-30.0277, -51.2287],
            "University Campus": [-30.0732, -51.1209],
            "North Location": [-30.0200, -51.2000],
            "Central Location": [-30.0346, -51.2177],
            "South Location": [-30.0500, -51.2200],
            "West Location": [-30.0346, -51.2400],
            "East Location": [-30.0346, -51.1900]
        }
        
        for location, coords in mock_coords.items():
            if location.lower() in address.lower():
                return coords
        
        # Default coordinates (center of Porto Alegre)
        return [-30.0346, -51.2177]
    
    def get_route(self, origin, destination, costing="auto", departure_time=None, day_of_week=None):
        """Calculate mock route based on distance"""
        
        # Calculate approximate distance using Haversine formula
        lat1, lon1 = origin
        lat2, lon2 = destination
        
        # Convert to radians
        lat1_r = math.radians(lat1)
        lon1_r = math.radians(lon1)
        lat2_r = math.radians(lat2)
        lon2_r = math.radians(lon2)
        
        # Haversine formula
        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r
        a = math.sin(dlat/2)**2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        distance_km = 6371 * c  # Earth's radius in km
        
        # Calculate time based on transport mode
        speed_map = {
            "auto": 40,        # 40 km/h average in city
            "bicycle": 15,     # 15 km/h
            "pedestrian": 5,   # 5 km/h
            "bus": 25,         # 25 km/h with stops
            "motor_scooter": 35,
            "truck": 30
        }
        
        speed = speed_map.get(costing, 40)
        time_minutes = (distance_km / speed) * 60
        
        # Add some randomness for realism
        import random
        time_minutes *= (0.8 + random.random() * 0.4)  # ±20% variation
        
        # Add traffic if time/day specified
        traffic_factor = 1.0
        if departure_time and day_of_week:
            # Add traffic during rush hours on weekdays
            if day_of_week.lower() in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
                hour = int(departure_time.split(':')[0])
                if 7 <= hour <= 9 or 17 <= hour <= 19:  # Rush hours
                    traffic_factor = 1.3
        
        traffic_time = time_minutes * traffic_factor
        
        return {
            "trip": {
                "summary": {
                    "time": time_minutes,
                    "distance": distance_km,
                    "traffic_time": traffic_time,
                    "traffic_impact_percent": (traffic_factor - 1) * 100
                }
            }
        }

def setup_demo_routing_client():
    """Setup demo routing client"""
    return DemoRoutingClient()

def load_demo_data():
    """Load demo data files if they exist, otherwise use defaults"""
    
    try:
        # Try to load demo files first
        if os.path.exists("destinations_demo.json"):
            with open("destinations_demo.json", 'r') as f:
                destinations = json.load(f)
        else:
            destinations = [
                {
                    "name": "Downtown Office",
                    "weight": 5.0,
                    "departure_time_to": "08:00",
                    "departure_time_from": "17:00", 
                    "day_of_week": "Monday",
                    "transport_mode": "auto",
                    "group": "work",
                    "coords": [-30.0346, -51.2177]
                },
                {
                    "name": "Shopping Center",
                    "weight": 2.0,
                    "departure_time_to": "10:00",
                    "departure_time_from": "12:00",
                    "day_of_week": "Saturday", 
                    "transport_mode": "auto",
                    "group": "shopping",
                    "coords": [-30.0277, -51.2287]
                }
            ]
        
        if os.path.exists("home_options_demo.json"):
            with open("home_options_demo.json", 'r') as f:
                origins = json.load(f)
        else:
            origins = [
                {"name": "North Location", "coords": [-30.0200, -51.2000]},
                {"name": "Central Location", "coords": [-30.0346, -51.2177]},
                {"name": "South Location", "coords": [-30.0500, -51.2200]}
            ]
        
        return destinations, origins
        
    except Exception as e:
        print(f"Error loading demo data: {e}")
        return [], []

def run_demo():
    """Run the unified service in demo mode"""
    
    # Set environment variable for demo mode
    os.environ['DEMO_MODE'] = 'true'
    
    # Start the unified service
    from app import main as app_main
    app_main()

if __name__ == '__main__':
    print("Home Location Optimizer - Demo Mode")
    print("This demo works without external routing services")
    print("=" * 50)
    run_demo()