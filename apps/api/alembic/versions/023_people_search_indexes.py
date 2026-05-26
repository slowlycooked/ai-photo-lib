"""add people search indexes

Revision ID: 023_people_search_indexes
Revises: 022_fix_face_embedding_vector_dimension
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "023_people_search_indexes"
down_revision: Union[str, None] = "022_fix_face_embedding_vector_dimension"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    if dialect == "postgresql":
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_persons_project_norm_named
            ON persons (project_id, normalized_name)
            WHERE is_named = true
            """
        )
    else:
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_persons_project_norm_named
            ON persons (project_id, normalized_name)
            """
        )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pfa_project_person_status
        ON person_face_assignments (project_id, person_id, assignment_status)
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_face_detections_project_photo_search
        ON face_detections (project_id, photo_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_face_detections_project_photo_search")
    op.execute("DROP INDEX IF EXISTS ix_pfa_project_person_status")
    op.execute("DROP INDEX IF EXISTS ix_persons_project_norm_named")
