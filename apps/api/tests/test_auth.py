from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.auth_service import create_session_cookie  # noqa: E402


class AuthMiddlewareTest(unittest.TestCase):
    def setUp(self) -> None:
        self._settings_patches = [
            patch.object(settings, "auth_enabled", True),
            patch.object(settings, "auth_password", "secret"),
            patch.object(settings, "auth_session_secret", "test-session-secret"),
        ]
        for setting_patch in self._settings_patches:
            setting_patch.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for setting_patch in reversed(self._settings_patches):
            setting_patch.stop()

    def test_health_does_not_require_login(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)

    def test_protected_endpoint_requires_login(self):
        res = self.client.get("/projects")
        self.assertEqual(res.status_code, 401)

    def test_login_sets_session_cookie(self):
        res = self.client.post("/auth/login", json={"username": "admin", "password": "secret"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("ai_photo_session", res.cookies)

    def test_bad_login_is_rejected(self):
        res = self.client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        self.assertEqual(res.status_code, 401)

    def test_expired_session_is_rejected(self):
        issued_at = datetime.now(timezone.utc) - timedelta(hours=2)
        cookie = create_session_cookie("admin", now=issued_at)
        res = self.client.get("/projects", cookies={"ai_photo_session": cookie})
        self.assertEqual(res.status_code, 401)

    def test_missing_password_configuration_blocks_login_and_protected_routes(self):
        with patch("app.services.auth_service.settings.auth_password", ""):
            login_res = self.client.post(
                "/auth/login",
                json={"username": "admin", "password": "secret"},
            )
            protected_res = self.client.get("/projects")

        self.assertEqual(login_res.status_code, 503)
        self.assertEqual(protected_res.status_code, 503)


if __name__ == "__main__":
    unittest.main()
