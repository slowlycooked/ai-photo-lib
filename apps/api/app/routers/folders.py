from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.folder import FolderTreeResponse, FolderBreadcrumbResponse
from ..services.project_folders_app_service import ProjectFoldersAppService

router = APIRouter(prefix="/projects", tags=["folders"])

@router.get("/{project_id}/folders/tree", response_model=FolderTreeResponse)
def get_folder_tree(
    project_id: int,
    db: Session = Depends(get_db),
):
    """获取项目的完整文件夹树"""
    service = ProjectFoldersAppService(db)
    return service.get_tree(project_id)


@router.get("/{project_id}/folders/{folder_id}/breadcrumb", response_model=FolderBreadcrumbResponse)
def get_folder_breadcrumb(
    project_id: int,
    folder_id: int,
    db: Session = Depends(get_db),
):
    """获取文件夹面包屑路径"""
    service = ProjectFoldersAppService(db)
    return service.get_breadcrumb(project_id, folder_id)


@router.post("/{project_id}/folders/recompute-counts")
def recompute_folder_counts(
    project_id: int,
    db: Session = Depends(get_db),
):
    """重新计算项目所有文件夹的照片计数"""
    service = ProjectFoldersAppService(db)
    return service.recompute_counts(project_id)
