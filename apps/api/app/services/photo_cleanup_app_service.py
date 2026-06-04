from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from ..models.photo import Photo
from ..repositories.unit_of_work import UnitOfWork
from .photo_cleanup import (
    PhotoBatchDeleteResult,
    PhotoDeleteResult,
    delete_photo_record,
    delete_photo_records_batch,
)


class PhotoCleanupAppService:
    """Application transaction boundary for photo cleanup mutations."""

    def __init__(self, db: Session) -> None:
        self._uow = UnitOfWork(db)

    def delete_photo_record(
        self,
        *,
        project_id: int,
        photo: Photo,
        delete_original: bool = False,
    ) -> PhotoDeleteResult:
        try:
            result = delete_photo_record(
                self._uow.db,
                project_id=project_id,
                photo=photo,
                delete_original=delete_original,
            )
            self._uow.commit()
            return result
        except Exception:
            self._uow.rollback()
            raise

    def delete_photo_records_batch(
        self,
        *,
        project_id: int,
        photo_ids: Sequence[int],
        delete_original: bool = False,
    ) -> PhotoBatchDeleteResult:
        try:
            result = delete_photo_records_batch(
                self._uow.db,
                project_id=project_id,
                photo_ids=photo_ids,
                delete_original=delete_original,
            )
            self._uow.commit()
            return result
        except Exception:
            self._uow.rollback()
            raise
