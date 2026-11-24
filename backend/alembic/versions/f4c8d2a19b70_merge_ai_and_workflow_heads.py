"""Merge AI settings and manuscript workflow migrations."""
from typing import Sequence, Union


revision: str = "f4c8d2a19b70"
down_revision: Union[str, Sequence[str], None] = ("b25d8f0a61ce", "e3f19a6b42d8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
