"""Track Story Bible scans and the embedding model used by each chapter."""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1d7e5c9f203"
down_revision: str | None = "f4c8d2a19b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("story_chapters", sa.Column("bible_scan_revision", sa.Integer(), nullable=True))
    op.add_column("story_chapters", sa.Column("bible_scan_error", sa.Text(), nullable=True))
    op.add_column(
        "story_chapters",
        sa.Column("indexed_embedding_model", sa.String(length=200), nullable=False, server_default="nomic-embed-text"),
    )
    op.alter_column("story_chapters", "indexed_embedding_model", server_default=None)


def downgrade() -> None:
    op.drop_column("story_chapters", "bible_scan_error")
    op.drop_column("story_chapters", "indexed_embedding_model")
    op.drop_column("story_chapters", "bible_scan_revision")
