# Data provenance and completeness

`fuel-prices-for-be-assessment.csv` is an unchanged copy of the file provided by the user. SHA-256:

`c704371f141ded9c54df6c32d488a0ba2ceb589f88c936c967daa5330e0cd241`

It contains 8,151 rows, no latitude/longitude fields, highway/exit-style addresses, Canadian records, repeated OPIS station IDs, and prices with up to eight decimal places. The original file remains intact. USA ingestion excludes 620 Canadian rows and retains 7,531 price quotes for 6,626 USA station IDs. All retained quotes are stored separately; minimum quoted station price is an explicit policy, not an average. No dates or grade distinctions are inferred. The current import preserves every retained numeric quote exactly.

`station-coordinates.csv` contains **518** location matches. Its only coordinate source is the official [Love's directory](https://www.loves.com/locations), retrieved on October 21, 2026. The publicly used `/api/fetch_stores` directory endpoint returned 734 location points. `loves-location-points.json` retains only store numbers, state, city, latitude, and longitude from that response so matching is reproducible offline. Other fields, contact details, and current chain prices are not retained in this file. Each companion row links to its official individual station page.

Matching requires exact Love's chain identity and store number in the original quote names, matching state, matching normalized city, and a unique assessment station ID. Punctuation/case/spacing are normalized; different cities or fuzzy names are not silently equated. Reproduce the join with:

```sh
python manage.py match_loves_coordinates data/loves-location-points.json --output reviewed-coordinates.csv
```

**6,108 USA stations remain unlocated.** They are kept in the imported dataset and their quotes remain available, but they cannot participate in spatial routing or price optimization. The route API and map disclose partial coverage. The supplied companion is useful for an actual-price demonstration and numerous interstate journeys; it is not a complete geocoding of the assessment file or proof of globally cheapest fuel stops. Additional accurate coordinates are needed for full coverage. Station entrance access also needs operational verification; routing snaps location points to a road within 100 meters.

Public Overpass endpoints returned errors/timeouts while attempting broader coordinate enrichment. The project includes an offline bounded-extract matching command as another enrichment path. Do not replace missing station locations with city centroids or synthetic road points.

`sample_stations.csv` is an explicitly synthetic fixture created before the original attachment became available. It is separate from the assessment dataset and is not used by the documented setup.

`us_states.geojson` is an overview basemap, decoded/simplified from US Atlas 3.0.1 state outlines derived from Census boundaries. Its license/source are in `BASEMAP_LICENSE.txt`. It is not a station address or entrance validation database.
