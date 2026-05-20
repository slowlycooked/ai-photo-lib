from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

from ..database import Base

class AppSettings(Base):
    __tablename__ = "app_settings"
    key = Column(String(64), primary_key=True, nullable=False)
    value_json = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
