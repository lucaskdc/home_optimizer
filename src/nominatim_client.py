import requests

class NominatimClient:
    def __init__(self, base_url="https://nominatim.openstreetmap.org"):
        self.base_url = base_url

    def geocode(self, query):
        params = {
            "q": query,
            "format": "json",
            "limit": 1
        }
        headers = {
            "User-Agent": "valhallaapi-project/1.0"
        }
        response = requests.get(f"{self.base_url}/search", params=params, headers=headers)
        response.raise_for_status()
        results = response.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            return (lat, lon)
        else:
            raise Exception(f"No results found for query: {query}")

    def reverse(self, lat, lon):
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json"
        }
        headers = {
            "User-Agent": "valhallaapi-project/1.0"
        }
        response = requests.get(f"{self.base_url}/reverse", params=params, headers=headers)
        response.raise_for_status()
        result = response.json()
        if "display_name" in result:
            return result["display_name"]
        else:
            raise Exception(f"No address found for coordinates: {lat}, {lon}")
