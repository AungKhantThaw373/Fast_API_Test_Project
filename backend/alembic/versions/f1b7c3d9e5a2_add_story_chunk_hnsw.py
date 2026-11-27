"""add HNSW index for story chunk vectors

The exact scan was acceptable at 10k chunks but reached 1.5 s at 100k.
HNSW with ef_search=200 measured 0.993 top-30 recall and under 5 ms on
the same clustered-vector benchmark. The index is explicitly named so it
is not confused with the legacy scene table index.

Revision ID: f1b7c3d9e5a2
Revises: e5a9c3d7b2f4
Create Date: 2026-11-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f1b7c3d9e5a2"
down_revision: str | Sequence[str] | None = "e5a9c3d7b2f4"


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_story_chunks_embedding_hnsw "
        "ON story_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_story_chunks_embedding_hnsw")