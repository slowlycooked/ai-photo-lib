from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Double, Index, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PhotoLocationCache(Base):
    __tablename__ = "photo_location_cache"
    __table_args__ = (
        sa.UniqueConstraint("location_key", name="uq_photo_location_cache_key"),
        Index(
            "ix_photo_location_cache_lat_lon",
            "latitude_rounded",
            "longitude_rounded",
        ),
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    location_key: Mapped[str] = mapped_column(Text, nullable=False)
    latitude_rounded: Mapped[float] = mapped_column(Double, nullable=False)
    longitude_rounded: Mapped[float] = mapped_column(Double, nullable=False)
    country_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    formatted_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False,
    )
