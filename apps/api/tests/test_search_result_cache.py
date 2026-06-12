from __future__ import annotations

import unittest

from app.services.search.result_cache import SearchResultCache, SearchResultCacheEntry


class SearchResultCacheTest(unittest.TestCase):
    def test_cache_hit_and_miss(self) -> None:
        cache = SearchResultCache(max_size=8)
        key = (1, 0, "cat")
        payload = SearchResultCacheEntry(total=1, items=[{"photo_id": 1}], debug_payload={"a": 1})

        self.assertIsNone(cache.get(key, ttl_seconds=60))
        cache.put(key, payload, ttl_seconds=60)
        hit = cache.get(key, ttl_seconds=60)

        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.total, 1)
        self.assertEqual(hit.items[0]["photo_id"], 1)

    def test_ttl_zero_disables_cache(self) -> None:
        cache = SearchResultCache(max_size=8)
        key = (1, 0, "cat")
        payload = SearchResultCacheEntry(total=1, items=[{"photo_id": 1}], debug_payload=None)

        cache.put(key, payload, ttl_seconds=0)
        self.assertIsNone(cache.get(key, ttl_seconds=0))

    def test_clear_project_only_removes_project_entries(self) -> None:
        cache = SearchResultCache(max_size=8)
        cache.put((1, 0, "cat"), SearchResultCacheEntry(total=1, items=[], debug_payload=None), ttl_seconds=60)
        cache.put((2, 0, "dog"), SearchResultCacheEntry(total=1, items=[], debug_payload=None), ttl_seconds=60)

        removed = cache.clear_project(1)

        self.assertEqual(removed, 1)
        self.assertIsNone(cache.get((1, 0, "cat"), ttl_seconds=60))
        self.assertIsNotNone(cache.get((2, 0, "dog"), ttl_seconds=60))

    def test_stats_tracks_hits_and_misses(self) -> None:
        cache = SearchResultCache(max_size=8)
        key = (1, 0, "cat")
        payload = SearchResultCacheEntry(total=1, items=[], debug_payload=None)

        cache.get(key, ttl_seconds=60)
        cache.put(key, payload, ttl_seconds=60)
        cache.get(key, ttl_seconds=60)

        stats = cache.stats(project_id=1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["project_entries"], 1)


if __name__ == "__main__":
    unittest.main()
