import unittest
from routes.services.fuel_optimizer import FuelOptimizer, InfeasibleRouteError
from routes.services.station_matching import CandidateStop


def make_stop(mile_marker: float, price: float, opis_id: int = 1, name: str = "Test Stop") -> CandidateStop:
    return CandidateStop(
        station_id=opis_id,
        opis_id=opis_id,
        name=f"{name} #{opis_id}",
        address=f"I-80 Mile {mile_marker}",
        city="TestCity",
        state="IA",
        latitude=41.5,
        longitude=-93.5,
        retail_price=price,
        mile_marker=mile_marker,
        detour_miles=0.5,
    )


class TestFuelOptimizer(unittest.TestCase):
    def test_destination_under_500_miles(self):
        """Trips under 500 miles require 0 fuel purchases because initial tank has 50 gallons."""
        stops = [
            make_stop(100.0, 3.20, 1),
            make_stop(250.0, 2.90, 2),
        ]
        result = FuelOptimizer.optimize(route_distance=350.0, candidate_stops=stops)

        self.assertEqual(result.total_distance_miles, 350.0)
        self.assertEqual(result.total_gallons_consumed, 35.0)
        self.assertEqual(result.total_gallons_purchased, 0.0)
        self.assertEqual(result.total_cost, 0.0)
        self.assertEqual(len(result.stops), 0)
        self.assertAlmostEqual(result.fuel_remaining_at_destination, 15.0, places=2)

    def test_destination_exactly_500_miles(self):
        """Trip of exactly 500 miles reaches destination on the initial full tank."""
        stops = [make_stop(250.0, 3.50, 1)]
        result = FuelOptimizer.optimize(route_distance=500.0, candidate_stops=stops)

        self.assertEqual(result.total_gallons_consumed, 50.0)
        self.assertEqual(result.total_gallons_purchased, 0.0)
        self.assertEqual(result.total_cost, 0.0)
        self.assertAlmostEqual(result.fuel_remaining_at_destination, 0.0, places=2)

    def test_station_exactly_at_500_miles(self):
        """Vehicle reaches a station at mile 500 with empty tank, buys fuel to finish."""
        stops = [make_stop(500.0, 3.00, 1)]
        result = FuelOptimizer.optimize(route_distance=800.0, candidate_stops=stops)

        self.assertEqual(len(result.stops), 1)
        self.assertEqual(result.stops[0].mile_marker, 500.0)
        # Needs 30 gallons to cover the remaining 300 miles
        self.assertAlmostEqual(result.stops[0].gallons_purchased, 30.0, places=2)
        self.assertAlmostEqual(result.stops[0].fuel_cost, 90.0, places=2)
        self.assertAlmostEqual(result.total_cost, 90.0, places=2)

    def test_no_station_reachable_raises_infeasible(self):
        """First station beyond initial 500-mile range raises InfeasibleRouteError."""
        stops = [make_stop(550.0, 3.00, 1)]
        with self.assertRaises(InfeasibleRouteError):
            FuelOptimizer.optimize(route_distance=1000.0, candidate_stops=stops)

    def test_fuel_gap_exceeds_500_miles_raises_infeasible(self):
        """Gap of > 500 miles between stations raises InfeasibleRouteError."""
        stops = [
            make_stop(200.0, 3.00, 1),
            make_stop(750.0, 3.00, 2),  # gap = 550 miles
        ]
        with self.assertRaises(InfeasibleRouteError):
            FuelOptimizer.optimize(route_distance=1000.0, candidate_stops=stops)

    def test_expensive_station_bypassed_for_reachable_cheap_station(self):
        """Vehicle should bypass an expensive station at mile 100 if a cheaper station at mile 300 is reachable with initial tank."""
        stops = [
            make_stop(100.0, 4.50, 1, "Expensive"),
            make_stop(300.0, 2.50, 2, "Cheap"),
        ]
        result = FuelOptimizer.optimize(route_distance=700.0, candidate_stops=stops)

        # Should NOT stop at Mile 100
        stop_miles = [s.mile_marker for s in result.stops]
        self.assertNotIn(100.0, stop_miles)
        self.assertIn(300.0, stop_miles)

    def test_cheap_station_just_in_reach(self):
        """
        Trip 900 miles.
        Station A at mile 400 ($4.00).
        Station B at mile 650 ($2.50).
        At Station A, B is cheaper ($2.50 < $4.00) and in reach (250 miles away).
        Vehicle should buy only enough fuel at A to reach B (or none if it has enough), then fill/purchase at B.
        """
        stops = [
            make_stop(400.0, 4.00, 1, "A"),
            make_stop(650.0, 2.50, 2, "B"),
        ]
        result = FuelOptimizer.optimize(route_distance=900.0, candidate_stops=stops)

        self.assertEqual(len(result.stops), 2)
        # At A, arrived with 10 gal. Needs 25 gal to reach B (250 mi). Buys 15 gal at $4.00 = $60.00
        self.assertAlmostEqual(result.stops[0].gallons_purchased, 15.0, places=2)
        self.assertAlmostEqual(result.stops[0].fuel_cost, 60.0, places=2)

        # At B, arrives with 0 gal. Needs 25 gal to finish 250 mi to mile 900. Buys 25 gal at $2.50 = $62.50
        self.assertAlmostEqual(result.stops[1].gallons_purchased, 25.0, places=2)
        self.assertAlmostEqual(result.stops[1].fuel_cost, 62.50, places=2)

        self.assertAlmostEqual(result.total_cost, 122.50, places=2)

    def test_station_immediately_before_destination(self):
        """Trip 950 miles. Stops at mile 450 ($3.00) and mile 900 ($3.20)."""
        stops = [
            make_stop(450.0, 3.00, 1),
            make_stop(900.0, 3.20, 2),
        ]
        result = FuelOptimizer.optimize(route_distance=950.0, candidate_stops=stops)
        self.assertTrue(len(result.stops) >= 1)
        self.assertAlmostEqual(result.total_distance_miles, 950.0)


if __name__ == "__main__":
    unittest.main()
