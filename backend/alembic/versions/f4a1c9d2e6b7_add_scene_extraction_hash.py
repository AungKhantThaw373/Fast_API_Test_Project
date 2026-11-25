"""Add per-scene extraction hashes.

Revision ID: f4a1c9d2e6b7
Revises: b7d2e4f9a1c3
Create Date: 2026-11-25
"""

from alembic import op
import sqlalchemy as sa

revision = "f4a1c9d2e6b7"
down_revision = "b7d2e4f9a1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scene_meta", sa.Column("last_extracted_hash", sa.String(64), nullable=True))
    op.add_column("scene_meta", sa.Column("last_extracted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("scene_meta", "last_extracted_at")
    op.drop_column("scene_meta", "last_extracted_hash")
