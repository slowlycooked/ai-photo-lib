from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    """Canonical status values for AI jobs (analyze / embed)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class AIJobType(str, Enum):
    """Canonical job-type values stored in ai_jobs.job_type."""

    ANALYZE_IMAGE = "analyze"
    REANALYZE_IMAGE = "reanalyze"
    BUILD_EMBEDDING = "embed"


class EmbeddingStatus(str, Enum):
    """Canonical status values for photo_embeddings.embedding_status."""

    READY = "ready"
    STALE = "stale"
    FAILED = "failed"
    MISSING = "missing"
