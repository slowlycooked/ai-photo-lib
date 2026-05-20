import logging
import re
from contextvars import ContextVar
from typing import Optional
from .services.runtime_settings_service import RuntimeSettingsService

# Context variables for request, project, task, photo
request_id_ctx = ContextVar("request_id", default=None)
project_id_ctx = ContextVar("project_id", default=None)
task_id_ctx = ContextVar("task_id", default=None)
photo_id_ctx = ContextVar("photo_id", default=None)

def set_log_context(request_id=None, project_id=None, task_id=None, photo_id=None):
    if request_id: request_id_ctx.set(request_id)
    if project_id: project_id_ctx.set(project_id)
    if task_id: task_id_ctx.set(task_id)
    if photo_id: photo_id_ctx.set(photo_id)

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
        return True

def truncate_log_text(text: str, max_length: int) -> str:
    if not isinstance(text, str):
        return text
    if len(text) > max_length:
        return text[:max_length] + "...[truncated]"
    return text

class ContextualFormatter(logging.Formatter):
    def format(self, record):
        ctx = get_log_context()
        for k, v in ctx.items():
            setattr(record, k, v)
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = record.msg.replace("\n", " ")
        return super().format(record)

def setup_logging(debug_config):
    root = logging.getLogger()
    for h in root.handlers:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    fmt = '[%(asctime)s][%(levelname)s][%(request_id)s][%(project_id)s][%(task_id)s][%(photo_id)s] %(name)s: %(message)s'
    handler.setFormatter(ContextualFormatter(fmt))
    handler.addFilter(SensitiveDataFilter())
    root.addHandler(handler)
    level = getattr(logging, debug_config.backend_log_level, logging.WARNING)
    root.setLevel(level)
