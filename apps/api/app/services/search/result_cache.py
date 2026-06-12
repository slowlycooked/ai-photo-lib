"""Project-scoped search result cache with cross-process invalidation epoch."""
from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ...models.app_settings import AppSettings

_CACHE_KEY_PREFIX = "search_result_cache_epoch:project:"
_CACHE_MAX_SIZE = 1024


@dataclass(frozen=True)
class SearchResultCacheEntry:
    total: int
    items: list
    debug_payload: Optional[dict]


class SearchResultCache:
    def __init__(self, max_size: int = _CACHE_MAX_SIZE) -> None:
        self._max_size = max(1, int(max_size))
        self._lock = threading.Lock()
        self._store: "OrderedDict[tuple, tuple[float, SearchResultCacheEntry]]" = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0

    def get(self, cache_key: tuple, ttl_seconds: int) -> Optional[SearchResultCacheEntry]:
        ttl = int(ttl_seconds)
        if ttl <= 0:
            return None

        now = time.monotonic()
        with self._lock:
            hit = self._store.get(cache_key)
            if not hit:
                self._misses += 1
                return None
            created_at, payload = hit
            if now - created_at > ttl:
                self._store.pop(cache_key, None)
                self._misses += 1
                return None
            self._store.move_to_end(cache_key)
            self._hits += 1
            return copy.deepcopy(payload)

    def put(self, cache_key: tuple, payload: SearchResultCacheEntry, ttl_seconds: int) -> None:
        ttl = int(ttl_seconds)
        if ttl <= 0:
            return

        with self._lock:
            self._store[cache_key] = (time.monotonic(), copy.deepcopy(payload))
            self._store.move_to_end(cache_key)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)
                self._evictions += 1

    def clear_project(self, project_id: int) -> int:
        removed = 0
        project_token = int(project_id)
        with self._lock:
            keys = [key for key in self._store.keys() if len(key) > 0 and key[0] == project_token]
            for key in keys:
                self._store.pop(key, None)
                removed += 1
            if removed > 0:
                self._invalidations += 1
        return removed

    def stats(self, *, project_id: Optional[int] = None) -> dict:
        with self._lock:
            entries = len(self._store)
            if project_id is None:
                project_entries = entries
            else:
                token = int(project_id)
                project_entries = sum(1 for key in self._store.keys() if len(key) > 0 and key[0] == token)
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "invalidations": self._invalidations,
                "entries": entries,
                "project_entries": project_entries,
                "max_size": self._max_size,
            }


_SEARCH_RESULT_CACHE = SearchResultCache()


def _epoch_setting_key(project_id: int) -> str:
    return f"{_CACHE_KEY_PREFIX}{int(project_id)}"


def get_project_search_cache_epoch(db: Session, project_id: int) -> int:
    try:
        row = (
            db.query(AppSettings)
            .filter(AppSettings.key == _epoch_setting_key(project_id))
            .first()
        )
    except Exception:  # noqa: BLE001
        return 0
    if row is None:
        return 0
    payload = row.value_json or {}
    try:
        return int(payload.get("epoch") or 0)
    except (TypeError, ValueError):
        return 0


def bump_project_search_cache_epoch(
    db: Session,
    project_id: int,
    *,
    reason: str,
) -> int:
    try:
        row = (
            db.query(AppSettings)
            .filter(AppSettings.key == _epoch_setting_key(project_id))
            .first()
        )
    except Exception:  # noqa: BLE001
        _SEARCH_RESULT_CACHE.clear_project(project_id)
        return 0
    now = datetime.now(timezone.utc)
    if row is None:
        next_epoch = 1
        row = AppSettings(
            key=_epoch_setting_key(project_id),
            value_json={
                "epoch": next_epoch,
                "updated_at": now.isoformat(),
                "reason": reason,
            },
            updated_at=now,
        )
        db.add(row)
    else:
        payload = row.value_json or {}
        try:
            current_epoch = int(payload.get("epoch") or 0)
        except (TypeError, ValueError):
            current_epoch = 0
        next_epoch = current_epoch + 1
        row.value_json = {
            "epoch": next_epoch,
            "updated_at": now.isoformat(),
            "reason": reason,
        }
        row.updated_at = now

    _SEARCH_RESULT_CACHE.clear_project(project_id)
    db.flush()
    return next_epoch


def get_search_result_cache_stats(*, project_id: Optional[int] = None) -> dict:
    return _SEARCH_RESULT_CACHE.stats(project_id=project_id)


def search_result_cache_get(cache_key: tuple, ttl_seconds: int) -> Optional[SearchResultCacheEntry]:
    return _SEARCH_RESULT_CACHE.get(cache_key, ttl_seconds)


def search_result_cache_put(cache_key: tuple, payload: SearchResultCacheEntry, ttl_seconds: int) -> None:
    _SEARCH_RESULT_CACHE.put(cache_key, payload, ttl_seconds)
