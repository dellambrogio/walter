# Walter app

Local stack (docker compose): PostGIS, FastAPI API, Martin tile server, React/Vite dev server.
All ports are bound to `127.0.0.1` only.

| Service | URL | Folder |
|---|---|---|
| web (React + MapLibre) | http://localhost:5173 | `frontend/` |
| api (FastAPI) | http://localhost:8000/api/health, docs at http://localhost:8000/docs | `backend/` |
| tiles (Martin) | http://localhost:3000/catalog | `infra/martin.yaml` |
| db (PostgreSQL 18 + PostGIS 3.6 + pgRouting 4.0, `infra/db/Dockerfile`) | `localhost:5432`, user/password/db `walter` (dev only) | |

Tasks are in the repo-root `justfile` ([just](https://just.systems)); run `just` from the repo root to list them.

```bash
just preview          # dev stack (hot reload), opens http://localhost:5173 when ready
just deploy           # production-style stack on this machine: built bundle via nginx at http://localhost:8080
just ps               # status
just logs api         # follow logs (no argument: all services)
just down             # stop (data is kept in the db-data volume)
just nuke             # stop and delete the database
```

The API reads the start station (`travel.from_station`) from the repo-root `config.local.json` (mounted
read-only) for the distance-from-station filter and its labels; without it the filter is hidden.

In dev, backend and frontend code are mounted into the containers and reload on save. `deploy` uses
`infra/docker-compose.prod.yml` on top: no source mounts, no `--reload`, frontend built with
`frontend/Dockerfile`. It is the same compose project and database, so `preview` and `deploy` replace
each other's api/web containers. The API runs migrations on start in both.

**Public transport travel times** (one-off, see `infra/otp/README.md`): `just otp-build` (once per
timetable), `just otp`, `just travel-times`, then `just otp-stop` (OTP holds ~6 GB of RAM).

**Checks** (dev stack running)
```bash
just test             # pytest
just lint             # ruff (backend + data scripts), tsc, oxlint
just typecheck        # pyrefly: backend in the API container, data scripts in .venv
```

All Python is fully annotated (ruff `ANN` enforces it) and checked by pyrefly: the backend with
`[tool.pyrefly]` in `backend/pyproject.toml`, the data scripts with the repo-root `pyrefly.toml`. The pyrefly
VS Code extension picks up both configs.

**Personal data and tiles:** Martin publishes only the tables listed in `infra/martin.yaml` (an explicit
allow-list, currently `sm_stage`). Personal tables such as `my_hike` are served only by the API
(`/api/me/hikes`); a test fails if the tile server ever publishes anything else.

**New migration**
```bash
just migration "add stages"   # autogenerate
just migrate                  # apply (also runs on every API container start)
```
