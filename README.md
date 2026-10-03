# US Truck Route & Fuel Optimizer API

A high-performance Django REST API that computes driving routes across the United States and determines the most cost-effective fuel stops along the highway corridor, subject to a **500-mile vehicle range** constraint and **10 MPG fuel economy**.

---

## 🏛️ System Architecture

```text
               ┌────────────────────────────────────────────────────────┐
               │         Offline Data Pipeline (Phase 1)                │
               │                                                        │
               │  fuel-prices-for-be-assessment.csv (8,151 rows)        │
               │                         │                              │
               │         Profile, Normalize & Geocode (100% US)         │
               │                         │                              │
               │          ┌──────────────┴──────────────┐               │
               │          ▼                             ▼               │
               │  TruckStop (6,626 facilities)   FuelPriceObservation   │
               │  (SQLite / Spatial Index)       (8,151 raw records)    │
               └────────────────────────────────────────────────────────┘
                                         │
                                         ▼
POST /api/routes/  ───►  RoutePlanner (Orchestrator Service)
                               │
                               ├── 1. GeocodingService (start/destination with cache)
                               ├── 2. RoutingService (1 single OSRM API call)
                               ├── 3. StationMatchingService (3D Cartesian KD-Tree, <15ms)
                               └── 4. FuelOptimizer (Greedy lookahead under 500-mi range)
                               │
                               ▼
                   JSON API + Leaflet Map Preview
```

---

## 📐 Core Engineering Assumptions

To turn ambiguous requirements into a verifiable, production-grade system, the following domain assumptions are explicitly defined:

1. **Tank Capacity & Range**:
   - The vehicle has a **50-gallon fuel tank** and achieves **10 miles per gallon (MPG)**.
   - The maximum usable driving range on a full tank is **500.0 miles**.
2. **Initial Departure State**:
   - The vehicle begins its journey with a **full 50-gallon tank** (500 miles of available range).
3. **Fuel Consumed vs. Fuel Purchased**:
   - **Fuel Consumed** = $\text{Total Distance} / 10\text{ MPG}$.
   - **Fuel Purchased** = The actual gallons pumped at selected fuel stops during the trip.
   - *Example*: On a 960-mile trip, the truck consumes 96.0 gallons. Starting with 50.0 gallons, it only needs to purchase 46.0 gallons to reach the destination.
4. **Route Corridor Definition**:
   - Fuel stations are considered candidates if they lie within a configurable perpendicular corridor (default **10.0 miles**) of the calculated highway route.
5. **Route vs. Fuel Optimization**:
   - The driving route is determined by the road network (via OSRM). The optimizer selects **where and how much to refuel along that route**; it does not divert hundreds of miles off-route to chase cheaper gas.
6. **Station Geocoding Provenance**:
   - Geocoding is executed during data preprocessing, **never at request time**, ensuring sub-second response times.

---

## 📊 Data Profiling & OPIS ID Normalization

The provided dataset (`fuel-prices-for-be-assessment.csv`) contains:
- **8,151 raw price records**
- **6,738 unique `OPIS Truckstop ID`s**
- **597 stations with multiple distinct price observations**

