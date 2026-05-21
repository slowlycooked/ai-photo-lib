from __future__ import annotations

"""Project Settings Resolver (Phase 5).

Provides ``ProjectSettingsResolver.resolve(db, project_id)`` which returns
an ``EffectiveProjectSettings`` object that merges:

  1. Global ``EnvSettings`` (from ``app.config.settings``)
  2. Per-project ``ProjectAISettings`` row (if present)

All Scan / AI / Embedding / Search logic should obtain runtime config from
this resolver instead of reading ``settings.*`` directly, so that per-project
overrides are honoured.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..config import settings as global_settings
from ..models.ai import ProjectAISettings


@dataclass(frozen=True)
class EffectiveAISettings:
    """AI/VLM runtime parameters derived for a specific project."""

    endpoint_url: str
    model_name: str
    temperature: float
    top_p: float
    max_tokens: int
    output_language: str
    json_parse_strategy: str
    active_prompt_template_id: int | None


@dataclass(frozen=True)
class EffectiveEmbeddingSettings:
    """Embedding parameters for a specific project."""

    endpoint_url: str
    model: str
    dimension: int
    timeout_seconds: int


@dataclass(frozen=True)
class EffectiveSearchSettings:
    """Search hyper-parameters for a specific project."""

    vector_top_k: int
    keyword_top_k: int
    rrf_k: int
    vector_weight: float
    keyword_weight: float
    vector_min_score: float
    caption_vector_weight: float
    tag_vector_weight: float
    ocr_vector_weight: float


@dataclass(frozen=True)
class EffectiveLibrarySettings:
    """Photo library paths for a specific project."""

    photo_library_path: str
    thumbnail_path: str
    thumbnail_size: int


@dataclass(frozen=True)
class EffectiveProjectSettings:
    """Merged effective settings for a project.

    Use this instead of reading ``settings.*`` and ``ProjectAISettings``
    separately in business logic.
    """

    project_id: int
    ai: EffectiveAISettings
    embedding: EffectiveEmbeddingSettings
    search: EffectiveSearchSettings
    library: EffectiveLibrarySettings


def _default_endpoint_url() -> str:
    base = global_settings.openai_base_url.rstrip("/")
    return f"{base}/chat/completions"


class ProjectSettingsResolver:
    """Resolves the effective settings for a project.

    Usage::

        effective = ProjectSettingsResolver.resolve(db, project_id)
        endpoint = effective.ai.endpoint_url
    """

    @staticmethod
    def resolve(db: Session, project_id: int) -> EffectiveProjectSettings:
        """Return the merged effective settings for *project_id*."""
        ai_row = (
            db.query(ProjectAISettings)
            .filter(ProjectAISettings.project_id == project_id)
            .first()
        )

        # ── AI settings ───────────────────────────────────────────────────────
        if ai_row is not None:
            endpoint_url = (ai_row.endpoint_url or "").strip() or _default_endpoint_url()
            model_name = (ai_row.model_name or "").strip() or global_settings.openai_vision_model
            temperature = ai_row.temperature if ai_row.temperature is not None else global_settings.ai_vision_temperature
            top_p = ai_row.top_p if ai_row.top_p is not None else 1.0
            max_tokens = ai_row.max_tokens if ai_row.max_tokens is not None else global_settings.ai_vision_max_tokens
            output_language = ai_row.output_language or "zh"
            json_parse_strategy = ai_row.json_parse_strategy or "auto_extract"
            active_prompt_template_id = ai_row.active_prompt_template_id
        else:
            endpoint_url = _default_endpoint_url()
            model_name = global_settings.openai_vision_model
            temperature = global_settings.ai_vision_temperature
            top_p = 1.0
            max_tokens = global_settings.ai_vision_max_tokens
            output_language = "zh"
            json_parse_strategy = "auto_extract"
            active_prompt_template_id = None

        # ── Embedding settings ────────────────────────────────────────────────
        embedding_base = (
            global_settings.embedding_base_url.rstrip("/")
            if global_settings.embedding_base_url
            else global_settings.openai_base_url.rstrip("/")
        )
        embedding_endpoint = f"{embedding_base}/embeddings"
        embedding_model = (
            global_settings.embedding_model
            or (ai_row.model_name if ai_row else None)
            or global_settings.openai_model
        )

        # ── Library settings ──────────────────────────────────────────────────
        # Per-project paths are stored in the projects table, not here.
        # Library settings from global config are used as fallbacks only during
        # initial project creation; after that the projects table is authoritative.
        library = EffectiveLibrarySettings(
            photo_library_path=global_settings.photo_library_path,
            thumbnail_path=global_settings.thumbnail_path,
            thumbnail_size=global_settings.thumbnail_size,
        )

        return EffectiveProjectSettings(
            project_id=project_id,
            ai=EffectiveAISettings(
                endpoint_url=endpoint_url,
                model_name=model_name,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                output_language=output_language,
                json_parse_strategy=json_parse_strategy,
                active_prompt_template_id=active_prompt_template_id,
            ),
            embedding=EffectiveEmbeddingSettings(
                endpoint_url=endpoint_url,  # Use project AI endpoint as embedding fallback
                model=embedding_model,
                dimension=global_settings.embedding_dimension,
                timeout_seconds=global_settings.embedding_timeout_seconds,
            ),
            search=EffectiveSearchSettings(
                vector_top_k=global_settings.search_vector_top_k,
                keyword_top_k=global_settings.search_keyword_top_k,
                rrf_k=global_settings.search_rrf_k,
                vector_weight=global_settings.search_vector_weight,
                keyword_weight=global_settings.search_keyword_weight,
                vector_min_score=global_settings.search_vector_min_score,
                caption_vector_weight=global_settings.search_caption_vector_weight,
                tag_vector_weight=global_settings.search_tag_vector_weight,
                ocr_vector_weight=global_settings.search_ocr_vector_weight,
            ),
            library=library,
        )
