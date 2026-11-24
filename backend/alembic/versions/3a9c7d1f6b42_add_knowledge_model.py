"""add knowledge model v2

Revision ID: 3a9c7d1f6b42
Revises: 8f3b6d2e5a17
Create Date: 2026-11-24 22:30:00.000000

Entities, aliases, facts, relationships, events, threads, mentions, canon
exceptions, chapter/scene metadata, and AI usage. Purely additive: the old
``story_bible_entries`` table stays until the Phase 4 wiki UI ships, so the
compatibility serializer can serve both.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3a9c7d1f6b42"
down_revision: str | Sequence[str] | None = "8f3b6d2e5a17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
UUID_ARRAY = postgresql.ARRAY(postgresql.UUID(as_uuid=True))


def upgrade() -> None:
    # Trigram similarity powers "is this the same name?" during entity resolution.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "entities",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("story_id", UUID, sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("canonical_name", sa.String(220), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "merged_into_id", UUID, sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("first_chapter_number", sa.Integer(), nullable=True),
        sa.Column("last_chapter_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_entities_type_canonical_active",
        "entities",
        ["story_id", "entity_type", "canonical_name"],
        unique=True,
        postgresql_where=sa.text("merged_into_id IS NULL"),
    )
    op.create_index("ix_entities_story_type", "entities", ["story_id", "entity_type"])
    op.create_index("ix_entities_story_status", "entities", ["story_id", "status"])
    op.create_index(
        "ix_entities_name_trgm",
        "entities",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "entity_aliases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "entity_id", UUID, sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("alias", sa.String(200), nullable=False),
        sa.Column("normalized_alias", sa.String(220), nullable=False),
        sa.Column("alias_type", sa.String(20), nullable=False, server_default="name"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("entity_id", "normalized_alias", name="uq_entity_alias_normalized"),
    )
    op.create_index("ix_entity_aliases_normalized", "entity_aliases", ["normalized_alias"])
    op.create_index(
        "ix_entity_aliases_alias_trgm",
        "entity_aliases",
        ["alias"],
        postgresql_using="gin",
        postgresql_ops={"alias": "gin_trgm_ops"},
    )

    op.create_table(
        "entity_facts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "entity_id", UUID, sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("predicate", sa.String(100), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Float(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column(
            "value_entity_id", UUID, sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("value_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column(
            "chapter_id", UUID, sa.ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("scene_index", sa.Integer(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("valid_from_chapter", sa.Integer(), nullable=True),
        sa.Column("valid_to_chapter", sa.Integer(), nullable=True),
        sa.Column(
            "supersedes_id", UUID, sa.ForeignKey("entity_facts.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(20), nullable=False, server_default="human"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_entity_facts_entity_predicate", "entity_facts", ["entity_id", "predicate"])
    op.create_index("ix_entity_facts_status", "entity_facts", ["status"])
    op.create_index("ix_entity_facts_chapter", "entity_facts", ["chapter_id"])

    op.create_table(
        "entity_relationships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("story_id", UUID, sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "from_entity_id", UUID, sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "to_entity_id", UUID, sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("relationship_type", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("since_chapter", sa.Integer(), nullable=True),
        sa.Column("until_chapter", sa.Integer(), nullable=True),
        sa.Column(
            "chapter_id", UUID, sa.ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="accepted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_entity_relationships_from", "entity_relationships", ["from_entity_id"])
    op.create_index("ix_entity_relationships_to", "entity_relationships", ["to_entity_id"])
    op.create_index("ix_entity_relationships_story", "entity_relationships", ["story_id"])

    op.create_table(
        "story_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("story_id", UUID, sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "chapter_id", UUID, sa.ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scene_index", sa.Integer(), nullable=True),
        sa.Column("timeline_order", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "location_entity_id", UUID, sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("participant_entity_ids", UUID_ARRAY, nullable=False, server_default="{}"),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_story_events_story_chapter", "story_events", ["story_id", "chapter_id"])
    op.create_index("ix_story_events_story_timeline", "story_events", ["story_id", "timeline_order"])

    op.create_table(
        "story_threads",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("story_id", UUID, sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "setup_chapter_id", UUID, sa.ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("setup_quote", sa.Text(), nullable=True),
        sa.Column(
            "payoff_chapter_id", UUID, sa.ForeignKey("story_chapters.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("state", sa.String(20), nullable=False, server_default="open"),
        sa.Column("linked_entity_ids", UUID_ARRAY, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_story_threads_story_state", "story_threads", ["story_id", "state"])

    op.create_table(
        "entity_mentions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "entity_id", UUID, sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "chapter_id", UUID, sa.ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scene_index", sa.Integer(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "entity_id", "chapter_id", "line_start", "line_end", name="uq_entity_mention_range"
        ),
    )
    op.create_index(
        "ix_entity_mentions_entity_chapter", "entity_mentions", ["entity_id", "chapter_id"]
    )
    op.create_index("ix_entity_mentions_chapter", "entity_mentions", ["chapter_id"])

    op.create_table(
        "canon_exceptions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("story_id", UUID, sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("entity_id", UUID, sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("predicate", sa.String(100), nullable=True),
        sa.Column("pattern", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(20), nullable=False, server_default="human"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_canon_exceptions_story", "canon_exceptions", ["story_id", "scope"])

    op.create_table(
        "chapter_meta",
        sa.Column(
            "chapter_id",
            UUID,
            sa.ForeignKey("story_chapters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("synopsis", sa.Text(), nullable=False, server_default=""),
        sa.Column("pov_entity_id", UUID, sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "location_entity_id", UUID, sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("story_time", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
    )

    op.create_table(
        "scene_meta",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "chapter_id", UUID, sa.ForeignKey("story_chapters.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scene_index", sa.Integer(), nullable=False),
        sa.Column("synopsis", sa.Text(), nullable=False, server_default=""),
        sa.Column("pov_entity_id", UUID, sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "location_entity_id", UUID, sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("story_time", sa.String(200), nullable=True),
        sa.Column("character_entity_ids", UUID_ARRAY, nullable=False, server_default="{}"),
        sa.UniqueConstraint("chapter_id", "scene_index", name="uq_scene_meta_index"),
    )

    op.create_table(
        "ai_usage",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("story_id", UUID, sa.ForeignKey("stories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_estimate", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_story_created", "ai_usage", ["story_id", "created_at"])

    for table in ("entities", "entity_facts", "story_threads", "entity_mentions"):
        op.execute(f"ANALYZE {table}")


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("scene_meta")
    op.drop_table("chapter_meta")
    op.drop_table("canon_exceptions")
    op.drop_index("ix_entity_mentions_chapter", table_name="entity_mentions")
    op.drop_index("ix_entity_mentions_entity_chapter", table_name="entity_mentions")
    op.drop_table("entity_mentions")
    op.drop_table("story_threads")
    op.drop_table("story_events")
    op.drop_table("entity_relationships")
    op.drop_table("entity_facts")
    op.drop_index("ix_entity_aliases_alias_trgm", table_name="entity_aliases")
    op.drop_index("ix_entity_aliases_normalized", table_name="entity_aliases")
    op.drop_table("entity_aliases")
    op.drop_index("ix_entities_name_trgm", table_name="entities")
    op.drop_index("ix_entities_story_status", table_name="entities")
    op.drop_index("ix_entities_story_type", table_name="entities")
    op.drop_index("uq_entities_type_canonical_active", table_name="entities")
    op.drop_table("entities")
