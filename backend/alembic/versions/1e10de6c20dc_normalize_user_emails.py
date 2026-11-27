"""normalize user emails

Revision ID: 1e10de6c20dc
Revises: a1d7e5c9f203
Create Date: 2026-11-24 17:38:22.552792

Emails are the login identifier, so they must compare case-insensitively. The
old data may contain mixed case. Duplicates are resolved by aborting the
migration rather than silently deleting an account.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1e10de6c20dc'
down_revision: str | Sequence[str] | None = 'a1d7e5c9f203'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT lower(email) AS email, count(*) AS total "
            "FROM users GROUP BY lower(email) HAVING count(*) > 1"
        )
    ).all()
    if duplicates:
        listed = ", ".join(f"{row.email} x{row.total}" for row in duplicates)
        raise RuntimeError(
            "Cannot normalize user emails: duplicate addresses exist after "
            f"lowercasing ({listed}). Resolve them manually, then re-run."
        )

    op.execute("UPDATE users SET email = lower(btrim(email)) WHERE email <> lower(btrim(email))")
    op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS uq_users_email_lower")
