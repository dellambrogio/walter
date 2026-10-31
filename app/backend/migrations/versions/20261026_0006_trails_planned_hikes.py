"""trail network for routing (pgRouting) and planned hikes

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgrouting")
    op.create_table(
        "trail_vertex",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("geom", geoalchemy2.Geometry("POINT", srid=2056, spatial_index=False), nullable=False),
    )
    op.create_index("idx_trail_vertex_geom", "trail_vertex", ["geom"], postgresql_using="gist")
    op.create_table(
        "trail_edge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.Integer(), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("length_m", sa.Float(), nullable=False),
        sa.Column("ascent_m", sa.Float(), nullable=False),
        sa.Column("descent_m", sa.Float(), nullable=False),
        sa.Column("cost_s", sa.Float(), nullable=False),
        sa.Column("reverse_cost_s", sa.Float(), nullable=False),
        sa.Column(
            "geom", geoalchemy2.Geometry("LINESTRINGZ", srid=2056, spatial_index=False), nullable=False
        ),
    )
    op.create_index("ix_trail_edge_source", "trail_edge", ["source"])
    op.create_index("ix_trail_edge_target", "trail_edge", ["target"])
    op.create_index("idx_trail_edge_geom", "trail_edge", ["geom"], postgresql_using="gist")
    op.create_table(
        "planned_hike",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("waypoints", postgresql.JSONB(), nullable=False),
        sa.Column("km", sa.Float(), nullable=False),
        sa.Column("ascent", sa.Integer(), nullable=False),
        sa.Column("descent", sa.Integer(), nullable=False),
        sa.Column("time_h", sa.Float(), nullable=False),
        sa.Column(
            "geom", geoalchemy2.Geometry("LINESTRINGZ", srid=2056, spatial_index=False), nullable=False
        ),
    )
    op.create_index("idx_planned_hike_geom", "planned_hike", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("planned_hike")
    op.drop_table("trail_edge")
    op.drop_table("trail_vertex")
    op.execute("DROP EXTENSION IF EXISTS pgrouting")
