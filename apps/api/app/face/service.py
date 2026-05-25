from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Protocol

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class FaceBoundingBox:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class DetectedFace:
    bbox: FaceBoundingBox
    detection_confidence: Optional[float] = None
    quality_score: Optional[float] = None
    provider_payload: Optional[object] = None


@dataclass(frozen=True)
class FaceEmbeddingResult:
    vector: List[float]
    embedding_dim: int
    model_provider: str
    model_name: str
    model_version: Optional[str] = None


class FaceRecognitionService(Protocol):
    """Inference contract for local face detection and embedding providers.

    Providers MUST implement the ``*_from_bgr`` variants.  The path-based
    helpers are convenience wrappers that decode the file first.
    """

    def detect_faces(self, image_path: Path) -> list[DetectedFace]:
        """Decode *image_path* and detect faces.  Handles HEIC via pillow-heif."""
        ...

    def detect_faces_from_bgr(self, image_bgr: "np.ndarray") -> list[DetectedFace]:
        """Detect faces in a pre-decoded OpenCV BGR array."""
        ...

    def embed_face(
        self, image_path: Path, detected_face: DetectedFace
    ) -> FaceEmbeddingResult:
        """Decode *image_path* and extract a face embedding."""
        ...

    def embed_face_from_bgr(
        self, image_bgr: "np.ndarray", detected_face: DetectedFace
    ) -> FaceEmbeddingResult:
        """Extract a face embedding from a pre-decoded OpenCV BGR array."""
        ...
