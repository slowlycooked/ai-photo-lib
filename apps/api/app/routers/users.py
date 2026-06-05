from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api.deps import require_admin, require_project
from ..database import get_db
from ..models.project import Project
from ..schemas.user import (
    ProjectMembershipListResponse,
    ProjectMembershipUpsert,
    ResetPasswordRequest,
    UserCreate,
    UserListResponse,
    UserProjectAccessListResponse,
    UserProjectAccessUpsert,
    UserResponse,
    UserUpdate,
)
from ..services.user_service import (
    DuplicateUserError,
    ProjectMembershipService,
    UserNotFoundError,
    UserService,
    UserDeletionError,
)

router = APIRouter(tags=["users"])


@router.get("/users", response_model=UserListResponse)
def list_users(
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = UserService(db).list_users()
    return UserListResponse(total=len(users), items=users)


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    body: UserCreate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return UserService(db).create_user(body)
    except DuplicateUserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: UserUpdate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return UserService(db).update_user(user_id, body)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
def reset_user_password(
    user_id: int,
    body: ResetPasswordRequest,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return UserService(db).reset_password(user_id, body.password)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        UserService(db).delete_user(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UserDeletionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/users/{user_id}/projects", response_model=UserProjectAccessListResponse)
def list_user_project_access(
    user_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = UserService(db).list_user_project_access(user_id)
    return UserProjectAccessListResponse(total=len(rows), items=rows)


@router.put("/users/{user_id}/projects/{project_id}", response_model=UserProjectAccessListResponse)
def upsert_user_project_access(
    user_id: int,
    project_id: int,
    body: UserProjectAccessUpsert,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = UserService(db).upsert_user_project_access(user_id, project_id, body)
    return UserProjectAccessListResponse(total=len(rows), items=rows)


@router.delete("/users/{user_id}/projects/{project_id}", response_model=UserProjectAccessListResponse)
def delete_user_project_access(
    user_id: int,
    project_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = UserService(db).delete_user_project_access(user_id, project_id)
    return UserProjectAccessListResponse(total=len(rows), items=rows)


@router.get("/projects/{project_id}/members", response_model=ProjectMembershipListResponse)
def list_project_members(
    project: Project = Depends(require_project),
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = ProjectMembershipService(db).list_project_members(project.id)
    return ProjectMembershipListResponse(total=len(rows), items=rows)


@router.put("/projects/{project_id}/members", response_model=ProjectMembershipListResponse)
def upsert_project_member(
    project_id: int,
    body: ProjectMembershipUpsert,
    project: Project = Depends(require_project),
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ProjectMembershipService(db).upsert_project_member(project.id, body)
    rows = ProjectMembershipService(db).list_project_members(project_id)
    return ProjectMembershipListResponse(total=len(rows), items=rows)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def delete_project_member(
    user_id: int,
    project: Project = Depends(require_project),
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ProjectMembershipService(db).delete_project_member(project.id, user_id)
