import datetime as dt
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from walter.db import Base

# SchweizMobil (Wanderland) data, loaded by data/preprocessing/load_schweizmobil.py.
# Geometry in LV95 (EPSG:2056) so lengths are in metres; Martin reprojects for tiles.


class SmRoute(Base):
    __tablename__ = "sm_route"

    nr: Mapped[str] = mapped_column(primary_key=True)  # NrR, unique across levels
    name: Mapped[str]
    level: Mapped[str]  # national / regional / local / handicap (barrier-free)
    from_name: Mapped[str]
    to_name: Mapped[str]
    km: Mapped[int]
    ascent: Mapped[int]
    descent: Mapped[int]
    fitness: Mapped[str]  # easy / medium / difficult
    technique: Mapped[str]
    stage_count: Mapped[int]


class SmStage(Base):
    """One hike: a stage (Etappe) of a route. Published as vector tiles by Martin (all columns)."""

    __tablename__ = "sm_stage"

    id: Mapped[str] = mapped_column(primary_key=True)  # "{NrR}.{NrEtappe:02}", same as geo.admin featureId
    route_nr: Mapped[str] = mapped_column(ForeignKey("sm_route.nr", ondelete="CASCADE"), index=True)
    nr: Mapped[int]  # 0 = single-stage route
    level: Mapped[str]  # copied from the route for tile styling
    route_name: Mapped[str]
    from_name: Mapped[str]
    to_name: Mapped[str]
    km: Mapped[int]  # official distance
    ascent: Mapped[int]
    descent: Mapped[int]
    time_h: Mapped[float]  # from -> to
    time_back_h: Mapped[float]  # to -> from
    fitness: Mapped[str]
    technique: Mapped[str]
    geom: Mapped[WKBElement] = mapped_column(
        Geometry("LINESTRING", srid=2056, spatial_index=True), nullable=False
    )


class SmStageProfile(Base):
    """Elevation along the stage, from the swissTLM3D heights in the geometry, resampled every step_m."""

    __tablename__ = "sm_stage_profile"

    stage_id: Mapped[str] = mapped_column(ForeignKey("sm_stage.id", ondelete="CASCADE"), primary_key=True)
    step_m: Mapped[int]
    elevations: Mapped[list[int]] = mapped_column(JSONB)


class SmStageTravel(Base):
    """Public transport from the start station to the stage start and back, on one reference day.

    Computed offline with OpenTripPlanner by data/preprocessing/travel_times.py. One station for now
    (config.local.json `travel.from_station`); becomes a per-user setting with accounts.
    """

    __tablename__ = "sm_stage_travel"

    stage_id: Mapped[str] = mapped_column(ForeignKey("sm_stage.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[str] = mapped_column(primary_key=True)  # sat / sun
    date: Mapped[dt.date]  # reference date in the timetable
    # None when there is no connection (e.g. no bus that day, or none back after the hike)
    out_depart: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    out_arrive: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    out_transfers: Mapped[int | None]
    out_legs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    back_depart: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    back_arrive: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    back_transfers: Mapped[int | None]
    back_legs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)


class SmStagePhotos(Base):
    """Cached Wikimedia Commons photos along a stage (see walter/photos.py), refreshed after 30 days."""

    __tablename__ = "sm_stage_photos"

    stage_id: Mapped[str] = mapped_column(ForeignKey("sm_stage.id", ondelete="CASCADE"), primary_key=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    photos: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)


# MeteoSwiss local forecasts (open data), fetched by walter/weather.py when the cached run is an hour old


class MeteoPoint(Base):
    """A forecast point: weather station (kind 1), postcode centre (2) or mountain point (3)."""

    __tablename__ = "meteo_point"

    kind: Mapped[int] = mapped_column(primary_key=True)  # point_type_id: point_id is unique only per kind
    point_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    height_m: Mapped[int]
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=2056, spatial_index=True), nullable=False)


class MeteoForecast(Base):
    """One day's forecast at a point (only points nearest to a stage are kept). Local days."""

    __tablename__ = "meteo_forecast"

    kind: Mapped[int] = mapped_column(primary_key=True)
    point_id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(primary_key=True)
    sun_h: Mapped[float | None]
    precip_mm: Mapped[float | None]
    tmin: Mapped[float | None]  # at the point's height
    tmax: Mapped[float | None]
    zero_m: Mapped[int | None]  # lowest freezing level during the day (08-18)


class MeteoRun(Base):
    """The forecast run in meteo_forecast (one row), and when MeteoSwiss was last asked for a newer one."""

    __tablename__ = "meteo_run"

    run: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    checked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class MyHike(Base):
    """A hike detected in my Google Timeline (data/ingest/detect_hikes.py), loaded by load_hikes.py.

    Personal data: served only by the API (/api/me/hikes), never published as tiles (see martin.yaml).
    """

    __tablename__ = "my_hike"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str]  # hike / hike? (probably, a fast leg) / hike_abroad?
    km: Mapped[float]
    hours: Mapped[float]  # start to end, breaks included
    walking_hours: Mapped[float]
    gain_m: Mapped[int | None]
    top_m: Mapped[int | None]
    geom: Mapped[WKBElement] = mapped_column(
        Geometry("LINESTRING", srid=2056, spatial_index=True), nullable=False
    )


class Lift(Base):
    """A cable car, gondola, chairlift or lift open to the public, from swissTLM3D (load_lifts.py).

    The Z values are the cable's height at the stations and pylons, so 3D views can hang it in the air.
    """

    __tablename__ = "lift"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]  # cable_car / gondola / chairlift / lift
    name: Mapped[str | None]
    geom: Mapped[WKBElement] = mapped_column(
        Geometry("LINESTRINGZ", srid=2056, spatial_index=True), nullable=False
    )


# swissTLM3D hiking trails (Wanderweg / Bergwanderweg / Alpinwanderweg) as a routing graph, loaded by
# data/preprocessing/load_trails.py. Used by pgRouting to snap planned hikes to the trails.


class TrailVertex(Base):
    """A junction or end of the trail network."""

    __tablename__ = "trail_vertex"

    id: Mapped[int] = mapped_column(primary_key=True)
    geom: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=2056, spatial_index=True), nullable=False)


class TrailEdge(Base):
    """A trail segment between two junctions, with walking times in both directions."""

    __tablename__ = "trail_edge"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[int] = mapped_column(index=True)  # trail_vertex.id at the first point
    target: Mapped[int] = mapped_column(index=True)  # ... and at the last
    kind: Mapped[str]  # Wanderweg / Bergwanderweg / Alpinwanderweg
    length_m: Mapped[float]  # horizontal
    ascent_m: Mapped[float]  # walking source -> target
    descent_m: Mapped[float]
    cost_s: Mapped[float]  # walking time source -> target (see trails.hiking_hours)
    reverse_cost_s: Mapped[float]  # target -> source
    geom: Mapped[WKBElement] = mapped_column(
        Geometry("LINESTRINGZ", srid=2056, spatial_index=True), nullable=False
    )


class PlannedHike(Base):
    """A hike I drew on the map, snapped to the trails. Personal: served only by the API, never as tiles.

    The waypoints are what was clicked; the line is re-routed from them on every save.
    """

    __tablename__ = "planned_hike"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    waypoints: Mapped[list[list[float]]] = mapped_column(JSONB)  # [[lon, lat], ...] WGS84
    km: Mapped[float]
    ascent: Mapped[int]
    descent: Mapped[int]
    time_h: Mapped[float]
    geom: Mapped[WKBElement] = mapped_column(
        Geometry("LINESTRINGZ", srid=2056, spatial_index=True), nullable=False
    )
