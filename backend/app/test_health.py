"""GET /health: what the launcher asks every few seconds. Alive + database answers; nothing else."""

import re

from fastapi.testclient import TestClient

from . import database
from .database import get_db
from .main import app
from .test_main import client, reset_db  # noqa: F401  (autouse fixtures come from test_main)


class TestHealth:

    def test_it_answers_without_any_credential_and_says_which_app_it_is(self):
        anonymous = TestClient(app)  # no device token, no internal token
        response = anonymous.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"status", "app", "version", "contract_version"}
        assert body["status"] == "ok" and body["app"] == "checkin" and body["contract_version"] == 1
        assert re.fullmatch(r"\d+\.\d+\.\d+", body["version"])

    def test_it_reveals_nothing_about_the_installation(self):
        text = TestClient(app).get("/health").text.lower()
        for secret in ("test-internal-token", "sqlite", ".db", "c:\\", "/users/", "token", "password", "customers", "owner_api_base", "programdata"):
            assert secret not in text, secret

    def test_it_is_unavailable_when_the_database_does_not_answer(self):
        class Broken:
            def execute(self, *a, **k):
                raise RuntimeError("database is locked at C:/secret/path.db")

        app.dependency_overrides[get_db] = lambda: Broken()
        try:
            response = TestClient(app).get("/health")
        finally:
            from .test_main import override_get_db
            app.dependency_overrides[get_db] = override_get_db
        assert response.status_code == 503 and response.json() == {"status": "unavailable", "app": "checkin"}
        assert "secret" not in response.text and ".db" not in response.text

    def test_it_is_read_only(self):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(TestClient(app), method)("/health").status_code == 405

    def test_the_reverse_proxy_never_forwards_it(self):
        from .test_lan_poc import _caddy_allows
        assert not _caddy_allows("GET", "/api/checkin/health")
