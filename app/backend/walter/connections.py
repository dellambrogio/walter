"""Live public transport connections for one stage on a chosen date, from transport.opendata.ch.

The precomputed travel times (stages.py, sm_stage_travel) are for a summer reference weekend; this asks
the current timetable for an actual date, so it knows the winter timetable, closed lifts, construction
work and rail replacement buses. Only stop names and the start station are sent; nothing about the user.
Answers are cached for CACHE_FOR, and nothing is fetched until a stage is opened.
"""

import datetime as dt
import json
import math
import time
import urllib.parse
import urllib.request
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from walter.db import get_session
from walter.models import SmStage
from walter.settings import from_station, settings
from walter.stages import Trip

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

API = "https://transport.opendata.ch/v1"
SBB = "https://www.sbb.ch/en/buying/pages/fahrplan/fahrplan.xhtml"
USER_AGENT = "Walter/0.1 (personal hiking map, runs locally)"
SWISS = ZoneInfo("Europe/Zurich")
CACHE_FOR = 300  # seconds
OPTIONS = 4  # connections each way
MAX_STOP_M = 1500  # a stop further than this from the trailhead isn't "at" the stage
DEFAULT_DEPARTURE = "08:00"
WALK_M_PER_MIN = 4000 / 60  # between the stop and the trailhead, on the flat
LON_LAT = r"^-?\d{1,3}(\.\d+)?,-?\d{1,2}(\.\d+)?$"

# transport.opendata.ch categories -> the modes the client knows (stages.Trip legs use OTP's names)
MODES = {
    **dict.fromkeys(["B", "BUS", "NFB", "KB", "BN", "BP"], "BUS"),
    **dict.fromkeys(["T", "TRAM", "NFT"], "TRAM"),
    **dict.fromkeys(["BAT", "BAV", "FAE"], "FERRY"),
    **dict.fromkeys(["PB", "GB", "LB", "SL", "SB", "ASC"], "CABLE_CAR"),
    "FUN": "FUNICULAR",
    "M": "SUBWAY",
}

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class Stop(BaseModel):
    id: str
    name: str
    distance_m: int  # from the stage end
    walk_min: int  # to or from the stage end, rounded up
    lon: float | None = None
    lat: float | None = None


class Connections(BaseModel):
    date: dt.date
    origin: str
    start_stop: Stop | None  # None: no stop within MAX_STOP_M
    end_stop: Stop | None
    out: list[Trip]
    back: list[Trip]  # leaving after back_after
    back_after: str  # HH:MM: the given one, or the first arrival plus walks and the official hiking time
    sbb_out: str | None  # the same search on sbb.ch, for tickets
    sbb_back: str | None


