# Five-minute demonstration and submission

The supplied assignment CSV is integrated with a partial official coordinate companion (518 of 6,626 stations). Show this coverage honestly in the recording. The separate sample CSV is synthetic and must be identified as such if used. Do not present mocked-provider tests as live-provider output.

## Recording outline (4 minutes 40 seconds)

- **0:00–0:30:** Show README setup, the actual fuel CSV import, and the running service. Explain 500 miles / 10 mpg = a 50-gallon tank and a full starting tank.
- **0:30–1:30:** In Postman, import `FuelPlanner.postman_collection.json`, set `base_url`, and send “Plan route.” Show resolved locations, fuel stops, purchase quantities, costs, and the external call counters. Use a long trip supported by the actual dataset.
- **1:30–2:00:** Open the returned map URL in a browser. Point out road geometry, start/finish, and station markers. Explain that the final routing call checks actual distances through the selected stops.
- **2:00–2:25:** Send the identical request again. Show `plan_cache_hit: true`, zero provider calls, and the measured response time. Avoid claiming that warm latency is cold latency.
- **2:25–2:50:** Show an invalid request and its structured error response. Optionally show a short trip without a fuel purchase.
- **2:50–4:10:** Brief code tour: `providers.py` for caching/timeouts/throttling; `geometry.py` for the spatial index; `optimizer.py` for the next-cheaper greedy strategy; `service.py` for final route verification and cost accounting. State that the fuel schedule is optimal for selected waypoints, while station selection is a heuristic.
- **4:10–4:40:** Run `python manage.py test`, mention the independent randomized optimizer oracle, and show the repository README and CI configuration.

## Before publishing

1. Import the supplied assessment CSV with the included companion using the README command. Add coordinates for the 6,108 unresolved stations to complete price coverage; do not claim the full file participates before that is done.
2. Run the test suite and a successful real-provider request. Confirm that no leg requiring fuel exceeds the actual available tank range.
3. Review which repository owner and visibility the user wants. The project contains no credentials or real attached fuel data by default. Do not upload private input data without authorization.
4. Push the reviewed source to the authorized GitHub repository, using normal authenticated Git or GitHub UI. No GitHub remote or credentials were supplied in this workspace.
5. Record in Loom using a signed-in session, sharing only the API client, map, and relevant code windows. Screen/audio permissions and a recording session must be available; a script alone is not a Loom video.
6. Verify both links are accessible to the intended reviewers, then paste them into the exercise's submission question. No question/submission portal URL was provided here.

## Submission text after successful uploads

> GitHub: [actual repository link]
>
> Loom walkthrough (under 5 minutes): [actual recording link]
>
> Implemented with Django 6.1.2. Includes CSV ingestion, cached routing, a cost-minimizing fuel schedule for selected route waypoints, road-distance verification, an interactive map, Postman requests, and automated tests. Assumptions and optimality limits are documented in README.md.
