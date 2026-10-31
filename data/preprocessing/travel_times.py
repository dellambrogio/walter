"""Public transport travel times between a start station and every SchweizMobil stage (local OpenTripPlanner).

Usage: .venv/bin/python data/preprocessing/travel_times.py [stage_id ...]   (or `just travel-times`)
Needs: the stack running with stages loaded, and `just otp` serving the graph for the reference weekend.
Writes sm_stage_travel; with stage ids, only those are recomputed.

Per stage and reference day (Saturday / Sunday from config.local.json `travel.days`):
- out:  `travel.from_station` (e.g. Zürich HB) -> stage start,
        leaving after `travel.departure`
- back: stage end -> the same station, leaving when the hike is done (arrival + official hiking time)
Picks the itinerary that arrives first. Nothing leaves this machine: OTP runs locally.

Some trailheads snap onto an isolated bit of footpath in OTP's street graph and can't be routed. Then the
nearest stops (within FALLBACK_M) are tried instead, with an estimated walk (straight line x DETOUR at
WALK_M_PER_MIN) between stop and trailhead; that leg is marked `"estimated": true`.
"""

import datetime as dt
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from zoneinfo import ZoneInfo

import psycopg

DB = os.environ.get("WALTER_DB", "postgresql://walter:walter@localhost:5432/walter")
OTP = os.environ.get("OTP_URL", "http://localhost:8090/otp/gtfs/v1")
CONFIG = json.loads(Path("config.local.json").read_text(encoding="utf-8"))
TZ = ZoneInfo("Europe/Zurich")
# Must be inside the trimmed timetable (data/preprocessing/trim_gtfs.py DATES)
DAYS = {"saturday": ("sat", dt.date(2026, 7, 11)), "sunday": ("sun", dt.date(2026, 7, 12))}
# Each OTP search holds a lot of memory; 4 in parallel crashed a 14 GB laptop. OTP_WORKERS=1 is the leanest.
WORKERS = int(os.environ.get("OTP_WORKERS", "2"))
FALLBACK_M = 1500
DETOUR = 1.25
WALK_M_PER_MIN = 70  # 4.2 km/h

LonLat = tuple[float, float]
Place = str | LonLat  # an OTP stop/station gtfsId, or a coordinate
Json = dict[str, Any]
Leg = TypedDict(
    "Leg",
    {  # "from" is a keyword, hence the functional form
        "mode": str,
        "line": str | None,
        "from": str,
        "to": str,
        "depart": str,
        "arrive": str,
        "estimated": NotRequired[bool],
    },
)


class Trip(TypedDict):
    depart: dt.datetime
    arrive: dt.datetime
    transfers: int
    legs: list[Leg]


Stage = tuple[str, LonLat, LonLat, float, str, str]  # id, start, end, hiking hours, from, to
TripCols = tuple[dt.datetime | None, dt.datetime | None, int | None, str | None]
# One sm_stage_travel row: stage id, day, date, then TripCols for out and for back
TravelRow = tuple[
    str,
    str,
    dt.date,
    dt.datetime | None,
    dt.datetime | None,
    int | None,
    str | None,
    dt.datetime | None,
    dt.datetime | None,
    int | None,
    str | None,
]

QUERY = """
query Plan($origin: PlanLabeledLocationInput!, $destination: PlanLabeledLocationInput!,
           $dateTime: PlanDateTimeInput!) {
  planConnection(origin: $origin, destination: $destination, dateTime: $dateTime, first: 5) {
    edges { node {
      start end numberOfTransfers
      legs { mode from { name } to { name } route { shortName }
             start { scheduledTime } end { scheduledTime } }
    } }
  }
}
"""


STATIONS = """
query Stations($name: String!) { stations(name: $name) { gtfsId name } }
"""

NEAREST = """
query Near($lat: Float!, $lon: Float!, $max: Int!) {
  nearest(lat: $lat, lon: $lon, maxDistance: $max, filterByPlaceTypes: [STOP], first: 3) {
    edges { node { distance place { ... on Stop { gtfsId name } } } }
  }
}
"""


