from __future__ import annotations

from pathlib import Path
from typing import Tuple


def build_relative_paths(library_path: str, entry: Path) -> Tuple[str, str]:
    """
    Compute the relative_path and folder_path for a photo entry.

    Returns:
        (relative_path, folder_path) where folder_path is the parent directory
        relative to library_path, or "" for top-level files.
    """
    lib_path = Path(library_path).resolve()
    entry_path = Path(entry).resolve()

    rel_path = str(entry_path.relative_to(lib_path))
    folder_path = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    return rel_path, folder_path
