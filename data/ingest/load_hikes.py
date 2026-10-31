"""Load my detected hikes into PostGIS (table my_hike), for the "My hikes" map layer.

Usage: .venv/bin/python data/ingest/load_hikes.py [data/processed/walks.geojson]   (or `just load-hikes`)
Input: the output of detect_hikes.py. Needs the stack running (the table is created by the API's
migrations). Replaces whatever was loaded before. Personal data: stays in the local database.
"""

import json
import os
import sys
from pathlib import Path

import psycopg

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "data/processed/walks.geojson")
DB = os.environ.get("WALTER_DB", "postgresql://walter:walter@localhost:5432/walter")
# hike: detected with confidence; hike?: probably (a leg was too fast for walking); hike_abroad?: no DEM
KINDS = {"hike", "hike?", "hike_abroad?"}

features = [f for f in json.loads(SRC.read_text())["features"] if f["properties"]["kind"] in KINDS]
rows = [
    (
        p["date"],
        p["start"],
        p["end"],
        p["kind"],
        p["km"],
        p["hours"],
        p["walking_hours"],
        p["gain_m"],
        p["top_m"],
        json.dumps(f["geometry"]),
    )
    for f in features
    for p in [f["properties"]]
]

with psycopg.connect(DB) as conn, conn.cursor() as cur:
    cur.execute("TRUNCATE my_hike RESTART IDENTITY")
    cur.executemany(
        'INSERT INTO my_hike (date, start, "end", kind, km, hours, walking_hours, gain_m, top_m, geom)'
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
        " ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 2056))",
        rows,
    )

print(f"{len(rows)} hikes loaded into {DB.rsplit('@', 1)[-1]}")
