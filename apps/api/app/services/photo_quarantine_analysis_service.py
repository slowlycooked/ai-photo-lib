from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from ..models.photo import Photo
from ..models.photo_quarantine import (
    CONTENT_RATINGS,
    SENSITIVE_CONTENT_FLAGS,
    PhotoQuarantineItem,
    ProjectPhotoQuarantineSettings,
)
from .photo_quarantine_service import PhotoQuarantineService
from .vlm_client import analyze_image

PROMPT_VERSION = "photo-quarantine-v3-duplicate-detection"
AUTO_MOVE_CATEGORIES = frozenset(
    {
        "accidental_capture",
        "severe_blur",
        "obscured_lens",
        "blank_image",
        "meaningless_test_image",
    }
)

_SYSTEM_PROMPT = (
    "你是私人照片库的保守清理与内容分级审核器。只返回一个 JSON 对象，不输出推理过程。"
    "误删的代价远高于漏删；只要存在生活、纪念、凭证、工作或记录价值，就必须 KEEP 或 REVIEW。"
    "成人、裸露、色情、暴力或其他敏感内容只能标记并交由人工复核，绝不能仅因此判为可删除。"
)

_FIRST_PASS_PROMPT = """
判断这张图片是否属于可安全移入“待删除区”的无价值图片。

必须保留：人物、家人朋友、宠物、旅行活动、纪念场景、票据订单、支付地址、二维码、聊天通知、证件合同、工作成果，以及施工进度、问题、事故、验收或取证照片。
不能仅因为图片是屏幕截图或工地场景就判断为可删除。

decision 只能是 KEEP、REVIEW、QUARANTINE。
classification 只能使用：valuable、uncertain、accidental_capture、severe_blur、obscured_lens、blank_image、meaningless_test_image、screenshot、construction_clutter、other。
同时独立识别可能的 18+ 或敏感内容：
- content_rating 只能是 SAFE、SENSITIVE、ADULT；
- sensitive_content_flags 只能从 explicit_sexual_content、sexual_content、nudity、suggestive_content、graphic_violence、violence、gore、self_harm、drug_use、disturbing_content、other_adult_content 中选择，可多选；
- 裸露、色情、血腥、重度暴力等使用 ADULT；性暗示、非血腥暴力、自残、药物或令人不适内容至少使用 SENSITIVE；
- 无法确认时宁可标记 SENSITIVE 并返回 REVIEW；任何 sensitive_content_flags 非空时 decision 必须是 REVIEW。
返回：
{"decision":"KEEP|REVIEW|QUARANTINE","classification":"...","confidence":0.0,"reason":"简短中文理由","preservation_flags":[],"has_record_value":false,"content_rating":"SAFE|SENSITIVE|ADULT","sensitive_content_flags":[]}
""".strip()

_VERIFY_PROMPT = """
这是误删防护复核。请从最保守角度重新判断图片是否可以安全移入待删除区。
若存在人物、纪念、凭证、文字信息、二维码、聊天、地址、工作成果、施工进度、问题记录、事故、验收或任何不确定性，必须返回 KEEP 或 REVIEW。
只有明显误触、严重模糊、镜头遮挡、空白图或无意义测试图才可返回 QUARANTINE。
若检测到任何 18+ 或敏感内容，必须返回 REVIEW，并保留 content_rating 与 sensitive_content_flags。
返回与上一轮相同字段的单个 JSON 对象。
""".strip()


@dataclass(frozen=True)
class AnalysisRunResult:
    analyzed: int
    kept: int
    review: int
    quarantined: int
    errors: int
    window_closed: bool


@dataclass(frozen=True)
class DuplicateSource:
    id: int
    file_name: str
    file_path: str


