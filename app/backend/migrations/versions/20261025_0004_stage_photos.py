"""cached Wikimedia Commons photos per stage

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sm_stage_photos",
        sa.Column(
            "stage_id", sa.String(), sa.ForeignKey("sm_stage.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("photos", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sm_stage_photos")
