from __future__ import annotations

from pydantic import BaseModel


class TagCount(BaseModel):
    tag: str
    count: int


class TagsResponse(BaseModel):
    scene_tags: list[TagCount]
    object_tags: list[TagCount]
    activity_tags: list[TagCount]
    quality_tags: list[TagCount]
    search_keywords: list[TagCount]
