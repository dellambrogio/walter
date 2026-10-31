"""Weather forecast per stage, from MeteoSwiss local forecasts (open data, "Source: MeteoSwiss").

The same point forecasts as the MeteoSwiss app, for ~5,800 points (weather stations, postcode centres,
mountain points), 9 days ahead, a new run every hour. Each stage uses the point nearest to its line;
temperatures are shifted to the stage's highest and lowest point with a standard lapse rate.

Cached in meteo_forecast; when the cache is more than CHECK_EVERY old, the next request is answered
from it while a newer run is fetched in the background. Nothing about the user is sent to MeteoSwiss.
"""

import csv
import datetime as dt
import io
import json
import logging
import threading
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Iterable
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from walter.db import SessionLocal, get_session
from walter.models import MeteoForecast, MeteoPoint, MeteoRun

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]
log = logging.getLogger(__name__)

COLLECTION = "ch.meteoschweiz.ogd-local-forecasting"
STAC = f"https://data.geo.admin.ch/api/stac/v1/collections/{COLLECTION}/items"
FILES = f"https://data.geo.admin.ch/{COLLECTION}"
USER_AGENT = "Walter/0.1 (personal hiking map, runs locally)"
SWISS = ZoneInfo("Europe/Zurich")
CHECK_EVERY = dt.timedelta(hours=1)
LAPSE_C_PER_M = 0.0065  # standard atmosphere: 0.65 °C colder per 100 m up
DAYTIME = range(8, 18)  # local hours for the freezing level: when people are on the trail

# Daily values (local days, 00:00 - 24:00) and hourly ones (UTC timestamps), see the parameter metadata
DAILY = {"rka150p0": "precip_mm", "tre200pn": "tmin", "tre200px": "tmax"}
HOURLY = {"sre000h0": "sun_h", "zprfr0hs": "zero_m"}

_refreshing = threading.Lock()


class DayWeather(BaseModel):
    sun_h: float | None
    precip_mm: float | None
    tmin: float | None  # at the stage's highest point
    tmax: float | None  # at its lowest point
    zero_m: int | None  # lowest freezing level during the day


class StageWeather(BaseModel):
    point: str  # forecast point name, e.g. "3818 Grindelwald" or "Schilthorn"
    point_m: int
    top_m: int
    low_m: int
    days: list[DayWeather | None]  # one per Weather.dates entry


class Weather(BaseModel):
    run: dt.datetime
    dates: list[dt.date]
    stages: dict[str, StageWeather]


class LineWeather(BaseModel):
    run: dt.datetime
    dates: list[dt.date]
    weather: StageWeather


class PointWeather(BaseModel):
    name: str
    height_m: int
    lon: float
    lat: float
    days: list[DayWeather | None]  # temperatures at the point's height


class WeatherPoints(BaseModel):
    run: dt.datetime
    dates: list[dt.date]
    points: list[PointWeather]


@router.get("/weather")
def weather(session: SessionDep, background: BackgroundTasks) -> Weather:
    """Forecast for every stage. The client filters by it; the stage panel shows one stage's days."""
    keep_fresh(session, background)
    return stage_weather(session)


class LineIn(BaseModel):
    coordinates: list[list[float]] = Field(min_length=2)  # WGS84 lon, lat, elevation


@router.post("/weather/line")
def weather_for_line(body: LineIn, session: SessionDep, background: BackgroundTasks) -> LineWeather:
    """Forecast for any line, e.g. a planned hike while it's drawn; temperatures at its top and low point."""
    if any(len(c) != 3 for c in body.coordinates):
        raise HTTPException(422, "coordinates need lon, lat and elevation")
    keep_fresh(session, background)
    line = {"type": "LineString", "coordinates": [c[:2] for c in body.coordinates]}
    geom = func.ST_Transform(func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(line)), 4326), 2056)
    heights = [c[2] for c in body.coordinates]
    return line_weather(session, geom, max(heights), min(heights))


