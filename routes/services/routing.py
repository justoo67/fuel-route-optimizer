from dataclasses import dataclass
from typing import List, Tuple
import requests


@dataclass
class RouteSummary:
    distance_miles: float
    duration_hours: float
    coordinates: List[Tuple[float, float]]  # List of (latitude, longitude)
    geojson_geometry: dict


class RoutingService:
    OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"
    METERS_TO_MILES = 0.000621371192

    @classmethod
    def get_route(
        cls,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
    ) -> RouteSummary:
        """
        Calls OSRM API in a single HTTP request to compute driving route.
        Returns distance, duration, polyline coordinates, and GeoJSON geometry.
        """
        # OSRM expects {longitude},{latitude};{longitude},{latitude}
        coords_str = f"{start_lon:.6f},{start_lat:.6f};{end_lon:.6f},{end_lat:.6f}"
        url = f"{cls.OSRM_BASE_URL}/{coords_str}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        }
        headers = {"User-Agent": "TruckRouteFuelPlanner/1.0"}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != "Ok" or not data.get("routes"):
                message = data.get("message", "No driving route found between coordinates.")
                raise ValueError(f"OSRM routing error: {message}")

            route = data["routes"][0]
            distance_meters = route["distance"]
            duration_seconds = route["duration"]
            geometry = route["geometry"]

            # GeoJSON coordinates are [lon, lat]
            # Convert to list of (lat, lon) tuples for spatial matching
            lat_lon_coords = [(pt[1], pt[0]) for pt in geometry["coordinates"]]

            return RouteSummary(
                distance_miles=round(distance_meters * cls.METERS_TO_MILES, 2),
                duration_hours=round(duration_seconds / 3600.0, 2),
                coordinates=lat_lon_coords,
                geojson_geometry=geometry,
            )

        except requests.RequestException as e:
            raise RuntimeError(f"Routing API unavailable: {e}")
