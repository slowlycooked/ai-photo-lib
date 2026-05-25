"""fix face embedding vector dimension

Revision ID: 022_fix_face_embedding_vector_dimension
Revises: 021_add_photo_derivatives
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "022_fix_face_embedding_vector_dimension"
down_revision: Union[str, None] = "021_add_photo_derivatives"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FACE_EMBEDDING_DIMENSION = 128
LEGACY_FACE_EMBEDDING_DIMENSION = 1024


def _alter_vector_dimension(table_name: str, target_dim: int) -> None:
    op.execute(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN embedding_vector TYPE vector({target_dim})
        USING (
            CASE
                WHEN embedding_vector IS NULL THEN NULL
                WHEN vector_dims(embedding_vector) = {target_dim} THEN embedding_vector::vector({target_dim})
                WHEN vector_dims(embedding_vector) > {target_dim} THEN subvector(embedding_vector, 1, {target_dim})::vector({target_dim})
                ELSE NULL
            END
        )
        """
    )


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_face_embeddings_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_person_prototypes_vector_hnsw")

    _alter_vector_dimension("face_embeddings", FACE_EMBEDDING_DIMENSION)
    _alter_vector_dimension("person_prototypes", FACE_EMBEDDING_DIMENSION)

    op.execute(
        f"""
        UPDATE face_embeddings
        SET embedding_dim = {FACE_EMBEDDING_DIMENSION}
        WHERE embedding_dim <> {FACE_EMBEDDING_DIMENSION}
        """
    )
    op.execute(
        f"""
        UPDATE person_prototypes
        SET embedding_dim = {FACE_EMBEDDING_DIMENSION}
        WHERE embedding_dim <> {FACE_EMBEDDING_DIMENSION}
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_face_embeddings_vector_hnsw
        ON face_embeddings
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_person_prototypes_vector_hnsw
        ON person_prototypes
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_face_embeddings_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_person_prototypes_vector_hnsw")

    _alter_vector_dimension("face_embeddings", LEGACY_FACE_EMBEDDING_DIMENSION)
    _alter_vector_dimension("person_prototypes", LEGACY_FACE_EMBEDDING_DIMENSION)

    op.execute(
        f"""
        UPDATE face_embeddings
        SET embedding_dim = {LEGACY_FACE_EMBEDDING_DIMENSION}
        WHERE embedding_dim <> {LEGACY_FACE_EMBEDDING_DIMENSION}
        """
    )
    op.execute(
        f"""
        UPDATE person_prototypes
        SET embedding_dim = {LEGACY_FACE_EMBEDDING_DIMENSION}
        WHERE embedding_dim <> {LEGACY_FACE_EMBEDDING_DIMENSION}
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_face_embeddings_vector_hnsw
        ON face_embeddings
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_person_prototypes_vector_hnsw
        ON person_prototypes
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """
    )
