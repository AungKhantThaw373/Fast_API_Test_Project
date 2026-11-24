"""merge proposals and auto-accept rules

Revision ID: 6d1f4b8c2e09
Revises: 0b5e2c7d9a64
Create Date: 2026-11-25 14:20:00.000000

Two additive tables: ``merge_proposals`` keeps a dismissal sticky so similar
names are not proposed on every inbox load, and ``auto_accept_rules`` stores the
per-story thresholds the review inbox previews and applies.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "6d1f4b8c2e09"
down_revision: str | Sequence[str] | None = "0b5e2c7d9a64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "merge_proposals",
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
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_id", "target_id", name="uq_merge_proposal_pair"),
    )
    op.create_index(
        "ix_merge_proposals_story_status", "merge_proposals", ["story_id", "status"], unique=False
    )

    op.create_table(
        "auto_accept_rules",
        sa.Column(
            "story_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("require_quote", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_confidence", sa.Integer(), nullable=False, server_default="80"),
        sa.Column(
            "require_existing_entity", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("block_conflicts", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_per_chapter", sa.Integer(), nullable=False, server_default="20"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("auto_accept_rules")
    op.drop_index("ix_merge_proposals_story_status", table_name="merge_proposals")
    op.drop_table("merge_proposals")
