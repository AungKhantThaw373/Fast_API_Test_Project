"""add stable chapter positions

Revision ID: 72e3aad68ab6
Revises: 7103cb022fd3
Create Date: 2026-11-24 18:40:00.000000

``chapter_number`` becomes a display value. ``position`` is the ordering source,
so reordering no longer needs a negative-number dance or one UPDATE per row.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "72e3aad68ab6"
down_revision: str | Sequence[str] | None = "7103cb022fd3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("story_chapters", sa.Column("position", sa.Float(), nullable=True))
    op.execute(
        """
        UPDATE story_chapters AS c
        SET position = ranked.rn * 1024.0
        FROM (
            SELECT id, row_number() OVER (PARTITION BY story_id ORDER BY chapter_number) AS rn
            FROM story_chapters
        ) AS ranked
        WHERE c.id = ranked.id
        """
    )
    op.alter_column("story_chapters", "position", nullable=False)
    op.create_index("ix_chapters_story_position", "story_chapters", ["story_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_chapters_story_position", table_name="story_chapters")
    op.drop_column("story_chapters", "position")
