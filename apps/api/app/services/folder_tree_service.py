from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.folder import ProjectFolder
from ..schemas.folder import FolderBreadcrumbItem, FolderNode


@dataclass
class _FolderRow:
    id: int
    parent_id: int | None
    name: str
    relative_path: str
    depth: int
    photo_count_direct: int
    photo_count_recursive: int


def _load_project_folders(db: Session, project_id: int) -> list[_FolderRow]:
    rows = (
        db.query(
            ProjectFolder.id,
            ProjectFolder.parent_id,
            ProjectFolder.name,
            ProjectFolder.relative_path,
            ProjectFolder.depth,
            ProjectFolder.photo_count_direct,
            ProjectFolder.photo_count_recursive,
        )
        .filter(
            ProjectFolder.project_id == project_id,
            ProjectFolder.deleted_at.is_(None),
        )
        .order_by(ProjectFolder.relative_path.asc(), ProjectFolder.id.asc())
        .all()
    )
    return [
        _FolderRow(
            id=row.id,
            parent_id=row.parent_id,
            name=row.name,
            relative_path=row.relative_path,
            depth=row.depth,
            photo_count_direct=row.photo_count_direct,
            photo_count_recursive=row.photo_count_recursive,
        )
        for row in rows
    ]


def build_project_folder_tree(db: Session, project_id: int) -> FolderNode | None:
    rows = _load_project_folders(db, project_id)
    if not rows:
        return None

    by_id = {row.id: row for row in rows}
    children_by_parent: dict[int | None, list[_FolderRow]] = defaultdict(list)
    root_id: int | None = None

    for row in rows:
        children_by_parent[row.parent_id].append(row)
        if row.relative_path == "":
            root_id = row.id

    if root_id is None:
        return None

    def _sort_key(row: _FolderRow) -> tuple[str, str, int]:
        return ((row.name or "").lower(), (row.relative_path or "").lower(), row.id)

    def _build(node_id: int) -> FolderNode:
        row = by_id[node_id]
        children = sorted(children_by_parent.get(node_id, []), key=_sort_key)
        return FolderNode(
            id=row.id,
            name=row.name,
            relative_path=row.relative_path,
            depth=row.depth,
            photo_count_direct=row.photo_count_direct,
            photo_count_recursive=row.photo_count_recursive,
            children=[_build(child.id) for child in children],
        )

    return _build(root_id)


def build_folder_breadcrumb(
    db: Session,
    project_id: int,
    folder_id: int,
) -> list[FolderBreadcrumbItem]:
    rows = _load_project_folders(db, project_id)
    by_id = {row.id: row for row in rows}

    current = by_id.get(folder_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    items: list[FolderBreadcrumbItem] = []
    while current is not None:
        items.append(
            FolderBreadcrumbItem(
                id=current.id,
                name=current.name,
                relative_path=current.relative_path,
            )
        )
        current = by_id.get(current.parent_id) if current.parent_id is not None else None

    items.reverse()
    return items
