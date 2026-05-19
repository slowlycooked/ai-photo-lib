from sqlalchemy import Column, BigInteger, Integer, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class ProjectFolder(Base):
    __tablename__ = "project_folders"

    id = Column(BigInteger, primary_key=True)
    project_id = Column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(BigInteger, ForeignKey("project_folders.id", ondelete="CASCADE"), nullable=True)
    name = Column(Text, nullable=False)
    relative_path = Column(Text, nullable=False)
    depth = Column(Integer, nullable=False, default=0)
    photo_count_direct = Column(Integer, nullable=False, default=0)
    photo_count_recursive = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    parent = relationship("ProjectFolder", remote_side=[id], backref="children", foreign_keys=[parent_id])

    __table_args__ = (
        UniqueConstraint("project_id", "relative_path", name="uq_project_folders_project_path"),
        {
            "sqlite_autoincrement": True,
            "sqlite_with_rowid": True,
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
        },
    )
