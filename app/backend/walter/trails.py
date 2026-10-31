"""Routing on the swissTLM3D hiking trails (pgRouting): snap clicked points to the trails, join them."""

import json
import math
from itertools import pairwise
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from walter.db import get_session

router = APIRouter(prefix="/api/trails")
SessionDep = Annotated[Session, Depends(get_session)]

MAX_SNAP_M = 1000  # a click further than this from any trail junction is rejected
# Routes are searched within the waypoints' box plus a margin; wider when that finds nothing
MARGINS_M = (3000, 20000)
PROFILE_STEP_M = 25

LonLat = Annotated[list[float], Field(min_length=2, max_length=2)]


class RouteRequest(BaseModel):
    waypoints: list[LonLat] = Field(min_length=2, max_length=100)  # [lon, lat], in walking order


class Profile(BaseModel):
    step_m: int
    elevations: list[int]


class Route(BaseModel):
    waypoints: list[list[float]]  # the requested points, snapped to the nearest trail junction
    geometry: dict[str, Any]  # GeoJSON LineString, [lon, lat, elevation]
    km: float
    ascent: int
    descent: int
    time_h: float
    bbox: list[float]  # west, south, east, north
    profile: Profile


def hiking_hours(km: float, ascent: float, descent: float) -> float:
    """DIN 33466: 4 km/h on the flat, 300 m/h up, 500 m/h down; the smaller part counts half.

    Same formula as data/preprocessing/load_trails.py, which uses it for the routing costs.
    """
    flat = km / 4
    climb = ascent / 300 + descent / 500
    return max(flat, climb) + min(flat, climb) / 2


SNAP = text("""
    SELECT v.id, ST_X(ST_Transform(v.geom, 4326)), ST_Y(ST_Transform(v.geom, 4326)),
           ST_X(v.geom), ST_Y(v.geom)
    FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 2056) AS g) p
    CROSS JOIN LATERAL (
        SELECT id, geom FROM trail_vertex
        WHERE ST_DWithin(geom, p.g, :max_m) ORDER BY geom <-> p.g LIMIT 1
    ) v
""")

# One line through all via points; each edge is reversed when walked target -> source
ROUTE = text("""
    WITH path AS (
        SELECT r.seq, CASE WHEN r.node = e.source THEN e.geom ELSE ST_Reverse(e.geom) END AS geom
        FROM pgr_dijkstraVia(
            'SELECT id, source, target, cost_s AS cost, reverse_cost_s AS reverse_cost FROM trail_edge'
            || ' WHERE geom && ST_MakeEnvelope(' || :west || ',' || :south || ',' || :east || ','
            || :north || ', 2056)',
            CAST(:vias AS bigint[]), directed => true, strict => true
        ) r
        JOIN trail_edge e ON e.id = r.edge
    ),
    line AS (SELECT ST_RemoveRepeatedPoints(ST_MakeLine(geom ORDER BY seq)) AS geom FROM path)
    SELECT ST_AsGeoJSON(geom, 1), ST_AsGeoJSON(ST_Transform(geom, 4326), 6) FROM line WHERE geom IS NOT NULL
""")


def route(session: Session, waypoints: list[list[float]]) -> Route:
    """Snap each waypoint to the trails and join them with the quickest walk (422 if impossible)."""
    snapped: list[tuple[int, float, float, float, float]] = []
    for i, (lon, lat) in enumerate(waypoints):
        row = session.execute(SNAP, {"lon": lon, "lat": lat, "max_m": MAX_SNAP_M}).one_or_none()
        if row is None:
            raise HTTPException(422, f"Point {i + 1} is more than {MAX_SNAP_M} m from a hiking trail")
        if not snapped or snapped[-1][0] != row[0]:  # two clicks on the same junction count once
            snapped.append((row[0], row[1], row[2], row[3], row[4]))
    if len(snapped) < 2:
        raise HTTPException(422, "The points snap to the same place on the trails")

    xs, ys = [s[3] for s in snapped], [s[4] for s in snapped]
    for margin in MARGINS_M:
        box = {"west": min(xs) - margin, "south": min(ys) - margin, "east": max(xs) + margin}
        box["north"] = max(ys) + margin
        row = session.execute(ROUTE, {**box, "vias": [s[0] for s in snapped]}).one_or_none()
        if row is not None:
            break
    else:
        raise HTTPException(422, "No trail connection between these points")

    lv95: list[list[float]] = json.loads(row[0])["coordinates"]
    geometry: dict[str, Any] = json.loads(row[1])
    return summarize([[round(s[1], 6), round(s[2], 6)] for s in snapped], lv95, geometry)


def summarize(waypoints: list[list[float]], lv95: list[list[float]], geometry: dict[str, Any]) -> Route:
    """Distance, height gained and lost, time and profile of a line given in LV95 metres with Z."""
    dist = [0.0]
    ascent = descent = 0.0
    for (x1, y1, z1), (x2, y2, z2) in pairwise(lv95):
        dist.append(dist[-1] + math.hypot(x2 - x1, y2 - y1))
        ascent += max(z2 - z1, 0)
        descent += max(z1 - z2, 0)
    km = dist[-1] / 1000
    lons, lats = [c[0] for c in geometry["coordinates"]], [c[1] for c in geometry["coordinates"]]
    return Route(
        waypoints=waypoints,
        geometry=geometry,
        km=round(km, 2),
        ascent=round(ascent),
        descent=round(descent),
        time_h=round(hiking_hours(km, ascent, descent), 2),
        bbox=[min(lons), min(lats), max(lons), max(lats)],
        profile=Profile(step_m=PROFILE_STEP_M, elevations=resample(dist, [c[2] for c in lv95])),
    )


def resample(dist: list[float], z: list[float]) -> list[int]:
    """Heights every PROFILE_STEP_M along the line, plus the end point."""
    out: list[int] = []
    i = 0
    for k in range(math.floor(dist[-1] / PROFILE_STEP_M) + 1):
        d = k * PROFILE_STEP_M
        while i < len(dist) - 2 and dist[i + 1] < d:
            i += 1
        span = dist[i + 1] - dist[i]
        t = (d - dist[i]) / span if span else 0
        out.append(round(z[i] + t * (z[i + 1] - z[i])))
    if dist[-1] % PROFILE_STEP_M:
        out.append(round(z[-1]))
    return out


@router.post("/route")
def route_between(request: RouteRequest, session: SessionDep) -> Route:
    return route(session, request.waypoints)
