from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from app.services.query_understanding_service import SearchQueryPlan
from app.services.search.concept_recall import (
    ConceptRecallService,
    derive_concept_query_context,
    derive_concept_query_terms,
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


def test_derive_concept_query_terms_for_animal_query() -> None:
    plan = SearchQueryPlan(
        original_query="动物",
        normalized_query="动物 猫 狗 鸟",
        intent="animal_search",
        exact_terms=["动物"],
        expanded_terms=["猫", "狗", "鸟", "马", "鹿", "兔子", "鱼"],
        broad_terms=["宠物", "野生动物"],
        concept_terms=["动物"],
    )

    concepts, entities = derive_concept_query_terms(plan)

    assert "动物" in concepts
    assert "宠物" in concepts
    assert "野生动物" in concepts
    assert "猫" in entities
    assert "狗" in entities
    assert "鸟" in entities


def test_derive_concept_query_context_for_group_photo_query() -> None:
    plan = SearchQueryPlan(
        original_query="合照",
        normalized_query="合照",
        intent="group_photo_search",
        exact_terms=["合照"],
        expanded_terms=["合影", "集体照", "多人"],
        core_facets=["people", "group_photo"],
    )

    concept_terms, entity_terms, concept_facets = derive_concept_query_context(plan)

    assert "人物" in concept_terms
    assert "合照" in concept_terms
    assert "多人" in concept_terms
    assert entity_terms == []
    assert "people" in concept_facets
    assert "group_photo" in concept_facets


def test_concept_recall_search_matches_semantic_concepts_and_entities() -> None:
    row = SimpleNamespace(
        photo_id=101,
        semantic_concepts=["动物"],
        raw_result={
            "semantic": {
                "entities": ["猫"],
                "concepts": ["动物", "宠物", "小动物"],
                "facets": ["animal", "object"],
            }
        },
        object_tags=["猫"],
        search_keywords=["猫", "宠物"],
    )
    db = _DBStub([row])
    svc = ConceptRecallService(db, _default_settings())

    plan = SearchQueryPlan(
        original_query="动物",
        normalized_query="动物",
        intent="animal_search",
        exact_terms=["动物"],
        expanded_terms=["猫"],
        broad_terms=["宠物"],
        concept_terms=["动物"],
    )

    candidates = svc.search(plan, project_id=1, folder_photo_subquery=None)

    assert len(candidates) == 1
    assert candidates[0].photo_id == 101
    assert "concept" in candidates[0].match_source
    assert "动物" in candidates[0].keyword_explain.get("semantic_concepts", [])
    assert "猫" in candidates[0].keyword_explain.get("semantic_entities", [])
    # concept_terms=[动物, 宠物], entity_terms=[猫], all matched => 1.0
    assert candidates[0].keyword_score == 1.0
    assert candidates[0].keyword_explain.get("concept_term_coverage") == 1.0
    assert candidates[0].keyword_explain.get("entity_term_coverage") == 1.0


def test_concept_recall_filters_are_project_scoped() -> None:
    db = _DBStub([])
    svc = ConceptRecallService(db, _default_settings())

    plan = SearchQueryPlan(
        original_query="动物",
        normalized_query="动物",
        intent="animal_search",
        exact_terms=["动物"],
        expanded_terms=["猫"],
        concept_terms=["动物"],
    )

    svc.search(plan, project_id=7, folder_photo_subquery=None)

    filter_strings = [str(expr) for expr in db.query_stub.filters]
    assert any("photos.project_id" in text for text in filter_strings)
    assert any("photo_ai_analysis.project_id" in text for text in filter_strings)


def test_concept_recall_returns_empty_on_empty_constrained_ids() -> None:
    row = SimpleNamespace(
        photo_id=101,
        semantic_concepts=["动物"],
        raw_result={"semantic": {"entities": ["猫"], "concepts": ["动物"]}},
        object_tags=["猫"],
        search_keywords=["猫"],
    )
    db = _DBStub([row])
    svc = ConceptRecallService(db, _default_settings())

    plan = SearchQueryPlan(
        original_query="动物",
        normalized_query="动物",
        intent="animal_search",
        exact_terms=["动物"],
        expanded_terms=["猫"],
        concept_terms=["动物"],
    )

    candidates = svc.search(
        plan,
        project_id=1,
        folder_photo_subquery=None,
        constrained_photo_ids=set(),
    )

    assert candidates == []


def test_concept_recall_score_is_concept_only_coverage_when_no_entities() -> None:
    row = SimpleNamespace(
        photo_id=201,
        semantic_concepts=["动物"],
        raw_result={"semantic": {"concepts": ["动物"]}},
        object_tags=[],
        search_keywords=[],
    )
    db = _DBStub([row])
    svc = ConceptRecallService(db, _default_settings())

    plan = SearchQueryPlan(
        original_query="动物",
        normalized_query="动物",
        intent="animal_search",
        exact_terms=["动物"],
        expanded_terms=[],
        broad_terms=["宠物", "野生动物"],
        concept_terms=["动物"],
    )

    candidates = svc.search(plan, project_id=1, folder_photo_subquery=None)

    assert len(candidates) == 1
    # concept terms are [动物, 宠物, 野生动物], hits=[动物] => 1/3
    assert candidates[0].keyword_score == 0.333333
