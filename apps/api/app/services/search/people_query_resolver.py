"""Resolve people entities from a raw search query.

This module is intentionally project-scoped: all person matching is resolved
from named people within the current project only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from sqlalchemy.orm import Session

from ...models.face import Person
from ...services.person_name_tags import person_name_search_terms
from ...services.query_understanding_service import SearchQueryPlan


_CONNECTOR_RE = re.compile(r"(和|与|跟|及|以及|还有|and|with)", re.IGNORECASE)
_NOISE_RE = re.compile(r"(的照片|的图片|的相片|照片|图片|相片)", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ResolvedPersonRef:
    person_id: int
    display_name: str
    normalized_name: str
    matched_term: str


@dataclass(frozen=True)
class PeopleQueryResolution:
    query: str
    residual_query: str
    people_filter_mode: str
    matched_people: List[ResolvedPersonRef] = field(default_factory=list)

    @property
    def matched_person_ids(self) -> List[int]:
        return [p.person_id for p in self.matched_people]

    @property
    def has_people(self) -> bool:
        return bool(self.matched_people)

    @property
    def is_people_only(self) -> bool:
        return self.has_people and not self.residual_query.strip()


def _normalize_text(value: str) -> str:
    return _SPACE_RE.sub(" ", (value or "").strip().lower())


def _strip_people_terms(query: str, matched_terms: List[str]) -> str:
    residual = query or ""
    for term in sorted({t for t in matched_terms if t}, key=len, reverse=True):
        residual = re.sub(re.escape(term), " ", residual, flags=re.IGNORECASE)
    residual = _NOISE_RE.sub(" ", residual)
    residual = _CONNECTOR_RE.sub(" ", residual)
    residual = _SPACE_RE.sub(" ", residual).strip()
    return residual


def resolve_people_query(
    db: Session,
    *,
    project_id: int,
    query: str,
    query_plan: SearchQueryPlan,
) -> PeopleQueryResolution:
    """Resolve named people references from the current query.

    Matching strategy:
    - search only named people in the same project
    - try normalized_name, display_name, display_name without #tags, and #tag aliases
    - remove matched names from query to produce residual semantic query
    """
    source_query = query
    original_query = getattr(query_plan, "original_query", None)
    if isinstance(original_query, str) and original_query.strip():
        source_query = original_query

    query_for_match = _normalize_text(source_query)
    if not query_for_match:
        return PeopleQueryResolution(
            query=query,
            residual_query="",
            people_filter_mode="none",
            matched_people=[],
        )

    people_rows = (
        db.query(Person)
        .filter(
            Person.project_id == project_id,
            Person.is_named.is_(True),
        )
        .all()
    )

    matched: List[ResolvedPersonRef] = []
    seen_ids: set[int] = set()
    matched_terms: List[str] = []
    for person in people_rows:
        candidates = person_name_search_terms(person.display_name, person.normalized_name)
        for candidate in sorted(candidates, key=len, reverse=True):
            if candidate and candidate in query_for_match:
                if int(person.id) not in seen_ids:
                    seen_ids.add(int(person.id))
                    matched.append(
                        ResolvedPersonRef(
                            person_id=int(person.id),
                            display_name=str(person.display_name),
                            normalized_name=str(person.normalized_name or person.display_name),
                            matched_term=candidate,
                        )
                    )
                matched_terms.append(candidate)
                break

    residual_query = _strip_people_terms(source_query, matched_terms)
    filter_mode = "all" if len(matched) > 1 else ("any" if matched else "none")

    return PeopleQueryResolution(
        query=query,
        residual_query=residual_query,
        people_filter_mode=filter_mode,
        matched_people=matched,
    )
