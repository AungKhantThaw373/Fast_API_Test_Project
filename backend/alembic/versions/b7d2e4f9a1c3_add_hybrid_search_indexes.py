"""add full-text and trigram indexes

Revision ID: b7d2e4f9a1c3
Revises: 9e4c1a7b8d20
"""

from alembic import op

revision = "b7d2e4f9a1c3"
down_revision = "9e4c1a7b8d20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # "simple" keeps proper nouns intact; English stemming would turn Voss into voss.
    op.execute(
        "ALTER TABLE story_chunks ADD COLUMN text_search tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text, ''))) STORED"
    )
    op.execute(
        "CREATE INDEX ix_story_chunks_fts "
        "ON story_chunks USING GIN (text_search)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entities_name_trgm "
        "ON entities USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entity_aliases_alias_trgm "
        "ON entity_aliases USING GIN (alias gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entity_aliases_alias_trgm")
    op.execute("DROP INDEX IF EXISTS ix_entities_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_story_chunks_fts")
    op.execute("ALTER TABLE story_chunks DROP COLUMN IF EXISTS text_search")
