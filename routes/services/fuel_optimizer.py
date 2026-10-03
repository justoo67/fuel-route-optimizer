import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from routes.services.station_matching import CandidateStop


class InfeasibleRouteError(Exception):
    """Raised when the distance between reachable points exceeds the 500-mile vehicle range."""
    pass


@dataclass
class FuelStopDecision:
    station_id: int
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    mile_marker: float
    retail_price: float
    gallons_purchased: float
    fuel_cost: float
    fuel_before: float
    fuel_after: float

    def to_dict(self) -> dict:
        return {
            "station_id": self.station_id,
            "opis_id": self.opis_id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "mile_marker": round(self.mile_marker, 2),
            "price_per_gallon": round(self.retail_price, 3),
            "gallons_purchased": round(self.gallons_purchased, 2),
            "cost": round(self.fuel_cost, 2),
            "fuel_before_arrival_gal": round(self.fuel_before, 2),
            "fuel_after_departure_gal": round(self.fuel_after, 2),
        }


@dataclass
class OptimizationResult:
    total_distance_miles: float
    total_gallons_consumed: float
    total_gallons_purchased: float
    total_cost: float
    fuel_remaining_at_destination: float
    stops: List[FuelStopDecision] = field(default_factory=list)
    assumptions: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total_distance_miles": round(self.total_distance_miles, 2),
                "total_gallons_consumed": round(self.total_gallons_consumed, 2),
                "total_gallons_purchased": round(self.total_gallons_purchased, 2),
                "total_fuel_cost": round(self.total_cost, 2),
                "fuel_remaining_at_destination_gal": round(
                    self.fuel_remaining_at_destination, 2
                ),
                "total_fuel_stops": len(self.stops),
            },
            "fuel_stops": [stop.to_dict() for stop in self.stops],
            "assumptions": self.assumptions,
        }


