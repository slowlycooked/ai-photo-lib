from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models.photo import Photo
from ..models.photo_quarantine import PhotoQuarantineItem, ProjectPhotoQuarantineSettings
from ..models.project import Project


class PhotoQuarantineError(RuntimeError):
    pass


class PhotoQuarantineConflict(PhotoQuarantineError):
    pass


@dataclass(frozen=True)
class QuarantineMoveResult:
    item: PhotoQuarantineItem
    moved: bool


class PhotoQuarantineService:
    def __init__(self, db: Session, *, root: Optional[Path] = None) -> None:
        self._db = db
        configured_root = root or Path(settings.photo_quarantine_root)
        self._root = configured_root.expanduser().resolve()

    def get_or_create_settings(self, project_id: int) -> ProjectPhotoQuarantineSettings:
        row = (
            self._db.query(ProjectPhotoQuarantineSettings)
            .filter(ProjectPhotoQuarantineSettings.project_id == project_id)
            .first()
        )
        if row is not None:
            return row
        row = ProjectPhotoQuarantineSettings(project_id=project_id)
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def update_settings(
        self, project_id: int, values: dict[str, object]
    ) -> ProjectPhotoQuarantineSettings:
        row = self.get_or_create_settings(project_id)
        for field in (
            "enabled",
            "dry_run",
            "start_hour",
            "end_hour",
            "timezone",
            "model_name",
            "retention_days",
        ):
            if field in values:
                setattr(row, field, values[field])
        row.updated_at = _now()
        self._db.commit()
        self._db.refresh(row)
        return row

    def list_items(
        self,
        *,
        project_id: int,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[PhotoQuarantineItem]]:
        query = self._db.query(PhotoQuarantineItem).filter(
            PhotoQuarantineItem.project_id == project_id
        )
        if status:
            statuses = [value.strip() for value in status.split(",") if value.strip()]
            if statuses:
                query = query.filter(PhotoQuarantineItem.status.in_(statuses))
        total = query.count()
        items = (
            query.order_by(
                PhotoQuarantineItem.created_at.desc(),
                PhotoQuarantineItem.id.desc(),
            )
            .offset(max(0, offset))
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return total, items

    def get_item(self, *, project_id: int, item_id: int) -> PhotoQuarantineItem:
        item = (
            self._db.query(PhotoQuarantineItem)
            .filter(
                PhotoQuarantineItem.id == item_id,
                PhotoQuarantineItem.project_id == project_id,
            )
            .first()
        )
        if item is None:
            raise PhotoQuarantineError("Quarantine item not found")
        return item

    def move(self, *, project_id: int, item_id: int) -> QuarantineMoveResult:
        item, photo, project = self._load_item_photo_project(project_id, item_id)
        if item.status == "quarantined":
            return QuarantineMoveResult(item=item, moved=False)
        if item.status not in {"review", "moving", "move_failed"}:
            raise PhotoQuarantineConflict(
                f"Item status {item.status!r} cannot be moved to quarantine"
            )

        source = self._validated_original_path(project, item.original_path, must_exist=False)
        destination = (
            self._validated_quarantine_path(item.quarantine_path)
            if item.quarantine_path
            else self._destination(item, source.name)
        )
        if not source.exists() and destination.exists():
            destination_hash = _sha256(destination)
            expected_hash = item.content_hash or photo.file_hash
            if expected_hash and destination_hash != expected_hash:
                raise PhotoQuarantineConflict(
                    "Recovered quarantine file hash does not match the audit record"
                )
            return QuarantineMoveResult(
                item=self._finalize_move(item.id, destination_hash),
                moved=False,
            )
        if not source.exists():
            raise PhotoQuarantineError("Original file is missing")

        source_hash = _sha256(source)
        expected_hash = item.content_hash or photo.file_hash
        if expected_hash and source_hash != expected_hash:
            raise PhotoQuarantineConflict("Original file hash changed since classification")

        item.status = "moving"
        item.quarantine_path = str(destination)
        item.content_hash = source_hash
        item.previous_photo_status = item.previous_photo_status or photo.status
        item.last_error = None
        item.updated_at = _now()
        self._db.commit()

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if _sha256(destination) != source_hash:
                    raise PhotoQuarantineConflict("Quarantine destination already exists")
                if source.exists():
                    raise PhotoQuarantineConflict("Source and destination both exist")
            elif source.exists():
                os.replace(source, destination)
            else:
                raise PhotoQuarantineError("Original file disappeared before move")

            if _sha256(destination) != source_hash:
                raise PhotoQuarantineError("Quarantine file hash verification failed")
        except Exception as exc:
            item = self._reload_item(item.id)
            item.status = "move_failed"
            item.last_error = str(exc)
            item.updated_at = _now()
            self._db.commit()
            raise

        return QuarantineMoveResult(
            item=self._finalize_move(item.id, source_hash),
            moved=True,
        )

    def restore(self, *, project_id: int, item_id: int) -> PhotoQuarantineItem:
        item, photo, project = self._load_item_photo_project(project_id, item_id)
        if item.status == "restored":
            return item
        if item.status not in {
            "quarantined",
            "restoring",
            "restore_conflict",
            "restore_failed",
        }:
            raise PhotoQuarantineConflict(f"Item status {item.status!r} cannot be restored")
        if not item.quarantine_path:
            raise PhotoQuarantineError("Quarantine path is missing")

        source = self._validated_quarantine_path(item.quarantine_path)
        destination = self._validated_original_path(project, item.original_path, must_exist=False)
        expected_hash = item.content_hash

        if destination.exists() and not source.exists():
            destination_hash = _sha256(destination)
            if expected_hash and destination_hash != expected_hash:
                raise PhotoQuarantineConflict(
                    "File at original path does not match the quarantined photo"
                )
            return self._finalize_restore(item.id)
        if destination.exists():
            item.status = "restore_conflict"
            item.last_error = "Original path is occupied; no file was overwritten"
            item.updated_at = _now()
            self._db.commit()
            raise PhotoQuarantineConflict(item.last_error)
        if not source.exists():
            item.status = "restore_failed"
            item.last_error = "Quarantine file is missing"
            item.updated_at = _now()
            self._db.commit()
            raise PhotoQuarantineError(item.last_error)
        if expected_hash and _sha256(source) != expected_hash:
            raise PhotoQuarantineConflict("Quarantine file hash does not match the audit record")

        item.status = "restoring"
        item.last_error = None
        item.updated_at = _now()
        self._db.commit()
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            if expected_hash and _sha256(destination) != expected_hash:
                raise PhotoQuarantineError("Restored file hash verification failed")
        except Exception as exc:
            item = self._reload_item(item.id)
            item.status = "restore_failed"
            item.last_error = str(exc)
            item.updated_at = _now()
            self._db.commit()
            raise

        return self._finalize_restore(item.id)

    def confirm_deleted(self, *, project_id: int, item_id: int) -> PhotoQuarantineItem:
        item, _photo, _project = self._load_item_photo_project(project_id, item_id)
        if item.status == "deleted_confirmed":
            return item
        if not item.quarantine_path:
            raise PhotoQuarantineConflict("Item has never been moved to quarantine")
        path = self._validated_quarantine_path(item.quarantine_path)
        if path.exists():
            raise PhotoQuarantineConflict(
                "Quarantine file still exists; this endpoint never deletes files"
            )
        now = _now()
        item.status = "deleted_confirmed"
        item.deleted_confirmed_at = now
        item.updated_at = now
        item.last_error = None
        self._db.commit()
        self._db.refresh(item)
        return item

    def _load_item_photo_project(
        self, project_id: int, item_id: int
    ) -> tuple[PhotoQuarantineItem, Photo, Project]:
        item = (
            self._db.query(PhotoQuarantineItem)
            .filter(
                PhotoQuarantineItem.id == item_id,
                PhotoQuarantineItem.project_id == project_id,
            )
            .first()
        )
        if item is None:
            raise PhotoQuarantineError("Quarantine item not found")
        photo = (
            self._db.query(Photo)
            .filter(Photo.id == item.photo_id, Photo.project_id == project_id)
            .first()
        )
        project = self._db.query(Project).filter(Project.id == project_id).first()
        if photo is None or project is None:
            raise PhotoQuarantineError("Quarantine item references missing project data")
        return item, photo, project

    def _reload_item(self, item_id: int) -> PhotoQuarantineItem:
        self._db.expire_all()
        item = self._db.query(PhotoQuarantineItem).filter(PhotoQuarantineItem.id == item_id).first()
        if item is None:
            raise PhotoQuarantineError("Quarantine item not found")
        return item

    def _finalize_move(self, item_id: int, content_hash: str) -> PhotoQuarantineItem:
        item = self._reload_item(item_id)
        photo = self._db.query(Photo).filter(Photo.id == item.photo_id).first()
        if photo is None:
            raise PhotoQuarantineError("Photo record disappeared after move")
        now = _now()
        photo.status = "quarantined"
        photo.deleted_at = now
        photo.updated_at = now
        item.status = "quarantined"
        item.content_hash = content_hash
        item.moved_at = item.moved_at or now
        item.last_error = None
        item.updated_at = now
        self._db.commit()
        self._db.refresh(item)
        return item

    def _finalize_restore(self, item_id: int) -> PhotoQuarantineItem:
        item = self._reload_item(item_id)
        photo = self._db.query(Photo).filter(Photo.id == item.photo_id).first()
        if photo is None:
            raise PhotoQuarantineError("Photo record disappeared during restore")
        now = _now()
        photo.status = item.previous_photo_status or "indexed"
        photo.deleted_at = None
        photo.updated_at = now
        item.status = "restored"
        item.restored_at = item.restored_at or now
        item.last_error = None
        item.updated_at = now
        self._db.commit()
        self._db.refresh(item)
        return item

    def _destination(self, item: PhotoQuarantineItem, file_name: str) -> Path:
        if item.id is None:
            raise PhotoQuarantineError("Quarantine item must be persisted before moving")
        day = _now().date().isoformat()
        path = self._root / f"project-{item.project_id}" / day / str(item.id) / file_name
        return _ensure_within(path, self._root)

    def _validated_original_path(
        self, project: Project, raw_path: str, *, must_exist: bool = True
    ) -> Path:
        library = Path(project.photo_library_path).expanduser().resolve()
        path = Path(raw_path).expanduser().resolve(strict=must_exist)
        return _ensure_within(path, library)

    def _validated_quarantine_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser().resolve(strict=False)
        return _ensure_within(path, self._root)


def _ensure_within(path: Path, root: Path) -> Path:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PhotoQuarantineError(f"Path escapes managed root: {path}") from exc
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)
