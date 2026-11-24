"""Add the structured editing draft library.

Revision ID: 4a7b8c9d2e10
Revises: 9c18b6a4f205
"""
from typing import Sequence, Union

from alembic import op


revision: str = "4a7b8c9d2e10"
down_revision: Union[str, Sequence[str], None] = "9c18b6a4f205"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The Editing tables may already exist in databases where the schema was
    # created before this revision was stamped in Alembic.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS editing_folders (
            id UUID NOT NULL PRIMARY KEY,
            owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            canonical_name VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_editing_folder_owner_name UNIQUE (owner_id, canonical_name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_editing_folders_owner ON editing_folders (owner_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS editing_draft_files (
            id UUID NOT NULL PRIMARY KEY,
            owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            folder_id UUID NOT NULL REFERENCES editing_folders(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            extension VARCHAR(20) NOT NULL,
            media_type VARCHAR(120) NOT NULL,
            size_bytes BIGINT NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            content BYTEA NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_editing_draft_files_folder "
        "ON editing_draft_files (folder_id, updated_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_editing_draft_files_owner ON editing_draft_files (owner_id)")


def downgrade() -> None:
    op.drop_index("ix_editing_draft_files_owner", table_name="editing_draft_files")
    op.drop_index("ix_editing_draft_files_folder", table_name="editing_draft_files")
    op.drop_table("editing_draft_files")
    op.drop_index("ix_editing_folders_owner", table_name="editing_folders")
    op.drop_table("editing_folders")
