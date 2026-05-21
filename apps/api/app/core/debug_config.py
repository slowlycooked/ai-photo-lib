from __future__ import annotations

import logging
from copy import deepcopy

logger = logging.getLogger(__name__)

DEBUG_MODE_VALUES = ("OFF", "BASIC", "DEBUG", "TRACE", "CUSTOM")
LOG_LEVEL_VALUES = ("OFF", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE")
DEBUG_MATRIX_FIELDS = (
    "frontend_log_level",
    "backend_log_level",
    "ai_log_level",
    "search_log_level",
    "sql_log_level",
    "task_log_level",
)

TRACE_LEVEL_NUM = 5

_DEBUG_MODE_ALIASES: dict[str, str] = {
    "off": "OFF",
    "basic": "BASIC",
    "debug": "DEBUG",
    "trace": "TRACE",
    "custom": "CUSTOM",
}

_LOG_LEVEL_ALIASES: dict[str, str] = {
    "off": "OFF",
    "error": "ERROR",
    "warning": "WARNING",
    "warn": "WARNING",
    "info": "INFO",
    "debug": "DEBUG",
    "trace": "TRACE",
}

_LOG_LEVEL_RANK: dict[str, int] = {
    "OFF": 0,
    "ERROR": 1,
    "WARNING": 2,
    "INFO": 3,
    "DEBUG": 4,
    "TRACE": 5,
}

PRESET_DEBUG_MATRICES: dict[str, dict[str, str]] = {
    "OFF": {
        "frontend_log_level": "OFF",
        "backend_log_level": "OFF",
        "ai_log_level": "OFF",
        "search_log_level": "OFF",
        "sql_log_level": "OFF",
        "task_log_level": "OFF",
    },
    "BASIC": {
        "frontend_log_level": "INFO",
        "backend_log_level": "INFO",
        "ai_log_level": "INFO",
        "search_log_level": "INFO",
        "sql_log_level": "WARNING",
        "task_log_level": "INFO",
    },
    "DEBUG": {
        "frontend_log_level": "DEBUG",
        "backend_log_level": "DEBUG",
        "ai_log_level": "DEBUG",
        "search_log_level": "DEBUG",
        "sql_log_level": "DEBUG",
        "task_log_level": "DEBUG",
    },
    "TRACE": {
        "frontend_log_level": "TRACE",
        "backend_log_level": "TRACE",
        "ai_log_level": "TRACE",
        "search_log_level": "TRACE",
        "sql_log_level": "TRACE",
        "task_log_level": "TRACE",
    },
}


def ensure_trace_logging_level() -> None:
    if logging.getLevelName(TRACE_LEVEL_NUM) != "TRACE":
        logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")

    if not hasattr(logging.Logger, "trace"):
        def _trace(self: logging.Logger, message: str, *args, **kwargs) -> None:
            if self.isEnabledFor(TRACE_LEVEL_NUM):
                self._log(TRACE_LEVEL_NUM, message, args, **kwargs)

        logging.Logger.trace = _trace  # type: ignore[attr-defined]


def normalize_debug_mode(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Debug mode must be a string, got {type(value).__name__!r}"
        )
    normalized = _DEBUG_MODE_ALIASES.get(value.strip().lower())
    if normalized is None:
        raise ValueError(
            f"Invalid debug mode {value!r}. Supported values: {', '.join(DEBUG_MODE_VALUES)}"
        )
    return normalized


def normalize_log_level(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Log level must be a string, got {type(value).__name__!r}"
        )
    normalized = _LOG_LEVEL_ALIASES.get(value.strip().lower())
    if normalized is None:
        raise ValueError(
            f"Invalid log level {value!r}. Supported values: {', '.join(LOG_LEVEL_VALUES)}"
        )
    return normalized


def _log_fallback_warning(
    *,
    setting_key: str,
    invalid_value: object,
    fallback_value: object,
    field_name: str,
) -> None:
    logger.warning(
        "Invalid debug configuration value detected "
        "(setting_key=%s, field_name=%s, invalid_value=%r, fallback_value=%r).",
        setting_key,
        field_name,
        invalid_value,
        fallback_value,
    )


def normalize_debug_mode_safe(
    value: object,
    *,
    fallback: str = "BASIC",
    setting_key: str = "global_debug_config",
    field_name: str = "debug_mode",
) -> str:
    try:
        return normalize_debug_mode(value)
    except ValueError:
        _log_fallback_warning(
            setting_key=setting_key,
            invalid_value=value,
            fallback_value=fallback,
            field_name=field_name,
        )
        return fallback


def normalize_log_level_safe(
    value: object,
    *,
    fallback: str,
    setting_key: str = "global_debug_config",
    field_name: str,
) -> str:
    try:
        return normalize_log_level(value)
    except ValueError:
        _log_fallback_warning(
            setting_key=setting_key,
            invalid_value=value,
            fallback_value=fallback,
            field_name=field_name,
        )
        return fallback


def build_preset_matrix(mode: str) -> dict[str, str]:
    normalized_mode = normalize_debug_mode(mode)
    if normalized_mode == "CUSTOM":
        raise ValueError("CUSTOM does not have a built-in preset matrix")
    return deepcopy(PRESET_DEBUG_MATRICES[normalized_mode])


def build_presets_map() -> dict[str, dict[str, str]]:
    return {mode: build_preset_matrix(mode) for mode in PRESET_DEBUG_MATRICES}


def default_matrix_for_mode(mode: str) -> dict[str, str]:
    normalized_mode = normalize_debug_mode(mode)
    if normalized_mode == "CUSTOM":
        return build_preset_matrix("BASIC")
    return build_preset_matrix(normalized_mode)


def is_level_at_least(current_level: str, threshold_level: str) -> bool:
    current = normalize_log_level(current_level)
    threshold = normalize_log_level(threshold_level)
    return _LOG_LEVEL_RANK[current] >= _LOG_LEVEL_RANK[threshold]


def legacy_debug_level_to_mode(value: object) -> str:
    normalized = normalize_log_level_safe(
        value,
        fallback="INFO",
        setting_key="global_debug_config",
        field_name="debug_level",
    )
    if normalized == "OFF":
        return "OFF"
    if normalized == "TRACE":
        return "TRACE"
    if normalized == "DEBUG":
        return "DEBUG"
    return "BASIC"


def python_logging_level(level: str) -> int:
    normalized = normalize_log_level(level)
    if normalized == "OFF":
        # logging.CRITICAL + 1 (51) effectively disables all log output.
        return logging.CRITICAL + 1
    if normalized == "TRACE":
        return TRACE_LEVEL_NUM
    if normalized == "DEBUG":
        return logging.DEBUG
    if normalized == "INFO":
        return logging.INFO
    if normalized == "WARNING":
        return logging.WARNING
    return logging.ERROR


def derive_runtime_flags(debug_mode: str, debug_matrix: dict[str, str]) -> dict[str, bool]:
    if normalize_debug_mode(debug_mode) == "OFF":
        return {
            "request_debug_middleware": False,
            "ai_raw_logging": False,
            "search_debug_payload": False,
            "search_trace_payload": False,
            "frontend_debug_panel": False,
        }

    return {
        "request_debug_middleware": is_level_at_least(
            debug_matrix["backend_log_level"], "DEBUG"
        ),
        "ai_raw_logging": is_level_at_least(debug_matrix["ai_log_level"], "TRACE"),
        "search_debug_payload": is_level_at_least(
            debug_matrix["search_log_level"], "DEBUG"
        ),
        "search_trace_payload": is_level_at_least(
            debug_matrix["search_log_level"], "TRACE"
        ),
        "frontend_debug_panel": True,
    }