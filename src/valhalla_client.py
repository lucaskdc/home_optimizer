import requests

class ValhallaClient:
    def __init__(self, base_url="https://valhalla.openstreetmap.de"):
        self.base_url = base_url

    def get_route(self, start, end, costing="auto"):
        # start and end should be (lat, lon) tuples
        url = f"{self.base_url}/route"
        payload = {
            "locations": [
                {"lat": start[0], "lon": start[1]},
                {"lat": end[0], "lon": end[1]}
            ],
            "costing": costing
        }
        response = requests.post(url, json=payload)
        return self.handle_response(response)

    def get_geocode(self, text):
        url = f"{self.base_url}/search"
        payload = {"text": text}
        response = requests.post(url, json=payload)
        return self.handle_response(response)

    def handle_response(self, response):
        if not response.ok:
            raise Exception(f"Valhalla API error: {response.status_code} {response.text}")
        return response.json()