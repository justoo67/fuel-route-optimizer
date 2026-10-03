import os
import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from fuel_stops.models import TruckStop, FuelPriceObservation


class Command(BaseCommand):
    help = "Import normalized and geocoded truck stops and raw price observations into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--geocoded-file",
            type=str,
            default="data/fuel_stops_geocoded.csv",
            help="Path to pre-geocoded truck stops CSV file",
        )
        parser.add_argument(
            "--observations-file",
            type=str,
            default="data/fuel_price_observations.csv",
            help="Path to raw fuel price observations CSV file",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing truck stop records before importing",
        )

    def handle(self, *args, **options):
        geocoded_path = options["geocoded_file"]
        obs_path = options["observations_file"]
        clear = options["clear"]

        if not os.path.exists(geocoded_path):
            self.stderr.write(self.style.ERROR(f"File not found: {geocoded_path}"))
            return

        if clear:
            self.stdout.write("Clearing existing truck stops and observations...")
            TruckStop.objects.all().delete()
            FuelPriceObservation.objects.all().delete()

        # 1. Import Truck Stops
        self.stdout.write(f"Reading truck stops from {geocoded_path}...")
        df_stops = pd.read_csv(geocoded_path)

        # Filter to valid geocoded US stops (or all with lat/lon)
        df_stops = df_stops[df_stops["lat"].notnull() & df_stops["lon"].notnull()]

        truck_stops = []
        for _, row in df_stops.iterrows():
            truck_stops.append(
                TruckStop(
                    opis_id=int(row["opis_id"]),
                    name=str(row["name"]).strip(),
                    address=str(row["address"]).strip(),
                    city=str(row["city"]).strip(),
                    state=str(row["state"]).strip(),
                    country=str(row["country"]).strip(),
                    latitude=float(row["lat"]),
                    longitude=float(row["lon"]),
                    retail_price=round(float(row["retail_price"]), 4),
                    min_price=round(float(row["min_price"]), 4),
                    max_price=round(float(row["max_price"]), 4),
                    price_count=int(row["price_count"]),
                    rack_ids=str(row["rack_ids"]) if pd.notnull(row["rack_ids"]) else "",
                    geocode_source=str(row["geocode_source"]) if pd.notnull(row["geocode_source"]) else "",
                    confidence=str(row["confidence"]) if pd.notnull(row["confidence"]) else "medium",
                )
            )

        with transaction.atomic():
            # Update or insert
            TruckStop.objects.bulk_create(
                truck_stops,
                batch_size=1000,
                update_conflicts=True,
                update_fields=[
                    "name", "address", "city", "state", "country",
                    "latitude", "longitude", "retail_price", "min_price",
                    "max_price", "price_count", "rack_ids", "geocode_source", "confidence"
                ],
                unique_fields=["opis_id"],
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully imported {len(truck_stops)} physical truck stops."))

        # 2. Import Raw Observations if file exists
        if os.path.exists(obs_path):
            self.stdout.write(f"Reading price observations from {obs_path}...")
            df_obs = pd.read_csv(obs_path)
            observations = []
            for _, row in df_obs.iterrows():
                observations.append(
                    FuelPriceObservation(
                        opis_id=int(row["opis_id"]),
                        truckstop_name=str(row["truckstop_name"]).strip(),
                        address=str(row["address"]).strip(),
                        city=str(row["city"]).strip(),
                        state=str(row["state"]).strip(),
                        rack_id=int(row["rack_id"]),
                        retail_price=round(float(row["retail_price"]), 4),
                    )
                )

            with transaction.atomic():
                FuelPriceObservation.objects.bulk_create(observations, batch_size=2000)

            self.stdout.write(self.style.SUCCESS(f"Successfully imported {len(observations)} raw price observations."))
