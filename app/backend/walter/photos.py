"""Openly licensed photos along a stage, from Wikimedia Commons (geotagged files near the trail).

SchweizMobil's own photos are copyrighted (view-only on their site), so they are not used.
Only stage coordinates (public data) are sent to Commons. Results are cached per stage in sm_stage_photos.
"""

import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from walter.db import get_session
from walter.models import SmStage, SmStagePhotos

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

COMMONS = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "Walter/0.1 (personal hiking map, runs locally)"
MAX_DISTANCE_M = 500  # from the trail
PIECE_M = 4000  # one geosearch box per piece of the stage (a box returns at most 500 files)
MAX_PHOTOS = 24
CACHE_FOR = dt.timedelta(days=30)
THUMB_WIDTH = 800


class Photo(BaseModel):
    title: str
    thumb: str  # ~800 px wide
    large: str  # ~1600 px wide
    page: str  # Commons file page (credits, full resolution)
    lon: float
    lat: float
    author: str
    licence: str
    licence_url: str | None
    description: str
    position: float  # 0 = stage start, 1 = end
    distance_m: int  # from the trail


@router.get("/stages/{stage_id}/photos")
def stage_photos(stage_id: str, session: SessionDep) -> list[Photo]:
    if session.get(SmStage, stage_id) is None:
        raise HTTPException(404, "stage not found")
    cached = session.get(SmStagePhotos, stage_id)
    if cached and dt.datetime.now(dt.UTC) - cached.fetched_at < CACHE_FOR:
        return [Photo(**p) for p in cached.photos]
    try:
        photos = find_photos(session, stage_id)
    except OSError as e:  # Commons unreachable: serve stale cache if any, don't cache the failure
        if cached:
            return [Photo(**p) for p in cached.photos]
        raise HTTPException(502, f"Wikimedia Commons not reachable: {e}") from e
    session.merge(
        SmStagePhotos(
            stage_id=stage_id, fetched_at=dt.datetime.now(dt.UTC), photos=[p.model_dump() for p in photos]
        )
    )
    session.commit()
    return photos


def find_photos(session: Session, stage_id: str) -> list[Photo]:
    candidates: dict[str, dict] = {}
    for box in piece_boxes(session, stage_id):
        for page in geosearch(box):
            candidates.setdefault(page["title"], page)
    photos = [p for p in (to_photo(page) for page in candidates.values()) if p]
    if not photos:
        return []
    # Distance from the trail and position along it, in LV95 metres (one query per photo: few dozen)
    located = []
    for p in photos:
        distance, position = session.execute(
            text("""
                SELECT ST_Distance(geom, pt), ST_LineLocatePoint(geom, pt)
                FROM sm_stage, ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 2056) AS pt
                WHERE id = :id
            """),
            {"id": stage_id, "lon": p.lon, "lat": p.lat},
        ).one()
        if distance <= MAX_DISTANCE_M:
            located.append(
                p.model_copy(update={"distance_m": round(distance), "position": round(position, 4)})
            )
    return spread(sorted(located, key=lambda p: p.position))


def piece_boxes(session: Session, stage_id: str) -> list[tuple[float, float, float, float]]:
    """WGS84 boxes (north, west, south, east) around pieces of the stage, padded by MAX_DISTANCE_M."""
    length = session.scalar(select(func.ST_Length(SmStage.geom)).where(SmStage.id == stage_id))
    pieces = max(1, round(length / PIECE_M))
    rows = session.execute(
        text("""
            SELECT ST_YMax(b), ST_XMin(b), ST_YMin(b), ST_XMax(b)
            FROM sm_stage, generate_series(0, :n - 1) AS i,
                 ST_Transform(ST_Expand(ST_Envelope(
                     ST_LineSubstring(geom, i::float / :n, (i + 1)::float / :n)), :pad), 4326) AS b
            WHERE id = :id
        """),
        {"id": stage_id, "n": pieces, "pad": MAX_DISTANCE_M},
    )
    return [tuple(r) for r in rows]


def geosearch(box: tuple[float, float, float, float]) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "geosearch",
        "ggsnamespace": "6",
        "ggslimit": "100",
        "ggsbbox": "|".join(f"{v:.5f}" for v in box),
        "prop": "imageinfo|coordinates",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": str(THUMB_WIDTH),
        "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl|ImageDescription",
    }
    request = urllib.request.Request(
        f"{COMMONS}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response).get("query", {}).get("pages", [])


def to_photo(page: dict) -> Photo | None:
    """Only photographs (JPEG) with coordinates and a known licence."""
    info = (page.get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata", {})
    coords = page.get("coordinates")
    licence = plain(meta.get("LicenseShortName", {}).get("value", ""))
    if info.get("mime") != "image/jpeg" or not coords or not licence or "thumburl" not in info:
        return None
    thumb = info["thumburl"]
    return Photo(
        title=page["title"].removeprefix("File:").rsplit(".", 1)[0],
        thumb=thumb,
        large=thumb.replace(f"/{THUMB_WIDTH}px-", f"/{THUMB_WIDTH * 2}px-"),
        page=info["descriptionurl"],
        lon=coords[0]["lon"],
        lat=coords[0]["lat"],
        author=plain(meta.get("Artist", {}).get("value", "")) or "unknown",
        licence=licence,
        licence_url=meta.get("LicenseUrl", {}).get("value"),
        description=plain(meta.get("ImageDescription", {}).get("value", ""))[:200],
        position=0,
        distance_m=0,
    )


def plain(value: str) -> str:
    """Commons metadata is HTML: strip tags and entities."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def spread(photos: list[Photo]) -> list[Photo]:
    """At most MAX_PHOTOS, evenly spread along the stage, preferring the ones closest to the trail."""
    if len(photos) <= MAX_PHOTOS:
        return photos
    bins: dict[int, Photo] = {}
    for p in photos:
        b = min(int(p.position * MAX_PHOTOS), MAX_PHOTOS - 1)
        if b not in bins or p.distance_m < bins[b].distance_m:
            bins[b] = p
    return sorted(bins.values(), key=lambda p: p.position)
