from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..config import settings


def build_missing_library_message(project_library_path: str) -> str:
    configured = (settings.photo_library_path or "").strip()
    project_path = (project_library_path or "").strip()
    message = f"photo_library_path not found or not a directory: {project_path}"
    if configured and configured != project_path:
        message += (
            "; project path differs from configured PHOTO_LIBRARY_PATH. "
            f"project={project_path}, configured={configured}. "
            "Update the project photo_library_path in settings before scanning."
        )
    return message


def validate_project_library_paths(project_library_paths: List[str]) -> List[str]:
    """Validate every configured library root; return one error per bad path."""
    errors: List[str] = []
    if not project_library_paths:
        return ["photo_library_path is empty."]

    seen: set[str] = set()
    for raw in project_library_paths:
        library_path = (raw or "").strip()
        if not library_path:
            errors.append("photo_library_path is empty.")
            continue
        library = Path(library_path).expanduser().resolve()
        if str(library) in seen:
            continue
        seen.add(str(library))
        if not library.exists() or not library.is_dir():
            errors.append(build_missing_library_message(str(library)))
    return errors


def validate_project_library_path(project_library_path: str) -> Optional[str]:
    """Backward-compatible single-path validation; returns first error or None."""
    errors = validate_project_library_paths([project_library_path])
    return errors[0] if errors else None
