from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Double, ForeignKey, Index, Integer, JSON, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "file_path", name="uq_photos_project_file_path"),
        Index("ix_photos_project_taken_at", "project_id", "taken_at"),
        Index("ix_photos_project_status", "project_id", "status"),
        Index("ix_photos_project_status_deleted_at", "project_id", "status", "deleted_at"),
        Index("ix_photos_project_folder_taken_at", "project_id", "folder_id", "taken_at"),
        Index("ix_photos_project_country_name", "project_id", "country_name"),
        Index("ix_photos_project_admin1", "project_id", "admin1"),
        Index("ix_photos_project_city", "project_id", "city"),
        Index("ix_photos_project_district", "project_id", "district"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    taken_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    exif: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    # ── Structured GPS ──────────────────────────────────────────────────────────
    gps_latitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    gps_longitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    gps_altitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    formatted_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location_resolved_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    # ── Camera / lens ───────────────────────────────────────────────────────────
    camera_make: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    camera_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lens_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    focal_length: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aperture: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exposure_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    iso: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    orientation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # ── Folder tree ────────────────────────────────────────────────────────────
    folder_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("project_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    relative_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    folder_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ────────────────────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)


_active_library_predicate = sa.and_(
    Photo.deleted_at.is_(None),
    Photo.status != "quarantined",
)

Index(
    "ix_photos_library_browse",
    Photo.project_id,
    Photo.taken_at.desc().nullslast(),
    Photo.created_at.desc(),
    Photo.id.desc(),
    postgresql_where=_active_library_predicate,
).ddl_if(dialect="postgresql")

Index(
    "ix_photos_folder_library_browse",
    Photo.project_id,
    Photo.folder_id,
    Photo.taken_at.desc().nullslast(),
    Photo.created_at.desc(),
    Photo.id.desc(),
    postgresql_where=_active_library_predicate,
).ddl_if(dialect="postgresql")
