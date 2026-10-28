from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, ForeignKey, Integer, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ProjectLibraryPath(Base):
    """A single photo library root mounted under a project (1 project : N paths).

    ``position`` keeps a stable ordering; ``position == 0`` is the primary path
    mirrored into ``projects.photo_library_path`` for backward compatibility.
    """

    __tablename__ = "project_library_paths"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "path", name="uq_project_library_paths_project_path"),
        sa.Index("ix_project_library_paths_project_position", "project_id", "position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
