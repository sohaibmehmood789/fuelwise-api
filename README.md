# US Fuel Planner API

Django **6.1.2** API for USA journeys, with a GeoJSON road route, an interactive map, cost-conscious fuel stops, gallon quantities, and USD fuel costs. Vehicle assumptions: **500 miles / 10 mpg = 50 gallons**. Python 3.12+ is required; development and CI use Python 3.14.

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py import_stations data/fuel-prices-for-be-assessment.csv --coordinates data/station-coordinates.csv --usa-only --duplicate-policy min-price --allow-unlocated
python manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/. The supplied `fuel-prices-for-be-assessment.csv` is bundled unchanged. Ingestion retains **7,531 USA quotes for 6,626 unique stations**, excludes **620 Canadian rows**, and preserves prices to **eight decimal places**. The 905 repeated quote rows are retained in `FuelQuote`; `min-price` selects the lowest supplied quote per station because the file does not distinguish quote dates or grades.

**Coordinate coverage is partial: 518 / 6,626 stations.** The CSV has no coordinates and mostly describes highway exits. The companion file matches 518 stations to official Love's location points by exact chain, store number, state, and city. The remaining **6,108 stations are imported but unlocated**, and cannot participate in optimization until accurate coordinates are added. Responses and maps disclose this limitation. A verified Los Angeles–Dallas route works with the located subset; cheapest-fuel coverage across the entire original file is **not complete**. See `data/dataset-report.json` and `data/station-coordinates.report.json` for provenance and counts.

`data/sample_stations.csv` remains an explicitly synthetic testing/demo fixture; it is not loaded by the setup above.

Environment variables in `.env.example` are documented examples; Django reads the process environment, not `.env` automatically. Export variables in your shell, or use Docker `--env-file`. Provider endpoints are configurable without code changes.

```sh
curl -sS http://127.0.0.1:8000/api/v1/plan/ \
  -H 'Content-Type: application/json' \
  -d '{"start":"Los Angeles, CA","finish":"Dallas, TX","initial_fuel_price_usd":3.65}'
```

Open the returned `map_url` relative to the server origin. It expires after 24 hours; plan responses are cached for 15 minutes. Import `docs/FuelPlanner.postman_collection.json` into Postman and run its requests in order. `docs/demo.http` also works with a compatible REST client. The OpenAPI 3.1 contract is in `docs/openapi.json`.

## Request and response

`POST /api/v1/plan/` with `Content-Type: application/json`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `start` | string | required | USA city/state or address, 2–200 characters |
| `finish` | string | required | USA city/state or address, 2–200 characters |
| `initial_fuel_gallons` | number | 50 | Starting tank contents, from 0 to 50 |
| `initial_fuel_price_usd` | number | nearest dataset station estimate | Starting fuel valuation, 0.01–100 USD/US gallon |
| `corridor_miles` | number | 2 | Station search corridor, 0.1–10 miles |

Use `City, ST` or `City, State` for unambiguous city matching. These queries use Photon's structured endpoint with a USA filter, expanding state abbreviations. Other queries use forward search and must return a USA result. Returned labels/coordinates show exactly what was resolved. Ambiguous addresses remain subject to geocoder quality. Only USA endpoints are accepted; routing is not constrained to stay within national borders. Disconnected journeys, for example Hawaii to the mainland, cannot return a drivable route.

The JSON includes:

- `route.geometry`: full GeoJSON `LineString`, longitude before latitude.
- `route.waypoints`: all selected station waypoints visited by the verified route, including any no longer requiring purchases after recalculation.
- `route.leg_distances_miles`: routed road distances, including station visits.
- `fuel_stops`: station details, price, mile position, gallons to purchase, stop cost, and tank contents on arrival/departure.
- `fuel.total_money_spent_usd`: sum of cent-rounded **purchases during this trip**.
- `fuel.total_trip_fuel_cost_usd`: those purchases plus the value of **starting fuel consumed**. Starting fuel left in the tank is not charged to this journey.
- `fuel.initial_fuel_price_source`: whether the starting fuel price was supplied or estimated, including the source station and its straight-line distance when estimated. A sparse dataset can make that estimate unrepresentative; provide the actual price for a meaningful total.
- `meta.external_calls`: actual HTTP requests made during this request, separated into routing and geocoding. `meta.plan_cache_hit` and `elapsed_ms` expose caching and latency.
- `dataset`: filename, import time, and version, making sample data and stale prices visible.

All money fields are decimal strings, rounded half-up to USD cents. Gallon fields are numbers rounded to eight decimals; optimization uses Decimal arithmetic before display rounding. The starting tank is assumed full unless provided otherwise. There is no arrival reserve, refueling fee, toll calculation, real-time station inventory, or changing mpg. A request with zero starting fuel needs a station reachable with that fuel; the API never invents free travel to an origin station.

