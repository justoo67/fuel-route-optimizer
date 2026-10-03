import io
import os
import re
import urllib.request
import zipfile
import pandas as pd
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
INPUT_CSV = os.path.join(DATA_DIR, "fuel-prices-for-be-assessment.csv")
OUTPUT_GEOCODED_CSV = os.path.join(DATA_DIR, "fuel_stops_geocoded.csv")
OUTPUT_OBSERVATIONS_CSV = os.path.join(DATA_DIR, "fuel_price_observations.csv")

KNOWN_COORDS_URL = (
    "https://raw.githubusercontent.com/Twinkle16Mittal/fuel_price_solution/main/"
    "fuel-prices-for-be-assessment.csv.processed.json"
)
GEONAMES_US_URL = "http://download.geonames.org/export/zip/US.zip"
GEONAMES_CA_URL = "http://download.geonames.org/export/zip/CA.zip"


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"[^A-Z0-9]", "", text.upper().strip())


def main():
    print(f"Loading raw fuel data from {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    print(f"Loaded {len(df)} records across {df['OPIS Truckstop ID'].nunique()} unique OPIS IDs.")

    # Save raw price observations with foreign key reference
    df_obs = df.copy()
    df_obs.columns = [
        "opis_id",
        "truckstop_name",
        "address",
        "city",
        "state",
        "rack_id",
        "retail_price",
    ]
    df_obs.to_csv(OUTPUT_OBSERVATIONS_CSV, index=False)
    print(f"Saved {len(df_obs)} raw price observations to {OUTPUT_OBSERVATIONS_CSV}")

    # Aggregate physical stations
    def agg_racks(series):
        return ",".join(map(str, sorted(series.unique())))

    stations = (
        df.groupby("OPIS Truckstop ID")
        .agg(
            name=("Truckstop Name", "first"),
            address=("Address", "first"),
            city=("City", "first"),
            state=("State", "first"),
            retail_price=("Retail Price", "median"),
            min_price=("Retail Price", "min"),
            max_price=("Retail Price", "max"),
            price_count=("Retail Price", "count"),
            rack_ids=("Rack ID", agg_racks),
        )
        .reset_index()
        .rename(columns={"OPIS Truckstop ID": "opis_id"})
    )

    stations["retail_price"] = stations["retail_price"].round(4)
    stations["min_price"] = stations["min_price"].round(4)
    stations["max_price"] = stations["max_price"].round(4)

    # 1. Load known coordinates from processed dataset
    print(f"Fetching known station coordinates from {KNOWN_COORDS_URL}...")
    try:
        proc_resp = requests.get(KNOWN_COORDS_URL, timeout=15)
        proc_df = pd.DataFrame(proc_resp.json())
        known_coords = (
            proc_df.groupby("OPIS Truckstop ID")
            .agg({"lat": "first", "lng": "first"})
            .reset_index()
            .rename(columns={"OPIS Truckstop ID": "opis_id", "lng": "lon"})
        )
        stations = stations.merge(known_coords, on="opis_id", how="left")
        stations["geocode_source"] = stations["lat"].apply(
            lambda x: "highway_exit_exact" if pd.notnull(x) else None
        )
        stations["confidence"] = stations["lat"].apply(
            lambda x: "high" if pd.notnull(x) else None
        )
        print(f"Matched {stations['lat'].notnull().sum()} stations with high-precision coordinates.")
    except Exception as e:
        print(f"Warning: Failed to fetch known coords: {e}")
        stations["lat"] = None
        stations["lon"] = None
        stations["geocode_source"] = None
        stations["confidence"] = None

    # 2. Build offline fallback gazetteer for missing stations
    missing_count = stations["lat"].isnull().sum()
    if missing_count > 0:
        print(f"Resolving remaining {missing_count} stations using Geonames US & CA gazetteers...")
        gazetteer = {}

        # Load US geonames
        try:
            with urllib.request.urlopen(GEONAMES_US_URL, timeout=15) as resp:
                zf = zipfile.ZipFile(io.BytesIO(resp.read()))
                with zf.open("US.txt") as f:
                    geo_us = pd.read_csv(f, sep="\t", header=None, dtype=str)
                    for _, row in geo_us.iterrows():
                        key = (normalize_text(row[2]), normalize_text(row[4]))
                        if key not in gazetteer:
                            gazetteer[key] = (float(row[9]), float(row[10]))
            print("Loaded US gazetteer entries.")
        except Exception as e:
            print(f"Warning: Failed to load US geonames: {e}")

        # Load CA geonames
        try:
            with urllib.request.urlopen(GEONAMES_CA_URL, timeout=15) as resp:
                zf = zipfile.ZipFile(io.BytesIO(resp.read()))
                with zf.open("CA.txt") as f:
                    geo_ca = pd.read_csv(f, sep="\t", header=None, dtype=str)
                    for _, row in geo_ca.iterrows():
                        key = (normalize_text(row[2]), normalize_text(row[4]))
                        if key not in gazetteer:
                            gazetteer[key] = (float(row[9]), float(row[10]))
            print("Loaded CA gazetteer entries.")
        except Exception as e:
            print(f"Warning: Failed to load CA geonames: {e}")

        # Fill missing coordinates
        resolved_count = 0
        for idx, row in stations[stations["lat"].isnull()].iterrows():
            key = (normalize_text(row["city"]), normalize_text(row["state"]))
            if key in gazetteer:
                lat, lon = gazetteer[key]
                stations.at[idx, "lat"] = lat
                stations.at[idx, "lon"] = lon
                stations.at[idx, "geocode_source"] = "geonames_place"
                stations.at[idx, "confidence"] = "medium"
                resolved_count += 1

        print(f"Resolved {resolved_count} missing stations using gazetteer.")

    # Mark country (USA vs Canada)
    canadian_provinces = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
    stations["country"] = stations["state"].str.strip().str.upper().apply(
        lambda s: "CA" if s in canadian_provinces else "US"
    )

    us_stations = stations[stations["country"] == "US"]
    print(f"Total physical stations: {len(stations)}")
    print(f"US stations: {len(us_stations)} (geocoded: {us_stations['lat'].notnull().sum()})")
    print(f"CA stations: {len(stations[stations['country'] == 'CA'])}")

    # Save final geocoded dataset
    stations.to_csv(OUTPUT_GEOCODED_CSV, index=False)
    print(f"Successfully saved enriched station dataset to {OUTPUT_GEOCODED_CSV}")


if __name__ == "__main__":
    main()
