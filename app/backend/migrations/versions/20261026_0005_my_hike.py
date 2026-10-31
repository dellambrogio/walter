"""my hikes detected in the Google Timeline

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "my_hike",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("km", sa.Float(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("walking_hours", sa.Float(), nullable=False),
        sa.Column("gain_m", sa.Integer()),
        sa.Column("top_m", sa.Integer()),
        sa.Column("geom", geoalchemy2.Geometry("LINESTRING", srid=2056, spatial_index=False), nullable=False),
    )
    op.create_index("ix_my_hike_date", "my_hike", ["date"])
    op.create_index("idx_my_hike_geom", "my_hike", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("my_hike")
