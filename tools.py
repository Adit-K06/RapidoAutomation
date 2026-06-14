import requests
import os

RAPIDO_RIDE_COORDS = {
    "Bike Direct": {"x": 540, "y": 1247},
    "Scooty Direct": {"x": 540, "y": 1450},
    "Auto": {"x": 540, "y": 1822},
}

def search_location(query: str) -> list:
    """
    Search for a location in Bengaluru using OpenStreetMap Nominatim (free, no API key needed).
    Returns top 3 results with name, full address, lat, lng.
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": f"{query}, Bengaluru, Karnataka, India",
            "format": "json",
            "limit": 3,
            "addressdetails": 1,
        }
        headers = {"User-Agent": "RapidoAutomator/1.0"}
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()

        results = []
        for item in data:
            results.append({
                "name": item.get("display_name", "").split(",")[0],
                "full_address": item.get("display_name", ""),
                "lat": float(item["lat"]),
                "lng": float(item["lon"]),
            })
        return results
    except Exception as e:
        return []

def get_ride_coords(ride_type: str) -> dict:
    """Returns screen coordinates for the given ride type."""
    return RAPIDO_RIDE_COORDS.get(ride_type, RAPIDO_RIDE_COORDS["Bike Direct"])