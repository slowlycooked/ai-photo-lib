from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import ProgrammingError

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.core.debug_config import build_preset_matrix  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.debug_config import (  # noqa: E402
    DebugConfig,
    DebugConfigUpdate,
    DebugMatrix,
    build_default_debug_config,
)
from app.services.runtime_settings_service import (  # noqa: E402
    RuntimeSettingsService,
    RuntimeSettingsStorageUnavailableError,
    _is_missing_app_settings_table_error,
    _sanitise_stored_config,
)


def _camel_matrix(mode: str) -> dict[str, str]:
    matrix = build_preset_matrix(mode)
    return {
        "frontendLogLevel": matrix["frontend_log_level"],
        "backendLogLevel": matrix["backend_log_level"],
        "aiLogLevel": matrix["ai_log_level"],
        "searchLogLevel": matrix["search_log_level"],
        "sqlLogLevel": matrix["sql_log_level"],
        "taskLogLevel": matrix["task_log_level"],
    }


class _RaisingQuery:
    def __init__(self, exc: Exception):
        self._exc = exc

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        raise self._exc


class _DBStub:
    def __init__(self, exc: Exception):
        self._exc = exc

    def query(self, model):  # noqa: ANN001
        return _RaisingQuery(self._exc)


class _RowStub:
    def __init__(self, value_json: dict | None = None, updated_at: datetime | None = None):
        self.value_json = value_json or {}
        self.updated_at = updated_at or datetime.now(timezone.utc)


class _DBWithRow:
    def __init__(self, row):  # noqa: ANN001
        self._row = row
        self.added = None
        self.commit_count = 0

    def query(self, model):  # noqa: ANN001
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row

    def add(self, row):  # noqa: ANN001
        self.added = row
        self._row = row

    def commit(self):
        self.commit_count += 1


class MissingTableDetectionTest(unittest.TestCase):
    def _make_prog_error(self, msg: str) -> ProgrammingError:
        return ProgrammingError("SELECT ...", {}, Exception(msg))

    def test_postgres_missing_table_detected(self):
        exc = self._make_prog_error('relation "app_settings" does not exist')
        self.assertTrue(_is_missing_app_settings_table_error(exc))

    def test_direct_psycopg_type_name_detected(self):
        undefined_table_cls = type(
            "UndefinedTable",
            (Exception,),
            {"__module__": "psycopg.errors"},
        )
        inner = undefined_table_cls("relation does not exist")
        outer = ProgrammingError("SELECT ...", {}, Exception("wrapped"))
        outer.__cause__ = inner
        self.assertTrue(_is_missing_app_settings_table_error(outer))


class DebugConfigValidationTest(unittest.TestCase):
    def test_custom_matrix_requires_all_fields(self):
        with self.assertRaises(ValidationError):
            DebugConfigUpdate(debugMode="CUSTOM", debugMatrix={"sqlLogLevel": "DEBUG"})

    def test_invalid_log_level_rejected(self):
        with self.assertRaises(ValidationError):
            DebugConfigUpdate(
                debugMode="CUSTOM",
                debugMatrix={
                    "frontendLogLevel": "INFO",
                    "backendLogLevel": "INFO",
                    "aiLogLevel": "INFO",
                    "searchLogLevel": "INFO",
                    "sqlLogLevel": "VERBOSE",
                    "taskLogLevel": "INFO",
                },
            )


