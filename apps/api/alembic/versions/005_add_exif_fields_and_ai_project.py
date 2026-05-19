"""add structured EXIF fields and project_id to ai_jobs

Revision ID: 005
Revises: 004
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add project_id to ai_jobs and backfill from photos
    # ------------------------------------------------------------------
    op.add_column(
        "ai_jobs",
        sa.Column(
            "project_id",
            sa.BigInteger,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE ai_jobs "
            "SET project_id = photos.project_id "
            "FROM photos "
            "WHERE ai_jobs.photo_id = photos.id"
        )
    )
    op.create_index(
        "ix_ai_jobs_project_status", "ai_jobs", ["project_id", "status"]
    )

    # ------------------------------------------------------------------
    # 2. Add structured GPS fields to photos
    # ------------------------------------------------------------------
    op.add_column("photos", sa.Column("gps_latitude", sa.Double, nullable=True))
    op.add_column("photos", sa.Column("gps_longitude", sa.Double, nullable=True))
    op.add_column("photos", sa.Column("gps_altitude", sa.Double, nullable=True))

    # ------------------------------------------------------------------
    # 3. Add camera / lens / exposure fields to photos
    # ------------------------------------------------------------------
    op.add_column("photos", sa.Column("camera_make", sa.Text, nullable=True))
    op.add_column("photos", sa.Column("camera_model", sa.Text, nullable=True))
    op.add_column("photos", sa.Column("lens_model", sa.Text, nullable=True))
    op.add_column("photos", sa.Column("focal_length", sa.Text, nullable=True))
    op.add_column("photos", sa.Column("aperture", sa.Text, nullable=True))
    op.add_column("photos", sa.Column("exposure_time", sa.Text, nullable=True))
    op.add_column("photos", sa.Column("iso", sa.Integer, nullable=True))
    op.add_column("photos", sa.Column("orientation", sa.Integer, nullable=True))

    # ------------------------------------------------------------------
    # 4. Indexes for GPS and camera queries
    # ------------------------------------------------------------------
    op.create_index(
        "ix_photos_project_gps",
        "photos",
        ["project_id", "gps_latitude", "gps_longitude"],
        postgresql_where=sa.text("gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL"),
    )
    op.create_index(
        "ix_photos_project_camera",
        "photos",
        ["project_id", "camera_make", "camera_model"],
    )


def downgrade() -> None:
    op.drop_index("ix_photos_project_camera", table_name="photos")
    op.drop_index("ix_photos_project_gps", table_name="photos")
    op.drop_column("photos", "orientation")
    op.drop_column("photos", "iso")
    op.drop_column("photos", "exposure_time")
    op.drop_column("photos", "aperture")
    op.drop_column("photos", "focal_length")
    op.drop_column("photos", "lens_model")
    op.drop_column("photos", "camera_model")
    op.drop_column("photos", "camera_make")
    op.drop_column("photos", "gps_altitude")
    op.drop_column("photos", "gps_longitude")
    op.drop_column("photos", "gps_latitude")
    op.drop_index("ix_ai_jobs_project_status", table_name="ai_jobs")
    op.drop_column("ai_jobs", "project_id")
