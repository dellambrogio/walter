# Walter tasks. `just` lists them.

dev := "docker compose -f app/infra/docker-compose.yml"
prod := dev + " -f app/infra/docker-compose.prod.yml"

default:
    @just --list

# Dev stack with hot reload, open http://localhost:5173 when ready
preview:
    {{dev}} up -d --build --wait
    @just _wait-for http://localhost:5173 180
    xdg-open http://localhost:5173 >/dev/null 2>&1 &

# Production-style stack on this machine (built bundle via nginx), http://localhost:8080
deploy:
    {{prod}} up -d --build --wait --remove-orphans
    @just _wait-for http://localhost:8080/api/health 60
    @echo "Deployed: http://localhost:8080"

# Stop the stack (database is kept; `just nuke` deletes it)
down:
    {{dev}} down

# Stop the stack and delete the database volume
nuke:
    {{dev}} down -v

# Container status
ps:
    {{dev}} ps

# Follow logs, e.g. `just logs api`
logs *services:
    {{dev}} logs -f {{services}}

# Backend tests (needs the stack running)
test:
    {{dev}} exec api pytest -q

# Lint backend, data scripts and frontend
lint:
    {{dev}} exec api ruff check .
    {{dev}} exec api ruff format --check .
    .venv/bin/ruff check data config.py
    .venv/bin/ruff format --check data config.py
    {{dev}} exec web sh -c "npx tsc -b && npm run lint"

# Type-check Python with pyrefly: backend (in the API container) and data scripts (project .venv)
typecheck:
    {{dev}} exec api pyrefly check
    .venv/bin/pyrefly check

# New Alembic migration, e.g. `just migration "add stages"`
migration message:
    {{dev}} exec api alembic revision --autogenerate -m "{{message}}"

# Load SchweizMobil routes + stages into PostGIS (needs the stack running and data/ref/wanderland_2056.gpkg)
load-schweizmobil: migrate
    .venv/bin/python data/preprocessing/load_schweizmobil.py

# Download the swissTLM3D roads/paths and lifts (~530 MB; only TLM_STRASSE and TLM_UEBRIGE_BAHN from the national zip)
download-tlm:
    .venv/bin/python data/preprocessing/download_tlm_strassen.py

# Load the swissTLM3D hiking trails as a routing graph, for drawing planned hikes (needs `just download-tlm`)
load-trails: migrate
    .venv/bin/python data/preprocessing/load_trails.py

# Load cable cars, gondolas, chairlifts and lifts for the "Lifts" layer (needs `just download-tlm`)
load-lifts: migrate
    .venv/bin/python data/preprocessing/load_lifts.py

# Load my detected hikes (data/processed/walks.geojson from detect_hikes.py) for the "My hikes" layer
load-hikes: migrate
    .venv/bin/python data/ingest/load_hikes.py

# Trim the Swiss GTFS feed and build the OpenTripPlanner graph (inputs: see app/infra/otp/README.md)
otp-build:
    python3 -I data/preprocessing/trim_gtfs.py
    cp app/infra/otp/build-config.json app/infra/otp/router-config.json data/ref/otp/graph/
    {{dev}} --profile otp run --rm otp --build --save

# Serve the OTP graph on http://localhost:8090
otp:
    {{dev}} --profile otp up -d otp
    @just _wait-for http://localhost:8090/otp/ 300

# Stop OTP (it holds ~6 GB of RAM)
otp-stop:
    {{dev}} --profile otp stop otp

# Public transport times home <-> every stage (needs `just otp`); optional stage ids, e.g. `just travel-times 1.05`
travel-times *stages: migrate
    .venv/bin/python data/preprocessing/travel_times.py {{stages}}

# Apply pending migrations
migrate:
    {{dev}} exec api alembic upgrade head

_wait-for url timeout:
    #!/usr/bin/env bash
    for _ in $(seq {{timeout}}); do
        curl -fsS -o /dev/null "{{url}}" && exit 0
        sleep 1
    done
    echo "timed out waiting for {{url}}" >&2
    exit 1
