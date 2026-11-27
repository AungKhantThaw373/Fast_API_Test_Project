"""normalise the legacy "ready" chapter index status

The demo seed and an older importer wrote "ready", but every reader, the
worker, and the UI only understand "indexed". Those chapters were therefore
excluded from continuity retrieval and displayed as forever updating.

Revision ID: c4e8b2a7d9f1
Revises: f1b7c3d9e5a2
Create Date: 2026-11-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4e8b2a7d9f1"
down_revision: str | Sequence[str] | None = "f1b7c3d9e5a2"


def upgrade() -> None:
    op.execute(
        "UPDATE story_chapters SET index_status = 'indexed' "
        "WHERE index_status = 'ready'"
    )


def downgrade() -> None:
    # "ready" was never a real state. Reversing this would mark genuinely
    # indexed chapters as unindexed, so the normalisation is intentionally
    # one-way.
    pass
