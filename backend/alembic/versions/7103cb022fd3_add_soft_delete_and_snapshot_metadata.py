"""add soft delete and snapshot metadata

Revision ID: 7103cb022fd3
Revises: 1e10de6c20dc
Create Date: 2026-11-24 18:10:00.000000

Phase 1: destructive actions become recoverable (trash), and version history
gets enough metadata to apply a retention policy and to diff cheaply.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7103cb022fd3"
down_revision: str | Sequence[str] | None = "1e10de6c20dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Soft delete ------------------------------------------------------
    op.add_column("stories", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("story_chapters", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_stories_owner_deleted", "stories", ["owner_id", "deleted_at"])
    op.create_index("ix_chapters_story_deleted", "story_chapters", ["story_id", "deleted_at"])

    # A trashed chapter must not reserve its number forever.
    op.drop_constraint("uq_story_chapter_number", "story_chapters", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_story_chapter_number_active
        ON story_chapters (story_id, chapter_number)
        WHERE deleted_at IS NULL
        """
    )

    # --- Idempotent saves -------------------------------------------------
    op.add_column("story_chapters", sa.Column("last_client_save_id", sa.Uuid(), nullable=True))

    # --- Snapshot metadata ------------------------------------------------
    op.add_column(
        "story_chapter_revisions",
        sa.Column("kind", sa.String(20), nullable=False, server_default="checkpoint"),
    )
    op.add_column("story_chapter_revisions", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("story_chapter_revisions", sa.Column("char_count", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE story_chapter_revisions
        SET content_hash = md5(content),
            char_count = length(content)
        """
    )
    op.alter_column("story_chapter_revisions", "content_hash", nullable=False)
    op.alter_column("story_chapter_revisions", "char_count", nullable=False)
    op.create_index(
        "ix_revisions_chapter_created",
        "story_chapter_revisions",
        ["chapter_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_revisions_chapter_created", table_name="story_chapter_revisions")
    op.drop_column("story_chapter_revisions", "char_count")
    op.drop_column("story_chapter_revisions", "content_hash")
    op.drop_column("story_chapter_revisions", "kind")
    op.drop_column("story_chapters", "last_client_save_id")
    op.drop_index("uq_story_chapter_number_active", table_name="story_chapters")
    op.create_unique_constraint(
        "uq_story_chapter_number", "story_chapters", ["story_id", "chapter_number"]
    )
    op.drop_index("ix_chapters_story_deleted", table_name="story_chapters")
    op.drop_index("ix_stories_owner_deleted", table_name="stories")
    op.drop_column("story_chapters", "deleted_at")
    op.drop_column("stories", "deleted_at")
