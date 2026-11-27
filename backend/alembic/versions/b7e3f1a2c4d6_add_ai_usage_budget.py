"""Add AI usage duration and per-story monthly budget.

Revision ID: b7e3f1a2c4d6
Revises: a5b2d8c1e9f3
Create Date: 2026-11-25
"""

import sqlalchemy as sa

from alembic import op

revision = "b7e3f1a2c4d6"
down_revision = "a5b2d8c1e9f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_usage",
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "stories",
        sa.Column(
            "monthly_ai_budget",
            sa.Numeric(12, 4),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("stories", "monthly_ai_budget")
    op.drop_column("ai_usage", "duration_ms")
