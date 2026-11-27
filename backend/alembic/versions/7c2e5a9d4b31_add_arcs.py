"""add arcs and chapter arcs

Revision ID: 7c2e5a9d4b31
Revises: 6d1f4b8c2e09
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "7c2e5a9d4b31"
down_revision = "6d1f4b8c2e09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "arcs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "story_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("position", sa.Float(), nullable=False, server_default="1024"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("story_id", "name", name="uq_arc_story_name"),
    )
    op.create_index("ix_arcs_story_id", "arcs", ["story_id"])
    op.add_column(
        "story_chapters",
        sa.Column(
            "arc_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("arcs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_chapters_arc_id", "story_chapters", ["arc_id"])

    # Every story that already has chapters gets one arc holding all of them, so
    # the rail can group from the first load without asking the writer first.
    op.execute(
        """
        INSERT INTO arcs (id, story_id, name, position, summary)
        SELECT gen_random_uuid(), s.id, 'Act one', 1024, ''
        FROM stories s
        WHERE EXISTS (SELECT 1 FROM story_chapters c WHERE c.story_id = s.id AND c.deleted_at IS NULL)
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE story_chapters c
        SET arc_id = a.id
        FROM arcs a
        WHERE a.story_id = c.story_id AND a.name = 'Act one' AND c.arc_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_chapters_arc_id", table_name="story_chapters")
    op.drop_column("story_chapters", "arc_id")
    op.drop_index("ix_arcs_story_id", table_name="arcs")
    op.drop_table("arcs")
