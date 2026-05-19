#!/usr/bin/env python3
"""
Alembic migration stamp script.
This script marks the current Alembic head as applied without running migrations,
useful when the database schema already exists.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text, inspect
from app.config import settings

def stamp_migrations():
    """Mark the current Alembic head as applied in the database."""
    engine = create_engine(str(settings.database_url))
    
    # Check if tables already exist
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if 'photos' not in tables or 'project_folders' not in tables:
        print("ERROR: Database schema not fully initialized. Run migrations first.")
        return False
    
    config = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
    config.set_main_option("sqlalchemy.url", str(settings.database_url))

    command.stamp(config, "head")

    print("\n✓ Current Alembic head marked as applied")
    return True

if __name__ == '__main__':
    success = stamp_migrations()
    sys.exit(0 if success else 1)
