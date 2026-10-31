"""schweizmobil routes and stages

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sm_route",
        sa.Column("nr", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("from_name", sa.String(), nullable=False),
        sa.Column("to_name", sa.String(), nullable=False),
        sa.Column("km", sa.Integer(), nullable=False),
        sa.Column("ascent", sa.Integer(), nullable=False),
        sa.Column("descent", sa.Integer(), nullable=False),
        sa.Column("fitness", sa.String(), nullable=False),
        sa.Column("technique", sa.String(), nullable=False),
        sa.Column("stage_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "sm_stage",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("route_nr", sa.String(), sa.ForeignKey("sm_route.nr", ondelete="CASCADE"), nullable=False),
        sa.Column("nr", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("route_name", sa.String(), nullable=False),
        sa.Column("from_name", sa.String(), nullable=False),
        sa.Column("to_name", sa.String(), nullable=False),
        sa.Column("km", sa.Integer(), nullable=False),
        sa.Column("ascent", sa.Integer(), nullable=False),
        sa.Column("descent", sa.Integer(), nullable=False),
        sa.Column("time_h", sa.Float(), nullable=False),
        sa.Column("time_back_h", sa.Float(), nullable=False),
        sa.Column("fitness", sa.String(), nullable=False),
        sa.Column("technique", sa.String(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry("LINESTRING", srid=2056, spatial_index=False),
            nullable=False,
        ),
    )
    op.create_index("ix_sm_stage_route_nr", "sm_stage", ["route_nr"])
    op.create_index("idx_sm_stage_geom", "sm_stage", ["geom"], postgresql_using="gist")
    op.create_table(
        "sm_stage_profile",
        sa.Column(
            "stage_id", sa.String(), sa.ForeignKey("sm_stage.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("step_m", sa.Integer(), nullable=False),
        sa.Column("elevations", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sm_stage_profile")
    op.drop_table("sm_stage")
    op.drop_table("sm_route")
