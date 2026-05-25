from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from .service import DetectedFace, FaceBoundingBox, FaceEmbeddingResult, FaceRecognitionService
from ..services.image_decode_service import read_image_bgr as _decode_bgr

logger = logging.getLogger(__name__)


class FaceRecognitionProviderUnavailableError(RuntimeError):
    """Raised when the configured local face provider cannot be used."""


@dataclass(frozen=True)
class OpenCVFaceProviderConfig:
    detector_model: str
    embedding_model: str
    detector_model_path: Optional[str]
    embedding_model_path: Optional[str]
    min_detection_confidence: float


class OpenCVFaceRecognitionService(FaceRecognitionService):
    """YuNet + SFace wrapper with lazy OpenCV loading.

    This is designed so tests can inject a fake provider without importing cv2.
    """

    def __init__(self, config: OpenCVFaceProviderConfig) -> None:
        self._config = config
        self._detector = None
        self._recognizer = None

    def detect_faces(self, image_path: Path) -> List[DetectedFace]:
        """Decode *image_path* (including HEIC) and detect faces."""
        image_bgr = _decode_bgr(image_path)
        return self.detect_faces_from_bgr(image_bgr)

    def detect_faces_from_bgr(self, image_bgr: np.ndarray) -> List[DetectedFace]:
        """Detect faces in a pre-decoded OpenCV BGR array."""
        height, width = image_bgr.shape[:2]
        detector = self._get_detector((width, height))
        _, faces = detector.detect(image_bgr)
        if faces is None:
            return []

        results: List[DetectedFace] = []
        for raw_face in faces:
            bbox = FaceBoundingBox(
                x=max(0, int(round(raw_face[0]))),
                y=max(0, int(round(raw_face[1]))),
                width=max(1, int(round(raw_face[2]))),
                height=max(1, int(round(raw_face[3]))),
            )
            confidence = float(raw_face[14]) if len(raw_face) > 14 else None
            results.append(
                DetectedFace(
                    bbox=bbox,
                    detection_confidence=confidence,
                    quality_score=None,
                    provider_payload=raw_face,
                )
            )
        return results

    def embed_face(
        self, image_path: Path, detected_face: DetectedFace
    ) -> FaceEmbeddingResult:
        """Decode *image_path* (including HEIC) and extract a face embedding."""
        image_bgr = _decode_bgr(image_path)
        return self.embed_face_from_bgr(image_bgr, detected_face)

    def embed_face_from_bgr(
        self, image_bgr: np.ndarray, detected_face: DetectedFace
    ) -> FaceEmbeddingResult:
        """Extract a face embedding from a pre-decoded OpenCV BGR array."""
        if detected_face.provider_payload is None:
            raise ValueError("Detected face is missing provider payload for alignment")

        recognizer = self._get_recognizer()
        aligned = recognizer.alignCrop(image_bgr, detected_face.provider_payload)
        feature = recognizer.feature(aligned)
        vector = feature.flatten().astype("float32").tolist()
        return FaceEmbeddingResult(
            vector=vector,
            embedding_dim=len(vector),
            model_provider="opencv",
            model_name=self._config.embedding_model,
            model_version="",
        )

    def _get_detector(self, input_size: Tuple[int, int]):
        cv2 = self._require_cv2()
        if not self._config.detector_model_path:
            raise FaceRecognitionProviderUnavailableError(
                "FACE_DETECTOR_MODEL_PATH is not configured for the OpenCV face provider"
            )
        if self._detector is None:
            self._detector = cv2.FaceDetectorYN.create(
                self._config.detector_model_path,
                "",
                input_size,
                self._config.min_detection_confidence,
                0.3,
                5000,
            )
        self._detector.setInputSize(input_size)
        return self._detector

    def _get_recognizer(self):
        cv2 = self._require_cv2()
        if not self._config.embedding_model_path:
            raise FaceRecognitionProviderUnavailableError(
                "FACE_EMBEDDING_MODEL_PATH is not configured for the OpenCV face provider"
            )
        if self._recognizer is None:
            self._recognizer = cv2.FaceRecognizerSF.create(
                self._config.embedding_model_path,
                "",
            )
        return self._recognizer

    @staticmethod
    def _require_cv2():
        try:
            import cv2  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise FaceRecognitionProviderUnavailableError(
                "OpenCV face provider is unavailable because `cv2` could not be imported. "
                "Install an OpenCV build with FaceDetectorYN / FaceRecognizerSF support."
            ) from exc
        return cv2
