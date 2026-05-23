from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..repositories.unit_of_work import UnitOfWork
from ..schemas.folder import FolderBreadcrumbResponse, FolderTreeResponse
from .folder_service import recompute_project_folder_counts
from .folder_tree_service import build_folder_breadcrumb, build_project_folder_tree


class ProjectFoldersAppService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._uow = UnitOfWork(db)

    def get_tree(self, project_id: int) -> FolderTreeResponse:
        project = self._uow.projects.get_active(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        root = build_project_folder_tree(self._db, project_id)
        return FolderTreeResponse(project_id=project_id, root=root)

    def get_breadcrumb(self, project_id: int, folder_id: int) -> FolderBreadcrumbResponse:
        project = self._uow.projects.get_active(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        items = build_folder_breadcrumb(self._db, project_id, folder_id)
        return FolderBreadcrumbResponse(items=items)

    def recompute_counts(self, project_id: int) -> dict:
        project = self._uow.projects.get_active(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        try:
            recompute_project_folder_counts(self._db, project_id)
            self._uow.commit()
            return {"message": "Folder counts recomputed successfully", "project_id": project_id}
        except Exception as exc:
            self._uow.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to recompute folder counts: {str(exc)}",
            ) from exc
