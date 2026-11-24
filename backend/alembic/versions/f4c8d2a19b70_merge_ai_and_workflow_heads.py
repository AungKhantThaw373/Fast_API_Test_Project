"""Merge AI settings and manuscript workflow migrations."""
from collections.abc import Sequence

revision: str = "f4c8d2a19b70"
down_revision: str | Sequence[str] | None = ("b25d8f0a61ce", "e3f19a6b42d8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
