"""Add per-scene continuity metadata and deterministic finding sources.

Revision ID: a5b2d8c1e9f3
Revises: f4a1c9d2e6b7
Create Date: 2026-11-25
"""

import sqlalchemy as sa

from alembic import op

revision = "a5b2d8c1e9f3"
down_revision = "f4a1c9d2e6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("continuity_scans", sa.Column("prompt_version", sa.String(60), nullable=True))
    op.add_column("continuity_scans", sa.Column("model", sa.String(200), nullable=True))
    op.add_column("continuity_scans", sa.Column("schema_version", sa.String(20), nullable=True))
    op.add_column("continuity_scans", sa.Column("context_hash", sa.String(64), nullable=True))
    op.add_column(
        "continuity_scans",
        sa.Column("scenes_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "continuity_scans",
        sa.Column("scenes_done", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "continuity_findings",
        sa.Column("source", sa.String(20), nullable=False, server_default="llm"),
    )
    op.add_column("continuity_findings", sa.Column("rule_id", sa.String(60), nullable=True))
    op.add_column("continuity_findings", sa.Column("scene_index", sa.Integer(), nullable=True))
    op.add_column("continuity_findings", sa.Column("evidence_kind", sa.String(20), nullable=True))
    op.add_column("continuity_findings", sa.Column("evidence_id", sa.String(80), nullable=True))
    op.alter_column("continuity_findings", "earlier_quote", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("continuity_findings", "earlier_quote", existing_type=sa.Text(), nullable=False)
    op.drop_column("continuity_findings", "evidence_id")
    op.drop_column("continuity_findings", "evidence_kind")
    op.drop_column("continuity_findings", "scene_index")
    op.drop_column("continuity_findings", "rule_id")
    op.drop_column("continuity_findings", "source")
    op.drop_column("continuity_scans", "scenes_done")
    op.drop_column("continuity_scans", "scenes_total")
    op.drop_column("continuity_scans", "context_hash")
    op.drop_column("continuity_scans", "schema_version")
    op.drop_column("continuity_scans", "model")
    op.drop_column("continuity_scans", "prompt_version")
