from __future__ import annotations

from typing import Dict, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models.folder import ProjectFolder
from ..models.photo import Photo


def ensure_folder_path(db: Session, project_id: int, folder_path: str, cache: Dict[str, ProjectFolder]) -> ProjectFolder:
    if folder_path in cache:
        return cache[folder_path]

    if folder_path == "":
        parent_id = None
        name = ""
        depth = 0
    else:
        parent_path = folder_path.rsplit("/", 1)[0] if "/" in folder_path else ""
        parent = ensure_folder_path(db, project_id, parent_path, cache)
        parent_id = parent.id
        name = folder_path.rsplit("/", 1)[-1]
        depth = parent.depth + 1

    folder = (
        db.query(ProjectFolder)
        .filter(
            ProjectFolder.project_id == project_id,
            ProjectFolder.relative_path == folder_path,
            ProjectFolder.deleted_at.is_(None),
        )
        .first()
    )
    if not folder:
        folder = ProjectFolder(
            project_id=project_id,
            parent_id=parent_id,
            name=name,
            relative_path=folder_path,
            depth=depth,
        )
        db.add(folder)
        db.flush()
    cache[folder_path] = folder
    return folder


def recompute_project_folder_counts(db: Session, project_id: int) -> None:
    # 1. 统计每个文件夹直接照片数
    direct_counts = dict(
        db.query(Photo.folder_id, func.count(Photo.id))
        .filter(Photo.project_id == project_id, Photo.deleted_at.is_(None))
        .group_by(Photo.folder_id)
        .all()
    )
    # 2. 获取所有文件夹
    folders = db.query(ProjectFolder).filter(ProjectFolder.project_id == project_id, ProjectFolder.deleted_at.is_(None)).all()
    folder_map = {f.id: f for f in folders}
    # 3. 初始化计数
    for f in folders:
        f.photo_count_direct = direct_counts.get(f.id, 0)
        f.photo_count_recursive = f.photo_count_direct
    # 4. 按 depth 降序遍历，递归累加
    for f in sorted(folders, key=lambda x: -x.depth):
        if f.parent_id and f.parent_id in folder_map:
            folder_map[f.parent_id].photo_count_recursive += f.photo_count_recursive
    db.flush()


def apply_folder_filter(query, db: Session, project_id: int, folder_id: Optional[int], folder_scope: str):
    if not folder_id:
        return query
    folder = db.query(ProjectFolder).filter(
        ProjectFolder.id == folder_id,
        ProjectFolder.project_id == project_id,
        ProjectFolder.deleted_at.is_(None),
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder_scope == "direct":
        return query.filter(Photo.folder_id == folder.id)
    if folder.relative_path == "":
        return query
    descendants = db.query(ProjectFolder.id).filter(
        ProjectFolder.project_id == project_id,
        ProjectFolder.deleted_at.is_(None),
        or_(
            ProjectFolder.relative_path == folder.relative_path,
            ProjectFolder.relative_path.like(folder.relative_path + "/%"),
        ),
    )
    return query.filter(Photo.folder_id.in_(descendants))
