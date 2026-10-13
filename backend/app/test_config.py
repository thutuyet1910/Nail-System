"""Configuration loading: process env beats .env, .env fills gaps, defaults still work."""

import logging
import os
import subprocess
import sys
from pathlib import Path

from . import config

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROBE = (
    "import app.database as d, app.security, app.owner_catalog, os;"
    "print(d.DATABASE_URL);"
    "print(os.getenv('OWNER_API_BASE', ''))"
)


def _run_probe(tmp_path, env_file_text, **process_env):
    env_file = tmp_path / ".env"
    if env_file_text is not None:
        env_file.write_text(env_file_text, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "OWNER_API_BASE")}
    env["CHECKIN_ENV_FILE"] = str(env_file)
    env.update(process_env)
    result = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


class TestEnvLoading:

    def test_process_database_url_works(self, tmp_path):
        out = _run_probe(tmp_path, None, DATABASE_URL="sqlite:///./from_process.db")
        assert out[0] == "sqlite:///./from_process.db"

    def test_dotenv_database_url_used_when_process_absent(self, tmp_path):
        out = _run_probe(tmp_path, "DATABASE_URL=sqlite:///./from_dotenv.db\n")
        assert out[0] == "sqlite:///./from_dotenv.db"

    def test_process_env_beats_dotenv(self, tmp_path):
        out = _run_probe(
            tmp_path,
            "DATABASE_URL=sqlite:///./from_dotenv.db\nOWNER_API_BASE=http://dotenv.test\n",
            DATABASE_URL="sqlite:///./from_process.db",
            OWNER_API_BASE="http://process.test",
        )
        assert out == ["sqlite:///./from_process.db", "http://process.test"]

    def test_default_database_url_when_nothing_supplied(self, tmp_path):
        out = _run_probe(tmp_path, None)
        assert out[0] == "sqlite:///./nail_system.db"

    def test_owner_api_base_from_dotenv_when_absent(self, tmp_path):
        out = _run_probe(tmp_path, "OWNER_API_BASE=http://dotenv.test\n")
        assert out[1] == "http://dotenv.test"

    def test_load_env_never_overrides_existing(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("CHECKIN_INTERNAL_SERVICE_TOKEN=from-dotenv\n", encoding="utf-8")
        monkeypatch.setenv("CHECKIN_INTERNAL_SERVICE_TOKEN", "from-process")
        config.load_env(env_file)
        assert os.environ["CHECKIN_INTERNAL_SERVICE_TOKEN"] == "from-process"

    def test_missing_env_file_is_fine(self, tmp_path):
        assert config.load_env(tmp_path / "absent.env") is False

    def test_internal_token_still_required_and_checked(self, monkeypatch):
        from fastapi.testclient import TestClient
        from .main import app

        anonymous = TestClient(app)
        assert anonymous.get("/today-checkins", headers={"X-Internal-Service-Token": "wrong"}).status_code == 401
        monkeypatch.delenv("CHECKIN_INTERNAL_SERVICE_TOKEN")
        assert anonymous.get("/today-checkins", headers={"X-Internal-Service-Token": "x"}).status_code == 503

    def test_secrets_not_logged(self, tmp_path, caplog, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("DATABASE_URL=sqlite:///./secretish.db\nEMAIL_PASSWORD=hunter2\n", encoding="utf-8")
        monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
        with caplog.at_level(logging.DEBUG):
            config.load_env(env_file)
        assert "hunter2" not in caplog.text and "secretish" not in caplog.text
