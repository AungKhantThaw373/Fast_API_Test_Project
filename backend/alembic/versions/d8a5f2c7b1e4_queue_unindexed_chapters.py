"""queue chapters that claim to be indexed but have no chunks

The demo seed wrote `index_status="ready"` for every chapter without ever
embedding it. The previous migration normalised the label, which made those
chapters look ready while retrieval had nothing to search. Mark any indexed
chapter with no chunks as pending and enqueue the durable reindex job so a
worker can actually build the memory.

Revision ID: d8a5f2c7b1e4
Revises: c4e8b2a7d9f1
Create Date: 2026-11-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d8a5f2c7b1e4"
down_revision: str | Sequence[str] | None = "c4e8b2a7d9f1"


def upgrade() -> None:
    # An indexed chapter with no chunks has no searchable memory. Treat it as
    # pending rather than pretending the retrieval layer can see it.
    op.execute(
        "UPDATE story_chapters AS c SET index_status = 'pending' "
        "WHERE c.index_status = 'indexed' AND c.deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM story_chunks AS k WHERE k.chapter_id = c.id)"
    )
    # Queue every pending chapter that has no active reindex job. This repairs
    # both the seeded chapters above and any queue lost to an earlier crash.
    op.execute(
        "INSERT INTO jobs (id, owner_id, type, payload, status, attempts, "
        "max_attempts, dedupe_key, run_at, progress, created_at, updated_at) "
        "SELECT gen_random_uuid(), s.owner_id, 'reindex_chapter', "
        "jsonb_build_object('chapter_id', c.id::text), 'queued', 0, 3, "
        "'chapter:' || c.id, now(), '{}'::jsonb, now(), now() "
        "FROM story_chapters AS c "
        "JOIN stories AS s ON s.id = c.story_id "
        "WHERE c.index_status = 'pending' AND c.deleted_at IS NULL "
        "AND s.deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM jobs AS j WHERE j.type = 'reindex_chapter' "
        "AND j.dedupe_key = 'chapter:' || c.id "
        "AND j.status IN ('queued', 'running'))"
    )


def downgrade() -> None:
    # The label repair is one-way, and deleting queued work could lose a
    # writer's overdue reindex. Leave both in place on downgrade.
    pass
