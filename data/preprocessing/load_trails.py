"""Load the swissTLM3D hiking trails into PostGIS as a routing graph: trail_vertex, trail_edge.

Usage: .venv/bin/python data/preprocessing/load_trails.py   (or `just load-trails`)
Source: data/ref/swisstlm3d/swissTLM3D_TLM_STRASSE.shp (`just download-tlm`). Needs the stack running
(tables are created by the API's migrations). Replaces whatever was loaded before.

- Only segments on the official hiking network (WANDERWEGE set: Wanderweg / Bergwanderweg /
  Alpinwanderweg), ~67,000 km. TLM segments already end at junctions, so junctions are the shared
  end points (rounded to 10 cm).
- Ascent and descent come from the TLM heights (Z); the edge costs are walking times both ways, so
  routes prefer the gentler direction like a hiker would.
"""

import io
import os
import time
from pathlib import Path
from typing import LiteralString

import numpy as np
import psycopg
import pyogrio
import shapely

SRC = Path("data/ref/swisstlm3d/swissTLM3D_TLM_STRASSE.shp")
DB = os.environ.get("WALTER_DB", "postgresql://walter:walter@localhost:5432/walter")


def hiking_hours(km: np.ndarray, ascent: np.ndarray, descent: np.ndarray) -> np.ndarray:
    """DIN 33466: 4 km/h on the flat, 300 m/h up, 500 m/h down; the smaller part counts half.

    Same formula as app/backend/walter/trails.py.
    """
    flat = km / 4
    climb = ascent / 300 + descent / 500
    return np.maximum(flat, climb) + np.minimum(flat, climb) / 2


start = time.monotonic()
trails = pyogrio.read_dataframe(SRC, columns=["WANDERWEGE"], where="WANDERWEGE IS NOT NULL")
lines = trails.geometry.to_numpy()
coords, part = shapely.get_coordinates(lines, include_z=True, return_index=True)

# Junctions: end points shared by segments
first = np.r_[0, np.flatnonzero(np.diff(part)) + 1]
last = np.r_[first[1:] - 1, len(coords) - 1]
ends = np.round(np.vstack([coords[first, :2], coords[last, :2]]), 1)
nodes, node_of = np.unique(ends, axis=0, return_inverse=True)
source, target = node_of[: len(lines)], node_of[len(lines) :]

# Per segment: horizontal length, and height gained / lost walking source -> target
step = np.diff(coords, axis=0)
same = part[1:] == part[:-1]  # steps within one segment
length = np.bincount(part[1:][same], np.hypot(step[same, 0], step[same, 1]), len(lines))
dz = step[same, 2]
ascent = np.bincount(part[1:][same], np.clip(dz, 0, None), len(lines))
descent = np.bincount(part[1:][same], np.clip(-dz, 0, None), len(lines))
cost = hiking_hours(length / 1000, ascent, descent) * 3600
reverse_cost = hiking_hours(length / 1000, descent, ascent) * 3600


def copy_rows(cur: psycopg.Cursor, statement: LiteralString, rows: io.StringIO) -> None:
    rows.seek(0)
    with cur.copy(statement) as copy:
        while data := rows.read(1 << 20):
            copy.write(data)


vertex_rows = io.StringIO()
for i, (x, y) in enumerate(nodes):
    vertex_rows.write(f"{i + 1}\tSRID=2056;POINT({x:.1f} {y:.1f})\n")
edge_rows = io.StringIO()
wkb = shapely.to_wkb(lines, hex=True, output_dimension=3, include_srid=False)
for i, kind in enumerate(trails["WANDERWEGE"]):
    edge_rows.write(
        f"{i + 1}\t{source[i] + 1}\t{target[i] + 1}\t{kind}\t{length[i]:.1f}\t{ascent[i]:.1f}\t"
        f"{descent[i]:.1f}\t{cost[i]:.1f}\t{reverse_cost[i]:.1f}\tSRID=2056;{wkb[i]}\n"
    )

with psycopg.connect(DB) as conn, conn.cursor() as cur:
    cur.execute("TRUNCATE trail_edge, trail_vertex")
    copy_rows(cur, "COPY trail_vertex (id, geom) FROM STDIN", vertex_rows)
    copy_rows(
        cur,
        "COPY trail_edge (id, source, target, kind, length_m, ascent_m, descent_m, cost_s, reverse_cost_s,"
        " geom) FROM STDIN",
        edge_rows,
    )
    cur.execute("ANALYZE trail_vertex")
    cur.execute("ANALYZE trail_edge")

print(
    f"{len(lines):,} trail segments ({length.sum() / 1000:,.0f} km), {len(nodes):,} junctions loaded"
    f" into {DB.rsplit('@', 1)[-1]} in {time.monotonic() - start:.0f} s"
)
