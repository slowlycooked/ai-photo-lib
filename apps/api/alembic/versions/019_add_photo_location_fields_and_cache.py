"""add structured photo location fields and cache table

Revision ID: 019
Revises: 018
Create Date: 2026-05-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018_add_search_quality_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("country_code", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("country_name", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("admin1", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("admin2", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("district", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("formatted_address", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("location_source", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("location_resolved_at", sa.TIMESTAMP(), nullable=True))

    op.create_index("ix_photos_project_country_name", "photos", ["project_id", "country_name"])
    op.create_index("ix_photos_project_admin1", "photos", ["project_id", "admin1"])
    op.create_index("ix_photos_project_city", "photos", ["project_id", "city"])
    op.create_index("ix_photos_project_district", "photos", ["project_id", "district"])

    op.create_table(
        "photo_location_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("location_key", sa.Text(), nullable=False),
        sa.Column("latitude_rounded", sa.Double(), nullable=False),
        sa.Column("longitude_rounded", sa.Double(), nullable=False),
        sa.Column("country_code", sa.Text(), nullable=True),
        sa.Column("country_name", sa.Text(), nullable=True),
        sa.Column("admin1", sa.Text(), nullable=True),
        sa.Column("admin2", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("district", sa.Text(), nullable=True),
        sa.Column("formatted_address", sa.Text(), nullable=True),
        sa.Column("location_source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("location_key", name="uq_photo_location_cache_key"),
    )
    op.create_index(
        "ix_photo_location_cache_lat_lon",
        "photo_location_cache",
        ["latitude_rounded", "longitude_rounded"],
    )


def downgrade() -> None:
    op.drop_index("ix_photo_location_cache_lat_lon", table_name="photo_location_cache")
    op.drop_table("photo_location_cache")
    op.drop_index("ix_photos_project_district", table_name="photos")
    op.drop_index("ix_photos_project_city", table_name="photos")
    op.drop_index("ix_photos_project_admin1", table_name="photos")
    op.drop_index("ix_photos_project_country_name", table_name="photos")
    op.drop_column("photos", "location_resolved_at")
    op.drop_column("photos", "location_source")
    op.drop_column("photos", "formatted_address")
    op.drop_column("photos", "district")
    op.drop_column("photos", "city")
    op.drop_column("photos", "admin2")
    op.drop_column("photos", "admin1")
    op.drop_column("photos", "country_name")
    op.drop_column("photos", "country_code")
