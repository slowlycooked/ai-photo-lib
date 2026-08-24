"""add photo library browse indexes

Revision ID: 038_photo_library_browse_indexes
Revises: 037_add_photo_quarantine_task_index
Create Date: 2026-08-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "038_photo_library_browse_indexes"
down_revision: Union[str, None] = "037_add_photo_quarantine_task_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = {
    "ix_photos_library_browse": "project_id, taken_at DESC NULLS LAST, created_at DESC, id DESC",
    "ix_photos_folder_library_browse": (
        "project_id, folder_id, taken_at DESC NULLS LAST, created_at DESC, id DESC"
    ),
}
_PREDICATE = "deleted_at IS NULL AND status <> 'quarantined'"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for name, columns in _INDEXES.items():
                op.execute(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                    f"ON photos ({columns}) WHERE {_PREDICATE}"
                )
        return

    for name, columns in _INDEXES.items():
        plain_columns = [part.split()[0] for part in columns.split(", ")]
        op.create_index(name, "photos", plain_columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for name in reversed(_INDEXES):
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        return

    for name in reversed(_INDEXES):
        op.drop_index(name, table_name="photos")
