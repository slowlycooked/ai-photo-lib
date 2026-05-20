from typing import Literal, Optional
from pydantic import BaseModel, Field, validator, root_validator

DEBUG_MODES = ("off", "basic", "debug", "trace")
LOG_LEVELS = ("ERROR", "WARNING", "INFO", "DEBUG")
MAX_LOG_TEXT_LENGTH_RANGE = (200, 10000)

DEFAULT_DEBUG_CONFIG = {
    "debug_mode": "off",
    "backend_log_level": "WARNING",
    "frontend_log_level": "WARNING",
    "ai_log_level": "WARNING",
    "search_log_level": "WARNING",
    "db_log_level": "WARNING",
    "task_log_level": "WARNING",
    "log_request_body": False,
    "log_ai_prompt": False,
    "log_ai_response": False,
    "log_sql": False,
    "log_stacktrace": False,
    "max_log_text_length": 1000,
}

class DebugConfig(BaseModel):
    debug_mode: Literal["off", "basic", "debug", "trace"] = Field("off")
    backend_log_level: Literal["ERROR", "WARNING", "INFO", "DEBUG"] = Field("WARNING")
    frontend_log_level: Literal["ERROR", "WARNING", "INFO", "DEBUG"] = Field("WARNING")
    ai_log_level: Literal["ERROR", "WARNING", "INFO", "DEBUG"] = Field("WARNING")
    search_log_level: Literal["ERROR", "WARNING", "INFO", "DEBUG"] = Field("WARNING")
    db_log_level: Literal["ERROR", "WARNING", "INFO", "DEBUG"] = Field("WARNING")
    task_log_level: Literal["ERROR", "WARNING", "INFO", "DEBUG"] = Field("WARNING")
    log_request_body: bool = Field(False)
    log_ai_prompt: bool = Field(False)
    log_ai_response: bool = Field(False)
    log_sql: bool = Field(False)
    log_stacktrace: bool = Field(False)
    max_log_text_length: int = Field(1000)

    @validator("max_log_text_length")
    def validate_max_log_text_length(cls, v):
        min_v, max_v = MAX_LOG_TEXT_LENGTH_RANGE
        if not (min_v <= v <= max_v):
            raise ValueError(f"max_log_text_length must be between {min_v} and {max_v}")
        return v
