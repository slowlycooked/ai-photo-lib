"""add people recognition foundation tables

Revision ID: 020_add_people_recognition_foundation
Revises: 019
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "020_add_people_recognition_foundation"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "project_face_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("face_recognition_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("face_provider", sa.Text(), server_default="opencv", nullable=False),
        sa.Column("face_detector_model", sa.Text(), server_default="yunet", nullable=False),
        sa.Column("face_embedding_model", sa.Text(), server_default="sface", nullable=False),
        sa.Column("face_runtime", sa.Text(), server_default="cpu", nullable=False),
        sa.Column("store_face_crops", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("face_crop_storage", sa.Text(), server_default="local", nullable=False),
        sa.Column("auto_accept_threshold", sa.Float(), server_default="0.62", nullable=False),
        sa.Column("review_threshold", sa.Float(), server_default="0.48", nullable=False),
        sa.Column("cluster_threshold", sa.Float(), server_default="0.50", nullable=False),
        sa.Column("min_face_size", sa.Integer(), server_default="40", nullable=False),
        sa.Column("min_detection_confidence", sa.Float(), server_default="0.75", nullable=False),
        sa.Column("min_quality_for_prototype", sa.Float(), server_default="0.70", nullable=False),
        sa.Column(
            "max_positive_samples_per_person",
            sa.Integer(),
            server_default="200",
            nullable=False,
        ),
        sa.Column("allow_auto_assignment", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "require_human_confirmation_for_new_person",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "enable_negative_constraints",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "enable_person_cannot_links",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", name="uq_project_face_settings_project_id"),
    )
    op.create_index(
        "ix_project_face_settings_project_id",
        "project_face_settings",
        ["project_id"],
    )

    op.create_table(
        "face_detections",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("photo_id", sa.BigInteger(), nullable=False),
        sa.Column("bbox_x", sa.Integer(), nullable=False),
        sa.Column("bbox_y", sa.Integer(), nullable=False),
        sa.Column("bbox_w", sa.Integer(), nullable=False),
        sa.Column("bbox_h", sa.Integer(), nullable=False),
        sa.Column("detection_confidence", sa.Float(), nullable=True),
        sa.Column("face_quality_score", sa.Float(), nullable=True),
        sa.Column("face_crop_path", sa.Text(), nullable=True),
        sa.Column("face_crop_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "photo_id",
            "bbox_x",
            "bbox_y",
            "bbox_w",
            "bbox_h",
            name="uq_face_detections_project_photo_bbox",
        ),
    )
    op.create_index("ix_face_detections_project_photo", "face_detections", ["project_id", "photo_id"])
    op.create_index("ix_face_detections_project_status", "face_detections", ["project_id", "status"])

    op.create_table(
        "persons",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=True),
        sa.Column("is_named", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("representative_face_detection_id", sa.BigInteger(), nullable=True),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confirmed_sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("auto_assigned_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("review_pending_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.Text(), server_default="system", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["representative_face_detection_id"],
            ["face_detections.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_persons_project_named", "persons", ["project_id", "is_named"])
    op.create_index("ix_persons_project_updated_at", "persons", ["project_id", "updated_at"])

    op.create_table(
        "face_embeddings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("face_detection_id", sa.BigInteger(), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), server_default="", nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embedding_vector", Vector(1024), nullable=True),
        sa.Column("embedding_hash", sa.Text(), nullable=True),
        sa.Column("embedded_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["face_detection_id"], ["face_detections.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "face_detection_id",
            "model_name",
            "model_version",
            name="uq_face_embeddings_project_detection_model",
        ),
    )
    op.create_index("ix_face_embeddings_project_id", "face_embeddings", ["project_id"])
    op.create_index("ix_face_embeddings_face_detection", "face_embeddings", ["face_detection_id"])
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_face_embeddings_vector_hnsw
        ON face_embeddings
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """
    )

    op.create_table(
        "person_face_assignments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("person_id", sa.BigInteger(), nullable=False),
        sa.Column("face_detection_id", sa.BigInteger(), nullable=False),
        sa.Column("assignment_status", sa.Text(), nullable=False),
        sa.Column("assignment_source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("is_positive_sample", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_training_candidate", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["face_detection_id"], ["face_detections.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "person_id",
            "face_detection_id",
            name="uq_person_face_assignments_project_person_face",
        ),
    )
    op.create_index(
        "ix_person_face_assignments_project_person",
        "person_face_assignments",
        ["project_id", "person_id"],
    )
    op.create_index(
        "ix_person_face_assignments_project_status",
        "person_face_assignments",
        ["project_id", "assignment_status"],
    )
    op.create_index(
        "ix_person_face_assignments_face_detection",
        "person_face_assignments",
        ["face_detection_id"],
    )

    op.create_table(
        "person_prototypes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("person_id", sa.BigInteger(), nullable=False),
        sa.Column("prototype_type", sa.Text(), nullable=False),
        sa.Column("embedding_vector", Vector(1024), nullable=True),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_assignment_ids", sa.JSON(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), server_default="", nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_person_prototypes_project_person",
        "person_prototypes",
        ["project_id", "person_id"],
    )
    op.create_index(
        "ix_person_prototypes_project_type",
        "person_prototypes",
        ["project_id", "prototype_type"],
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_person_prototypes_vector_hnsw
        ON person_prototypes
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """
    )

    op.create_table(
        "face_negative_constraints",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("face_detection_id", sa.BigInteger(), nullable=False),
        sa.Column("not_person_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["face_detection_id"], ["face_detections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["not_person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "face_detection_id",
            "not_person_id",
            name="uq_face_negative_constraints_project_face_person",
        ),
    )
    op.create_index(
        "ix_face_negative_constraints_project_face",
        "face_negative_constraints",
        ["project_id", "face_detection_id"],
    )
    op.create_index(
        "ix_face_negative_constraints_project_person",
        "face_negative_constraints",
        ["project_id", "not_person_id"],
    )

    op.create_table(
        "person_cannot_links",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("person_id_a", sa.BigInteger(), nullable=False),
        sa.Column("person_id_b", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id_a"], ["persons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id_b"], ["persons.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "person_id_a",
            "person_id_b",
            name="uq_person_cannot_links_project_pair",
        ),
    )
    op.create_index(
        "ix_person_cannot_links_project_person_a",
        "person_cannot_links",
        ["project_id", "person_id_a"],
    )
    op.create_index(
        "ix_person_cannot_links_project_person_b",
        "person_cannot_links",
        ["project_id", "person_id_b"],
    )


def downgrade() -> None:
    op.drop_index("ix_person_cannot_links_project_person_b", table_name="person_cannot_links")
    op.drop_index("ix_person_cannot_links_project_person_a", table_name="person_cannot_links")
    op.drop_table("person_cannot_links")

    op.drop_index(
        "ix_face_negative_constraints_project_person",
        table_name="face_negative_constraints",
    )
    op.drop_index(
        "ix_face_negative_constraints_project_face",
        table_name="face_negative_constraints",
    )
    op.drop_table("face_negative_constraints")

    op.execute("DROP INDEX IF EXISTS ix_person_prototypes_vector_hnsw")
    op.drop_index("ix_person_prototypes_project_type", table_name="person_prototypes")
    op.drop_index("ix_person_prototypes_project_person", table_name="person_prototypes")
    op.drop_table("person_prototypes")

    op.drop_index(
        "ix_person_face_assignments_face_detection",
        table_name="person_face_assignments",
    )
    op.drop_index(
        "ix_person_face_assignments_project_status",
        table_name="person_face_assignments",
    )
    op.drop_index(
        "ix_person_face_assignments_project_person",
        table_name="person_face_assignments",
    )
    op.drop_table("person_face_assignments")

    op.execute("DROP INDEX IF EXISTS ix_face_embeddings_vector_hnsw")
    op.drop_index("ix_face_embeddings_face_detection", table_name="face_embeddings")
    op.drop_index("ix_face_embeddings_project_id", table_name="face_embeddings")
    op.drop_table("face_embeddings")

    op.drop_index("ix_persons_project_updated_at", table_name="persons")
    op.drop_index("ix_persons_project_named", table_name="persons")
    op.drop_table("persons")

    op.drop_index("ix_face_detections_project_status", table_name="face_detections")
    op.drop_index("ix_face_detections_project_photo", table_name="face_detections")
    op.drop_table("face_detections")

    op.drop_index("ix_project_face_settings_project_id", table_name="project_face_settings")
    op.drop_table("project_face_settings")