class PhotoQuarantineAnalysisService:
    def __init__(
        self,
        db: Session,
        *,
        analyzer: Callable[..., str] = analyze_image,
        clock: Callable[[ZoneInfo], datetime] | None = None,
    ) -> None:
        self._db = db
        self._analyzer = analyzer
        self._clock = clock or (lambda tz: datetime.now(tz))

    def run_project(
        self,
        *,
        project_id: int,
        ignore_window: bool = False,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> dict:
        settings_row = PhotoQuarantineService(self._db).get_or_create_settings(project_id)
        timezone = load_timezone(settings_row.timezone)
        counters = {"analyzed": 0, "kept": 0, "review": 0, "quarantined": 0, "errors": 0}
        window_closed = False
        if not settings_row.enabled and not ignore_window:
            return {
                "project_id": project_id,
                "running": False,
                "message": "disabled",
                **counters,
                "window_closed": False,
                "recent_errors": [],
            }

        duplicate_sources = self._build_duplicate_source_map(project_id)
        while True:
            now = self._clock(timezone)
            if not ignore_window and not is_hour_in_window(
                now.hour, settings_row.start_hour, settings_row.end_hour
            ):
                window_closed = True
                break
            photo = self._next_candidate(project_id, settings_row.model_name)
            if photo is None:
                break
            try:
                item = self._analyze_photo(
                    photo,
                    settings_row,
                    duplicate_source=duplicate_sources.get(photo.id),
                )
                counters["analyzed"] += 1
                if item.status == "kept":
                    counters["kept"] += 1
                elif item.status == "quarantined":
                    counters["quarantined"] += 1
                else:
                    counters["review"] += 1
            except Exception as exc:  # noqa: BLE001
                self._persist_analysis_error(
                    photo=photo,
                    model_name=settings_row.model_name,
                    error=str(exc),
                )
                counters["errors"] += 1
            if progress_callback:
                progress_callback(
                    {
                        "project_id": project_id,
                        "running": True,
                        "message": "analyzing photo quarantine candidates",
                        "current_photo_id": photo.id,
                        **counters,
                        "recent_errors": [],
                    }
                )

        result = AnalysisRunResult(**counters, window_closed=window_closed)
        return {
            "project_id": project_id,
            "running": False,
            "message": "window_closed" if window_closed else "done",
            "analyzed": result.analyzed,
            "kept": result.kept,
            "review": result.review,
            "quarantined": result.quarantined,
            "errors": result.errors,
            "window_closed": result.window_closed,
            "recent_errors": [],
        }

    def _next_candidate(self, project_id: int, model_name: str) -> Optional[Photo]:
        return (
            self._db.query(Photo)
            .outerjoin(
                PhotoQuarantineItem,
                (PhotoQuarantineItem.photo_id == Photo.id)
                & (PhotoQuarantineItem.project_id == project_id),
            )
            .filter(
                Photo.project_id == project_id,
                Photo.deleted_at.is_(None),
                Photo.status != "quarantined",
                or_(
                    PhotoQuarantineItem.id.is_(None),
                    PhotoQuarantineItem.model_name != model_name,
                    PhotoQuarantineItem.prompt_version != PROMPT_VERSION,
                ),
            )
            .order_by(
                case(
                    (PhotoQuarantineItem.status == "analysis_retry_queued", 0),
                    else_=1,
                ),
                Photo.id.asc(),
            )
            .first()
        )

    def _analyze_photo(
        self,
        photo: Photo,
        settings_row: ProjectPhotoQuarantineSettings,
        *,
        duplicate_source: Optional[DuplicateSource] = None,
    ) -> PhotoQuarantineItem:
        if duplicate_source is not None:
            return self._persist_duplicate_candidate(
                photo=photo,
                duplicate_source=duplicate_source,
                model_name=settings_row.model_name,
            )

        image_path = _analysis_image_path(photo)
        first = _parse_decision(
            self._analyzer(
                str(image_path),
                provider="ollama",
                model_name=settings_row.model_name,
                system_text=_SYSTEM_PROMPT,
                prompt_text=_FIRST_PASS_PROMPT,
                temperature=0.0,
                top_p=0.1,
                max_tokens=500,
            )
        )

        verification: Optional[dict] = None
        final_decision = str(first["decision"])
        if first["sensitive_content_flags"]:
            final_decision = "REVIEW"
        elif _is_first_pass_auto_candidate(first):
            verification = _parse_decision(
                self._analyzer(
                    str(image_path),
                    provider="ollama",
                    model_name=settings_row.model_name,
                    system_text=_SYSTEM_PROMPT,
                    prompt_text=_VERIFY_PROMPT,
                    temperature=0.0,
                    top_p=0.1,
                    max_tokens=500,
                )
            )
            if not _is_verified_auto_candidate(first, verification):
                final_decision = "REVIEW"

        item = (
            self._db.query(PhotoQuarantineItem)
            .filter(
                PhotoQuarantineItem.project_id == photo.project_id,
                PhotoQuarantineItem.photo_id == photo.id,
            )
            .first()
        )
        if item is None:
            item = PhotoQuarantineItem(project_id=photo.project_id, photo_id=photo.id)
            self._db.add(item)
        item.status = "kept" if final_decision == "KEEP" else "review"
        item.decision = final_decision
        item.classification = str(first["classification"])
        item.confidence = float(first["confidence"])
        item.reason = _review_reason(first)
        item.preservation_flags = list(first["preservation_flags"])
        item.first_result = first
        item.verification_result = verification
        item.model_name = settings_row.model_name
        item.prompt_version = PROMPT_VERSION
        item.original_path = photo.file_path
        item.content_hash = photo.file_hash
        item.last_error = None
        self._db.commit()
        self._db.refresh(item)

        if final_decision == "QUARANTINE" and not settings_row.dry_run:
            item = PhotoQuarantineService(self._db).move(
                project_id=photo.project_id,
                item_id=item.id,
            ).item
        return item

    def _build_duplicate_source_map(
        self, project_id: int
    ) -> dict[int, DuplicateSource]:
        rows = (
            self._db.query(Photo.id, Photo.file_hash, Photo.file_name, Photo.file_path)
            .filter(
                Photo.project_id == project_id,
                Photo.deleted_at.is_(None),
                Photo.status != "quarantined",
                Photo.file_hash.isnot(None),
            )
            .order_by(Photo.id.asc())
            .all()
        )
        canonical_by_hash: dict[str, DuplicateSource] = {}
        duplicates: dict[int, DuplicateSource] = {}
        for photo_id, file_hash, file_name, file_path in rows:
            source = canonical_by_hash.get(file_hash)
            if source is None:
                canonical_by_hash[file_hash] = DuplicateSource(
                    id=photo_id,
                    file_name=file_name,
                    file_path=file_path,
                )
            else:
                duplicates[photo_id] = source
        return duplicates

    def _persist_duplicate_candidate(
        self,
        *,
        photo: Photo,
        duplicate_source: DuplicateSource,
        model_name: str,
    ) -> PhotoQuarantineItem:
        item = (
            self._db.query(PhotoQuarantineItem)
            .filter(
                PhotoQuarantineItem.project_id == photo.project_id,
                PhotoQuarantineItem.photo_id == photo.id,
            )
            .first()
        )
        if item is None:
            item = PhotoQuarantineItem(project_id=photo.project_id, photo_id=photo.id)
            self._db.add(item)
        result = {
            "decision": "REVIEW",
            "classification": "suspected_duplicate",
            "confidence": 1.0,
            "reason": f"与 {duplicate_source.file_name} 的内容哈希一致",
            "preservation_flags": [],
            "has_record_value": False,
            "content_rating": "SAFE",
            "sensitive_content_flags": [],
            "duplicate_photo_id": duplicate_source.id,
            "duplicate_original_path": duplicate_source.file_path,
        }
        item.status = "review"
        item.decision = "REVIEW"
        item.classification = "suspected_duplicate"
        item.confidence = 1.0
        item.reason = str(result["reason"])
        item.preservation_flags = []
        item.first_result = result
        item.verification_result = None
        item.model_name = model_name
        item.prompt_version = PROMPT_VERSION
        item.original_path = photo.file_path
        item.content_hash = photo.file_hash
        item.last_error = None
        self._db.commit()
        self._db.refresh(item)
        return item

    def _persist_analysis_error(self, *, photo: Photo, model_name: str, error: str) -> None:
        item = (
            self._db.query(PhotoQuarantineItem)
            .filter(
                PhotoQuarantineItem.project_id == photo.project_id,
                PhotoQuarantineItem.photo_id == photo.id,
            )
            .first()
        )
        if item is None:
            item = PhotoQuarantineItem(project_id=photo.project_id, photo_id=photo.id)
            self._db.add(item)
        item.status = "analysis_failed"
        item.decision = "REVIEW"
        item.classification = "uncertain"
        item.confidence = 0.0
        item.reason = "模型分析失败，必须人工复核"
        item.preservation_flags = ["analysis_error"]
        item.first_result = {}
        item.verification_result = None
        item.model_name = model_name
        item.prompt_version = PROMPT_VERSION
        item.original_path = photo.file_path
        item.content_hash = photo.file_hash
        item.last_error = error[:2000]
        self._db.commit()


def _analysis_image_path(photo: Photo) -> Path:
    if photo.thumbnail_path:
        thumbnail = Path(photo.thumbnail_path).expanduser()
        if thumbnail.is_file():
            return thumbnail
    original = Path(photo.file_path).expanduser()
    if not original.is_file():
        raise FileNotFoundError(f"Photo file not found: {photo.file_path}")
    return original


def _parse_decision(raw: str) -> dict:
    text = (raw or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model did not return a JSON object")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Model decision must be a JSON object")
    decision = str(data.get("decision") or "").strip().upper()
    if decision not in {"KEEP", "REVIEW", "QUARANTINE"}:
        raise ValueError("Invalid model decision")
    classification = str(data.get("classification") or "uncertain").strip().lower()
    confidence = max(0.0, min(1.0, float(data.get("confidence") or 0.0)))
    flags = data.get("preservation_flags") or []
    if not isinstance(flags, list):
        raise ValueError("preservation_flags must be a JSON array")
    has_record_value = data.get("has_record_value", True)
    if not isinstance(has_record_value, bool):
        raise ValueError("has_record_value must be a JSON boolean")
    sensitive_flags = data.get("sensitive_content_flags") or []
    if not isinstance(sensitive_flags, list):
        raise ValueError("sensitive_content_flags must be a JSON array")
    normalized_sensitive_flags = list(
        dict.fromkeys(str(flag).strip() for flag in sensitive_flags)
    )
    unknown_sensitive_flags = set(normalized_sensitive_flags) - SENSITIVE_CONTENT_FLAGS
    if unknown_sensitive_flags:
        raise ValueError("Invalid sensitive_content_flags")
    content_rating = str(data.get("content_rating") or "SAFE").strip().upper()
    if content_rating not in CONTENT_RATINGS:
        raise ValueError("Invalid content_rating")
    content_rating = _minimum_content_rating(content_rating, normalized_sensitive_flags)
    return {
        "decision": decision,
        "classification": classification,
        "confidence": confidence,
        "reason": str(data.get("reason") or "").strip()[:1000],
        "preservation_flags": [str(flag)[:200] for flag in flags],
        "has_record_value": has_record_value,
        "content_rating": content_rating,
        "sensitive_content_flags": normalized_sensitive_flags,
    }


def _minimum_content_rating(content_rating: str, flags: list[str]) -> str:
    adult_flags = {
        "explicit_sexual_content",
        "nudity",
        "graphic_violence",
        "gore",
        "other_adult_content",
    }
    if adult_flags.intersection(flags):
        return "ADULT"
    if flags and content_rating == "SAFE":
        return "SENSITIVE"
    return content_rating


def _review_reason(result: dict) -> str:
    if not result["sensitive_content_flags"]:
        return str(result["reason"])
    return f"检测到可能的 18+ 或敏感内容，需人工复核。{result['reason']}"[:1000]


def _is_first_pass_auto_candidate(result: dict) -> bool:
    return (
        result["decision"] == "QUARANTINE"
        and result["classification"] in AUTO_MOVE_CATEGORIES
        and result["confidence"] >= 0.98
        and not result["preservation_flags"]
        and not result["has_record_value"]
    )


def _is_verified_auto_candidate(first: dict, verification: dict) -> bool:
    return (
        _is_first_pass_auto_candidate(first)
        and _is_first_pass_auto_candidate(verification)
        and first["classification"] == verification["classification"]
    )


def is_hour_in_window(hour: int, start_hour: int, end_hour: int) -> bool:
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def load_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc
