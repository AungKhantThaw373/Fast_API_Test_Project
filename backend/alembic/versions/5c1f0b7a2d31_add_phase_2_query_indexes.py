"""add phase 2 query indexes

Revision ID: 5c1f0b7a2d31
Revises: 72e3aad68ab6
Create Date: 2026-11-24 20:10:00.000000

The remaining Phase 2 index. ``ix_story_bible_story_status`` and
``ix_revisions_chapter_created`` already exist, and ``ix_continuity_findings_scan_id``
already covers the ``scan_id`` lookup, so no duplicate index is created here.
``ANALYZE`` runs inside the migration so the planner sees the new index
immediately, in CI and locally alike.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "5c1f0b7a2d31"
down_revision: str | Sequence[str] | None = "72e3aad68ab6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("continuity_scans", "continuity_findings", "story_bible_entries", "story_chapters")


def upgrade() -> None:
    # "Latest scan for this chapter" and the reuse-cache lookup both order by
    # created_at within a chapter. Postgres scans the index backwards for DESC.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scans_chapter_created "
        "ON continuity_scans (chapter_id, created_at)"
    )
    for table in TABLES:
        op.execute(f"ANALYZE {table}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scans_chapter_created")
