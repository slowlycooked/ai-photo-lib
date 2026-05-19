from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.folder import ProjectFolder
from ..models.project import Project
from ..schemas.folder import FolderNode, FolderTreeResponse, FolderBreadcrumbResponse, FolderBreadcrumbItem

router = APIRouter(prefix="/projects", tags=["folders"])


def build_folder_tree(folder: ProjectFolder) -> FolderNode:
    """递归构建文件夹树"""
    return FolderNode(
        id=folder.id,
        name=folder.name,
        relative_path=folder.relative_path,
        depth=folder.depth,
        photo_count_direct=folder.photo_count_direct,
        photo_count_recursive=folder.photo_count_recursive,
        children=[build_folder_tree(child) for child in folder.children] if folder.children else [],
    )


@router.get("/{project_id}/folders/tree", response_model=FolderTreeResponse)
def get_folder_tree(
    project_id: int,
    db: Session = Depends(get_db),
):
    """获取项目的完整文件夹树"""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    root_folder = (
        db.query(ProjectFolder)
        .filter(
            ProjectFolder.project_id == project_id,
            ProjectFolder.relative_path == "",
            ProjectFolder.deleted_at.is_(None),
        )
        .first()
    )

    root_tree = None
    if root_folder:
        # 获取所有非删除的文件夹，建立树
        all_folders = (
            db.query(ProjectFolder)
            .filter(
                ProjectFolder.project_id == project_id,
                ProjectFolder.deleted_at.is_(None),
            )
            .all()
        )
        # 构建 parent -> children 映射
        folder_map = {f.id: f for f in all_folders}
        for folder in all_folders:
            folder.children = [f for f in all_folders if f.parent_id == folder.id]
        
        root_tree = build_folder_tree(root_folder)

    return FolderTreeResponse(project_id=project_id, root=root_tree)


@router.get("/{project_id}/folders/{folder_id}/breadcrumb", response_model=FolderBreadcrumbResponse)
def get_folder_breadcrumb(
    project_id: int,
    folder_id: int,
    db: Session = Depends(get_db),
):
    """获取文件夹面包屑路径"""
    folder = (
        db.query(ProjectFolder)
        .filter(
            ProjectFolder.id == folder_id,
            ProjectFolder.project_id == project_id,
            ProjectFolder.deleted_at.is_(None),
        )
        .first()
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # 向上遍历获取所有祖先
    items = []
    current = folder
    while current:
        items.insert(0, FolderBreadcrumbItem(
            id=current.id,
            name=current.name,
            relative_path=current.relative_path,
        ))
        if current.parent_id:
            current = db.query(ProjectFolder).filter(
                ProjectFolder.id == current.parent_id
            ).first()
        else:
            break

    return FolderBreadcrumbResponse(items=items)


@router.post("/{project_id}/folders/recompute-counts")
def recompute_folder_counts(
    project_id: int,
    db: Session = Depends(get_db),
):
    """重新计算项目所有文件夹的照片计数"""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        from ..services.folder_service import recompute_project_folder_counts
        recompute_project_folder_counts(db, project_id)
        db.commit()
        return {"message": "Folder counts recomputed successfully", "project_id": project_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to recompute folder counts: {str(e)}")
