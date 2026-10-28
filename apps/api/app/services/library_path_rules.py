"""Pure validation rules for project library paths.

Kept free of model/schema imports so both ``schemas`` and ``services`` layers
can depend on it without creating an import cycle.
"""

from __future__ import annotations

import os


def normalize_library_path(v: str) -> str:
    """Validate and normalize a single absolute library path."""
    v = v.strip().rstrip("/")
    if not v:
        raise ValueError("photo_library_path must not be empty")
    # Must be absolute to prevent ambiguity
    if not v.startswith("/"):
        raise ValueError("photo_library_path must be an absolute path")
    # Prevent path traversal
    if os.path.normpath(v) != v:
        raise ValueError("photo_library_path must not contain '..'")
    return v


def normalize_library_paths(values: list[str]) -> list[str]:
    """Validate a list of library paths; dedupe preserving order."""
    normalized: list[str] = []
    for raw in values:
        path = normalize_library_path(raw)
        if path not in normalized:
            normalized.append(path)
    if not normalized:
        raise ValueError("photo_library_paths must contain at least one path")
    return normalized