For example, a 1,200-mile verified trip with 50 gallons initially, purchases of 20 gallons at $3 and 50 gallons at $2, and starting fuel valued at $4 yields **$160 purchased en route** and **$360 trip fuel cost** (120 gallons consumed).

## Import the fuel-price file

```sh
python manage.py import_stations /absolute/path/fuel-prices.csv
```

Canonical CSV columns:

```csv
id,name,address,city,state,price,latitude,longitude
123,Example Truck Stop,123 Main Street,Amarillo,TX,3.1990,35.1930,-101.7340
```

The importer also accepts the assignment-style headers `OPIS Truckstop ID`, `Truckstop Name`, `Address`, `City`, `State`, `Retail Price`; `lat`, `lon`, and `lng` aliases are supported. Prices must be USD per US gallon, strictly between 0 and 100, with at most eight decimal places. Repeated IDs fail by default; `--duplicate-policy min-price` retains all quotes and selects the minimum station price. `--usa-only` excludes recognized Canadian province rows, while unknown state codes still fail. Coordinates must be finite and valid when present; `--allow-unlocated` explicitly retains unresolved stations with null coordinates. Such records are excluded from route candidates. An invalid file leaves the previous dataset intact. A successful atomic replacement updates its version and invalidates plan/station-index caches. Import reports include source SHA-256, quote counts, excluded rows, price policy, and coordinate coverage.

If the file has addresses but lacks coordinates, supply an offline, pre-geocoded companion CSV:

```csv
id,latitude,longitude
123,35.1930,-101.7340
```

```sh
python manage.py import_stations fuel-prices.csv --coordinates station-coordinates.csv
```

Add coordinates later without changing source prices or quotes:

```sh
python manage.py apply_coordinates additional-coordinates.csv
```

The official chain-coordinate companion is reproducible from an offline export of its public location directory:

```sh
python manage.py match_loves_coordinates data/loves-location-points.json --output reviewed-coordinates.csv
```

Only exact, unique chain/store-number/city/state identities are accepted. The directory's public map data endpoint was observed in its shipped client code (`/api/fetch_stores`); it is not a guaranteed stable API. Live chain prices are never imported. Each companion row links to the official station source page.

A second offline path supports bounded OSM extracts, using conservative store-number or exact name/city/state matching:

```sh
python manage.py enrich_stations --input osm-fuel-extract.json --output reviewed-osm-coordinates.csv
# Or download one bounded extract, outside the request path:
python manage.py enrich_stations --bbox 30,-120,36,-96 --output reviewed-osm-coordinates.csv
python manage.py apply_coordinates reviewed-osm-coordinates.csv
```

Public Overpass endpoints returned gateway errors/timeouts during validation, so this path did not produce the bundled coordinates. Review the generated match report before applying it. Conflicting identities and incomplete extracts are rejected; no city-centroid substitutes are used. OSM extracts are subject to OpenStreetMap's ODbL license and the selected server's usage policy. Calls have bounded timeouts, no automatic retries, and a 64 MiB response limit.

Coordinates must represent actual stations; city centroids are not suitable for fuel-stop feasibility. Geocode a missing coordinate dataset once using an appropriately licensed batch provider or a self-hosted geocoder. The importer deliberately makes **zero network calls**, and station geocoding never runs inside a trip request. It cannot derive station locations from prices alone. Station address/state consistency must be checked during data preparation; the importer validates numeric coordinates, not a USA boundary polygon or entrance access.

## Routing, optimization, and latency

