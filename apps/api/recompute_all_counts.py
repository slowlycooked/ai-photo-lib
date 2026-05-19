#!/usr/bin/env python3
"""
重新计算所有项目的文件夹计数
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models.project import Project
from app.services.folder_service import recompute_project_folder_counts

# Create engine and session
engine = create_engine(str(settings.database_url))
Session = sessionmaker(bind=engine)

def recompute_all():
    """Recompute folder counts for all projects."""
    db = Session()
    try:
        # Get all projects
        projects = db.query(Project).filter(Project.deleted_at.is_(None)).all()
        
        for project in projects:
            print(f"重新计算项目 {project.id} ({project.name}) 的文件夹计数...")
            try:
                recompute_project_folder_counts(db, project.id)
                db.commit()
                print(f"  ✓ 成功")
            except Exception as e:
                print(f"  ✗ 失败: {e}")
                db.rollback()
        
        print("\n✓ 所有项目的文件夹计数已重新计算")
        return True
    except Exception as e:
        print(f"✗ 错误: {e}")
        return False
    finally:
        db.close()

if __name__ == '__main__':
    success = recompute_all()
    sys.exit(0 if success else 1)
