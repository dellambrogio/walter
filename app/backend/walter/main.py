from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from walter import connections, hikes, lifts, photos, planned, stages, trails, weather
from walter.db import get_session
from walter.settings import settings

app = FastAPI(title="Walter API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)  # the stage list is ~340 kB of JSON
app.include_router(stages.router)
app.include_router(photos.router)
app.include_router(hikes.router)
app.include_router(trails.router)
app.include_router(planned.router)
app.include_router(weather.router)
app.include_router(lifts.router)
app.include_router(connections.router)

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/api/health")
def health(session: SessionDep) -> dict[str, str]:
    postgis = session.execute(text("SELECT postgis_lib_version()")).scalar_one()
    return {"status": "ok", "postgis": postgis}
