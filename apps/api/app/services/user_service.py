from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models.project import Project
from ..models.user import AIServiceProfile, ProjectMembership, User
from ..schemas.user import (
    AIServiceProfileCreate,
    AIServiceProfileResponse,
    AIServiceProfileUpdate,
    CurrentUser,
    ProjectMembershipResponse,
    ProjectMembershipUpsert,
    UserProjectAccessResponse,
    UserProjectAccessUpsert,
    UserCreate,
    UserUpdate,
)

_PASSWORD_ALGO = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 260_000


class UserNotFoundError(RuntimeError):
    pass


class DuplicateUserError(RuntimeError):
    pass


class UserDeletionError(RuntimeError):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        _PASSWORD_ITERATIONS,
    ).hex()
    return f"{_PASSWORD_ALGO}${_PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iterations_raw, salt, expected = password_hash.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError:
        return False
    if algo != _PASSWORD_ALGO:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    ).hex()
    return secrets.compare_digest(actual, expected)


def capabilities_for_role(role: str) -> list[str]:
    if role == "admin":
        return [
            "system:read",
            "system:write",
            "users:manage",
            "projects:manage",
            "projects:read",
            "projects:write",
        ]
    if role == "project_manager":
        return ["projects:read", "projects:write"]
    return ["projects:read"]


