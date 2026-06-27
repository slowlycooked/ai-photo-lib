from __future__ import annotations

from typing import Collection, Optional

from sqlalchemy.orm import Session

from ..models.face import Person
from .people_feedback_effects_service import PeopleFeedbackEffects, PeopleFeedbackEffectsService
from .person_lifecycle_mutation_service import PersonLifecycleMutationService


class PeopleLifecycleMutationService:
    def __init__(self, db: Session) -> None:
        self._feedback_effects = PeopleFeedbackEffectsService(db)
        self._lifecycle = PersonLifecycleMutationService(db)

    def get_feedback_effects(self) -> PeopleFeedbackEffects:
        return self._feedback_effects.get()

    def _reset_feedback_effects(self) -> None:
        self._feedback_effects.reset()

    def _set_feedback_effects(
        self,
        *,
        project_id: int,
        rebuilt_person_ids: Collection[int],
        rematch_scope: Optional[str] = None,
        rematch_person_id: Optional[int] = None,
    ) -> None:
        self._feedback_effects.set(
            project_id=project_id,
            rebuilt_person_ids=rebuilt_person_ids,
            rematch_scope=rematch_scope,
            rematch_person_id=rematch_person_id,
        )

    def create_person(
        self,
        *,
        project_id: int,
        display_name: Optional[str],
        is_named: bool,
    ) -> Person:
        self._reset_feedback_effects()
        person = self._lifecycle.create_person(
            project_id=project_id,
            display_name=display_name,
            is_named=is_named,
        )
        self._set_feedback_effects(project_id=project_id, rebuilt_person_ids=[])
        return person

    def rename_person(
        self,
        *,
        project_id: int,
        person_id: int,
        display_name: str,
    ) -> Person:
        self._reset_feedback_effects()
        person, promoted_to_label = self._lifecycle.rename_person(
            project_id=project_id,
            person_id=person_id,
            display_name=display_name,
        )
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[person_id] if promoted_to_label else [],
            rematch_scope="person" if promoted_to_label else None,
            rematch_person_id=person_id if promoted_to_label else None,
        )
        return person

    def delete_person(
        self,
        *,
        project_id: int,
        person_id: int,
    ) -> None:
        self._reset_feedback_effects()
        self._lifecycle.delete_person(project_id=project_id, person_id=person_id)
        self._set_feedback_effects(project_id=project_id, rebuilt_person_ids=[])

    def merge_people(
        self,
        *,
        project_id: int,
        source_person_id: int,
        target_person_id: int,
    ) -> tuple[Person, Person, int]:
        self._reset_feedback_effects()
        source_person, target_person, moved_assignments = self._lifecycle.merge_people(
            project_id=project_id,
            source_person_id=source_person_id,
            target_person_id=target_person_id,
        )
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[source_person.id, target_person.id],
            rematch_scope="person",
            rematch_person_id=target_person.id,
        )
        return source_person, target_person, moved_assignments

    def split_person(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
        new_display_name: Optional[str],
    ) -> tuple[Person, Person, int]:
        self._reset_feedback_effects()
        source_person, target_person, moved_assignments = self._lifecycle.split_person(
            project_id=project_id,
            person_id=person_id,
            face_detection_ids=face_detection_ids,
            new_display_name=new_display_name,
        )
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[source_person.id, target_person.id],
            rematch_scope="person",
            rematch_person_id=target_person.id,
        )
        return source_person, target_person, moved_assignments
