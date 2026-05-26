from __future__ import annotations

from app.services.concept_normalizer import (
    CONCEPT_NORMALIZER_VERSION,
    NormalizedConcepts,
    attach_semantic_concepts_to_raw_result,
    normalize_concepts_from_payload,
)


def test_cat_derives_animal_pet_small_animal() -> None:
    normalized = normalize_concepts_from_payload(object_tags=["猫"])

    assert "猫" in normalized.semantic_entities
    assert "动物" in normalized.semantic_concepts
    assert "宠物" in normalized.semantic_concepts
    assert "小动物" in normalized.semantic_concepts
    assert "animal" in normalized.semantic_facets
    assert "object" in normalized.semantic_facets


def test_dog_alias_derives_concepts() -> None:
    normalized = normalize_concepts_from_payload(object_tags=["狗狗"])

    assert "狗" in normalized.semantic_entities
    assert "动物" in normalized.semantic_concepts
    assert "宠物" in normalized.semantic_concepts
    assert "小动物" in normalized.semantic_concepts


def test_zoo_scene_does_not_create_animal_entity() -> None:
    normalized = normalize_concepts_from_payload(
        scene_tags=["动物园"],
        location_clues=["动物园"],
    )

    assert "动物" not in normalized.semantic_entities
    assert "动物" not in normalized.semantic_concepts


def test_raw_result_animals_is_strong_source() -> None:
    normalized = normalize_concepts_from_payload(raw_result={"animals": ["猫"]})

    assert "猫" in normalized.semantic_entities
    assert "动物" in normalized.semantic_concepts


def test_attach_semantic_preserves_existing_raw_result() -> None:
    normalized = NormalizedConcepts(
        semantic_entities=["猫"],
        semantic_concepts=["动物", "宠物", "小动物"],
        semantic_facets=["animal", "object"],
        concept_sources={
            "动物": ["object_tags:猫"],
            "宠物": ["object_tags:猫"],
            "小动物": ["object_tags:猫"],
        },
    )

    raw_result = {"caption": "xxx", "foo": "bar"}
    merged = attach_semantic_concepts_to_raw_result(raw_result, normalized)

    assert merged["foo"] == "bar"
    assert merged["caption"] == "xxx"
    assert "semantic" in merged
    assert merged["semantic"]["version"] == CONCEPT_NORMALIZER_VERSION


def test_attach_semantic_is_idempotent() -> None:
    normalized = NormalizedConcepts(
        semantic_entities=["猫"],
        semantic_concepts=["动物", "宠物", "小动物"],
        semantic_facets=["animal", "object"],
        concept_sources={"动物": ["object_tags:猫"]},
    )

    once = attach_semantic_concepts_to_raw_result({}, normalized)
    twice = attach_semantic_concepts_to_raw_result(once, normalized)

    assert twice["semantic"]["entities"] == ["猫"]
    assert twice["semantic"]["concepts"] == ["动物", "宠物", "小动物"]
    assert twice["semantic"]["version"] == CONCEPT_NORMALIZER_VERSION
