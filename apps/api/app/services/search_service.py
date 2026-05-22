"""search_service.py — backward-compatible shim over the new search package.

All legacy imports (SearchCandidate, VectorMatchScores, _rrf_merge,
_vector_search, search_photos) remain importable from this module so that
existing tests and routers continue to work without modification.

New code should import from ``app.services.search`` directly.
"""
from __future__ import annotations

from typing import Literal, Optional, Tuple

# Re-export core types from the new package so callers don't have to change
from .search.types import (  # noqa: F401
    SearchCandidate,
    VectorMatchScores,
)
from .search.app_service import search_photos  # noqa: F401

# Keep the Literal type alias
SearchMode = Literal["keyword", "vector", "hybrid"]

# ── Private function aliases kept for test backward compatibility ─────────────

def _rrf_merge(keyword_results, vector_scores):
    """Backward-compat wrapper around :func:`search.fusion.rrf_merge`."""
    from .search.fusion import rrf_merge
    from .search.settings_resolver import SearchSettingsResolver
    return rrf_merge(keyword_results, vector_scores, SearchSettingsResolver.defaults())


def _vector_search(
    db,
    *,
    query: str,
    normalized_query: str,
    project_id: int,
    folder_photo_ids,
    limit: int,
):
    """Backward-compat wrapper around :class:`search.vector_recall.VectorRecallService`."""
    from .search.settings_resolver import SearchSettingsResolver
    from .search.vector_recall import VectorRecallService

    settings = SearchSettingsResolver.resolve(db, project_id)
    svc = VectorRecallService(db, settings)
    return svc.search(
        query=query,
        normalized_query=normalized_query,
        is_ocr_query=False,
        project_id=project_id,
        folder_photo_ids=folder_photo_ids,
        limit=limit,
    )
