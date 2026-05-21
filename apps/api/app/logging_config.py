from __future__ import annotations

import logging
import re
from contextvars import ContextVar

from .core.debug_config import (
    TRACE_LEVEL_NUM,
    derive_runtime_flags,
    ensure_trace_logging_level,
    python_logging_level,
)

# Context variables for request, project, task, photo
request_id_ctx = ContextVar("request_id", default=None)
project_id_ctx = ContextVar("project_id", default=None)
task_id_ctx = ContextVar("task_id", default=None)
photo_id_ctx = ContextVar("photo_id", default=None)

ensure_trace_logging_level()

_handler: logging.Handler | None = None
_runtime_debug_state: dict[str, object] = {
    "debug_mode": "BASIC",
    "debug_matrix": {
        "frontend_log_level": "INFO",
        "backend_log_level": "INFO",
        "ai_log_level": "INFO",
        "search_log_level": "INFO",
        "sql_log_level": "WARNING",
        "task_log_level": "INFO",
    },
    "request_debug_middleware": False,
    "ai_raw_logging": False,
    "search_debug_payload": False,
    "search_trace_payload": False,
    "frontend_debug_panel": True,
}

_LOGGER_GROUPS: dict[str, tuple[str, ...]] = {
    "backend_log_level": (
        "ai_photo_lib.backend",
        "app",
        "app.main",
        "app.routers",
        "app.services.runtime_settings_service",
    ),
    "ai_log_level": (
        "ai_photo_lib.ai",
        "app.services.vlm_client",
        "app.services.project_ai_service",
        "app.services.json_parser",
    ),
    "search_log_level": (
        "ai_photo_lib.search",
        "app.services.search_service",
        "app.services.embedding_client",
        "app.services.embedding_service",
    ),
    "sql_log_level": (
        "sqlalchemy.engine",
    ),
    "task_log_level": (
        "ai_photo_lib.scan",
        "ai_photo_lib.tasks",
        "app.services.scanner",
        "worker",
        "worker.main",
    ),
}

def get_log_context():
    return {
        "request_id": request_id_ctx.get(),
        "project_id": project_id_ctx.get(),
        "task_id": task_id_ctx.get(),
        "photo_id": photo_id_ctx.get(),
    }

class SensitiveDataFilter(logging.Filter):
    SENSITIVE_PATTERNS = [
        re.compile(r"(Authorization|Api[-_]?Key|token|secret|DATABASE_URL)['\"]?[:= ]+([^'\"\s]+)", re.I),
        re.compile(r"(Bearer|Token) [A-Za-z0-9\-\._~\+\/]+=*", re.I),
        re.compile(r"postgres://[^:]+:([^@]+)@", re.I),
    ]
    MASK = "***"
    def filter(self, record):
        msg = record.getMessage()
        for pat in self.SENSITIVE_PATTERNS:
            msg = pat.sub(r"\\1: {}".format(self.MASK), msg)
        record.msg = msg
        record.args = ()
        return True

class ContextualFormatter(logging.Formatter):
    def format(self, record):
        ctx = get_log_context()
        for k, v in ctx.items():
            setattr(record, k, v)
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = record.msg.replace("\n", " ")
        return super().format(record)

def _ensure_handler() -> logging.Handler:
    global _handler
    if _handler is None:
        handler = logging.StreamHandler()
        fmt = "[%(asctime)s][%(levelname)s][%(request_id)s][%(project_id)s][%(task_id)s][%(photo_id)s] %(name)s: %(message)s"
        handler.setFormatter(ContextualFormatter(fmt))
        handler.addFilter(SensitiveDataFilter())
        handler.setLevel(TRACE_LEVEL_NUM)
        _handler = handler

    for logger_name in ("app", "worker", "ai_photo_lib", "sqlalchemy.engine"):
        logger = logging.getLogger(logger_name)
        if _handler not in logger.handlers:
            logger.handlers.clear()
            logger.addHandler(_handler)
        logger.propagate = False
        logger.setLevel(TRACE_LEVEL_NUM)
    return _handler


def apply_debug_config(debug_config) -> None:
    _ensure_handler()
    debug_matrix = debug_config.debug_matrix.model_dump()
    debug_mode = debug_config.debug_mode
    runtime_flags = derive_runtime_flags(debug_mode, debug_matrix)

    for field, logger_names in _LOGGER_GROUPS.items():
        level = python_logging_level(debug_matrix[field])
        for logger_name in logger_names:
            logging.getLogger(logger_name).setLevel(level)

    _runtime_debug_state.update(
        {
            "debug_mode": debug_mode,
            "debug_matrix": debug_matrix,
            **runtime_flags,
        }
    )
    logging.getLogger("app.logging").info(
        "Applied debug config at runtime. debug_mode=%s debug_matrix=%s",
        debug_mode,
        debug_matrix,
    )


def setup_logging(debug_config) -> None:
    apply_debug_config(debug_config)


def should_log_request_debug_middleware() -> bool:
    return bool(_runtime_debug_state["request_debug_middleware"])


def should_log_ai_raw_payload() -> bool:
    return bool(_runtime_debug_state["ai_raw_logging"])


def should_include_search_debug_payload() -> bool:
    return bool(_runtime_debug_state["search_debug_payload"])


def should_include_search_trace_payload() -> bool:
    return bool(_runtime_debug_state["search_trace_payload"])


def is_frontend_debug_panel_enabled() -> bool:
    return bool(_runtime_debug_state["frontend_debug_panel"])
