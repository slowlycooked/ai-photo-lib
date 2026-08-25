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
_SOFT_PEOPLE_ONLY_TERMS = {
    "爸爸",
    "爸",
    "父亲",
    "妈妈",
    "妈",
    "母亲",
    "爷爷",
    "奶奶",
    "外公",
    "外婆",
    "儿子",
    "女儿",
    "孩子",
    "家人",
    "亲子",
    "father",
    "mother",
    "dad",
    "mom",
}


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
    unresolved_people: List[str] = field(default_factory=list)

    @property
    def matched_person_ids(self) -> List[int]:
        return [p.person_id for p in self.matched_people]

    @property
    def has_people(self) -> bool:
        return bool(self.matched_people)

    @property
    def has_people_constraint(self) -> bool:
        return self.has_people or bool(self.unresolved_people)

    @property
    def is_people_only(self) -> bool:
        return (
            self.has_people_constraint
            and self.people_filter_mode != "boost"
            and not self.residual_query.strip()
        )


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


def _should_soften_people_only(
    *,
    query_for_match: str,
    query_plan: SearchQueryPlan,
    matched: List[ResolvedPersonRef],
    matched_terms: List[str],
    residual_query: str,
) -> bool:
    """Let kinship terms expand semantically instead of ending at named people."""
    if len(matched) != 1 or residual_query.strip():
        return False
    if getattr(query_plan, "intent", "") != "people_search":
        return False
    normalized_terms = {_normalize_text(term) for term in matched_terms if term}
    soft_query = _normalize_text(
        _CONNECTOR_RE.sub(" ", _NOISE_RE.sub(" ", query_for_match))
    )
    if soft_query not in _SOFT_PEOPLE_ONLY_TERMS:
        return False
    return bool(normalized_terms & _SOFT_PEOPLE_ONLY_TERMS)


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

    planner_filters = getattr(query_plan, "planner_filters", None) or {}
    planned_people = [
        item
        for item in list(planner_filters.get("people") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    planned_names = [str(item["name"]).strip() for item in planned_people]
    uses_planned_people = (
        str(getattr(query_plan, "planner_contract_version", "1")) == "2"
        and bool(planned_names)
    )
    query_for_match = _normalize_text(
        " ".join(planned_names) if uses_planned_people else source_query
    )
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
    unresolved_people: List[str] = []
    if uses_planned_people:
        for search_term in planned_names:
            normalized_search_term = _normalize_text(search_term)
            matched_search_term = False
            for person in people_rows:
                candidates = person_name_search_terms(person.display_name, person.normalized_name)
                for candidate in sorted(candidates, key=len, reverse=True):
                    if _normalize_text(candidate) != normalized_search_term:
                        continue
                    if int(person.id) not in seen_ids:
                        seen_ids.add(int(person.id))
                        matched.append(
                            ResolvedPersonRef(
                                person_id=int(person.id),
                                display_name=str(person.display_name),
                                normalized_name=str(person.normalized_name or person.display_name),
                                matched_term=search_term,
                            )
                        )
                    matched_terms.append(search_term)
                    matched_search_term = True
                    break
                if matched_search_term:
                    break
            if not matched_search_term:
                unresolved_people.append(search_term)
    else:
        for person in people_rows:
            candidates = person_name_search_terms(person.display_name, person.normalized_name)
            for candidate in sorted(candidates, key=len, reverse=True):
                if not candidate or candidate not in query_for_match:
                    continue
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

    if uses_planned_people:
        semantic_plan = getattr(query_plan, "semantic_plan", None) or {}
        lexical_plan = getattr(query_plan, "lexical_plan", None) or {}
        visual_plan = getattr(query_plan, "visual_plan", None) or {}
        residual_terms = (
            list(semantic_plan.get("queries") or [])
            + list(lexical_plan.get("required") or [])
            + list(lexical_plan.get("preferred") or [])
            + list(visual_plan.get("objects") or [])
            + list(visual_plan.get("scenes") or [])
            + list(visual_plan.get("activities") or [])
            + list(visual_plan.get("attributes") or [])
        )
        residual_query = " ".join(dict.fromkeys(str(item) for item in residual_terms if str(item).strip()))
        unresolved = dict(getattr(query_plan, "unresolved_entities", None) or {})
        unresolved["people"] = list(
            dict.fromkeys(list(unresolved.get("people") or []) + unresolved_people)
        )
        query_plan.unresolved_entities = unresolved
    else:
        residual_query = _strip_people_terms(source_query, matched_terms)

    people_constraint_count = len(planned_names) if uses_planned_people else len(matched)
    filter_mode = (
        "all"
        if people_constraint_count > 1
        else ("any" if people_constraint_count == 1 else "none")
    )
    if _should_soften_people_only(
        query_for_match=query_for_match,
        query_plan=query_plan,
        matched=matched,
        matched_terms=matched_terms,
        residual_query=residual_query,
    ):
        filter_mode = "boost"

    return PeopleQueryResolution(
        query=query,
        residual_query=residual_query,
        people_filter_mode=filter_mode,
        matched_people=matched,
        unresolved_people=unresolved_people,
    )