@router.get("/weather/points")
def weather_points(session: SessionDep, background: BackgroundTasks) -> WeatherPoints:
    """The forecast points the stages use, for the weather symbols on the map."""
    keep_fresh(session, background)
    run, dates, forecast = load_forecast(session)
    used = {(kind, point_id) for _, kind, point_id, *_ in nearest_points(session)}
    rows = session.execute(
        select(
            MeteoPoint.kind,
            MeteoPoint.point_id,
            MeteoPoint.name,
            MeteoPoint.height_m,
            func.ST_X(func.ST_Transform(MeteoPoint.geom, 4326)),
            func.ST_Y(func.ST_Transform(MeteoPoint.geom, 4326)),
        )
    )
    points = []
    for kind, point_id, name, height_m, lon, lat in rows:
        if (kind, point_id) not in used:
            continue
        by_date = forecast.get((kind, point_id), {})
        days = [day_weather(by_date.get(d), height_m, height_m, height_m) for d in dates]
        points.append(PointWeather(name=name, height_m=height_m, lon=lon, lat=lat, days=days))
    return WeatherPoints(run=run, dates=dates, points=points)


def keep_fresh(session: Session, background: BackgroundTasks) -> None:
    """Fetch the first run now; later ones in the background once the cache is CHECK_EVERY old."""
    current = session.scalar(select(MeteoRun))
    if current is None:
        try:
            refresh(session)
        except OSError as e:
            raise HTTPException(502, f"MeteoSwiss not reachable: {e}") from e
    elif dt.datetime.now(dt.UTC) - current.checked_at > CHECK_EVERY:
        background.add_task(refresh_in_background)


def refresh_in_background() -> None:
    if not _refreshing.acquire(blocking=False):
        return  # another request is already fetching
    try:
        with SessionLocal() as session:
            refresh(session)
    except OSError as e:  # keep serving the cached run; try again on a later request
        log.warning("MeteoSwiss forecast refresh failed: %s", e)
    finally:
        _refreshing.release()


def refresh(session: Session) -> None:
    """Load the newest complete run into meteo_forecast (only the points nearest to a stage)."""
    if session.scalar(select(MeteoPoint.kind).limit(1)) is None:
        load_points(session)
    run, item = latest_run()
    now = dt.datetime.now(dt.UTC)
    current = session.scalar(select(MeteoRun))
    if current and current.run == run:
        current.checked_at = now
        session.commit()
        return
    wanted = {(str(kind), str(point_id)) for _, kind, point_id, *_ in nearest_points(session)}
    wanted |= {(str(kind), str(point_id)) for kind, point_id in planned_points(session)}
    base = f"{FILES}/{item}/vnut12.lssw.{run:%Y%m%d%H%M}"
    days: dict[tuple[str, str], dict[dt.date, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for param, field in DAILY.items():
        for key, date, value in daily(rows(fetch(f"{base}.{param}.csv"), wanted)):
            days[key][date][field] = value
    for param, field in HOURLY.items():
        combine = sum_hours if field == "sun_h" else daytime_min
        for key, date, value in combine(rows(fetch(f"{base}.{param}.csv"), wanted)):
            days[key][date][field] = value
    today = now.astimezone(SWISS).date()
    session.execute(delete(MeteoForecast))
    session.execute(delete(MeteoRun))
    forecast = [
        {"kind": int(kind), "point_id": int(point_id), "date": date} | values
        for (kind, point_id), by_date in days.items()
        for date, values in by_date.items()
        if date >= today
    ]
    if forecast:
        session.execute(insert(MeteoForecast), forecast)
    session.add(MeteoRun(run=run, checked_at=now))
    session.commit()


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("latin-1")  # the metadata has accents; the forecasts are ASCII


def latest_run() -> tuple[dt.datetime, str]:
    """The newest run with every parameter we use, and its STAC item (one item per UTC day)."""
    today = dt.datetime.now(dt.UTC).date()
    for day in (today, today - dt.timedelta(days=1)):
        item = f"{day:%Y%m%d}-ch"
        try:
            assets = json.loads(fetch(f"{STAC}/{item}"))["assets"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        params: dict[str, set[str]] = defaultdict(set)
        for name in assets:  # vnut12.lssw.202610252300.sre000h0.csv
            parts = name.split(".")
            if len(parts) == 5:
                params[parts[2]].add(parts[3])
        complete = [run for run, have in params.items() if {*DAILY, *HOURLY} <= have]
        if complete:
            run = max(complete)
            return dt.datetime.strptime(run, "%Y%m%d%H%M").replace(tzinfo=dt.UTC), item
    raise OSError("no complete MeteoSwiss forecast run in the last two days")


def load_points(session: Session) -> None:
    content = fetch(f"{FILES}/ogd-local-forecasting_meta_point.csv")
    points = [
        {
            "kind": int(r["point_type_id"]),
            "point_id": int(r["point_id"]),
            "name": " ".join(filter(None, [r["postal_code"], r["point_name"]])),
            "height_m": round(float(r["point_height_masl"])),
            "x": float(r["point_coordinates_lv95_east"]),
            "y": float(r["point_coordinates_lv95_north"]),
        }
        for r in csv.DictReader(io.StringIO(content), delimiter=";")
    ]
    session.execute(
        text("""
            INSERT INTO meteo_point (kind, point_id, name, height_m, geom)
            VALUES (:kind, :point_id, :name, :height_m, ST_SetSRID(ST_MakePoint(:x, :y), 2056))
            ON CONFLICT DO NOTHING
        """),
        points,
    )
    session.commit()


def nearest_points(session: Session) -> list[tuple[str, int, int, str, int, float, float]]:
    """Per stage: the nearest forecast point (kind, id, name, height) and the stage's top and low height."""
    return [
        tuple(r)
        for r in session.execute(
            text("""
                SELECT s.id, p.kind, p.point_id, p.name, p.height_m,
                       (SELECT max(e::float) FROM jsonb_array_elements_text(pr.elevations) e),
                       (SELECT min(e::float) FROM jsonb_array_elements_text(pr.elevations) e)
                FROM sm_stage s
                JOIN sm_stage_profile pr ON pr.stage_id = s.id
                CROSS JOIN LATERAL (
                    SELECT kind, point_id, name, height_m FROM meteo_point m
                    ORDER BY m.geom <-> s.geom LIMIT 1
                ) p
            """)
        )
    ]


def planned_points(session: Session) -> list[tuple[int, int]]:
    """The forecast points nearest to my planned hikes, fetched along with the stages' ones."""
    return [
        (kind, point_id)
        for kind, point_id in session.execute(
            text("""
                SELECT DISTINCT p.kind, p.point_id
                FROM planned_hike h
                CROSS JOIN LATERAL (
                    SELECT kind, point_id FROM meteo_point m ORDER BY m.geom <-> h.geom LIMIT 1
                ) p
            """)
        )
    ]


def line_weather(session: Session, geom: object, top_m: float, low_m: float) -> LineWeather:
    """Forecast for a line (LV95 geometry or expression): from the nearest point that has a forecast.

    The refresh only fetches points near stages and planned hikes, so a hike saved since the last run may
    use a point a little further away until the next one.
    """
    run, dates, forecast = load_forecast(session)
    kind, point_id, name, point_m = session.execute(
        select(MeteoPoint.kind, MeteoPoint.point_id, MeteoPoint.name, MeteoPoint.height_m)
        .where(
            select(MeteoForecast.kind)
            .where(MeteoForecast.kind == MeteoPoint.kind, MeteoForecast.point_id == MeteoPoint.point_id)
            .exists()
        )
        .order_by(MeteoPoint.geom.op("<->")(geom))
        .limit(1)
    ).one()
    by_date = forecast.get((kind, point_id), {})
    days = [day_weather(by_date.get(d), point_m, top_m, low_m) for d in dates]
    weather = StageWeather(point=name, point_m=point_m, top_m=round(top_m), low_m=round(low_m), days=days)
    return LineWeather(run=run, dates=dates, weather=weather)


Row = tuple[tuple[str, str], str, float]  # (kind, point id), YYYYMMDDHHMM, value


def rows(content: str, wanted: set[tuple[str, str]]) -> Iterable[Row]:
    """`point_id;point_type_id;Date;<param>` lines for the wanted points; missing values skipped."""
    lines = iter(content.splitlines())
    next(lines, None)  # header
    for line in lines:
        point_id, kind, stamp, value = line.split(";")
        if (kind, point_id) in wanted and value not in ("", "-"):
            yield (kind, point_id), stamp, float(value)


def daily(values: Iterable[Row]) -> Iterable[tuple[tuple[str, str], dt.date, float]]:
    for key, stamp, value in values:
        yield key, dt.date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8])), value


def local_hours(values: Iterable[Row]) -> Iterable[tuple[tuple[str, str], dt.datetime, float]]:
    local: dict[str, dt.datetime] = {}  # a few hundred distinct timestamps per file
    for key, stamp, value in values:
        if stamp not in local:
            utc = dt.datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=dt.UTC)
            local[stamp] = utc.astimezone(SWISS)
        yield key, local[stamp], value


def sum_hours(values: Iterable[Row]) -> Iterable[tuple[tuple[str, str], dt.date, float]]:
    """Sunshine minutes per hour -> hours per local day; only whole days (the last one is cut off)."""
    total: dict[tuple[tuple[str, str], dt.date], float] = defaultdict(float)
    hours: dict[tuple[tuple[str, str], dt.date], int] = defaultdict(int)
    for key, when, minutes in local_hours(values):
        total[key, when.date()] += minutes
        hours[key, when.date()] += 1
    for (key, date), minutes in total.items():
        if hours[key, date] >= 23:  # 23 on the day clocks go forward
            yield key, date, round(minutes / 60, 1)


def daytime_min(values: Iterable[Row]) -> Iterable[tuple[tuple[str, str], dt.date, int]]:
    lowest: dict[tuple[tuple[str, str], dt.date], float] = {}
    hours: dict[tuple[tuple[str, str], dt.date], int] = defaultdict(int)
    for key, when, value in local_hours(values):
        if when.hour in DAYTIME:
            k = (key, when.date())
            lowest[k] = min(value, lowest.get(k, value))
            hours[k] += 1
    for (key, date), value in lowest.items():
        if hours[key, date] == len(DAYTIME):
            yield key, date, round(value)


def at_height(t: float | None, point_m: float, height_m: float) -> float | None:
    return None if t is None else round(t - LAPSE_C_PER_M * (height_m - point_m), 1)


Forecast = dict[tuple[int, int], dict[dt.date, MeteoForecast]]


def load_forecast(session: Session) -> tuple[dt.datetime, list[dt.date], Forecast]:
    run = session.scalars(select(MeteoRun.run)).one()
    forecast: Forecast = defaultdict(dict)
    for f in session.scalars(select(MeteoForecast)):
        forecast[f.kind, f.point_id][f.date] = f
    return run, sorted({d for by_date in forecast.values() for d in by_date}), forecast


def day_weather(f: MeteoForecast | None, point_m: float, top_m: float, low_m: float) -> DayWeather | None:
    if f is None:
        return None
    return DayWeather(
        sun_h=f.sun_h,
        precip_mm=f.precip_mm,
        tmin=at_height(f.tmin, point_m, top_m),
        tmax=at_height(f.tmax, point_m, low_m),
        zero_m=f.zero_m,
    )


def stage_weather(session: Session) -> Weather:
    run, dates, forecast = load_forecast(session)
    stages = {}
    for stage_id, kind, point_id, name, point_m, top_m, low_m in nearest_points(session):
        by_date = forecast.get((kind, point_id), {})
        days = [day_weather(by_date.get(d), point_m, top_m, low_m) for d in dates]
        stages[stage_id] = StageWeather(
            point=name, point_m=point_m, top_m=round(top_m), low_m=round(low_m), days=days
        )
    return Weather(run=run, dates=dates, stages=stages)
