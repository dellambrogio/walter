"""cable cars, gondolas, chairlifts and lifts (swissTLM3D)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lift",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String()),
        sa.Column(
            "geom", geoalchemy2.Geometry("LINESTRINGZ", srid=2056, spatial_index=False), nullable=False
        ),
    )
    op.create_index("idx_lift_geom", "lift", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("lift")
