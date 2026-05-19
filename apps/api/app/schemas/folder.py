from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

class FolderNode(BaseModel):
    id: int
    name: str
    relative_path: str
    depth: int
    photo_count_direct: int
    photo_count_recursive: int
    children: Optional[List['FolderNode']] = None

    class Config:
        orm_mode = True
        arbitrary_types_allowed = True

class FolderTreeResponse(BaseModel):
    project_id: int
    root: Optional[FolderNode]

class FolderBreadcrumbItem(BaseModel):
    id: int
    name: str
    relative_path: str

class FolderBreadcrumbResponse(BaseModel):
    items: List[FolderBreadcrumbItem]
