"""Detect hikes in a Google Timeline on-device export.

Usage: .venv/bin/python data/ingest/detect_hikes.py [data/raw/Timeline_full.json]

Writes data/processed/walks.geojson (all merged walks with stats and a `kind`:
hike / long_walk / walk) and prints a per-year summary.
"""

import json
import math
import sys
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, NotRequired, TypedDict

import rasterio
from pyproj import Transformer

TIMELINE = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/Timeline_full.json")
DEM = Path("data/ref/swissaltiregio_80m.tif")
OUT = Path("data/processed/walks.geojson")

WALK_TYPES = {"WALKING", "HIKING"}
MAX_BREAK = timedelta(minutes=90)  # summit stop, lunch at a hut
MAX_RIDE_M = 1500  # a longer vehicle leg splits two walks

# hike rules
MIN_KM = 5
MIN_HOURS = 1.5
MIN_GAIN_M = 300
MIN_TOP_M = 1000
MAX_KMH = 6.5

LatLng = tuple[float, float]
TimedPoint = tuple[datetime, LatLng]


class Activity(TypedDict):
    start: datetime
    end: datetime
    type: str
    dist: float
    a: LatLng | None
    b: LatLng | None


class WalkStats(TypedDict):
    date: str
    start: str
    end: str
    km: float
    hours: float
    walking_hours: float
    kmh: float | None
    gain_m: int | None
    top_m: int | None
    low_m: int | None
    in_ch: bool
    legs: int
    points: int
    kind: NotRequired[str]


def latlng(s: str) -> LatLng:
    lat, lng = s.replace("°", "").split(",")
    return float(lat), float(lng)


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def haversine_m(a: LatLng, b: LatLng) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def load(path: Path) -> tuple[list[TimedPoint], list[Activity]]:
    segs = json.loads(path.read_text())["semanticSegments"]
    points: dict[str, LatLng] = {}
    for s in segs:
        for p in s.get("timelinePath", []):
            points[p["time"]] = latlng(p["point"])
    pts = sorted((ts(t), ll) for t, ll in points.items())
    acts: list[Activity] = []
    for s in segs:
        a = s.get("activity")
        if not a:
            continue
        acts.append(
            {
                "start": ts(s["startTime"]),
                "end": ts(s["endTime"]),
                "type": a.get("topCandidate", {}).get("type", "UNKNOWN"),
                "dist": float(a.get("distanceMeters", 0)),
                "a": latlng(a["start"]["latLng"]) if "start" in a else None,
                "b": latlng(a["end"]["latLng"]) if "end" in a else None,
            }
        )
    acts.sort(key=lambda a: a["start"])
    return pts, acts


def merge_walks(acts: list[Activity]) -> list[list[Activity]]:
    walks: list[list[Activity]] = []
    cur: list[Activity] | None = None
    ride = 0.0
    for a in acts:
        if a["type"] in WALK_TYPES:
            if (
                cur
                and a["start"] - cur[-1]["end"] <= MAX_BREAK
                and ride <= MAX_RIDE_M
                and a["start"].date() == cur[-1]["end"].date()
            ):
                cur.append(a)
            else:
                if cur:
                    walks.append(cur)
                cur = [a]
            ride = 0.0
        elif cur:
            ride += a["dist"]
    if cur:
        walks.append(cur)
    return walks


class Elevation:
    def __init__(self, path: Path) -> None:
        self.src = rasterio.open(path)
        self.band = self.src.read(1)
        self.to_lv95 = Transformer.from_crs(4326, 2056, always_xy=True)

    def __call__(self, coords: Sequence[LatLng]) -> list[float | None]:
        if not coords:
            return []
        lons, lats = zip(*[(c[1], c[0]) for c in coords], strict=True)
        xs, ys = self.to_lv95.transform(lons, lats)
        out: list[float | None] = []
        for x, y in zip(xs, ys, strict=True):
            r, c = self.src.index(x, y)
            if 0 <= r < self.band.shape[0] and 0 <= c < self.band.shape[1]:
                v = float(self.band[r, c])
                out.append(v if v < 1e30 and v > 0 else None)
            else:
                out.append(None)
        return out


def walk_stats(
    chain: list[Activity], pts: list[TimedPoint], pt_times: list[datetime], elev: Elevation
) -> tuple[WalkStats, list[LatLng]]:
    start, end = chain[0]["start"], chain[-1]["end"]
    i, j = bisect_left(pt_times, start), bisect_right(pt_times, end)
    coords = [ll for _, ll in pts[i:j]]
    if chain[0]["a"]:
        coords.insert(0, chain[0]["a"])
    if chain[-1]["b"]:
        coords.append(chain[-1]["b"])
    path_m = sum(haversine_m(a, b) for a, b in pairwise(coords))
    dist_m = max(sum(a["dist"] for a in chain), path_m)
    walking_h = sum((a["end"] - a["start"]).total_seconds() for a in chain) / 3600
    eles = elev(coords)
    known = [e for e in eles if e is not None]
    gain = sum(max(0, b - a) for a, b in pairwise(known))
    return {
        "date": start.date().isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "km": round(dist_m / 1000, 1),
        "hours": round((end - start).total_seconds() / 3600, 2),
        "walking_hours": round(walking_h, 2),
        "kmh": round(dist_m / 1000 / walking_h, 1) if walking_h else None,
        "gain_m": round(gain) if known else None,
        "top_m": round(max(known)) if known else None,
        "low_m": round(min(known)) if known else None,
        "in_ch": len(known) >= 0.5 * len(eles) if eles else False,
        "legs": len(chain),
        "points": len(coords),
    }, coords


def classify(s: WalkStats) -> str:
    if s["km"] < MIN_KM or s["hours"] < MIN_HOURS:
        return "walk"
    if s["kmh"] and s["kmh"] > MAX_KMH:
        # too fast for walking: likely a vehicle/cable car leg labelled as walking (or a bike ride)
        climbs = s["in_ch"] and ((s["gain_m"] or 0) >= MIN_GAIN_M or (s["top_m"] or 0) >= MIN_TOP_M)
        return "hike?" if climbs else "walk"
    if s["in_ch"]:
        if (s["gain_m"] or 0) >= MIN_GAIN_M or (s["top_m"] or 0) >= MIN_TOP_M:
            return "hike"
        return "long_walk"
    return "hike_abroad?" if s["km"] >= 10 else "long_walk"


def main() -> None:
    pts, acts = load(TIMELINE)
    pt_times = [t for t, _ in pts]
    elev = Elevation(DEM)
    features: list[dict[str, Any]] = []
    for chain in merge_walks(acts):
        s, coords = walk_stats(chain, pts, pt_times, elev)
        if s["km"] < 2:
            continue
        s["kind"] = classify(s)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(c[1], 6), round(c[0], 6)] for c in coords],
                },
                "properties": s,
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}))

    from collections import Counter

    kinds = Counter(f["properties"]["kind"] for f in features)
    print("walks >= 2 km:", len(features), dict(kinds))
    per_year = Counter(f["properties"]["date"][:4] for f in features if f["properties"]["kind"] == "hike")
    print("hikes per year:", dict(sorted(per_year.items())))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
