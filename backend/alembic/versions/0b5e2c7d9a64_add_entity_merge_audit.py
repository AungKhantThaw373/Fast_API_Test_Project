"""add entity merge audit

Revision ID: 0b5e2c7d9a64
Revises: 3a9c7d1f6b42
Create Date: 2026-11-25 09:10:00.000000

One row per merge, holding the ids of everything that moved. A merge can then be
undone exactly instead of by name matching.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0b5e2c7d9a64"
down_revision: str | Sequence[str] | None = "3a9c7d1f6b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_merges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "story_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "moved",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", sa.String(length=20), nullable=False, server_default="human"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_entity_merges_source", "entity_merges", ["source_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_entity_merges_source", table_name="entity_merges")
    op.drop_table("entity_merges")
