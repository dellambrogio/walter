"""Import swisstopo app tour exports (GPX) into one GeoJSON file.

Usage: python3 data/ingest/swisstopo_tours.py [data/raw/swisstopo] [data/processed/swisstopo_tours.geojson]

Each tour becomes a LineString feature (lon, lat, ele) with name, creation
date, distance and ascent/descent. These are planned tours: the date is when
the tour was created in the app, not when it was walked.
"""

import json
import math
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

NS = {"g": "http://www.topografix.com/GPX/1/1"}


def haversine_m(a: Sequence[float], b: Sequence[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def parse_tour(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    meta = root.find("g:metadata", NS)
    name = meta.findtext("g:name", default="", namespaces=NS) if meta is not None else ""
    created = meta.findtext("g:time", default=None, namespaces=NS) if meta is not None else None

    coords: list[list[float]] = []
    for pt in root.iterfind(".//g:trkpt", NS):
        lon, lat = pt.get("lon"), pt.get("lat")
        if lon is None or lat is None:  # invalid GPX point
            continue
        c = [round(float(lon), 7), round(float(lat), 7)]
        ele = pt.findtext("g:ele", namespaces=NS)
        if ele is not None:
            c.append(round(float(ele), 1))
        if not coords or coords[-1][:2] != c[:2]:
            coords.append(c)

    dist = sum(haversine_m(a, b) for a, b in pairwise(coords))
    eles = [c[2] for c in coords if len(c) > 2]
    up = sum(max(0, b - a) for a, b in pairwise(eles))
    down = sum(max(0, a - b) for a, b in pairwise(eles))

    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "source": "swisstopo-app",
            "file": path.name,
            "name": name,
            "created": created,
            "distance_km": round(dist / 1000, 2),
            "ascent_m": round(up),
            "descent_m": round(down),
            "points": len(coords),
        },
    }


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/swisstopo")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/processed/swisstopo_tours.geojson")
    features = [parse_tour(p) for p in sorted(src.glob("*.gpx"))]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False))
    for f in features:
        p = f["properties"]
        print(
            f"{p['file']}: {p['name']!r} {p['distance_km']} km, +{p['ascent_m']} / -{p['descent_m']} m, "
            f"{p['points']} pts, created {p['created']}"
        )
    print(f"{len(features)} tours -> {out}")


if __name__ == "__main__":
    main()
