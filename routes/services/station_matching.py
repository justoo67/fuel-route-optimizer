import math
from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
from scipy.spatial import cKDTree
from fuel_stops.models import TruckStop

EARTH_RADIUS_MILES = 3958.8


@dataclass
class CandidateStop:
    station_id: int
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    retail_price: float
    mile_marker: float      # Distance from route start in miles
    detour_miles: float     # Perpendicular distance off route in miles

    def to_dict(self):
        return {
            "station_id": self.station_id,
            "opis_id": self.opis_id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "retail_price": self.retail_price,
            "mile_marker": round(self.mile_marker, 2),
            "detour_miles": round(self.detour_miles, 2),
        }


def lat_lon_to_cartesian_3d(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Converts latitude and longitude arrays to 3D Cartesian coordinates (in miles)."""
    rad_lat = np.radians(lats)
    rad_lon = np.radians(lons)
    x = EARTH_RADIUS_MILES * np.cos(rad_lat) * np.cos(rad_lon)
    y = EARTH_RADIUS_MILES * np.cos(rad_lat) * np.sin(rad_lon)
    z = EARTH_RADIUS_MILES * np.sin(rad_lat)
    return np.column_stack([x, y, z])


class StationMatchingService:
    @classmethod
    def find_candidate_stops(
        cls,
        route_coords: List[Tuple[float, float]],  # List of (latitude, longitude)
        route_distance_miles: float,
        corridor_radius_miles: float = 10.0,
    ) -> List[CandidateStop]:
        """
        High-performance two-stage corridor matching:
        1. Bounding box database pre-filter for geographic scope.
        2. 3D Cartesian cKDTree spatial query for sub-15ms nearest-neighbor and mile marker projection.
        """
        if not route_coords or len(route_coords) < 2:
            return []

        route_lats = np.array([c[0] for c in route_coords], dtype=np.float64)
        route_lons = np.array([c[1] for c in route_coords], dtype=np.float64)

        # 1. Bounding Box Query
        min_lat, max_lat = float(route_lats.min()), float(route_lats.max())
        min_lon, max_lon = float(route_lons.min()), float(route_lons.max())

        lat_buffer = max(corridor_radius_miles / 60.0, 0.2)
        lon_buffer = max(corridor_radius_miles / 45.0, 0.25)

        stops_qs = TruckStop.objects.filter(
            latitude__gte=min_lat - lat_buffer,
            latitude__lte=max_lat + lat_buffer,
            longitude__gte=min_lon - lon_buffer,
            longitude__lte=max_lon + lon_buffer,
            country="US",
        ).values(
            "id", "opis_id", "name", "address", "city", "state",
            "latitude", "longitude", "retail_price"
        )

        stops_list = list(stops_qs)
        if not stops_list:
            return []

        # 2. Compute cumulative mileage along route vertices
        route_xyz = lat_lon_to_cartesian_3d(route_lats, route_lons)
        d_xyz = np.diff(route_xyz, axis=0)
        seg_dists = np.sqrt((d_xyz ** 2).sum(axis=1))
        cum_dist = np.insert(np.cumsum(seg_dists), 0, 0.0)

        # Scale cumulative distance to match OSRM driving distance
        total_poly_dist = cum_dist[-1]
        scale = route_distance_miles / total_poly_dist if total_poly_dist > 0 else 1.0
        cum_dist_miles = cum_dist * scale

        # 3. Build 3D KDTree of route vertices
        tree = cKDTree(route_xyz)

        # 4. Query station coordinates against route KDTree
        stop_lats = np.array([s["latitude"] for s in stops_list], dtype=np.float64)
        stop_lons = np.array([s["longitude"] for s in stops_list], dtype=np.float64)
        stop_xyz = lat_lon_to_cartesian_3d(stop_lats, stop_lons)

        dists, indices = tree.query(stop_xyz, distance_upper_bound=corridor_radius_miles)

        candidates: List[CandidateStop] = []
        for i, (dist, idx) in enumerate(zip(dists, indices)):
            if dist <= corridor_radius_miles and idx < len(cum_dist_miles):
                stop_data = stops_list[i]
                mile_marker = float(cum_dist_miles[idx])

                candidates.append(
                    CandidateStop(
                        station_id=stop_data["id"],
                        opis_id=stop_data["opis_id"],
                        name=stop_data["name"],
                        address=stop_data["address"],
                        city=stop_data["city"],
                        state=stop_data["state"],
                        latitude=stop_data["latitude"],
                        longitude=stop_data["longitude"],
                        retail_price=float(stop_data["retail_price"]),
                        mile_marker=mile_marker,
                        detour_miles=float(dist),
                    )
                )

        # Sort chronologically along route
        candidates.sort(key=lambda s: s.mile_marker)

        # Deduplicate stations with the same OPIS ID, keeping closest detour
        unique_candidates = []
        seen_opis = set()
        for c in candidates:
            if c.opis_id not in seen_opis:
                seen_opis.add(c.opis_id)
                unique_candidates.append(c)

        return unique_candidates
