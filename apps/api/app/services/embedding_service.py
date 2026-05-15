"""Embedding service — placeholder for v0.4 pgvector semantic search.

In v0.3 search is powered by keyword matching (search_service.py).
This module stubs out the embedding API so the rest of the codebase can
import it without errors; real implementations will be added in v0.4.
"""
from __future__ import annotations

from typing import List


def embed_text(text: str) -> List[float]:
    """Return a text embedding vector.

    TODO (v0.4): Call a local embedding model (e.g. bge-small-zh-v1.5 via
    llama-server or sentence-transformers) and return the float vector.
    """
    raise NotImplementedError("Vector embeddings are not yet implemented (v0.4+)")


def embed_tags(tags: List[str]) -> List[float]:
    """Return an embedding for a list of tags joined as a sentence.

    TODO (v0.4): implement using embed_text(", ".join(tags)).
    """
    raise NotImplementedError("Vector embeddings are not yet implemented (v0.4+)")
