# OpenTripPlanner (public transport travel times)

Used offline by `data/preprocessing/travel_times.py` (`just travel-times`); not part of the normal stack
(compose profile `otp`).

Inputs in `data/ref/otp/graph/` (git-ignored):
- `gtfs.zip`: the Swiss feed trimmed to the reference weekend by `data/preprocessing/trim_gtfs.py`
  (source: opentransportdata.swiss "Timetable 2026 (GTFS2020)", permalink in that script's docstring)
- `switzerland.osm.pbf`: Geofabrik extract, for walking to/from stops

`just otp-build` builds `graph.obj` (~4 minutes); `just otp` serves it on
http://localhost:8090 (GraphQL: `/otp/gtfs/v1`). The config files here are copied next to the inputs.

Memory: the container is capped at 7 GB (5 GB Java heap). Close other heavy apps while it runs, and
`just otp-stop` when done. With less RAM, lower `WORKERS` in `travel_times.py`.
