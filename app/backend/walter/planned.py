"""My planned hikes: drawn on the map and snapped to the trails. Personal, served only here."""

import datetime as dt
import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from geoalchemy2 import WKBElement
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from walter.db import get_session
from walter.models import PlannedHike
from walter.trails import LonLat, Route, route, summarize

router = APIRouter(prefix="/api/me/planned-hikes")
SessionDep = Annotated[Session, Depends(get_session)]


class PlannedHikeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    waypoints: list[LonLat] = Field(min_length=2, max_length=100)


class PlannedHikeOut(Route):
    id: int
    name: str
    updated_at: dt.datetime


class PlannedProperties(BaseModel):
    id: int
    name: str
    km: float
    ascent: int
    descent: int
    time_h: float
    updated_at: dt.datetime


class PlannedFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]  # GeoJSON LineString, WGS84
    properties: PlannedProperties


class PlannedCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[PlannedFeature]


@router.get("")
def list_planned(session: SessionDep) -> PlannedCollection:
    rows = session.execute(
        select(
            PlannedHike, func.ST_AsGeoJSON(func.ST_Force2D(func.ST_Transform(PlannedHike.geom, 4326)), 6)
        ).order_by(PlannedHike.updated_at.desc())
    )
    return PlannedCollection(
        features=[
            PlannedFeature(
                geometry=json.loads(geometry),
                properties=PlannedProperties(
                    id=hike.id,
                    name=hike.name,
                    km=hike.km,
                    ascent=hike.ascent,
                    descent=hike.descent,
                    time_h=hike.time_h,
                    updated_at=hike.updated_at,
                ),
            )
            for hike, geometry in rows
        ]
    )


@router.get("/{hike_id}")
def get_planned(hike_id: int, session: SessionDep) -> PlannedHikeOut:
    return detail(session, find(session, hike_id))


@router.post("", status_code=201)
def create_planned(body: PlannedHikeIn, session: SessionDep) -> PlannedHikeOut:
    now = dt.datetime.now(dt.UTC)
    hike = PlannedHike(created_at=now)
    store(session, hike, body, now)
    session.add(hike)
    session.commit()
    return detail(session, hike)


@router.put("/{hike_id}")
def update_planned(hike_id: int, body: PlannedHikeIn, session: SessionDep) -> PlannedHikeOut:
    hike = find(session, hike_id)
    store(session, hike, body, dt.datetime.now(dt.UTC))
    session.commit()
    return detail(session, hike)


@router.delete("/{hike_id}", status_code=204)
def delete_planned(hike_id: int, session: SessionDep) -> Response:
    session.delete(find(session, hike_id))
    session.commit()
    return Response(status_code=204)


def find(session: Session, hike_id: int) -> PlannedHike:
    hike = session.get(PlannedHike, hike_id)
    if hike is None:
        raise HTTPException(404, "Planned hike not found")
    return hike


def store(session: Session, hike: PlannedHike, body: PlannedHikeIn, now: dt.datetime) -> None:
    """Re-route from the waypoints (never trust a line sent by the client) and copy the result in."""
    planned = route(session, body.waypoints)
    hike.name = body.name.strip()
    hike.updated_at = now
    hike.waypoints = planned.waypoints
    hike.km, hike.ascent, hike.descent, hike.time_h = (
        planned.km,
        planned.ascent,
        planned.descent,
        planned.time_h,
    )
    hike.geom = session.execute(
        select(
            func.ST_Transform(
                func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(planned.geometry)), 4326), 2056
            )
        )
    ).scalar_one()


def detail(session: Session, hike: PlannedHike) -> PlannedHikeOut:
    geom: WKBElement = hike.geom
    lv95, wgs84 = session.execute(
        select(func.ST_AsGeoJSON(geom, 1), func.ST_AsGeoJSON(func.ST_Transform(geom, 4326), 6))
    ).one()
    planned = summarize(hike.waypoints, json.loads(lv95)["coordinates"], json.loads(wgs84))
    return PlannedHikeOut(
        **planned.model_dump(),
        id=hike.id,
        name=hike.name,
        updated_at=hike.updated_at,
    )
