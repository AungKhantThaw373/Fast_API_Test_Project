"""add continuity scan failure counter

Revision ID: c9d4e7f1a2b3
Revises: b7e3f1a2c4d6
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d4e7f1a2b3"
down_revision: str | None = "b7e3f1a2c4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "continuity_scans",
        sa.Column("scenes_failed", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("continuity_scans", "scenes_failed")
