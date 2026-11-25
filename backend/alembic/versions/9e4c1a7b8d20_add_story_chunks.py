"""add story chunks

Revision ID: 9e4c1a7b8d20
Revises: 7c2e5a9d4b31
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "9e4c1a7b8d20"
down_revision = "7c2e5a9d4b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "story_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "story_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("story_chapters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("scene_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_kind", sa.String(20), nullable=False, server_default="scene"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column(
            "entities",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "pov_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "location_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("chapter_id", "chunk_kind", "chunk_index", name="uq_story_chunk_index"),
    )
    op.create_index("ix_story_chunks_story_chapter", "story_chunks", ["story_id", "chapter_number"])
    op.create_index("ix_story_chunks_entities", "story_chunks", ["entities"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_story_chunks_entities", table_name="story_chunks")
    op.drop_index("ix_story_chunks_story_chapter", table_name="story_chunks")
    op.drop_table("story_chunks")