class SanitiseStoredConfigTest(unittest.TestCase):
    def test_missing_config_returns_basic(self):
        cfg = _sanitise_stored_config({})
        self.assertEqual(cfg.debug_mode, "BASIC")
        self.assertEqual(cfg.debug_matrix.model_dump(), build_preset_matrix("BASIC"))

    def test_invalid_mode_falls_back_to_basic(self):
        cfg = _sanitise_stored_config({"debug_mode": "broken"})
        self.assertEqual(cfg.debug_mode, "BASIC")
        self.assertEqual(cfg.debug_matrix.model_dump(), build_preset_matrix("BASIC"))

    def test_historical_invalid_log_level_falls_back_without_500(self):
        cfg = _sanitise_stored_config(
            {
                "debug_mode": "CUSTOM",
                "debug_matrix": {
                    "frontend_log_level": "TRACE",
                    "backend_log_level": "INFO",
                    "ai_log_level": "INFO",
                    "search_log_level": "INFO",
                    "sql_log_level": "NOT_A_LEVEL",
                    "task_log_level": "INFO",
                },
            }
        )
        self.assertEqual(cfg.debug_mode, "CUSTOM")
        self.assertEqual(cfg.debug_matrix.sql_log_level, "WARNING")

    def test_legacy_debug_level_maps_to_new_model(self):
        cfg = _sanitise_stored_config({"debug_level": "debug"})
        self.assertEqual(cfg.debug_mode, "DEBUG")
        self.assertEqual(cfg.debug_matrix.backend_log_level, "DEBUG")


class RuntimeSettingsServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        RuntimeSettingsService.clear_cache()

    def test_get_debug_config_returns_basic_when_row_missing(self):
        db = _DBWithRow(None)
        cfg = RuntimeSettingsService.get_debug_config(db)
        self.assertEqual(cfg.debug_mode, "BASIC")
        self.assertEqual(cfg.debug_matrix.model_dump(), build_preset_matrix("BASIC"))

    def test_get_debug_config_raises_domain_error_when_table_missing(self):
        exc = ProgrammingError(
            "SELECT ...",
            {},
            Exception('relation "app_settings" does not exist'),
        )
        db = _DBStub(exc)
        with self.assertRaises(RuntimeSettingsStorageUnavailableError):
            RuntimeSettingsService.get_debug_config(db)

    def test_set_debug_config_applies_runtime_update(self):
        db = _DBWithRow(None)
        payload = DebugConfigUpdate(
            debugMode="OFF",
            debugMatrix=DebugMatrix(**build_preset_matrix("BASIC")),
        )

        with patch("app.services.runtime_settings_service.apply_debug_config") as apply_mock:
            saved = RuntimeSettingsService.set_debug_config(db, payload)

        self.assertEqual(saved.debug_mode, "OFF")
        self.assertEqual(saved.debug_matrix.model_dump(), build_preset_matrix("OFF"))
        apply_mock.assert_called_once()
        self.assertEqual(db.commit_count, 1)

    def test_set_debug_config_updates_existing_row_with_selected_mode(self):
        existing_row = _RowStub(
            {
                "debug_mode": "OFF",
                "debug_matrix": build_preset_matrix("OFF"),
            }
        )
        db = _DBWithRow(existing_row)
        payload = DebugConfigUpdate(
            debugMode="DEBUG",
            debugMatrix=DebugMatrix(**build_preset_matrix("DEBUG")),
        )

        with patch("app.services.runtime_settings_service.apply_debug_config") as apply_mock:
            saved = RuntimeSettingsService.set_debug_config(db, payload)

        self.assertEqual(saved.debug_mode, "DEBUG")
        self.assertEqual(saved.debug_matrix.model_dump(), build_preset_matrix("DEBUG"))
        self.assertEqual(db._row.value_json["debug_mode"], "DEBUG")
        self.assertEqual(db._row.value_json["debug_matrix"]["frontend_log_level"], "DEBUG")
        apply_mock.assert_called_once()
        self.assertEqual(db.commit_count, 1)


class SettingsDebugEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        RuntimeSettingsService.clear_cache()
        self.client = TestClient(app)

    def test_get_returns_basic_when_no_config(self):
        with patch.object(
            RuntimeSettingsService,
            "get_debug_config",
            return_value=DebugConfig(**build_default_debug_config().model_dump()),
        ):
            resp = self.client.get("/settings/debug")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["debugMode"], "BASIC")
        self.assertEqual(body["debugMatrix"], _camel_matrix("BASIC"))
        self.assertIn("presets", body)

    def test_put_off_expands_all_matrix_levels_to_off(self):
        payload = {
            "debugMode": "OFF",
            "debugMatrix": build_preset_matrix("DEBUG"),
        }

        with patch.object(
            RuntimeSettingsService,
            "set_debug_config",
            return_value=DebugConfig(
                debugMode="OFF",
                debugMatrix=DebugMatrix(**build_preset_matrix("OFF")),
                updatedAt=datetime.now(timezone.utc),
            ),
        ):
            resp = self.client.put("/settings/debug", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["debugMatrix"], _camel_matrix("OFF"))

    def test_put_debug_expands_all_matrix_levels_to_debug(self):
        payload = {
            "debugMode": "DEBUG",
            "debugMatrix": build_preset_matrix("BASIC"),
        }

        with patch.object(
            RuntimeSettingsService,
            "set_debug_config",
            return_value=DebugConfig(
                debugMode="DEBUG",
                debugMatrix=DebugMatrix(**build_preset_matrix("DEBUG")),
                updatedAt=datetime.now(timezone.utc),
            ),
        ):
            resp = self.client.put("/settings/debug", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["debugMatrix"], _camel_matrix("DEBUG"))

    def test_put_basic_keeps_sql_warning_and_other_major_items_info(self):
        payload = {
            "debugMode": "BASIC",
            "debugMatrix": build_preset_matrix("TRACE"),
        }

        with patch.object(
            RuntimeSettingsService,
            "set_debug_config",
            return_value=DebugConfig(
                debugMode="BASIC",
                debugMatrix=DebugMatrix(**build_preset_matrix("BASIC")),
                updatedAt=datetime.now(timezone.utc),
            ),
        ):
            resp = self.client.put("/settings/debug", json=payload)

        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["debugMatrix"]["sqlLogLevel"], "WARNING")
        self.assertEqual(body["debugMatrix"]["backendLogLevel"], "INFO")
        self.assertEqual(body["debugMatrix"]["frontendLogLevel"], "INFO")

    def test_put_custom_valid_matrix_succeeds(self):
        payload = {
            "debugMode": "CUSTOM",
            "debugMatrix": {
                "frontendLogLevel": "INFO",
                "backendLogLevel": "DEBUG",
                "aiLogLevel": "TRACE",
                "searchLogLevel": "DEBUG",
                "sqlLogLevel": "WARNING",
                "taskLogLevel": "ERROR",
            },
        }

        with patch.object(
            RuntimeSettingsService,
            "set_debug_config",
            return_value=DebugConfig(
                debugMode="CUSTOM",
                debugMatrix=DebugMatrix(**payload["debugMatrix"]),
                updatedAt=datetime.now(timezone.utc),
            ),
        ):
            resp = self.client.put("/settings/debug", json=payload)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["debugMode"], "CUSTOM")
        self.assertEqual(resp.json()["debugMatrix"]["aiLogLevel"], "TRACE")

    def test_put_custom_missing_field_returns_422(self):
        payload = {
            "debugMode": "CUSTOM",
            "debugMatrix": {
                "frontendLogLevel": "INFO",
                "backendLogLevel": "DEBUG",
                "aiLogLevel": "TRACE",
                "searchLogLevel": "DEBUG",
                "sqlLogLevel": "WARNING",
            },
        }
        resp = self.client.put("/settings/debug", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_put_invalid_log_level_returns_422(self):
        payload = {
            "debugMode": "CUSTOM",
            "debugMatrix": {
                "frontendLogLevel": "INFO",
                "backendLogLevel": "DEBUG",
                "aiLogLevel": "TRACE",
                "searchLogLevel": "DEBUG",
                "sqlLogLevel": "NOT_A_LEVEL",
                "taskLogLevel": "INFO",
            },
        }
        resp = self.client.put("/settings/debug", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_put_returns_503_when_storage_unavailable(self):
        payload = {
            "debugMode": "BASIC",
            "debugMatrix": build_preset_matrix("BASIC"),
        }

        with patch.object(
            RuntimeSettingsService,
            "set_debug_config",
            side_effect=RuntimeSettingsStorageUnavailableError("table missing"),
        ):
            resp = self.client.put("/settings/debug", json=payload)

        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
