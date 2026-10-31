"""Cable cars, gondolas, chairlifts and lifts (public swissTLM3D data), as GeoJSON with heights.

Not vector tiles: tiles are 2D, and the 3D map hangs the cables at their real height.
"""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from walter.db import get_session
from walter.models import Lift

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]


class LiftProperties(BaseModel):
    id: int
    kind: str  # cable_car / gondola / chairlift / lift
    name: str | None
    bottom_m: int  # the lower station
    top_m: int
    length_m: int  # horizontal


class LiftFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]  # GeoJSON LineString, WGS84, [lon, lat, height in m]
    properties: LiftProperties


class LiftCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[LiftFeature]


@router.get("/lifts")
def lifts(session: SessionDep) -> LiftCollection:
    start, end = func.ST_Z(func.ST_StartPoint(Lift.geom)), func.ST_Z(func.ST_EndPoint(Lift.geom))
    rows = session.execute(
        select(
            Lift,
            func.ST_AsGeoJSON(func.ST_Transform(Lift.geom, 4326), 6),
            func.least(start, end),
            func.greatest(start, end),
            func.ST_Length(Lift.geom),
        ).order_by(Lift.id)
    )
    return LiftCollection(
        features=[
            LiftFeature(
                geometry=json.loads(geometry),
                properties=LiftProperties(
                    id=lift.id,
                    kind=lift.kind,
                    name=lift.name,
                    bottom_m=round(bottom),
                    top_m=round(top),
                    length_m=round(length),
                ),
            )
            for lift, geometry, bottom, top, length in rows
        ]
    )
