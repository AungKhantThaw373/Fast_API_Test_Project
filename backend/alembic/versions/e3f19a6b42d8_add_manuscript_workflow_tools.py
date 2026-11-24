"""Add chapter version history, review states, and story collections."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e3f19a6b42d8"
down_revision: Union[str, None] = "d7a2b4c8e9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("collection_name", sa.String(length=100), nullable=False, server_default=""))
    op.add_column("continuity_findings", sa.Column("review_status", sa.String(length=20), nullable=False, server_default="open"))
    op.create_table(
        "story_chapter_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["story_chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "revision_number", name="uq_chapter_revision_number"),
    )
    op.create_index("ix_story_chapter_revisions_chapter_id", "story_chapter_revisions", ["chapter_id"])


def downgrade() -> None:
    op.drop_index("ix_story_chapter_revisions_chapter_id", table_name="story_chapter_revisions")
    op.drop_table("story_chapter_revisions")
    op.drop_column("continuity_findings", "review_status")
    op.drop_column("stories", "collection_name")
