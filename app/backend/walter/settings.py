import json
from functools import cache
from pathlib import Path
from typing import NamedTuple

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WALTER_")

    database_url: str = "postgresql+psycopg://walter:walter@localhost:5432/walter"
    cors_origins: list[str] = ["http://localhost:5173"]
    # Repo-root config.local.json (git-ignored), mounted read-only by docker compose
    config_file: Path = Path("/config/config.local.json")


settings = Settings()


class Station(NamedTuple):
    name: str
    lon: float
    lat: float


@cache
def from_station() -> Station | None:
    """Where trips start and end (config.local.json `travel.from_station`), or None if not configured.

    Single station for now; becomes a user setting with accounts (W0 auth).
    """
    if not settings.config_file.is_file():
        return None
    config = json.loads(settings.config_file.read_text(encoding="utf-8"))
    try:
        station = config["travel"]["from_station"]
        return Station(str(station["name"]), float(station["lon"]), float(station["lat"]))
    except (KeyError, TypeError, ValueError):
        return None