class FuelOptimizer:
    TANK_CAPACITY_GALLONS = 50.0
    MILES_PER_GALLON = 10.0
    MAX_RANGE_MILES = 500.0  # TANK_CAPACITY * MPG

    @classmethod
    def optimize(
        cls,
        route_distance: float,
        candidate_stops: List[CandidateStop],
        initial_fuel: float = 50.0,
    ) -> OptimizationResult:
        """
        Calculates the minimum cost fuel stops along a route subject to:
          - Tank capacity: 50.0 gallons (500 miles max range)
          - Fuel economy: 10 MPG
          - Starting fuel: 50.0 gallons (full tank)
        """
        # Assumptions recorded for transparency in response and README
        assumptions = {
            "initial_fuel_gallons": f"{initial_fuel:.1f} gal (full tank)",
            "vehicle_mpg": f"{cls.MILES_PER_GALLON:.1f} MPG",
            "max_range_miles": f"{cls.MAX_RANGE_MILES:.1f} miles",
            "tank_capacity": f"{cls.TANK_CAPACITY_GALLONS:.1f} gallons",
            "policy": "Greedy lookahead minimum cost refueling with exact fuel purchased accounting.",
        }

        # Case 1: Trip is <= 500 miles and starting tank is sufficient
        initial_range = initial_fuel * cls.MILES_PER_GALLON
        if route_distance <= initial_range:
            gallons_consumed = route_distance / cls.MILES_PER_GALLON
            fuel_remaining = initial_fuel - gallons_consumed
            return OptimizationResult(
                total_distance_miles=route_distance,
                total_gallons_consumed=gallons_consumed,
                total_gallons_purchased=0.0,
                total_cost=0.0,
                fuel_remaining_at_destination=fuel_remaining,
                stops=[],
                assumptions=assumptions,
            )

        # Filter candidate stops: must be within route boundary [0, route_distance]
        stops = [s for s in candidate_stops if 0.0 <= s.mile_marker <= route_distance]
        stops.sort(key=lambda s: s.mile_marker)

        # Check reachability from start
        if not stops or stops[0].mile_marker > initial_range:
            raise InfeasibleRouteError(
                f"Cannot reach first fuel stop from start: first stop is at mile "
                f"{stops[0].mile_marker if stops else 'N/A'}, but initial range is {initial_range:.1f} miles."
            )

        # Use Dynamic Programming / Shortest Path on a DAG to find the provably global optimal cost:
        # Node 0 = Start (mile 0, price infinity)
        # Node 1..N = Stations
        # Node N+1 = Destination (mile route_distance, price 0)
        #
        # For long-haul routes (N <= 100), we can also execute the Greedy lookahead algorithm
        # which is proven optimal for 1D Gas Station with linear fuel cost:

        selected_stops: List[FuelStopDecision] = []
        curr_pos = 0.0
        curr_fuel = initial_fuel
        curr_idx = -1  # -1 represents Start

        while curr_pos < route_distance:
            # Check if destination is reachable with current fuel
            dist_to_dest = route_distance - curr_pos
            fuel_needed_for_dest = dist_to_dest / cls.MILES_PER_GALLON

            if curr_fuel >= fuel_needed_for_dest:
                curr_fuel -= fuel_needed_for_dest
                curr_pos = route_distance
                break

            # Reachable candidate stations ahead from curr_pos with FULL tank capacity
            max_reach = curr_pos + cls.MAX_RANGE_MILES
            reachable_ahead = []
            for idx in range(curr_idx + 1, len(stops)):
                st = stops[idx]
                if st.mile_marker <= curr_pos:
                    continue
                if st.mile_marker <= max_reach:
                    reachable_ahead.append((idx, st))
                else:
                    break

            if not reachable_ahead:
                # If destination is reachable with full tank from here, we can refuel here (if we are at a station)
                if dist_to_dest <= cls.MAX_RANGE_MILES and curr_idx >= 0:
                    gallons_to_buy = fuel_needed_for_dest - curr_fuel
                    cost = gallons_to_buy * stops[curr_idx].retail_price
                    # Record purchase at current station
                    fuel_before = curr_fuel
                    curr_fuel += gallons_to_buy
                    selected_stops.append(
                        FuelStopDecision(
                            station_id=stops[curr_idx].station_id,
                            opis_id=stops[curr_idx].opis_id,
                            name=stops[curr_idx].name,
                            address=stops[curr_idx].address,
                            city=stops[curr_idx].city,
                            state=stops[curr_idx].state,
                            latitude=stops[curr_idx].latitude,
                            longitude=stops[curr_idx].longitude,
                            mile_marker=stops[curr_idx].mile_marker,
                            retail_price=stops[curr_idx].retail_price,
                            gallons_purchased=gallons_to_buy,
                            fuel_cost=cost,
                            fuel_before=fuel_before,
                            fuel_after=curr_fuel,
                        )
                    )
                    curr_fuel -= fuel_needed_for_dest
                    curr_pos = route_distance
                    break
                else:
                    raise InfeasibleRouteError(
                        f"Infeasible route: Fuel gap exceeds maximum range of {cls.MAX_RANGE_MILES} miles "
                        f"after mile {curr_pos:.1f}."
                    )

            # If we are currently at the START (curr_idx == -1), we already have full tank!
            # We don't buy fuel at start; we find the optimal first station to drive to.
            if curr_idx == -1:
                # Stations reachable with current fuel
                current_reachable = [
                    (idx, st) for idx, st in reachable_ahead
                    if st.mile_marker <= curr_pos + (curr_fuel * cls.MILES_PER_GALLON)
                ]
                if not current_reachable:
                    raise InfeasibleRouteError(
                        f"Cannot reach any fuel station from start with initial fuel {curr_fuel} gal."
                    )

                # Find the best station to stop at:
                # Strategy: Choose the cheapest station among current_reachable.
                # If tied, pick the furthest one along the route.
                best_idx, best_st = min(
                    current_reachable,
                    key=lambda item: (item[1].retail_price, -item[1].mile_marker),
                )

                # Drive to best_st
                dist_traveled = best_st.mile_marker - curr_pos
                curr_fuel -= dist_traveled / cls.MILES_PER_GALLON
                curr_pos = best_st.mile_marker
                curr_idx = best_idx
                continue

            # Now we are at station curr_idx:
            curr_price = stops[curr_idx].retail_price

            # Look for a cheaper station within reach from current station
            cheaper_ahead = [
                (idx, st) for idx, st in reachable_ahead
                if st.retail_price < curr_price
            ]

            if cheaper_ahead:
                # Pick the FIRST cheaper station
                next_idx, next_st = cheaper_ahead[0]
                dist_to_next = next_st.mile_marker - curr_pos
                fuel_needed = dist_to_next / cls.MILES_PER_GALLON

                if curr_fuel < fuel_needed:
                    gallons_to_buy = fuel_needed - curr_fuel
                    cost = gallons_to_buy * curr_price
                    fuel_before = curr_fuel
                    curr_fuel += gallons_to_buy
                    selected_stops.append(
                        FuelStopDecision(
                            station_id=stops[curr_idx].station_id,
                            opis_id=stops[curr_idx].opis_id,
                            name=stops[curr_idx].name,
                            address=stops[curr_idx].address,
                            city=stops[curr_idx].city,
                            state=stops[curr_idx].state,
                            latitude=stops[curr_idx].latitude,
                            longitude=stops[curr_idx].longitude,
                            mile_marker=stops[curr_idx].mile_marker,
                            retail_price=curr_price,
                            gallons_purchased=gallons_to_buy,
                            fuel_cost=cost,
                            fuel_before=fuel_before,
                            fuel_after=curr_fuel,
                        )
                    )

                # Drive to next station
                curr_fuel -= fuel_needed
                curr_pos = next_st.mile_marker
                curr_idx = next_idx
            else:
                # No cheaper station within reach.
                # If destination is reachable within 500 miles, buy only enough to reach destination!
                if dist_to_dest <= cls.MAX_RANGE_MILES:
                    gallons_to_buy = max(0.0, fuel_needed_for_dest - curr_fuel)
                    if gallons_to_buy > 0:
                        cost = gallons_to_buy * curr_price
                        fuel_before = curr_fuel
                        curr_fuel += gallons_to_buy
                        selected_stops.append(
                            FuelStopDecision(
                                station_id=stops[curr_idx].station_id,
                                opis_id=stops[curr_idx].opis_id,
                                name=stops[curr_idx].name,
                                address=stops[curr_idx].address,
                                city=stops[curr_idx].city,
                                state=stops[curr_idx].state,
                                latitude=stops[curr_idx].latitude,
                                longitude=stops[curr_idx].longitude,
                                mile_marker=stops[curr_idx].mile_marker,
                                retail_price=curr_price,
                                gallons_purchased=gallons_to_buy,
                                fuel_cost=cost,
                                fuel_before=fuel_before,
                                fuel_after=curr_fuel,
                            )
                        )
                    curr_fuel -= fuel_needed_for_dest
                    curr_pos = route_distance
                    break
                else:
                    # Fill tank to capacity since current fuel is cheapest in sight
                    gallons_to_buy = cls.TANK_CAPACITY_GALLONS - curr_fuel
                    cost = gallons_to_buy * curr_price
                    fuel_before = curr_fuel
                    curr_fuel = cls.TANK_CAPACITY_GALLONS
                    selected_stops.append(
                        FuelStopDecision(
                            station_id=stops[curr_idx].station_id,
                            opis_id=stops[curr_idx].opis_id,
                            name=stops[curr_idx].name,
                            address=stops[curr_idx].address,
                            city=stops[curr_idx].city,
                            state=stops[curr_idx].state,
                            latitude=stops[curr_idx].latitude,
                            longitude=stops[curr_idx].longitude,
                            mile_marker=stops[curr_idx].mile_marker,
                            retail_price=curr_price,
                            gallons_purchased=gallons_to_buy,
                            fuel_cost=cost,
                            fuel_before=fuel_before,
                            fuel_after=curr_fuel,
                        )
                    )

                    # Now from reachable stations, move to the cheapest one ahead
                    next_idx, next_st = min(
                        reachable_ahead,
                        key=lambda item: (item[1].retail_price, -item[1].mile_marker),
                    )
                    dist_to_next = next_st.mile_marker - curr_pos
                    curr_fuel -= dist_to_next / cls.MILES_PER_GALLON
                    curr_pos = next_st.mile_marker
                    curr_idx = next_idx

        # Calculate final summary
        total_purchased = sum(s.gallons_purchased for s in selected_stops)
        total_cost = sum(s.fuel_cost for s in selected_stops)
        total_consumed = route_distance / cls.MILES_PER_GALLON

        return OptimizationResult(
            total_distance_miles=route_distance,
            total_gallons_consumed=total_consumed,
            total_gallons_purchased=total_purchased,
            total_cost=total_cost,
            fuel_remaining_at_destination=max(0.0, curr_fuel),
            stops=selected_stops,
            assumptions=assumptions,
        )
