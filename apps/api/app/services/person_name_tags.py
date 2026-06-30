from __future__ import annotations

import re

_HASHTAG_RE = re.compile(r"#([^\s#，,;；、]+)")
_SPACE_RE = re.compile(r"\s+")


def extract_person_name_tags(display_name: str | None) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for match in _HASHTAG_RE.finditer(display_name or ""):
        tag = match.group(1).strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def strip_person_name_tags(display_name: str | None) -> str:
    without_tags = _HASHTAG_RE.sub(" ", display_name or "")
    return _SPACE_RE.sub(" ", without_tags).strip()


def person_name_search_terms(display_name: str | None, normalized_name: str | None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        term = _SPACE_RE.sub(" ", (value or "").strip().lower())
        if not term or term in seen:
            return
        seen.add(term)
        terms.append(term)

    add(normalized_name)
    add(display_name)
    add(strip_person_name_tags(display_name))
    for tag in extract_person_name_tags(display_name):
        add(f"#{tag}")
        add(tag)
    return terms
