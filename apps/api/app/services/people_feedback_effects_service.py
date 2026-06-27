from __future__ import annotations

from dataclasses import dataclass, field
from typing import Collection, Optional

from sqlalchemy.orm import Session

from .project_task_service import enqueue_face_rematch_unknown_task

_DEFAULT_MANUAL_REMATCH_MAX_FACES = 1000


@dataclass
class PeopleFeedbackEffects:
    project_id: Optional[int] = None
    prototype_rebuilt: bool = False
    rebuilt_person_ids: list[int] = field(default_factory=list)
    unknown_rematch_requested: bool = False
    unknown_rematch_scope: Optional[str] = None
    unknown_rematch_person_id: Optional[int] = None
    unknown_rematch_task_id: Optional[int] = None
    unknown_rematch_task_created: bool = False


class PeopleFeedbackEffectsService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._last_effects = PeopleFeedbackEffects()

    def get(self) -> PeopleFeedbackEffects:
        return self._last_effects

    def reset(self) -> None:
        self._last_effects = PeopleFeedbackEffects()

    def set(
        self,
        *,
        project_id: int,
        rebuilt_person_ids: Collection[int],
        rematch_scope: Optional[str] = None,
        rematch_person_id: Optional[int] = None,
    ) -> None:
        unique_person_ids = sorted({int(person_id) for person_id in rebuilt_person_ids})
        effects = PeopleFeedbackEffects(
            project_id=project_id,
            prototype_rebuilt=bool(unique_person_ids),
            rebuilt_person_ids=unique_person_ids,
        )
        if rematch_scope:
            effects.unknown_rematch_requested = True
            effects.unknown_rematch_scope = rematch_scope
            effects.unknown_rematch_person_id = rematch_person_id
            try:
                result = enqueue_face_rematch_unknown_task(
                    self._db,
                    project_id=project_id,
                    max_faces=_DEFAULT_MANUAL_REMATCH_MAX_FACES,
                    scope=rematch_scope,
                    person_id=rematch_person_id,
                )
                effects.unknown_rematch_task_id = result.task.id
                effects.unknown_rematch_task_created = bool(result.created)
            except Exception:  # noqa: BLE001
                self._db.rollback()
                effects.unknown_rematch_task_id = None
                effects.unknown_rematch_task_created = False
        self._last_effects = effects
