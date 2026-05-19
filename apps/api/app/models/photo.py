from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Double, ForeignKey, Integer, JSON, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    file_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
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
