from __future__ import annotations

import app.routers.project_tags as project_tags_router
from app.routers.project_tags import _count_tag_groups, project_tags


def setup_function():
    with project_tags_router._TAG_GROUP_CACHE_LOCK:
        project_tags_router._TAG_GROUP_CACHE.clear()


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def execute(self, statement, params):
        self.executions.append((str(statement), params))
        return FakeResult(self.rows)


def test_count_tag_groups_groups_all_categories_from_one_query():
    db = FakeSession(
        [
            ("scene_tags", "beach", 4),
            ("scene_tags", "city", 2),
            ("object_tags", "camera", 3),
            ("location_clues", "shanghai", 1),
        ]
    )

    groups = _count_tag_groups(db, project_id=7, limit=20)

    assert len(db.executions) == 1
    statement, params = db.executions[0]
    assert params == {"pid": 7, "limit": 20}
    assert "ROW_NUMBER() OVER (PARTITION BY category" in statement
    assert "CROSS JOIN LATERAL" in statement
    assert groups["scene_tags"][0].tag == "beach"
    assert groups["scene_tags"][0].count == 4
    assert groups["scene_tags"][1].tag == "city"
    assert groups["object_tags"][0].tag == "camera"
    assert groups["location_clues"][0].tag == "shanghai"
    assert groups["activity_tags"] == []


def test_project_tags_response_uses_grouped_counts():
    db = FakeSession(
        [
            ("scene_tags", "night", 5),
            ("search_keywords", "neon", 3),
        ]
    )

    response = project_tags(project_id=9, project=object(), db=db)

    assert len(db.executions) == 1
    assert response.scene_tags[0].tag == "night"
    assert response.search_keywords[0].count == 3
    assert response.object_tags == []


def test_project_tags_reuses_cached_counts_until_project_epoch_changes(monkeypatch):
    epoch = 4
    monkeypatch.setattr(
        project_tags_router,
        "get_project_search_cache_epoch",
        lambda db, project_id: epoch,
    )
    db = FakeSession([("scene_tags", "night", 5)])

    first = project_tags(project_id=11, project=object(), db=db)
    db.rows = [("scene_tags", "day", 2)]
    cached = project_tags(project_id=11, project=object(), db=db)

    assert len(db.executions) == 1
    assert first.scene_tags[0].tag == "night"
    assert cached.scene_tags[0].tag == "night"

    epoch = 5
    refreshed = project_tags(project_id=11, project=object(), db=db)

    assert len(db.executions) == 2
    assert refreshed.scene_tags[0].tag == "day"
