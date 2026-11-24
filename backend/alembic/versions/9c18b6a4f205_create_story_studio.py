"""Create the writing studio and continuity tables.

Revision ID: 9c18b6a4f205
Revises: aab5d9340617
"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "9c18b6a4f205"
down_revision: str | Sequence[str] | None = "aab5d9340617"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # The historical initial migration was empty. Create the account table when
    # bootstrapping a fresh database while leaving existing accounts untouched.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            username VARCHAR NOT NULL UNIQUE,
            fullname VARCHAR,
            email VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            password VARCHAR NOT NULL
        )
        """
    )
    op.create_table(
        "stories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("scan_interval_words", sa.Integer(), nullable=False, server_default="1500"),
        sa.Column("external_analysis_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stories_owner_id", "stories", ["owner_id"])

    op.create_table(
        "story_chapters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("index_status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("story_id", "chapter_number", name="uq_story_chapter_number"),
    )
    op.create_index("ix_story_chapters_story_id", "story_chapters", ["story_id"])

    op.create_table(
        "story_scene_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("chunk_metadata", JSONB(), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["story_chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_story_scene_embeddings_chapter_id", "story_scene_embeddings", ["chapter_id"])
    op.create_index("ix_story_scene_story_chapter", "story_scene_embeddings", ["story_id", "chapter_number"])
    op.execute(
        "CREATE INDEX ix_story_scene_embedding_hnsw "
        "ON story_scene_embeddings USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "story_bible_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("canonical_name", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="suggested"),
        sa.Column("thread_state", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("source_chapter_id", sa.Uuid(), nullable=True),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.Column("details", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chapter_id"], ["story_chapters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("story_id", "category", "canonical_name", name="uq_story_bible_canonical_entry"),
    )
    op.create_index("ix_story_bible_story_status", "story_bible_entries", ["story_id", "status"])

    op.create_table(
        "continuity_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_revision", sa.Integer(), nullable=False),
        sa.Column("chapter_word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="complete"),
        sa.Column("finding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["story_chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_continuity_scans_story_id", "continuity_scans", ["story_id"])
    op.create_index("ix_continuity_scans_chapter_id", "continuity_scans", ["chapter_id"])

    op.create_table(
        "continuity_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("draft_quote", sa.Text(), nullable=False),
        sa.Column("draft_line", sa.Integer(), nullable=False),
        sa.Column("earlier_quote", sa.Text(), nullable=False),
        sa.Column("earlier_chapter_id", sa.Uuid(), nullable=True),
        sa.Column("earlier_chapter_number", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("intentional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["continuity_scans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["earlier_chapter_id"], ["story_chapters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_continuity_findings_scan_id", "continuity_findings", ["scan_id"])


def downgrade() -> None:
    op.drop_index("ix_continuity_findings_scan_id", table_name="continuity_findings")
    op.drop_table("continuity_findings")
    op.drop_index("ix_continuity_scans_chapter_id", table_name="continuity_scans")
    op.drop_index("ix_continuity_scans_story_id", table_name="continuity_scans")
    op.drop_table("continuity_scans")
    op.drop_index("ix_story_bible_story_status", table_name="story_bible_entries")
    op.drop_table("story_bible_entries")
    op.execute("DROP INDEX IF EXISTS ix_story_scene_embedding_hnsw")
    op.drop_index("ix_story_scene_story_chapter", table_name="story_scene_embeddings")
    op.drop_index("ix_story_scene_embeddings_chapter_id", table_name="story_scene_embeddings")
    op.drop_table("story_scene_embeddings")
    op.drop_index("ix_story_chapters_story_id", table_name="story_chapters")
    op.drop_table("story_chapters")
    op.drop_index("ix_stories_owner_id", table_name="stories")
    op.drop_table("stories")
