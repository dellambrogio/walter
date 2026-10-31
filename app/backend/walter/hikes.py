"""My past hikes (personal: detected in my Google Timeline). Served only here, never as tiles."""

import datetime as dt
import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from walter.db import get_session
from walter.models import MyHike

router = APIRouter(prefix="/api/me")
SessionDep = Annotated[Session, Depends(get_session)]


class HikeProperties(BaseModel):
    id: int
    date: dt.date
    certain: bool  # False: probably a hike, but part of it was too fast for walking
    km: float
    hours: float
    gain_m: int | None
    top_m: int | None


class HikeFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]  # GeoJSON LineString, WGS84
    properties: HikeProperties


class HikeCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[HikeFeature]


@router.get("/hikes")
def my_hikes(session: SessionDep) -> HikeCollection:
    rows = session.execute(
        select(MyHike, func.ST_AsGeoJSON(func.ST_Transform(MyHike.geom, 4326), 6)).order_by(MyHike.date)
    )
    return HikeCollection(
        features=[
            HikeFeature(
                geometry=json.loads(geometry),
                properties=HikeProperties(
                    id=hike.id,
                    date=hike.date,
                    certain=hike.kind == "hike",
                    km=hike.km,
                    hours=hike.hours,
                    gain_m=hike.gain_m,
                    top_m=hike.top_m,
                ),
            )
            for hike, geometry in rows
        ]
    )
