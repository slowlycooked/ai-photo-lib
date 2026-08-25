from __future__ import annotations

import hashlib
import logging
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
from .photo_cleanup import queue_original_trash_request


logger = logging.getLogger(__name__)


class PhotoQuarantineError(RuntimeError):
    pass


class PhotoQuarantineConflict(PhotoQuarantineError):
    pass


@dataclass(frozen=True)
class QuarantineMoveResult:
    item: PhotoQuarantineItem
    moved: bool


@dataclass(frozen=True)
class QuarantineBatchItemResult:
    item_id: int
    item: Optional[PhotoQuarantineItem] = None
    error_code: Optional[str] = None
    message: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.item is not None


@dataclass(frozen=True)
class QuarantineBatchResult:
    results: list[QuarantineBatchItemResult]

    @property
    def succeeded(self) -> int:
        return sum(1 for result in self.results if result.succeeded)

    @property
    def failed(self) -> int:
        return len(self.results) - self.succeeded


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
        human_label: Optional[str] = None,
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
        if human_label == "UNLABELED":
            query = query.filter(PhotoQuarantineItem.human_label.is_(None))
        elif human_label in {"KEEP", "TRASH"}:
            query = query.filter(PhotoQuarantineItem.human_label == human_label)
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

    def move(
        self,
        *,
        project_id: int,
        item_id: int,
        labeled_by: Optional[str] = None,
    ) -> QuarantineMoveResult:
        item, photo, project = self._load_item_photo_project(project_id, item_id)
        if item.status in {"delete_queued", "quarantined"}:
            if labeled_by:
                self._save_label(item, label="TRASH", labeled_by=labeled_by)
            return QuarantineMoveResult(item=item, moved=False)
        if item.status not in {"review", "moving", "move_failed", "queue_failed"}:
            raise PhotoQuarantineConflict(
                f"Item status {item.status!r} cannot be queued for deletion"
            )

        source = self._validated_original_path(project, item.original_path, must_exist=False)
        if not source.exists():
            raise PhotoQuarantineError("Original file is missing")

        source_hash = _sha256(source)
        expected_hash = item.content_hash or photo.file_hash
        if expected_hash and source_hash != expected_hash:
            raise PhotoQuarantineConflict("Original file hash changed since classification")

        try:
            queue_original_trash_request(
                self._db,
                project_id=project_id,
                photo=photo,
            )
        except Exception as exc:
            item.status = "queue_failed"
            item.last_error = str(exc)
            item.updated_at = _now()
            self._db.commit()
            raise

        queued_item = self._finalize_delete_queue(item.id, source_hash)
        if labeled_by:
            self._save_label(queued_item, label="TRASH", labeled_by=labeled_by)
        return QuarantineMoveResult(item=queued_item, moved=False)

    def restore(
        self,
        *,
        project_id: int,
        item_id: int,
        labeled_by: Optional[str] = None,
    ) -> PhotoQuarantineItem:
        item, photo, project = self._load_item_photo_project(project_id, item_id)
        if item.status == "restored":
            if labeled_by:
                self._save_label(item, label="KEEP", labeled_by=labeled_by)
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
            restored = self._finalize_restore(item.id)
            if labeled_by:
                self._save_label(restored, label="KEEP", labeled_by=labeled_by)
            return restored
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

        restored = self._finalize_restore(item.id)
        if labeled_by:
            self._save_label(restored, label="KEEP", labeled_by=labeled_by)
        return restored

    def confirm_deleted(self, *, project_id: int, item_id: int) -> PhotoQuarantineItem:
        item, _photo, project = self._load_item_photo_project(project_id, item_id)
        if item.status == "deleted_confirmed":
            return item
        if item.quarantine_path:
            path = self._validated_quarantine_path(item.quarantine_path)
        elif item.status == "delete_queued":
            path = self._validated_original_path(
                project, item.original_path, must_exist=False
            )
        else:
            raise PhotoQuarantineConflict("Item has not been queued or quarantined")
        if path.exists():
            raise PhotoQuarantineConflict(
                "Original or quarantined file still exists; this endpoint never deletes files"
            )
        now = _now()
        item.status = "deleted_confirmed"
        item.deleted_confirmed_at = now
        item.updated_at = now
        item.last_error = None
        self._db.commit()
        self._db.refresh(item)
        return item

    def keep(
        self,
        *,
        project_id: int,
        item_id: int,
        labeled_by: Optional[str] = None,
    ) -> PhotoQuarantineItem:
        """Record a human keep decision without moving or deleting the photo."""
        item, photo, _project = self._load_item_photo_project(project_id, item_id)
        if item.status == "kept":
            if labeled_by:
                self._save_label(item, label="KEEP", labeled_by=labeled_by)
            return item
        if item.status not in {"review", "analysis_failed", "move_failed"}:
            raise PhotoQuarantineConflict(
                f"Item status {item.status!r} cannot be marked as kept"
            )
        if photo.status == "quarantined" or photo.deleted_at is not None:
            raise PhotoQuarantineConflict(
                "Photo is already quarantined and must be restored instead"
            )
        item.status = "kept"
        item.decision = "KEEP"
        self._set_label_fields(item, label="KEEP", labeled_by=labeled_by)
        item.last_error = None
        item.updated_at = _now()
        self._db.commit()
        self._db.refresh(item)
        return item

    def label(
        self,
        *,
        project_id: int,
        item_id: int,
        label: str,
        labeled_by: str,
        note: Optional[str] = None,
    ) -> PhotoQuarantineItem:
        item = self.get_item(project_id=project_id, item_id=item_id)
        self._save_label(
            item,
            label=label,
            labeled_by=labeled_by,
            note=note,
        )
        return item

    def calibration_report(self, *, project_id: int) -> dict[str, object]:
        items = self.list_labeled_items(project_id=project_id)
        totals = _empty_confusion_counts()
        categories: dict[str, dict[str, int]] = {}
        for item in items:
            counts = categories.setdefault(
                item.classification, _empty_confusion_counts()
            )
            predicted_trash = bool(
                item.verification_result
                and _is_verified_auto_candidate(
                    item.first_result, item.verification_result
                )
            )
            actual_trash = item.human_label == "TRASH"
            bucket = (
                "true_positive" if predicted_trash and actual_trash
                else "false_positive" if predicted_trash
                else "false_negative" if actual_trash
                else "true_negative"
            )
            for target in (totals, counts):
                target["labeled_total"] += 1
                target["human_trash" if actual_trash else "human_keep"] += 1
                target[bucket] += 1

        precision = _safe_ratio(
            totals["true_positive"],
            totals["true_positive"] + totals["false_positive"],
        )
        recall = _safe_ratio(
            totals["true_positive"],
            totals["true_positive"] + totals["false_negative"],
        )
        false_positive_rate = _safe_ratio(
            totals["false_positive"], totals["human_keep"]
        )
        target_sample_size = 300
        minimum_per_label = 100
        sample_target_met = totals["labeled_total"] >= target_sample_size
        class_balance_met = (
            totals["human_keep"] >= minimum_per_label
            and totals["human_trash"] >= minimum_per_label
        )
        zero_false_positive_met = totals["false_positive"] == 0
        return {
            **totals,
            "precision": precision,
            "recall": recall,
            "false_positive_rate": false_positive_rate,
            "target_sample_size": target_sample_size,
            "minimum_per_label": minimum_per_label,
            "sample_target_met": sample_target_met,
            "class_balance_met": class_balance_met,
            "zero_false_positive_met": zero_false_positive_met,
            "ready_for_auto_move": (
                sample_target_met and class_balance_met and zero_false_positive_met
            ),
            "categories": [
                {"classification": classification, **counts}
                for classification, counts in sorted(categories.items())
            ],
        }

    def list_labeled_items(self, *, project_id: int) -> list[PhotoQuarantineItem]:
        return (
            self._db.query(PhotoQuarantineItem)
            .filter(
                PhotoQuarantineItem.project_id == project_id,
                PhotoQuarantineItem.human_label.in_(["KEEP", "TRASH"]),
            )
            .order_by(
                PhotoQuarantineItem.human_labeled_at.desc(),
                PhotoQuarantineItem.id.desc(),
            )
            .all()
        )

    def batch_action(
        self,
        *,
        project_id: int,
        item_ids: list[int],
        action: str,
        labeled_by: Optional[str] = None,
    ) -> QuarantineBatchResult:
        operations = {
            "KEEP": lambda **kwargs: self.keep(**kwargs, labeled_by=labeled_by),
            "MOVE": lambda **kwargs: self.move(**kwargs, labeled_by=labeled_by).item,
            "RESTORE": lambda **kwargs: self.restore(**kwargs, labeled_by=labeled_by),
            "LABEL_KEEP": lambda **kwargs: self.label(
                **kwargs, label="KEEP", labeled_by=labeled_by or "unknown"
            ),
            "LABEL_TRASH": lambda **kwargs: self.label(
                **kwargs, label="TRASH", labeled_by=labeled_by or "unknown"
            ),
        }
        operation = operations.get(action)
        if operation is None:
            raise ValueError(f"Unsupported quarantine batch action: {action}")

        results: list[QuarantineBatchItemResult] = []
        for item_id in item_ids:
            try:
                item = operation(project_id=project_id, item_id=item_id)
                results.append(QuarantineBatchItemResult(item_id=item_id, item=item))
            except PhotoQuarantineConflict as exc:
                results.append(
                    QuarantineBatchItemResult(
                        item_id=item_id,
                        error_code="conflict",
                        message=str(exc),
                    )
                )
            except PhotoQuarantineError as exc:
                results.append(
                    QuarantineBatchItemResult(
                        item_id=item_id,
                        error_code="invalid_item",
                        message=str(exc),
                    )
                )
            except Exception:  # noqa: BLE001 - a batch must report partial completion
                self._db.rollback()
                logger.exception(
                    "photo_quarantine.batch_item_failed project_id=%d item_id=%d action=%s",
                    project_id,
                    item_id,
                    action,
                )
                results.append(
                    QuarantineBatchItemResult(
                        item_id=item_id,
                        error_code="operation_failed",
                        message="Operation failed; check server logs",
                    )
                )
        return QuarantineBatchResult(results=results)

    def _save_label(
        self,
        item: PhotoQuarantineItem,
        *,
        label: str,
        labeled_by: str,
        note: Optional[str] = None,
    ) -> None:
        self._set_label_fields(item, label=label, labeled_by=labeled_by, note=note)
        item.updated_at = _now()
        self._db.commit()
        self._db.refresh(item)

    @staticmethod
    def _set_label_fields(
        item: PhotoQuarantineItem,
        *,
        label: str,
        labeled_by: Optional[str],
        note: Optional[str] = None,
    ) -> None:
        if label not in {"KEEP", "TRASH"}:
            raise ValueError(f"Unsupported human label: {label}")
        if labeled_by is None:
            return
        item.human_label = label
        item.human_label_note = note
        item.human_labeled_by = labeled_by
        item.human_labeled_at = _now()

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

    def _finalize_delete_queue(
        self, item_id: int, content_hash: str
    ) -> PhotoQuarantineItem:
        item = self._reload_item(item_id)
        photo = self._db.query(Photo).filter(Photo.id == item.photo_id).first()
        if photo is None:
            raise PhotoQuarantineError("Photo record disappeared after deletion was queued")
        now = _now()
        item.previous_photo_status = item.previous_photo_status or photo.status
        item.status = "delete_queued"
        item.quarantine_path = None
        item.content_hash = content_hash
        item.moved_at = item.moved_at or now
        item.last_error = None
        item.updated_at = now
        photo.status = "quarantined"
        photo.deleted_at = now
        photo.updated_at = now
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


def _empty_confusion_counts() -> dict[str, int]:
    return {
        "labeled_total": 0,
        "human_keep": 0,
        "human_trash": 0,
        "true_positive": 0,
        "false_positive": 0,
        "true_negative": 0,
        "false_negative": 0,
    }


def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


def _is_verified_auto_candidate(first: dict, verification: dict) -> bool:
    auto_move_categories = {
        "accidental_capture",
        "severe_blur",
        "obscured_lens",
        "blank_image",
        "meaningless_test_image",
    }

    def is_candidate(result: dict) -> bool:
        return (
            result.get("decision") == "QUARANTINE"
            and result.get("classification") in auto_move_categories
            and float(result.get("confidence", 0)) >= 0.98
            and not result.get("preservation_flags")
            and result.get("has_record_value") is False
        )

    return (
        is_candidate(first)
        and is_candidate(verification)
        and first.get("classification") == verification.get("classification")
    )
