"""Load SchweizMobil (Wanderland) routes and stages into PostGIS: sm_route, sm_stage, sm_stage_profile.

Usage: .venv/bin/python data/preprocessing/load_schweizmobil.py   (or `just load-schweizmobil`)
Source: data/ref/wanderland_2056.gpkg (geo.admin STAC, ch.astra.wanderland). Needs the stack running
(tables are created by the API's migrations). Replaces whatever was loaded before.

- Barrier-free routes (Typ_TR = handicap) are kept; the app hides them by default.
- Routes 28, 42, 73 come as Hinweg + Rückweg variants that differ by < 100 m: only the Hinweg is kept.
- Stage geometry is MultiLineString Z with parts in walking order; they are joined into one LineString.
  The Z values (swissTLM3D heights) give the elevation profile, resampled every PROFILE_STEP_M.
"""

import json
import os
from itertools import pairwise
from pathlib import Path
from typing import cast

import geopandas as gpd
import numpy as np
import psycopg
import shapely
from shapely.geometry.base import BaseGeometry

SRC = Path("data/ref/wanderland_2056.gpkg")
DB = os.environ.get("WALTER_DB", "postgresql://walter:walter@localhost:5432/walter")
PROFILE_STEP_M = 25


def join_parts(geom: BaseGeometry) -> np.ndarray:
    """Concatenate the parts of a MultiLineString Z (already in order) into one XYZ coordinate array."""
    parts = [np.asarray(p.coords) for p in getattr(geom, "geoms", [geom])]
    # Drop a part's first point when it repeats the previous part's last one
    coords = [parts[0]] + [
        p[1:] if np.allclose(p[0, :2], prev[-1, :2], atol=2) else p for prev, p in pairwise(parts)
    ]
    return np.concatenate(coords)


def profile(xyz: np.ndarray) -> list[int]:
    dist = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xyz[:, :2], axis=0).T))])
    samples = np.arange(0, dist[-1], PROFILE_STEP_M)
    return [round(z) for z in np.interp(np.append(samples, dist[-1]), dist, xyz[:, 2])]


routes = gpd.read_file(SRC, layer="Route", ignore_geometry=True)
routes = routes[routes["Abwicklung"] != "Rückweg"]
stages = gpd.read_file(SRC, layer="Etappe")
stages = stages[stages["Abwicklung"] != "Rückweg"]
assert routes["NrR"].is_unique and not stages.duplicated(["NrR", "NrEtappe"]).any()
routes = routes.set_index("NrR")
stage_count = stages.groupby("NrR").size().to_dict()

route_rows = [
    (
        nr,
        r.NameR,
        r.Typ_TR,
        r.AOrt,
        r.ZOrt,
        r.LaengeR,
        r.HoeheAufR,
        r.HoeheAbR,
        r.KonditionR,
        r.TechnikR,
        stage_count[nr],
    )
    for nr, r in routes.iterrows()
]
stage_rows, profile_rows = [], []
for s in stages.itertuples():
    route = routes.loc[s.NrR]
    stage_id = f"{s.NrR}.{s.NrEtappe:02d}"
    xyz = join_parts(cast(BaseGeometry, s.geometry))  # itertuples() rows carry no column types
    line = shapely.LineString(xyz[:, :2])
    stage_rows.append(
        (
            stage_id,
            s.NrR,
            s.NrEtappe,
            route.Typ_TR,
            route.NameR,
            s.NameS,
            s.NameZ,
            s.DistanzE,
            s.HoeheAufE,
            s.HoeheAbE,
            s.ZeitStZiE,
            s.ZeitZiStE,
            s.KonditionE,
            s.TechnikE,
            line.wkb,
        )
    )
    profile_rows.append((stage_id, PROFILE_STEP_M, json.dumps(profile(xyz))))

with psycopg.connect(DB) as conn, conn.cursor() as cur:
    cur.execute("TRUNCATE sm_route CASCADE")
    cur.executemany("INSERT INTO sm_route VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", route_rows)
    cur.executemany(
        "INSERT INTO sm_stage VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
        " ST_SetSRID(ST_GeomFromWKB(%s), 2056))",
        stage_rows,
    )
    cur.executemany("INSERT INTO sm_stage_profile VALUES (%s, %s, %s)", profile_rows)

print(f"{len(route_rows)} routes, {len(stage_rows)} stages loaded into {DB.rsplit('@', 1)[-1]}")