1. Resolve two endpoints with [Photon](https://github.com/komoot/photon). Cache by provider URL and normalized query for 30 days. Structured USA city/state queries avoid fuzzy matches against businesses whose names contain “USA”.
2. Fetch one driving route from the free [FOSSGIS OSRM service](https://routing.openstreetmap.de/about.html), requesting full GeoJSON. Cache by coordinates/provider/options for 24 hours.
3. Use a per-dataset, in-process Shapely STRtree to select corridor stations; project them onto the base route and order by travel progress. Candidate discovery uses an approximate local projection and lightly simplified geometry, not extra distance-matrix calls.
4. Use an O(n) greedy optimizer with a monotonic next-cheaper-station stack. Buy just enough to reach the first cheaper station within range; otherwise buy up to tank capacity or the destination. Carry existing fuel forward. This minimizes fuel purchase cost for a fixed ordered station sequence when gallons are divisible and there are no stop fees.
5. If purchases are needed, make **one additional routing call** through the selected stations. Recompute all fuel purchases on its actual leg distances and reject any infeasible tank schedule. The returned map follows this verified road geometry, including detours.

**Limits of optimality:** candidate station selection uses projected base-route distances; final purchases are optimal for the selected ordered waypoints. This is not a global search over all roads or a proof of minimum cost across every candidate after road detours. A failed final verification returns 422 instead of silently exceeding 500 miles or making unbounded provider calls. A different corridor or station choice might be feasible. Some selected waypoints can require no purchase on the final route; they remain in the geometry and are disclosed separately.

Cold requests use **1–2 routing calls**, plus up to **2 geocoding calls**: 3–4 total external calls. The routing-call requirement is counted separately from geocoding. If three calls is intended as a strict combined ceiling, the verified two-route design exceeds it on a fully cold multi-stop trip. Repeated identical requests use **zero external calls**, and changes in starting fuel can reuse cached provider results. The map serves vendored Leaflet assets and simplified US state outlines locally: it makes **zero browser-side third-party requests**. It is a geographic overview, without street tiles. Basemap attribution and source licenses are in `data/BASEMAP_LICENSE.txt` and `planner/static/planner/LICENSE`.

Same-key requests share a file lock to prevent cache stampedes. Each provider has a process-shared, single-host lock and a 1.05-second start interval, with bounded queue waits. No automatic retries multiply the call budget. Each HTTP request has a 3.05-second connection timeout and a 15-second read-inactivity timeout (not a strict total wall-clock deadline). Public service latency dominates cold requests; there is no latency SLA.

The [FOSSGIS policy](https://routing.openstreetmap.de/about.html) allows at most one request per second and prohibits heavy use. [Photon's demo policy](https://github.com/komoot/photon#demo-server) requires reasonable traffic and provides no availability guarantee. The code throttles both, caches results, and displays attribution. Use these endpoints for a low-volume exercise; configure self-hosted services for larger workloads. Set an identifying contact in `PROVIDER_USER_AGENT` for deployment. No bulk station lookup, autocomplete, tile scraping, or per-station external requests are performed.

## Errors

Errors have the form `{"error":{"code":"...","message":"..."}}`.

| Status | Examples |
|---|---|
| 400 | Invalid JSON/fields, non-USA location, same start/finish |
| 405 | Method other than POST on plan endpoint |
| 413 | Request body larger than 16 KiB |
| 415 | Body not sent as application/json |
| 422 | Insufficient station coverage, disconnected route, infeasible verified route, too many stops |
| 503 | Missing station data, timeout, provider unavailable/malformed, provider queue busy |
| 404 | Unknown/expired map |

The app permits at most 40 selected station waypoints per request. Inputs have a 16 KiB body limit. There is no automatic fallback provider request that could unexpectedly exceed the call budget.

## Verify

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 2
python scripts/smoke.py  # optional, real external calls, current dataset
```

Tests cover route verification, multi-stop costs, zero-purchase trips, provider call counts and cache reuse, USA validation, upstream failure handling, atomic CSV import, and safe map JSON rendering. The fuel optimizer is independently checked against exhaustive dynamic programming over 120 seeded randomized cases. Tests use mocked providers and do not depend on public service availability. GitHub Actions runs the same checks.

## Deployment

```sh
docker build -t fuel-planner .
docker run --rm --env-file .env.example -p 8000:8000 fuel-planner \
  sh -c 'python manage.py migrate && python manage.py import_stations data/fuel-prices-for-be-assessment.csv --coordinates data/station-coordinates.csv --usa-only --duplicate-policy min-price --allow-unlocated && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 90'
```

Replace `.env.example` values first, including a random secret and the real allowed host. This container command imports the provided assessment data with the bundled partial coordinate companion. Persist the database/cache and add the remaining coordinates for full price coverage. The image runs as an unprivileged user. The plain image CMD starts Gunicorn; migration/import is an explicit initialization step.

This implementation targets one host with SQLite, shared file-cache storage, and `fcntl` locks (Linux/macOS). Cache directories must remain private and writable by the application user. Multiple containers/hosts require a shared database plus a distributed cache, single-flight locks, and a globally shared provider limiter; the included local locks are insufficient across hosts. Provider URLs are operator-configured, never request-supplied.

Before an internet-facing deployment, configure TLS, a reverse-proxy request timeout, authentication and request quotas, database backups, and platform logging. This stateless evaluation API has no cookie authentication and exempts its JSON endpoint from CSRF; do not add session privileges without revisiting that decision. Map tokens are unguessable UUIDs with a 24-hour lifetime but are not authorization controls for private journeys.

## Submission

See `docs/DEMO.md` for a recording script under five minutes and GitHub delivery steps. Actual GitHub and Loom URLs must come from successful uploads; none are fabricated here. The supplied fuel attachment is integrated. GitHub destination/access and a signed-in Loom recording/upload session are still pending. Full station coordinate coverage also remains incomplete; it must not be presented as complete in a submission.