@router.get("/stages/{stage_id}/connections")
def connections(
    stage_id: str,
    session: SessionDep,
    date: Annotated[dt.date, Query()],
    back_after: Annotated[str | None, Query(pattern=r"^\d{2}:\d{2}$")] = None,
    pause_min: Annotated[int, Query(ge=0, le=240)] = 0,
) -> Connections:
    """Connections there and back; `back_after` (HH:MM) searches the way back from that time, e.g. after
    the client picked a later connection there; `pause_min` (e.g. lunch) adds to the hike."""
    row = session.execute(
        select(
            SmStage.time_h,
            func.ST_Y(func.ST_Transform(func.ST_StartPoint(SmStage.geom), 4326)),
            func.ST_X(func.ST_Transform(func.ST_StartPoint(SmStage.geom), 4326)),
            func.ST_Y(func.ST_Transform(func.ST_EndPoint(SmStage.geom), 4326)),
            func.ST_X(func.ST_Transform(func.ST_EndPoint(SmStage.geom), 4326)),
        ).where(SmStage.id == stage_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "stage not found")
    time_h, start_lat, start_lon, end_lat, end_lon = row
    return day_connections((start_lat, start_lon), (end_lat, end_lon), time_h, date, back_after, pause_min)


@router.get("/connections")
def line_connections(
    start: Annotated[str, Query(pattern=LON_LAT)],
    end: Annotated[str, Query(pattern=LON_LAT)],
    time_h: Annotated[float, Query(gt=0, le=24)],
    date: Annotated[dt.date, Query()],
    back_after: Annotated[str | None, Query(pattern=r"^\d{2}:\d{2}$")] = None,
    pause_min: Annotated[int, Query(ge=0, le=240)] = 0,
) -> Connections:
    """The same for any hike, e.g. a planned one while it's drawn: `start` and `end` as "lon,lat"."""
    return day_connections(lat_lon(start), lat_lon(end), time_h, date, back_after, pause_min)


def lat_lon(point: str) -> tuple[float, float]:
    lon, lat = (float(v) for v in point.split(","))
    return lat, lon


def day_connections(
    start: tuple[float, float],
    end: tuple[float, float],
    time_h: float,
    date: dt.date,
    back_after: str | None = None,
    pause_min: int = 0,
) -> Connections:
    """Connections for a hike from `start` to `end` (lat, lon): there to the stop nearest the start, back
    from the one nearest the end. Used for stages and for planned hikes."""
    station = from_station()
    if station is None:
        raise HTTPException(404, "no start station configured (config.local.json travel.from_station)")
    try:
        start_stop = nearest_stop(*start)
        end_stop = nearest_stop(*end)
        departure = departure_time()
        out = search(station.name, start_stop.id, date, departure, arrive_by=False) if start_stop else []
        ready = back_after or finish_time(out, time_h, start_stop, end_stop, pause_min)
        back = search(end_stop.id, station.name, date, ready, arrive_by=False) if end_stop else []
    except OSError as e:
        raise HTTPException(502, f"transport.opendata.ch not reachable: {e}") from e
    return Connections(
        date=date,
        origin=station.name,
        start_stop=start_stop,
        end_stop=end_stop,
        out=out,
        back=back,
        back_after=ready,
        sbb_out=sbb_link(station.name, start_stop.name, date, departure) if start_stop else None,
        sbb_back=sbb_link(end_stop.name, station.name, date, ready) if end_stop else None,
    )


def finish_time(
    out: list[Trip], time_h: float, start: Stop | None, end: Stop | None, pause_min: int = 0
) -> str:
    """Ready for the way back after the earliest arrival: walk to the start, hike and pause, walk to the stop.

    The client does the same sum for the connection it picked (ConnectionsSection), in whole minutes.
    Mid-afternoon if there's no way there.
    """
    arrival = min((t.arrive for t in out), default=None)
    if arrival is None:
        return "15:00"
    walks = (start.walk_min if start else 0) + (end.walk_min if end else 0)
    return (arrival + dt.timedelta(minutes=walks + math.floor(time_h * 60) + pause_min)).strftime("%H:%M")


def departure_time() -> str:
    """config.local.json `travel.departure`, like the precomputed travel times."""
    try:
        config = json.loads(settings.config_file.read_text(encoding="utf-8"))
        return str(config["travel"]["departure"])
    except (OSError, KeyError, TypeError, ValueError):
        return DEFAULT_DEPARTURE


def get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{API}/{path}?{urllib.parse.urlencode(params, doseq=True)}"
    cached = _cache.get(url)
    if cached and time.monotonic() - cached[0] < CACHE_FOR:
        return cached[1]
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.load(response)
    _cache[url] = (time.monotonic(), body)
    return body


def nearest_stop(lat: float, lon: float) -> Stop | None:
    """The nearest public transport stop (any mode, a lift station too); addresses have no id."""
    stations = get("locations", {"x": lat, "y": lon, "type": "station"}).get("stations", [])
    for s in stations:
        if s.get("id") and s.get("distance") is not None and s["distance"] <= MAX_STOP_M:
            distance = round(s["distance"])
            coordinate = s.get("coordinate") or {}  # x = latitude, y = longitude, like the query
            return Stop(
                id=s["id"],
                name=s["name"],
                distance_m=distance,
                walk_min=math.ceil(distance / WALK_M_PER_MIN),
                lon=coordinate.get("y"),
                lat=coordinate.get("x"),
            )
    return None


def search(origin: str, destination: str, date: dt.date, at: str, arrive_by: bool) -> list[Trip]:
    params = {
        "from": origin,
        "to": destination,
        "date": date.isoformat(),
        "time": at,
        "isArrivalTime": int(arrive_by),
        "limit": OPTIONS,
    }
    trips = (to_trip(c) for c in get("connections", params).get("connections", []))
    # Late searches run into the night: a trip leaving after midnight is no way home from a day hike
    return [t for t in trips if t and t.depart.date() == date]


def to_trip(connection: dict[str, Any]) -> Trip | None:
    depart, arrive = connection["from"].get("departure"), connection["to"].get("arrival")
    if not depart or not arrive:
        return None
    return Trip(
        depart=parse(depart),
        arrive=parse(arrive),
        transfers=connection.get("transfers") or 0,
        legs=[leg(s) for s in connection.get("sections", [])],
    )


def leg(section: dict[str, Any]) -> dict[str, Any]:
    """One section as the client's Leg: mode, line, from, to, depart, arrive (HH:MM), delay (min)."""
    journey = section.get("journey")
    start, end = section["departure"], section["arrival"]
    if journey is None:
        mode, line = "WALK", None
    else:
        category, number = journey.get("category") or "", (journey.get("number") or "").lstrip("0")
        mode = MODES.get(category, "EV" if category == "EV" else "RAIL")
        if mode == "EV":
            line = "Rail replacement bus"
        elif mode == "RAIL":
            # Long-distance trains carry a train number, not a line: show the category only (IC, IR)
            line = f"{category} {number}" if number and len(number) <= 3 else category
        else:
            line = number or None
    return {
        "mode": mode,
        "line": line,
        "from": start["station"]["name"],
        "to": end["station"]["name"],
        "depart": hhmm(start.get("departure")),
        "arrive": hhmm(end.get("arrival")),
        "delay": start.get("delay"),
        "platform": start.get("platform"),
    }


def parse(stamp: str) -> dt.datetime:
    return dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z").astimezone(SWISS)


def hhmm(stamp: str | None) -> str:
    return parse(stamp).strftime("%H:%M") if stamp else ""


def sbb_link(origin: str, destination: str, date: dt.date, at: str) -> str:
    params = {"von": origin, "nach": destination, "datum": f"{date:%d.%m.%Y}", "zeit": at, "an": "false"}
    return f"{SBB}?{urllib.parse.urlencode(params | {'suche': 'true'})}"
