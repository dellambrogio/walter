"""Export SchweizMobil (Wanderland) hiking routes as simplified WGS84 GeoJSON.

Usage: .venv/bin/python data/preprocessing/schweizmobil_routes.py
Source: data/ref/wanderland_2056.gpkg (geo.admin STAC, ch.astra.wanderland)
"""

from pathlib import Path

import geopandas as gpd

SRC = Path("data/ref/wanderland_2056.gpkg")
OUT = Path("data/processed/schweizmobil_routes.geojson")
TOLERANCE_M = 15

routes = gpd.read_file(SRC, layer="Route")
routes = routes[routes["Typ_TR"].isin(["national", "regional", "local"])]
routes["geometry"] = routes.geometry.simplify(TOLERANCE_M)
routes = routes.rename(
    columns={
        "NrR": "nr",
        "NameR": "name",
        "Typ_TR": "level",
        "LaengeR": "km",
        "HoeheAufR": "ascent_m",
        "HoeheAbR": "descent_m",
        "AOrt": "from",
        "ZOrt": "to",
        "KonditionR": "fitness",
        "TechnikR": "technique",
    }
)[["nr", "name", "level", "km", "ascent_m", "descent_m", "from", "to", "fitness", "technique", "geometry"]]
routes = routes.to_crs(4326)
OUT.parent.mkdir(parents=True, exist_ok=True)
routes.to_file(OUT, driver="GeoJSON", COORDINATE_PRECISION=5)
print(routes["level"].value_counts().to_dict(), f"-> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
