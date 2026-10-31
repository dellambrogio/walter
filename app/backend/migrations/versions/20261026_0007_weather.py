"""MeteoSwiss local forecasts per forecast point

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meteo_point",
        sa.Column("kind", sa.Integer(), primary_key=True),
        sa.Column("point_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("height_m", sa.Integer(), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry("POINT", srid=2056, spatial_index=False), nullable=False),
    )
    op.create_index("idx_meteo_point_geom", "meteo_point", ["geom"], postgresql_using="gist")
    op.create_table(
        "meteo_forecast",
        sa.Column("kind", sa.Integer(), primary_key=True),
        sa.Column("point_id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("sun_h", sa.Float()),
        sa.Column("precip_mm", sa.Float()),
        sa.Column("tmin", sa.Float()),
        sa.Column("tmax", sa.Float()),
        sa.Column("zero_m", sa.Integer()),
    )
    op.create_table(
        "meteo_run",
        sa.Column("run", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("meteo_run")
    op.drop_table("meteo_forecast")
    op.drop_table("meteo_point")
