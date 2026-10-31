"""public transport travel times per stage

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sm_stage_travel",
        sa.Column(
            "stage_id", sa.String(), sa.ForeignKey("sm_stage.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("day", sa.String(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("out_depart", sa.DateTime(timezone=True)),
        sa.Column("out_arrive", sa.DateTime(timezone=True)),
        sa.Column("out_transfers", sa.Integer()),
        sa.Column("out_legs", postgresql.JSONB()),
        sa.Column("back_depart", sa.DateTime(timezone=True)),
        sa.Column("back_arrive", sa.DateTime(timezone=True)),
        sa.Column("back_transfers", sa.Integer()),
        sa.Column("back_legs", postgresql.JSONB()),
    )


def downgrade() -> None:
    op.drop_table("sm_stage_travel")
