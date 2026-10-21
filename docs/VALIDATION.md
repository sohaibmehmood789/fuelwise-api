# Validation results

Validated locally on October 21, 2026 with Python 3.14.6 and Django 6.1.2.

- `python manage.py test`: **31 tests passed**, including 120 seeded randomized optimizer cases compared with an independent exhaustive dynamic program.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no missing migrations.
- `pip check`: no broken requirements.
- Actual attachment import: **8,151 source rows**, **620 Canadian rows excluded**, **7,531 USA quotes retained**, **6,626 unique USA stations**. All retained quote prices were compared with their source decimal strings: **zero precision mismatches**.
- Partial coordinate companion: **518 stations** matched against official Love's store points using exact chain/store-number/city/state identity. **6,108 remain unlocated and are excluded from routing comparisons**, explicitly disclosed in API/map output.
- Real-provider, actual-CSV smoke check: **200 OK**, Los Angeles, California to Dallas, Texas, **1,440.128 road miles**, **5 fuel purchases**. Every returned stop price was checked against the imported CSV price. The final route was re-optimized using actual road leg distances, with feasible tank contents.
- Isolated fully cold cache: **2 geocoding calls + 2 routing calls**, approximately **5.58 seconds**. This is one measurement, not a latency guarantee; geocoding calls are separate from the two-call routing budget.
- Cached identical request: **0 external calls**, approximately **13 ms**.
- Actual CSV costs for that journey: **144.01279030 gallons consumed**, **94.01279031 gallons purchased**, **$296.09 in en-route purchases**, **$478.59 including starting fuel consumed at the supplied $3.65/gallon valuation**. The one-hundred-millionth gallon display difference is rounding; optimization uses Decimal values before display rounding.
- The actual-CSV map was inspected in a browser. It identifies the original CSV, shows five real station names/prices, and prominently displays coordinate coverage (518 / 6,626). Bundled Leaflet/state outlines avoid browser-side tile/CDN requests.
- Gunicorn was started locally with two workers/two threads to serve the updated application.

The optimal fuel purchase schedule is exact for the final selected waypoint order. Station selection is a heuristic, and incomplete coordinate coverage prevents comparisons against every station in the file. Additional accurate coordinates are required for full assessment-data coverage; the source prices themselves are all imported.

GitHub publishing and Loom recording/upload were checked in the available browser; both services required sign-in. No repository remote, authenticated publishing session, or submission-question URL was available. A Postman collection, REST-client requests, OpenAPI contract, Docker setup, CI workflow, and a recording script are included; actual upload links remain pending.
