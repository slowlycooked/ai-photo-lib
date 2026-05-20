import threading
import time
from sqlalchemy.orm import Session
from ..models.app_settings import AppSettings
from ..schemas.debug_config import DebugConfig, DEFAULT_DEBUG_CONFIG

class RuntimeSettingsService:
    _debug_config_cache = None
    _cache_expire = 10  # seconds
    _last_load = 0
    _lock = threading.Lock()

    @classmethod
    def get_debug_config(cls, db: Session) -> DebugConfig:
        now = time.time()
        with cls._lock:
            if cls._debug_config_cache and now - cls._last_load < cls._cache_expire:
                return cls._debug_config_cache
            row = db.query(AppSettings).filter(AppSettings.key == "global_debug_config").first()
            if row:
                config_dict = {**DEFAULT_DEBUG_CONFIG, **row.value_json}
            else:
                config_dict = DEFAULT_DEBUG_CONFIG.copy()
            config = DebugConfig(**config_dict)
            cls._debug_config_cache = config
            cls._last_load = now
            return config

    @classmethod
    def set_debug_config(cls, db: Session, config: DebugConfig):
        with cls._lock:
            row = db.query(AppSettings).filter(AppSettings.key == "global_debug_config").first()
            if row:
                row.value_json = config.dict()
            else:
                row = AppSettings(key="global_debug_config", value_json=config.dict())
                db.add(row)
            db.commit()
            cls._debug_config_cache = config
            cls._last_load = time.time()

    @classmethod
    def clear_cache(cls):
        with cls._lock:
            cls._debug_config_cache = None
            cls._last_load = 0