### What Multiple Prices Mean
In commercial trucking feeds (OPIS - Oil Price Information Service), a single travel center frequently reports multiple prices simultaneously representing different fuel grades (e.g., Ultra-Low Sulfur Diesel #2 vs. Biodiesel B5/B20) or cash vs. credit payment tiers.

### Data Modeling Solution
- **`TruckStop`**: Represents the unique physical travel center (`opis_id`, `name`, `address`, `city`, `state`, `latitude`, `longitude`, `retail_price`, `min_price`, `max_price`, `price_count`, `rack_ids`, `geocode_source`, `confidence`).
- **`FuelPriceObservation`**: Preserves all 8,151 raw price observations with foreign references.
- **Coverage**: **100% of US truck stops** are resolved with geographic coordinates.

---

## ⚡ Spatial & Algorithmic Performance

### 1. Two-Stage 3D Cartesian KD-Tree Spatial Matching
Projecting thousands of stations onto a detailed route polyline with thousands of vertices can easily cause multi-second latency ($O(N \times M)$).
- **Stage 1**: Fast bounding-box pre-filtering in the database.
- **Stage 2**: Vectorized 3D spherical Earth Cartesian coordinate projection using `scipy.spatial.cKDTree`.
- **Result**: Station matching executes in **under 15 milliseconds**.

### 2. Greedy Lookahead Refueling Algorithm
At any station $i$, the algorithm scans ahead up to 500 miles:
- **Cheaper station ahead**: If a cheaper station $j$ is within reach, buy **only enough fuel** to reach station $j$.
- **No cheaper station ahead**: If station $i$ is the cheapest option within 500 miles, fill the tank to capacity (or buy only enough to finish the trip if destination is reachable).
- **Gap detection**: If any gap between stations exceeds 500 miles, raises `InfeasibleRouteError` (HTTP 422).

---

## 🚀 Quickstart & Setup

### Prerequisites
- Python 3.10+ (or Docker)

### Option A: Local Python Setup

```bash
# 1. Clone repository
git clone <repository_url>
cd ena

# 2. Create virtual environment & activate
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run migrations
python manage.py migrate

# 5. Populate database (takes ~2 seconds from pre-geocoded artifact)
python manage.py import_fuel_stops

# 6. Run test suite
python manage.py test tests

# 7. Start server
python manage.py runserver 0.0.0.0:8000
```

### Option B: Docker Compose

```bash
docker compose up --build
```

The application is accessible at:
- **Interactive Map Preview**: `http://localhost:8000/map/` or `http://localhost:8000/`
- **REST API Endpoint**: `http://localhost:8000/api/routes/`

---

## 📡 API Reference

### `POST /api/routes/`

#### Request Body
```json
{
  "start": "Chicago, IL",
  "destination": "Dallas, TX",
  "corridor_radius_miles": 10.0
}
```
*Note: `start` and `destination` also accept raw GPS coordinates, e.g. `"41.8781, -87.6298"`.*

#### Response Payload (Example: Chicago to Dallas)
```json
{
  "origin": {
    "query": "Chicago, IL",
    "display_name": "Chicago, IL, United States",
    "latitude": 41.8781,
    "longitude": -87.6298
  },
  "destination": {
    "query": "Dallas, TX",
    "display_name": "Dallas, TX, United States",
    "latitude": 32.7767,
    "longitude": -96.7970
  },
  "route": {
    "distance_miles": 960.75,
    "duration_hours": 17.03,
    "corridor_radius_miles": 10.0,
    "candidate_stations_found": 188,
    "geometry": {
      "type": "LineString",
      "coordinates": [[-87.534, 41.691], ...]
    }
  },
  "fuel": {
    "total_gallons_consumed": 96.08,
    "total_gallons_purchased": 46.08,
    "total_fuel_cost": 134.11,
    "fuel_remaining_at_destination_gal": 0.0,
    "total_stops": 5,
    "vehicle_mpg": 10.0,
    "max_range_miles": 500.0
  },
  "stops": [
    {
      "station_id": 412,
      "opis_id": 2690,
      "name": "DEERFIELD TRAVEL CENTER",
      "address": "I-55, EXIT 14",
      "city": "Steele",
      "state": "MO",
      "latitude": 36.089,
      "longitude": -89.832,
      "mile_marker": 445.1,
      "price_per_gallon": 2.976,
      "gallons_purchased": 1.63,
      "cost": 4.86,
      "fuel_before_arrival_gal": 5.49,
      "fuel_after_departure_gal": 7.12
    },
    {
      "station_id": 1420,
      "opis_id": 6120,
      "name": "BLU STATION- LAMAR AVE",
      "address": "US-78 & LAMAR AVE",
      "city": "Memphis",
      "state": "TN",
      "latitude": 35.051,
      "longitude": -89.905,
      "mile_marker": 516.33,
      "price_per_gallon": 2.969,
      "gallons_purchased": 26.84,
      "cost": 79.68,
      "fuel_before_arrival_gal": 0.0,
      "fuel_after_departure_gal": 26.84
    },
    {
      "station_id": 2341,
      "opis_id": 7900,
      "name": "Quiktrip #7900",
      "address": "I-30, EXIT 220",
      "city": "Texarkana",
      "state": "TX",
      "latitude": 33.435,
      "longitude": -94.043,
      "mile_marker": 784.71,
      "price_per_gallon": 2.857,
      "gallons_purchased": 1.15,
      "cost": 3.28,
      "fuel_before_arrival_gal": 0.0,
      "fuel_after_departure_gal": 1.15
    },
    {
      "station_id": 2511,
      "opis_id": 9124,
      "name": "EXTRA MILE TRUCK STOP",
      "address": "I-30, EXIT 208",
      "city": "Hooks",
      "state": "TX",
      "latitude": 33.468,
      "longitude": -94.238,
      "mile_marker": 796.18,
      "price_per_gallon": 2.817,
      "gallons_purchased": 12.24,
      "cost": 34.47,
      "fuel_before_arrival_gal": 0.0,
      "fuel_after_departure_gal": 12.24
    },
    {
      "station_id": 2890,
      "opis_id": 10450,
      "name": "CADOO MILLS",
      "address": "I-30, EXIT 83",
      "city": "Caddo Mills",
      "state": "TX",
      "latitude": 33.064,
      "longitude": -96.230,
      "mile_marker": 918.53,
      "price_per_gallon": 2.801,
      "gallons_purchased": 4.22,
      "cost": 11.83,
      "fuel_before_arrival_gal": 0.0,
      "fuel_after_departure_gal": 4.22
    }
  ],
  "assumptions": {
    "initial_fuel_gallons": "50.0 gal (full tank)",
    "vehicle_mpg": "10.0 MPG",
    "max_range_miles": "500.0 miles",
    "tank_capacity": "50.0 gallons",
    "policy": "Greedy lookahead minimum cost refueling with exact fuel purchased accounting."
  }
}
```

---

## 🧪 Comprehensive Unit & Integration Tests

The project includes 11 automated test cases verifying both synthetic edge cases and API views:

```bash
python manage.py test tests
```

### Verified Test Cases
1. `test_destination_under_500_miles`: Verifies 0 gallons purchased and $0 cost when trip < 500 mi.
2. `test_destination_exactly_500_miles`: Reaches destination on initial tank with 0 purchases.
3. `test_station_exactly_at_500_miles`: Reaches station at mile 500 with empty tank, buys fuel to finish.
4. `test_no_station_reachable_raises_infeasible`: Unreachable initial stop raises `InfeasibleRouteError`.
5. `test_fuel_gap_exceeds_500_miles_raises_infeasible`: Gap > 500 miles between stations raises `InfeasibleRouteError`.
6. `test_expensive_station_bypassed_for_reachable_cheap_station`: Bypasses expensive stations within reach of cheaper ones.
7. `test_cheap_station_just_in_reach`: Purchases minimal fuel to reach a cheaper station ahead.
8. `test_station_immediately_before_destination`: Correctly refuels just enough to complete the journey.
9. `test_post_routes_missing_params_returns_400`: DRF validation test.
10. `test_post_routes_short_trip_success`: End-to-end API test for trips under 500 miles.
11. `test_get_map_preview_returns_200`: Verifies Leaflet visualization endpoint.

---

## 🎬 5-Minute Loom Presentation Blueprint

Follow this exact minute-by-minute plan to record a compelling walkthrough:

* **0:00 – 0:45 | Live API Demonstration**
  - Open Postman (or browser at `http://localhost:8000/map/`).
  - Run `POST /api/routes/` with `Chicago, IL` $\rightarrow$ `Dallas, TX`.
  - Highlight the key numbers: 960.7 miles, 96.08 gallons consumed, 46.08 gallons purchased, $134.11 total spent, and 5 optimal stops.
  - Show the interactive Leaflet map rendering the route and fuel stops with click popups.
* **0:45 – 1:45 | Data Preprocessing & Highway Geocoding**
  - Open `fuel-prices-for-be-assessment.csv` vs `fuel_stops_geocoded.csv`.
  - Explain: *"The raw dataset contained 8,151 rows with highway exits but zero GPS coordinates. Geocoding during request time would violate the 1-routing-call constraint and destroy latency."*
  - Explain the OPIS ID normalization: 6,738 physical facilities, multiple price observations preserved, and 100% of US truck stops pre-geocoded offline.
* **1:45 – 2:45 | Routing & Sub-15ms Spatial Matching**
  - Walk through `routes/services/routing.py`: exactly **1 single call** to OSRM to get the route geometry.
  - Walk through `routes/services/station_matching.py`: explain the two-stage search using **3D Cartesian KD-Trees** (`scipy.spatial.cKDTree`) to project stations onto route mile markers in **< 15ms**.
* **2:45 – 4:00 | The Fuel Optimizer & Vehicle Physics**
  - Walk through `routes/services/fuel_optimizer.py`.
  - Explain the 500-mile range constraint and 10 MPG economy.
  - Clarify the distinction between **Fuel Consumed** vs. **Fuel Purchased** (starting with a full 50-gallon tank).
  - Walk through the greedy lookahead logic: buy minimal fuel to reach cheaper stations ahead; fill up when at the lowest price in reach.
* **4:00 – 5:00 | Tests, Performance & Code Quality**
  - Run `python manage.py test tests` in the terminal to show all 11 unit tests passing in ~0.1s.
  - Point to the decoupled service layer (`RoutePlanner` orchestrator, thin DRF view).
  - Mention Docker setup and wrap up.
