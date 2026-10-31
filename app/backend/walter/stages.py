"""SchweizMobil stages and routes (shared Swiss data, same for every user)."""

import datetime as dt
from collections import defaultdict
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Numeric, func, null, select
from sqlalchemy.orm import QueryableAttribute, Session

from walter.db import get_session
from walter.models import SmRoute, SmStage, SmStageProfile, SmStageTravel
from walter.settings import Station, from_station

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

SCHWEIZMOBIL = "https://schweizmobil.ch/de/wanderland"
SWISS = ZoneInfo("Europe/Zurich")

# A column or SQL expression (PostGIS helpers below build on either)
SqlExpr = ColumnElement[Any] | QueryableAttribute[Any]


class RouteRef(BaseModel):
    nr: str
    name: str
    level: str
    stage_count: int
    url: str


class StageRef(BaseModel):
    id: str
    nr: int
    from_name: str
    to_name: str


class StageListItem(StageRef):
    km: int
    time_h: float


class StageSummary(StageListItem):
    """Everything the filters and the results list need; no geometry (the map has the tiles)."""

    route_nr: str
    route_name: str
    level: str
    ascent: int
    descent: int
    fitness: str
    technique: str
    bbox: list[float] = []  # west, south, east, north (WGS84): which stages are in the map view
    station_km: float | None = None  # straight line from the start station to the nearer end
    # Public transport, on the better reference day (None: not computed, or no connection there and back)
    travel_h: float | None = None  # each way: the longer of out and back
    day_h: float | None = None  # leaving the station to back there, hike included
    travel_day: str | None = None


class Trip(BaseModel):
    depart: dt.datetime
    arrive: dt.datetime
    transfers: int
    legs: list[dict[str, Any]]  # mode, line, from, to, depart, arrive (HH:MM)


class DayTravel(BaseModel):
    day: str  # sat / sun
    date: dt.date
    out: Trip | None
    back: Trip | None
    travel_h: float | None
    day_h: float | None


def hours(start: dt.datetime, end: dt.datetime) -> float:
    return round((end - start).total_seconds() / 3600, 2)


def trip(
    depart: dt.datetime | None,
    arrive: dt.datetime | None,
    transfers: int | None,
    legs: list[dict[str, Any]] | None,
) -> Trip | None:
    # Swiss local time, so clients can show HH:MM straight from the string
    if depart is None or arrive is None or transfers is None or legs is None:
        return None
    return Trip(
        depart=depart.astimezone(SWISS), arrive=arrive.astimezone(SWISS), transfers=transfers, legs=legs
    )


def day_travel(t: SmStageTravel) -> DayTravel:
    out = trip(t.out_depart, t.out_arrive, t.out_transfers, t.out_legs)
    back = trip(t.back_depart, t.back_arrive, t.back_transfers, t.back_legs)
    travel_h = day_h = None
    if out and back:
        travel_h = max(hours(out.depart, out.arrive), hours(back.depart, back.arrive))
        day_h = hours(out.depart, back.arrive)
    return DayTravel(day=t.day, date=t.date, out=out, back=back, travel_h=travel_h, day_h=day_h)


def best_day(days: list[DayTravel]) -> DayTravel | None:
    complete = [d for d in days if d.travel_h is not None]
    return min(complete, key=lambda d: (d.travel_h, d.day_h)) if complete else None


class Profile(BaseModel):
    step_m: int
    elevations: list[int]


class StageDetail(BaseModel):
    id: str
    nr: int
    from_name: str
    to_name: str
    km: int
    ascent: int
    descent: int
    time_h: float
    time_back_h: float
    fitness: str
    technique: str
    url: str
    route: RouteRef
    prev: StageRef | None
    next: StageRef | None
    bbox: list[float]  # west, south, east, north (WGS84)
    start: list[float]  # lon, lat
    end: list[float]
    profile: Profile
    travel: list[DayTravel]  # one per computed reference day, empty if not computed


class RouteDetail(BaseModel):
    nr: str
    name: str
    level: str
    from_name: str
    to_name: str
    km: int
    ascent: int
    descent: int
    fitness: str
    technique: str
    url: str
    bbox: list[float]
    stages: list[StageListItem]


def route_url(nr: str) -> str:
    return f"{SCHWEIZMOBIL}/route-{nr}"


def stage_url(route: SmRoute, stage: SmStage) -> str:
    # Single-stage routes (nr 0) only have a route page
    return route_url(route.nr) if stage.nr == 0 else f"{route_url(route.nr)}/etappe-{stage.nr}"


def bbox(geom: SqlExpr) -> list[ColumnElement[float]]:
    box = func.ST_Transform(func.ST_Envelope(geom), 4326)
    return [func.ST_XMin(box), func.ST_YMin(box), func.ST_XMax(box), func.ST_YMax(box)]


def point(geom: SqlExpr) -> list[ColumnElement[float]]:
    p = func.ST_Transform(geom, 4326)
    return [func.ST_X(p), func.ST_Y(p)]


STAGE_FIELDS = (
    "id",
    "nr",
    "from_name",
    "to_name",
    "km",
    "ascent",
    "descent",
    "time_h",
    "time_back_h",
    "fitness",
    "technique",
)


def ref(stage: SmStage | None) -> StageRef | None:
    return StageRef.model_validate(stage, from_attributes=True) if stage else None


@router.get("/stages")
def list_stages(session: SessionDep) -> list[StageSummary]:
    # ~1,000 rows: the client filters and sorts them
    station = from_station()
    station_km = (
        func.round(func.cast(distance_m(SmStage.geom, station) / 1000, Numeric), 1) if station else null()
    )
    rows = session.execute(select(SmStage, station_km).order_by(SmStage.route_nr, SmStage.nr))
    boxes = {
        stage_id: [round(float(v), 5) for v in box]
        for stage_id, *box in session.execute(select(SmStage.id, *bbox(SmStage.geom)))
    }
    travel: dict[str, list[DayTravel]] = defaultdict(list)
    for t in session.scalars(select(SmStageTravel)):
        travel[t.stage_id].append(day_travel(t))
    summaries = []
    for stage, km in rows:
        best = best_day(travel[stage.id])
        extra: dict[str, Any] = {"station_km": km, "bbox": boxes[stage.id]}
        if best:
            extra |= {"travel_h": best.travel_h, "day_h": best.day_h, "travel_day": best.day}
        summaries.append(StageSummary.model_validate(stage, from_attributes=True).model_copy(update=extra))
    return summaries


class Origin(BaseModel):
    name: str
    lon: float
    lat: float


@router.get("/origin")
def get_origin() -> Origin | None:
    """The station trips start and end at, or null if none is configured."""
    station = from_station()
    return Origin(name=station.name, lon=station.lon, lat=station.lat) if station else None


def distance_m(geom: SqlExpr, station: Station) -> ColumnElement[float]:
    """Metres from the station to the nearer end of the stage (stages can be walked either way)."""
    point = func.ST_Transform(func.ST_SetSRID(func.ST_MakePoint(station.lon, station.lat), 4326), 2056)
    return func.least(
        func.ST_Distance(func.ST_StartPoint(geom), point), func.ST_Distance(func.ST_EndPoint(geom), point)
    )


@router.get("/stages/{stage_id}")
def get_stage(stage_id: str, session: SessionDep) -> StageDetail:
    row = session.execute(
        select(SmStage, SmRoute, SmStageProfile)
        .join(SmRoute)
        .join(SmStageProfile)
        .where(SmStage.id == stage_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "stage not found")
    stage, route, profile = row
    west, south, east, north, start_x, start_y, end_x, end_y = session.execute(
        select(
            *bbox(SmStage.geom),
            *point(func.ST_StartPoint(SmStage.geom)),
            *point(func.ST_EndPoint(SmStage.geom)),
        ).where(SmStage.id == stage_id)
    ).one()
    neighbours = {
        s.nr: s
        for s in session.scalars(
            select(SmStage).where(SmStage.route_nr == route.nr, SmStage.nr.in_([stage.nr - 1, stage.nr + 1]))
        )
    }
    return StageDetail(
        **{k: getattr(stage, k) for k in STAGE_FIELDS},
        url=stage_url(route, stage),
        route=RouteRef(
            nr=route.nr,
            name=route.name,
            level=route.level,
            stage_count=route.stage_count,
            url=route_url(route.nr),
        ),
        prev=ref(neighbours.get(stage.nr - 1)),
        next=ref(neighbours.get(stage.nr + 1)),
        bbox=[west, south, east, north],
        start=[start_x, start_y],
        end=[end_x, end_y],
        profile=Profile(step_m=profile.step_m, elevations=profile.elevations),
        travel=[
            day_travel(t)
            for t in session.scalars(
                select(SmStageTravel).where(SmStageTravel.stage_id == stage.id).order_by(SmStageTravel.date)
            )
        ],
    )


@router.get("/routes/{nr}")
def get_route(nr: str, session: SessionDep) -> RouteDetail:
    route = session.get(SmRoute, nr)
    if route is None:
        raise HTTPException(404, "route not found")
    extent = func.ST_Extent(SmStage.geom)
    box = session.execute(select(*bbox(func.ST_SetSRID(extent, 2056))).where(SmStage.route_nr == nr)).one()
    stages = session.scalars(select(SmStage).where(SmStage.route_nr == nr).order_by(SmStage.nr))
    return RouteDetail(
        **{k: getattr(route, k) for k in RouteDetail.model_fields if k not in ("url", "bbox", "stages")},
        url=route_url(nr),
        bbox=[float(v) for v in box],
        stages=[StageListItem.model_validate(s, from_attributes=True) for s in stages],
    )
