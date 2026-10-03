import json
from unittest.mock import patch
from django.test import TestCase, Client
from routes.services.routing import RouteSummary
from routes.services.station_matching import CandidateStop
from fuel_stops.models import TruckStop


class TestRouteAPIViews(TestCase):
    def setUp(self):
        self.client = Client()
        # Seed test stations
        TruckStop.objects.create(
            opis_id=101,
            name="Pilot Travel Center #101",
            address="I-80 Exit 50",
            city="Des Moines",
            state="IA",
            country="US",
            latitude=41.5868,
            longitude=-93.6250,
            retail_price=3.1000,
            min_price=3.1000,
            max_price=3.1000,
            price_count=1,
            rack_ids="100",
            geocode_source="test",
            confidence="high",
        )

    def test_post_routes_missing_params_returns_400(self):
        response = self.client.post(
            "/api/routes/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)

    @patch("routes.services.geocoding.GeocodingService.resolve_location")
    @patch("routes.services.routing.RoutingService.get_route")
    def test_post_routes_short_trip_success(self, mock_routing, mock_geocoding):
        mock_geocoding.side_effect = [
            (41.8781, -87.6298, "Chicago, IL"),
            (43.0389, -87.9065, "Milwaukee, WI"),
        ]
        mock_routing.return_value = RouteSummary(
            distance_miles=92.0,
            duration_hours=1.5,
            coordinates=[(41.8781, -87.6298), (43.0389, -87.9065)],
            geojson_geometry={"type": "LineString", "coordinates": [[-87.6298, 41.8781], [-87.9065, 43.0389]]},
        )

        response = self.client.post(
            "/api/routes/",
            data=json.dumps({"start": "Chicago, IL", "destination": "Milwaukee, WI"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("route", data)
        self.assertIn("fuel", data)
        self.assertEqual(data["route"]["distance_miles"], 92.0)
        self.assertEqual(data["fuel"]["total_gallons_consumed"], 9.2)
        self.assertEqual(data["fuel"]["total_gallons_purchased"], 0.0)
        self.assertEqual(data["fuel"]["total_fuel_cost"], 0.0)
        self.assertEqual(len(data["stops"]), 0)

    def test_get_map_preview_returns_200(self):
        response = self.client.get("/map/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "US Truck Route & Fuel Optimizer")
        self.assertContains(response, "POST /api/routes/")