def graphql(query: str, variables: Json) -> Json:
    body = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(OTP, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(result["errors"])
    return result["data"]


def place(p: Place) -> Json:
    """A (lon, lat) coordinate or a stop's gtfsId."""
    if isinstance(p, str):
        return {"location": {"stopLocation": {"stopLocationId": p}}}
    return {"location": {"coordinate": {"latitude": p[1], "longitude": p[0]}}}


def plan(origin: Place, destination: Place, depart: dt.datetime, names: tuple[str, str]) -> Trip | None:
    """Fastest-arriving itinerary leaving after `depart`, or None. `names` label OTP's Origin/Destination."""
    data = graphql(
        QUERY,
        {
            "origin": place(origin),
            "destination": place(destination),
            "dateTime": {"earliestDeparture": depart.isoformat()},
        },
    )
    itineraries = [edge["node"] for edge in data["planConnection"]["edges"]]
    if not itineraries:
        return None
    best = min(itineraries, key=lambda i: (i["end"], i["numberOfTransfers"]))
    return {
        "depart": dt.datetime.fromisoformat(best["start"]),
        "arrive": dt.datetime.fromisoformat(best["end"]),
        "transfers": best["numberOfTransfers"],
        "legs": [leg_summary(leg, names) for leg in best["legs"]],
    }


def leg_summary(leg: Json, names: tuple[str, str]) -> Leg:
    name = lambda place: {"Origin": names[0], "Destination": names[1]}.get(place["name"], place["name"])  # noqa: E731
    hhmm = lambda t: dt.datetime.fromisoformat(t).strftime("%H:%M")  # noqa: E731
    return {
        "mode": leg["mode"],
        "line": (leg.get("route") or {}).get("shortName"),
        "from": name(leg["from"]),
        "to": name(leg["to"]),
        "depart": hhmm(leg["start"]["scheduledTime"]),
        "arrive": hhmm(leg["end"]["scheduledTime"]),
    }


def nearest_stops(point: LonLat) -> list[tuple[str, str, dt.timedelta]]:
    """(gtfsId, name, estimated walk) of the stops nearest to a (lon, lat) point."""
    data = graphql(NEAREST, {"lat": point[1], "lon": point[0], "max": FALLBACK_M})
    return [
        (
            n["place"]["gtfsId"],
            n["place"]["name"],
            dt.timedelta(minutes=round(n["distance"] * DETOUR / WALK_M_PER_MIN)),
        )
        for n in (edge["node"] for edge in data["nearest"]["edges"])
    ]


def walk_leg(origin: str, destination: str, start: dt.datetime, duration: dt.timedelta) -> Leg:
    hhmm = lambda t: t.astimezone(TZ).strftime("%H:%M")  # noqa: E731
    return {
        "mode": "WALK",
        "line": None,
        "from": origin,
        "to": destination,
        "depart": hhmm(start),
        "arrive": hhmm(start + duration),
        "estimated": True,
    }


def plan_to(origin: Place, point: LonLat, depart: dt.datetime, names: tuple[str, str]) -> Trip | None:
    """Route to a trailhead; if it can't be reached directly, to a stop near it plus an estimated walk."""
    trip = plan(origin, point, depart, names)
    if trip:
        return trip
    for stop_id, stop_name, walk in nearest_stops(point):
        trip = plan(origin, stop_id, depart, (names[0], stop_name))
        if trip:
            trip["legs"].append(walk_leg(stop_name, names[1], trip["arrive"], walk))
            trip["arrive"] += walk
            return trip
    return None


def plan_from(point: LonLat, destination: Place, depart: dt.datetime, names: tuple[str, str]) -> Trip | None:
    """Route from a trailhead; if it can't be reached directly, from a nearby stop after an estimated walk."""
    trip = plan(point, destination, depart, names)
    if trip:
        return trip
    for stop_id, stop_name, walk in nearest_stops(point):
        trip = plan(stop_id, destination, depart + walk, (stop_name, names[1]))
        if trip:
            trip["depart"] -= walk
            trip["legs"].insert(0, walk_leg(names[0], stop_name, trip["depart"], walk))
            return trip
    return None


def trip_cols(t: Trip | None) -> TripCols:
    return (
        (t["depart"], t["arrive"], t["transfers"], json.dumps(t["legs"])) if t else (None, None, None, None)
    )


def travel(stage: Stage, day: str, date: dt.date) -> TravelRow:
    stage_id, start, end, hike_h, from_name, to_name = stage
    leave = dt.datetime.combine(date, dt.time.fromisoformat(CONFIG["travel"]["departure"]), TZ)
    out = plan_to(ORIGIN, start, leave, (ORIGIN_NAME, from_name))
    back = (
        plan_from(end, ORIGIN, out["arrive"] + dt.timedelta(hours=hike_h), (to_name, ORIGIN_NAME))
        if out
        else None
    )
    return (stage_id, day, date, *trip_cols(out), *trip_cols(back))


def origin() -> tuple[Place, str]:
    """OTP station id and name to start and end at (config.local.json `travel.from_station.name`)."""
    station = CONFIG["travel"].get("from_station")
    if not station:
        sys.exit("config.local.json: set travel.from_station (see config.example.json)")
    name = station["name"]
    matches = [s for s in graphql(STATIONS, {"name": name})["stations"] if s["name"] == name]
    if not matches:
        sys.exit(f"travel.from_station {name!r}: no station with exactly that name in the OTP graph")
    return matches[0]["gtfsId"], name


days = [DAYS[d] for d in CONFIG["travel"]["days"]]
ORIGIN, ORIGIN_NAME = origin()
only = sys.argv[1:]

with psycopg.connect(DB) as conn:
    stages = [
        (sid, (sx, sy), (ex, ey), hike_h, from_name, to_name)
        for sid, sx, sy, ex, ey, hike_h, from_name, to_name in conn.execute(
            """SELECT id,
                      ST_X(ST_Transform(ST_StartPoint(geom), 4326)),
                      ST_Y(ST_Transform(ST_StartPoint(geom), 4326)),
                      ST_X(ST_Transform(ST_EndPoint(geom), 4326)),
                      ST_Y(ST_Transform(ST_EndPoint(geom), 4326)),
                      time_h, from_name, to_name
               FROM sm_stage WHERE cardinality(%s::text[]) = 0 OR id = ANY(%s) ORDER BY id""",
            (only, only),
        )
    ]
    jobs = [(stage, day, date) for stage in stages for day, date in days]
    print(
        f"From {ORIGIN_NAME}: {len(stages)} stages x {len(days)} days = {len(jobs)} trips "
        f"({WORKERS} parallel)",
        flush=True,
    )

    rows = []
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, row in enumerate(pool.map(lambda job: travel(*job), jobs), 1):
            rows.append(row)
            if i % 100 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}", flush=True)

    with conn.cursor() as cur:
        if only:
            cur.execute("DELETE FROM sm_stage_travel WHERE stage_id = ANY(%s)", (only,))
        else:
            cur.execute("TRUNCATE sm_stage_travel")
        cur.executemany(
            "INSERT INTO sm_stage_travel VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", rows
        )

reachable = sum(1 for r in rows if r[3] and r[7])
print(f"{reachable}/{len(rows)} trips with a connection there and back")
