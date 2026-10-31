# PostGIS + pgRouting (shortest paths on the swissTLM3D trail network, for drawing planned hikes)
FROM postgis/postgis:18-3.6
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-18-pgrouting \
    && rm -rf /var/lib/apt/lists/*
