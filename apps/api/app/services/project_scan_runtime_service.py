from __future__ import annotations

from pathlib import Path
from typing import Optional

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


def validate_project_library_path(project_library_path: str) -> Optional[str]:
    library_path = (project_library_path or "").strip()
    if not library_path:
        return "photo_library_path is empty."

    library = Path(library_path).expanduser().resolve()
    if not library.exists() or not library.is_dir():
        return build_missing_library_message(str(library))
    return None
