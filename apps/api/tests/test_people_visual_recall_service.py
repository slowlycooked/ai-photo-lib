from __future__ import annotations

from types import SimpleNamespace

from app.services.query_understanding_service import SearchQueryPlan
from app.services.search.people_visual_recall import (
    PeopleVisualRecallService,
    derive_people_visual_terms,
)
from app.services.search.settings_resolver import SearchSettingsResolver


class _QueryStub:
    def __init__(self, rows):
        self._rows = rows
        self.filters = []

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *args):
        self.filters.extend(args)
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class _DBStub:
    def __init__(self, rows):
        self.query_stub = _QueryStub(rows)

    def query(self, *_args, **_kwargs):
        return self.query_stub


def _default_settings():
    return SearchSettingsResolver.defaults()


def test_people_visual_recall_project_isolation() -> None:
    row_a = SimpleNamespace(
        photo_id=101,
        people_count=3,
        raw_result={"semantic": {"facets": ["people", "group_photo"], "concepts": ["人物", "多人", "合照"]}},
        search_keywords=["合照"],
        activity_tags=["合影"],
    )
    db = _DBStub([row_a])
    svc = PeopleVisualRecallService(db, _default_settings())

    plan = SearchQueryPlan(
        original_query="合照",
        normalized_query="合照",
        intent="group_photo_search",
        exact_terms=["合照"],
        expanded_terms=["合影", "集体照", "多人"],
        core_facets=["people", "group_photo"],
    )

    candidates = svc.search(plan, project_id=1)

    assert len(candidates) == 1
    assert candidates[0].photo_id == 101
    filter_strings = [str(expr) for expr in db.query_stub.filters]
    assert any("photos.project_id" in text for text in filter_strings)
    assert any("photo_ai_analysis.project_id" in text for text in filter_strings)


def test_people_visual_recall_prefers_group_photo_count() -> None:
    terms, min_people_count, facets = derive_people_visual_terms(
        SearchQueryPlan(
            original_query="集体照",
            normalized_query="集体照",
            intent="group_photo_search",
            exact_terms=["集体照"],
            expanded_terms=["合照", "合影", "多人"],
            core_facets=["people", "group_photo"],
        )
    )

    assert min_people_count >= 3
    assert "people" in facets
    assert "group_photo" in facets
    assert "合照" in terms
