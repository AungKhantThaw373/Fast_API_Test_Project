"""add per-story wiki format

Revision ID: b7c1e4a9d2f0
Revises: d8a5f2c7b1e4
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b7c1e4a9d2f0"
down_revision = "d8a5f2c7b1e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("wiki_format", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "wiki_format")
