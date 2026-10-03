from typing import Dict, Any
from routes.services.geocoding import GeocodingService
from routes.services.routing import RoutingService
from routes.services.station_matching import StationMatchingService
from routes.services.fuel_optimizer import FuelOptimizer, InfeasibleRouteError


class RoutePlanner:
    """
    Orchestrator service that coordinates:
    1. Location geocoding (with in-memory caching)
    2. OSRM driving route retrieval (1 API call)
    3. Spatial route corridor station matching
    4. Optimal fuel purchase calculation under 500-mile range constraint
    """

    @classmethod
    def plan(
        cls,
        start_location: str,
        destination_location: str,
        corridor_radius_miles: float = 10.0,
    ) -> Dict[str, Any]:
        # 1. Resolve locations
        start_lat, start_lon, start_name = GeocodingService.resolve_location(start_location)
        end_lat, end_lon, end_name = GeocodingService.resolve_location(destination_location)

        # 2. Get driving route from OSRM (1 single API call)
        route_summary = RoutingService.get_route(start_lat, start_lon, end_lat, end_lon)

        # 3. Match candidate truck stops along the route corridor
        candidates = StationMatchingService.find_candidate_stops(
            route_coords=route_summary.coordinates,
            route_distance_miles=route_summary.distance_miles,
            corridor_radius_miles=corridor_radius_miles,
        )

        # 4. Optimize fuel purchases
        opt_result = FuelOptimizer.optimize(
            route_distance=route_summary.distance_miles,
            candidate_stops=candidates,
        )

        # 5. Assemble comprehensive, clean response payload
        return {
            "origin": {
                "query": start_location,
                "display_name": start_name,
                "latitude": start_lat,
                "longitude": start_lon,
            },
            "destination": {
                "query": destination_location,
                "display_name": end_name,
                "latitude": end_lat,
                "longitude": end_lon,
            },
            "route": {
                "distance_miles": route_summary.distance_miles,
                "duration_hours": route_summary.duration_hours,
                "corridor_radius_miles": corridor_radius_miles,
                "candidate_stations_found": len(candidates),
                "geometry": route_summary.geojson_geometry,
            },
            "fuel": {
                "total_gallons_consumed": round(opt_result.total_gallons_consumed, 2),
                "total_gallons_purchased": round(opt_result.total_gallons_purchased, 2),
                "total_fuel_cost": round(opt_result.total_cost, 2),
                "fuel_remaining_at_destination_gal": round(opt_result.fuel_remaining_at_destination, 2),
                "total_stops": len(opt_result.stops),
                "vehicle_mpg": 10.0,
                "max_range_miles": 500.0,
            },
            "stops": [stop.to_dict() for stop in opt_result.stops],
            "assumptions": opt_result.assumptions,
        }
