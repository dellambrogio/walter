"""Load cable cars, gondolas, chairlifts and lifts from swissTLM3D into PostGIS (table lift).

Usage: .venv/bin/python data/preprocessing/load_lifts.py   (or `just load-lifts`)
Source: data/ref/swisstlm3d/swissTLM3D_TLM_UEBRIGE_BAHN.shp (`just download-tlm`). Needs the stack
running (the table is created by the API's migrations). Replaces whatever was loaded before.

- Only what hikers can ride: Luftseilbahn, Gondelbahn, Sesselbahn, Lift. Left out: material ropeways
  (Transportseil), ski lifts, conveyor belts, service-only lines (BETRIEBSBA) and ones out of service.
- Kept in 3D: the Z values are the cable's height at stations and pylons (10-50 m above the ground).
"""

import os
from pathlib import Path

import psycopg
import pyogrio
import shapely

SRC = Path("data/ref/swisstlm3d/swissTLM3D_TLM_UEBRIGE_BAHN.shp")
DB = os.environ.get("WALTER_DB", "postgresql://walter:walter@localhost:5432/walter")
KINDS = {"Luftseilbahn": "cable_car", "Gondelbahn": "gondola", "Sesselbahn": "chairlift", "Lift": "lift"}

lifts = pyogrio.read_dataframe(SRC, columns=["OBJEKTART", "NAME", "AUSSER_BET", "BETRIEBSBA"])
lifts = lifts[
    lifts.OBJEKTART.isin(list(KINDS)) & (lifts.AUSSER_BET == "Falsch") & (lifts.BETRIEBSBA == "Falsch")
]
names = [n if isinstance(n, str) else None for n in lifts.NAME]
rows = [
    (KINDS[kind], name, shapely.to_wkb(geom, hex=True))
    for kind, name, geom in zip(lifts.OBJEKTART, names, lifts.geometry, strict=True)
]

with psycopg.connect(DB) as conn, conn.cursor() as cur:
    cur.execute("TRUNCATE lift RESTART IDENTITY")
    cur.executemany(
        "INSERT INTO lift (kind, name, geom) VALUES (%s, %s, ST_SetSRID(ST_Force3D(%s::geometry), 2056))",
        rows,
    )

counts = ", ".join(f"{n} {kind}" for kind, n in lifts.OBJEKTART.map(KINDS).value_counts().items())
print(f"{len(rows)} lifts ({counts}) loaded into {DB.rsplit('@', 1)[-1]}")