@dataclass
class UserService:
    db: Session

    def get_by_username(self, username: str) -> User | None:
        return (
            self.db.query(User)
            .filter(User.username == username, User.status == "active")
            .first()
        )

    def list_users(self) -> list[User]:
        return self.db.query(User).order_by(User.username.asc()).all()

    def create_user(self, body: UserCreate) -> User:
        if self.db.query(User).filter(User.username == body.username).first():
            raise DuplicateUserError("User already exists")
        row = User(
            username=body.username,
            password_hash=hash_password(body.password),
            display_name=body.display_name,
            role=body.role,
            status=body.status,
        )
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateUserError("User already exists") from exc
        self.db.refresh(row)
        return row

    def update_user(self, user_id: int, body: UserUpdate) -> User:
        row = self.db.query(User).filter(User.id == user_id).first()
        if row is None:
            raise UserNotFoundError("User not found")
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return row

    def reset_password(self, user_id: int, password: str) -> User:
        row = self.db.query(User).filter(User.id == user_id).first()
        if row is None:
            raise UserNotFoundError("User not found")
        row.password_hash = hash_password(password)
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_user(self, user_id: int) -> None:
        row = self.db.query(User).filter(User.id == user_id).first()
        if row is None:
            raise UserNotFoundError("User not found")
        self.db.query(ProjectMembership).filter(ProjectMembership.user_id == user_id).delete(
            synchronize_session=False
        )
        self.db.delete(row)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise UserDeletionError("User cannot be deleted") from exc

    def list_user_project_access(self, user_id: int) -> list[UserProjectAccessResponse]:
        rows = (
            self.db.query(ProjectMembership, Project)
            .join(Project, Project.id == ProjectMembership.project_id)
            .filter(ProjectMembership.user_id == user_id, Project.deleted_at.is_(None))
            .order_by(Project.is_default.desc(), Project.name.asc())
            .all()
        )
        return [
            UserProjectAccessResponse(
                project_id=project.id,
                project_name=project.name,
                project_description=project.description,
                project_role=membership.project_role,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
            for membership, project in rows
        ]

    def upsert_user_project_access(
        self,
        user_id: int,
        project_id: int,
        body: UserProjectAccessUpsert,
    ) -> list[UserProjectAccessResponse]:
        membership = (
            self.db.query(ProjectMembership)
            .filter(
                ProjectMembership.user_id == user_id,
                ProjectMembership.project_id == project_id,
            )
            .first()
        )
        if membership is None:
            membership = ProjectMembership(
                user_id=user_id,
                project_id=project_id,
                project_role=body.project_role,
            )
            self.db.add(membership)
        else:
            membership.project_role = body.project_role
            membership.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(membership)
        return self.list_user_project_access(user_id)

    def delete_user_project_access(self, user_id: int, project_id: int) -> list[UserProjectAccessResponse]:
        membership = (
            self.db.query(ProjectMembership)
            .filter(
                ProjectMembership.user_id == user_id,
                ProjectMembership.project_id == project_id,
            )
            .first()
        )
        if membership is not None:
            self.db.delete(membership)
            self.db.commit()
        return self.list_user_project_access(user_id)

    def authenticate(self, username: str, password: str) -> User | None:
        row = self.get_by_username(username)
        if row is None:
            return None
        if not verify_password(password, row.password_hash):
            return None
        return row

    def user_can_access_project(self, user: CurrentUser, project_id: int) -> bool:
        if user.role == "admin":
            return True
        if user.id is None:
            return False
        return (
            self.db.query(ProjectMembership)
            .filter(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user.id,
            )
            .first()
            is not None
        )

    def user_can_manage_project(self, user: CurrentUser, project_id: int) -> bool:
        if user.role == "admin":
            return True
        if user.id is None or user.role != "project_manager":
            return False
        return (
            self.db.query(ProjectMembership)
            .filter(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user.id,
                ProjectMembership.project_role == "manager",
            )
            .first()
            is not None
        )


@dataclass
class ProjectMembershipService:
    db: Session

    def list_project_members(self, project_id: int) -> list[ProjectMembershipResponse]:
        rows = (
            self.db.query(ProjectMembership, User)
            .join(User, User.id == ProjectMembership.user_id)
            .filter(ProjectMembership.project_id == project_id)
            .order_by(User.username.asc())
            .all()
        )
        return [
            ProjectMembershipResponse(
                id=membership.id,
                project_id=membership.project_id,
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                project_role=membership.project_role,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
            for membership, user in rows
        ]

    def upsert_project_member(
        self,
        project_id: int,
        body: ProjectMembershipUpsert,
    ) -> ProjectMembership:
        row = (
            self.db.query(ProjectMembership)
            .filter(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == body.user_id,
            )
            .first()
        )
        if row is None:
            row = ProjectMembership(
                project_id=project_id,
                user_id=body.user_id,
                project_role=body.project_role,
            )
            self.db.add(row)
        else:
            row.project_role = body.project_role
            row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_project_member(self, project_id: int, user_id: int) -> None:
        row = (
            self.db.query(ProjectMembership)
            .filter(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
            .first()
        )
        if row is not None:
            self.db.delete(row)
            self.db.commit()


@dataclass
class AIServiceProfileService:
    db: Session

    def list_profiles(self, *, admin: bool) -> list[AIServiceProfileResponse]:
        query = self.db.query(AIServiceProfile)
        if not admin:
            query = query.filter(
                AIServiceProfile.enabled.is_(True),
                AIServiceProfile.visible_to_projects.is_(True),
            )
        return [
            self._to_response(row, admin=admin)
            for row in query.order_by(AIServiceProfile.capability.asc(), AIServiceProfile.name.asc()).all()
        ]

    def create_profile(self, body: AIServiceProfileCreate) -> AIServiceProfileResponse:
        row = AIServiceProfile(**body.model_dump())
        self.db.add(row)
        self._apply_default_constraint(row)
        self.db.commit()
        self.db.refresh(row)
        return self._to_response(row, admin=True)

    def import_from_environment(self) -> list[AIServiceProfileResponse]:
        candidates = [
            {
                "name": "Env Vision Model",
                "capability": "vision",
                "provider": "llama-server",
                "endpoint_url": f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                "api_key": settings.openai_api_key or None,
                "model_name": settings.openai_vision_model,
                "timeout_seconds": 60,
            },
            {
                "name": "Env Embedding Model",
                "capability": "embedding",
                "provider": "openai-compatible",
                "endpoint_url": settings.embedding_base_url or settings.openai_base_url,
                "api_key": settings.embedding_api_key or settings.openai_api_key or None,
                "model_name": settings.embedding_model or settings.openai_model,
                "timeout_seconds": settings.embedding_timeout_seconds,
            },
            {
                "name": "Env Query Planner Model",
                "capability": "query_planner",
                "provider": "llama-server",
                "endpoint_url": settings.query_planner_base_url,
                "api_key": settings.openai_api_key or None,
                "model_name": settings.query_planner_alias,
                "timeout_seconds": 20,
            },
        ]
        imported: list[AIServiceProfile] = []
        for candidate in candidates:
            endpoint_url = str(candidate["endpoint_url"] or "").strip()
            model_name = str(candidate["model_name"] or "").strip()
            if not endpoint_url or not model_name:
                continue
            row = (
                self.db.query(AIServiceProfile)
                .filter(
                    AIServiceProfile.capability == candidate["capability"],
                    AIServiceProfile.endpoint_url == endpoint_url,
                    AIServiceProfile.model_name == model_name,
                )
                .first()
            )
            if row is None:
                row = AIServiceProfile(
                    name=str(candidate["name"]),
                    capability=str(candidate["capability"]),
                    provider=str(candidate["provider"]),
                    endpoint_url=endpoint_url,
                    api_key=candidate["api_key"],
                    model_name=model_name,
                    timeout_seconds=int(candidate["timeout_seconds"]),
                    enabled=True,
                    visible_to_projects=True,
                    is_default=True,
                )
                self.db.add(row)
                self.db.flush()
            else:
                row.name = row.name or str(candidate["name"])
                row.provider = str(candidate["provider"])
                row.api_key = candidate["api_key"]
                row.timeout_seconds = int(candidate["timeout_seconds"])
                row.enabled = True
                row.visible_to_projects = True
                row.is_default = True
                row.updated_at = datetime.now(timezone.utc)
            self._apply_default_constraint(row)
            imported.append(row)
        self.db.commit()
        for row in imported:
            self.db.refresh(row)
        return [self._to_response(row, admin=True) for row in imported]

    def update_profile(
        self,
        profile_id: int,
        body: AIServiceProfileUpdate,
    ) -> AIServiceProfileResponse:
        row = self.db.query(AIServiceProfile).filter(AIServiceProfile.id == profile_id).first()
        if row is None:
            raise UserNotFoundError("AI service profile not found")
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self._apply_default_constraint(row)
        self.db.commit()
        self.db.refresh(row)
        return self._to_response(row, admin=True)

    def _apply_default_constraint(self, row: AIServiceProfile) -> None:
        if not row.is_default:
            return
        self.db.query(AIServiceProfile).filter(
            AIServiceProfile.capability == row.capability,
            AIServiceProfile.id != row.id,
        ).update({"is_default": False})

    def _to_response(self, row: AIServiceProfile, *, admin: bool) -> AIServiceProfileResponse:
        return AIServiceProfileResponse(
            id=row.id,
            name=row.name,
            capability=row.capability,
            provider=row.provider,
            endpoint_url=row.endpoint_url if admin else None,
            has_api_key=bool(row.api_key),
            model_name=row.model_name,
            model_params_json=row.model_params_json,
            timeout_seconds=row.timeout_seconds,
            enabled=row.enabled,
            visible_to_projects=row.visible_to_projects,
            is_default=row.is_default,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
