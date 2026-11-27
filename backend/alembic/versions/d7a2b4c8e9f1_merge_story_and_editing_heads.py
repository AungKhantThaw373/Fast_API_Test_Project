"""Join the Story Bible and Editing migration branches.

Revision ID: d7a2b4c8e9f1
Revises: c82e4a7f1b63, 4a7b8c9d2e10
"""
from collections.abc import Sequence

revision: str = "d7a2b4c8e9f1"
down_revision: str | Sequence[str] | None = ("c82e4a7f1b63", "4a7b8c9d2e10")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
