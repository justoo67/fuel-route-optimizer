import re
import urllib.parse
from typing import Optional, Tuple
import requests

# In-memory cache for resolved locations to guarantee 0 network calls on repeat queries
_GEOCODE_CACHE = {}


class GeocodingService:
    PHOTON_URL = "https://photon.komoot.io/api/"

    @classmethod
    def resolve_location(cls, location_str: str) -> Tuple[float, float, str]:
        """
        Resolves a location string to (latitude, longitude, display_name).
        Supports:
          1. Direct coordinates: "41.8781, -87.6298" or "41.8781 -87.6298"
          2. Cached addresses
          3. Fast resolution via Photon (OpenStreetMap geocoder)
        """
        if not location_str or not location_str.strip():
            raise ValueError("Location string cannot be empty.")

        clean_query = location_str.strip()

        # 1. Check if raw coordinates were passed
        coord_match = re.match(
            r"^([+-]?\d+(?:\.\d+)?)[,\s]+([+-]?\d+(?:\.\d+)?)$", clean_query
        )
        if coord_match:
            lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon, f"Coordinates ({lat:.4f}, {lon:.4f})"

        # 2. Check in-memory cache
        cache_key = clean_query.lower()
        if cache_key in _GEOCODE_CACHE:
            return _GEOCODE_CACHE[cache_key]

        # 3. Query Photon API
        query = clean_query
        # Bias towards USA if not specified
        if "usa" not in query.lower() and "united states" not in query.lower():
            query_with_country = f"{query}, USA"
        else:
            query_with_country = query

        params = {"q": query_with_country, "limit": 1}
        headers = {"User-Agent": "TruckRouteFuelPlanner/1.0"}

        try:
            resp = requests.get(cls.PHOTON_URL, params=params, headers=headers, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                # Retry with raw query
                resp = requests.get(cls.PHOTON_URL, params={"q": clean_query, "limit": 1}, headers=headers, timeout=8)
                data = resp.json()
                features = data.get("features", [])

            if not features:
                raise ValueError(f"Could not resolve coordinates for location: '{location_str}'")

            feature = features[0]
            lon, lat = feature["geometry"]["coordinates"]
            props = feature.get("properties", {})
            parts = [props.get("name"), props.get("city"), props.get("state"), props.get("country")]
            display_name = ", ".join(p for p in parts if p) or clean_query

            result = (lat, lon, display_name)
            _GEOCODE_CACHE[cache_key] = result
            return result

        except requests.RequestException as e:
            raise RuntimeError(f"Geocoding service unavailable for '{location_str}': {e}")
