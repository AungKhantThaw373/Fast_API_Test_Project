"""Move legacy world-rule entries into the Worldbuilding category.

Revision ID: c82e4a7f1b63
Revises: 9c18b6a4f205
"""
from collections.abc import Sequence

from alembic import op

revision: str = "c82e4a7f1b63"
down_revision: str | Sequence[str] | None = "9c18b6a4f205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE story_bible_entries "
        "SET category = 'worldbuilding' "
        "WHERE category = 'world_rule'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE story_bible_entries "
        "SET category = 'world_rule' "
        "WHERE category = 'worldbuilding'"
    )
