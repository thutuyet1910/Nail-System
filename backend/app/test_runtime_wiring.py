"""The Check-In backend really uses the installed layout (product mode) and still behaves as before in development.

Each check starts a fresh Python process (an app's settings are read once, at import), against a temporary
NAILSYSTEM_HOME. Nothing here touches the real C:\\ProgramData\\NailSystem or the developer's database.
"""

import json
import os
import pathlib
import subprocess
import sys

import pytest

from . import nailsystem_runtime as rt

APP_DIR = pathlib.Path(__file__).resolve().parent
BACKEND = APP_DIR.parent
REPO = BACKEND.parent
WINDOWS = sys.platform == "win32"
needs_windows = pytest.mark.skipif(not WINDOWS, reason="Windows DPAPI")
TOKEN = "wiring-test-token-" + "Zx9Qw3Er" * 3

# Everything the apps (or this layer) read; the child process starts without any of it.
MANAGED = ("DATABASE_URL", "ALLOWED_ORIGINS", "SALON_TIMEZONE", "CHECKIN_API_BASE", "OWNER_API_BASE", "CHECKIN_INTERNAL_SERVICE_TOKEN",
           "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "OPENAI_API_KEY", "OWNER_BOOTSTRAP_PASSWORD", "OWNER_PASSWORD_HASH", "EMAIL_PASSWORD",
           "NAILSYSTEM_MODE", "NAILSYSTEM_HOME", "NAILSYSTEM_ALLOW_ENV_OVERRIDE", "CHECKIN_ENV_FILE", "PROGRAMDATA")


def child_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in MANAGED}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    env.update(extra)
    return env


def run(code, env, timeout=180):
    return subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND), env=env, capture_output=True, text=True, timeout=timeout)


def installed(tmp_path, *, token=TOKEN, extra=None):
    home = tmp_path / "NailSystem"
    assert rt.main(["init", "--no-acl", "--salon-id", "wiring"], {"NAILSYSTEM_HOME": str(home)}) == 0
    store = rt.DpapiSecrets(rt.RuntimePaths(home).secrets_file)
    if token:
        store.set("CHECKIN_INTERNAL_SERVICE_TOKEN", token)
    for name, value in (extra or {}).items():
        store.set(name, value)
    return home, rt.RuntimePaths(home)


PROBE = r"""
import json, logging, os
import app.main as main
import app.database as database
from fastapi.testclient import TestClient
client = TestClient(main.app)
connection = database.engine.connect()
pragma = lambda name: connection.exec_driver_sql(f"PRAGMA {name}").scalar()
connection.exec_driver_sql("CREATE TEMP TABLE parent (id INTEGER PRIMARY KEY)")
connection.exec_driver_sql("CREATE TEMP TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))")
try:
    connection.exec_driver_sql("INSERT INTO child (parent_id) VALUES (999)")
    orphan_refused = False
except Exception:
    orphan_refused = True
logging.getLogger("nail_system").warning("probe for 6025550177 jane.doe@example.com token=%s", os.environ.get("CHECKIN_INTERNAL_SERVICE_TOKEN"))
for handler in logging.getLogger().handlers:
    handler.flush()
print("RESULT " + json.dumps({
    "root": client.get("/").status_code,
    "database_url": database.DATABASE_URL,
    "journal": str(pragma("journal_mode")).lower(), "foreign_keys": pragma("foreign_keys"), "busy_ms": pragma("busy_timeout"),
    "orphan_refused": orphan_refused,
    "token_ok": os.environ.get("CHECKIN_INTERNAL_SERVICE_TOKEN") == os.environ.get("EXPECT_TOKEN"),
    "owner_base": os.environ.get("OWNER_API_BASE"), "tz": os.environ.get("SALON_TIMEZONE"),
    "voice_key_in_env": "OPENAI_API_KEY" in os.environ or "TWILIO_AUTH_TOKEN" in os.environ,
    "mode": __import__("app").RUNTIME.mode,
}))
"""


def result_of(process):
    lines = [line for line in process.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, f"no result:\n{process.stdout[-1500:]}\n{process.stderr[-2500:]}"
    return json.loads(lines[-1][len("RESULT "):])


# ══════════════════════════════════════════════════════════════════════════════
class TestProductMode:

    @needs_windows
    def test_the_app_starts_on_the_installed_layout_with_hardened_sqlite_and_redacted_logs(self, tmp_path):
        home, paths = installed(tmp_path)
        stale = tmp_path / "stale-from-an-old-session.db"
        process = run(PROBE, child_env(NAILSYSTEM_MODE="product", NAILSYSTEM_HOME=str(home), EXPECT_TOKEN=TOKEN,
                                        DATABASE_URL=f"sqlite:///{stale.as_posix()}", CHECKIN_INTERNAL_SERVICE_TOKEN="stale-token-from-a-dev-session",
                                        OPENAI_API_KEY="tk-leftover-in-the-environment-123"))
        result = result_of(process)
        assert result["root"] == 200 and result["mode"] == "product"
        assert result["database_url"] == rt.sqlite_url(paths.db_path("checkin"))
        assert paths.db_path("checkin").is_file() and not stale.exists(), "no silent fallback to an old or repository database"
        assert (result["journal"], result["foreign_keys"], result["busy_ms"]) == ("wal", 1, 5000)
        assert result["orphan_refused"] is True, "foreign keys are enforced on the real engine"
        assert result["token_ok"] is True and result["voice_key_in_env"] is False
        assert result["owner_base"] == "http://127.0.0.1:8001" and result["tz"] == "America/Phoenix"
        log = (paths.log_dir("checkin") / "checkin.log").read_text(encoding="utf-8")
        assert "probe for" in log and "Ignored process-environment values" in log
        for leaked in (TOKEN, "6025550177", "jane.doe", "stale-token", "tk-leftover"):
            assert leaked not in log, f"{leaked!r} reached the log file"
            assert leaked not in process.stderr, f"{leaked!r} reached the console"
            assert leaked not in process.stdout, f"{leaked!r} reached stdout"

    @needs_windows
    def test_a_missing_required_secret_stops_the_app_with_a_plain_message(self, tmp_path):
        home, _ = installed(tmp_path, token=None)
        process = run("import app.main", child_env(NAILSYSTEM_MODE="product", NAILSYSTEM_HOME=str(home),
                                                   CHECKIN_INTERNAL_SERVICE_TOKEN="dev-token-that-must-not-count"))
        assert process.returncode != 0
        assert "CHECKIN_INTERNAL_SERVICE_TOKEN" in process.stderr and "dev-token-that-must-not-count" not in process.stderr + process.stdout

    def test_a_missing_salon_json_stops_the_app(self, tmp_path):
        home = tmp_path / "NailSystem"
        process = run("import app.main", child_env(NAILSYSTEM_MODE="product", NAILSYSTEM_HOME=str(home)))
        assert process.returncode != 0 and "salon.json was not found" in process.stderr
        assert not (home / "data" / "checkin" / "checkin.db").exists()

    @needs_windows
    def test_a_malformed_salon_json_stops_the_app(self, tmp_path):
        home, paths = installed(tmp_path)
        paths.salon_json.write_text('{"schema_version": 7}')
        process = run("import app.main", child_env(NAILSYSTEM_MODE="product", NAILSYSTEM_HOME=str(home)))
        assert process.returncode != 0 and "unsupported schema_version 7" in process.stderr

    @needs_windows
    def test_a_forgotten_dotenv_cannot_override_the_installed_configuration(self, tmp_path):
        home, paths = installed(tmp_path)
        env_file = tmp_path / "forgotten.env"
        env_file.write_text(f"DATABASE_URL=sqlite:///{(tmp_path / 'from-dotenv.db').as_posix()}\nSALON_TIMEZONE=Asia/Tokyo\nOWNER_API_BASE=http://evil.example\n")
        process = run(PROBE, child_env(NAILSYSTEM_MODE="product", NAILSYSTEM_HOME=str(home), CHECKIN_ENV_FILE=str(env_file), EXPECT_TOKEN=TOKEN))
        result = result_of(process)
        assert result["database_url"] == rt.sqlite_url(paths.db_path("checkin")) and result["tz"] == "America/Phoenix" and result["owner_base"] == "http://127.0.0.1:8001"
        assert not (tmp_path / "from-dotenv.db").exists()
        assert ".env found" in process.stderr and "ignored" in process.stderr, "the ignored file is reported by name, not silently"

    @needs_windows
    def test_support_mode_is_the_only_way_for_the_environment_to_win_and_it_is_reported(self, tmp_path):
        home, paths = installed(tmp_path)
        process = run(PROBE, child_env(NAILSYSTEM_MODE="product", NAILSYSTEM_HOME=str(home), NAILSYSTEM_ALLOW_ENV_OVERRIDE="true",
                                        SALON_TIMEZONE="America/Los_Angeles", EXPECT_TOKEN=TOKEN))
        result = result_of(process)
        assert result["tz"] == "America/Los_Angeles"
        assert "NAILSYSTEM_ALLOW_ENV_OVERRIDE is on" in (paths.log_dir("checkin") / "checkin.log").read_text(encoding="utf-8")


class TestDevelopmentMode:

    def test_without_any_new_setting_the_app_behaves_exactly_as_before(self, tmp_path):
        db = tmp_path / "dev.db"
        process = run(PROBE, child_env(DATABASE_URL=f"sqlite:///{db.as_posix()}", CHECKIN_INTERNAL_SERVICE_TOKEN="dev-token-123456789", EXPECT_TOKEN="dev-token-123456789"))
        result = result_of(process)
        assert result["mode"] == "development" and result["root"] == 200
        assert result["database_url"] == f"sqlite:///{db.as_posix()}" and db.is_file()
        assert (result["journal"], result["foreign_keys"], result["busy_ms"]) == ("wal", 1, 5000) and result["orphan_refused"] is True
        assert result["token_ok"] is True
        assert not (tmp_path / "NailSystem").exists()

    def test_dotenv_still_fills_in_what_the_environment_lacks_but_never_overrides_it(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(f"DATABASE_URL=sqlite:///{(tmp_path / 'from-dotenv.db').as_posix()}\nSALON_TIMEZONE=Asia/Tokyo\n")
        result = result_of(run(PROBE, child_env(CHECKIN_ENV_FILE=str(env_file), SALON_TIMEZONE="America/Denver")))
        assert result["tz"] == "America/Denver", "the environment wins over .env"
        assert result["database_url"].endswith("from-dotenv.db") and (tmp_path / "from-dotenv.db").is_file(), ".env fills in what is missing"

    def test_the_developer_can_opt_in_to_the_installed_layout_without_product_protections(self, tmp_path):
        home = tmp_path / "dev-home"
        assert rt.main(["init", "--no-acl"], {"NAILSYSTEM_HOME": str(home)}) == 0
        result = result_of(run(PROBE, child_env(NAILSYSTEM_HOME=str(home), CHECKIN_INTERNAL_SERVICE_TOKEN="dev-token-123456789")))
        assert result["mode"] == "development" and result["database_url"] == rt.sqlite_url(rt.RuntimePaths(home).db_path("checkin"))
        assert not list((home / "logs").rglob("*.log")), "development logs stay on the console"


class TestWiring:

    def test_the_package_loads_dotenv_first_and_then_bootstraps_before_any_submodule(self):
        text = (APP_DIR / "__init__.py").read_text(encoding="utf-8")
        assert text.index("load_env()") < text.index('nailsystem_runtime.bootstrap("checkin")')
        assert "from . import main" not in text and "import database" not in text

    def test_the_database_module_installs_the_pragmas_and_dotenv_is_skipped_in_product_mode(self):
        assert "install_sqlite_pragmas(engine)" in (APP_DIR / "database.py").read_text(encoding="utf-8")
        assert "should_load_dotenv" in (APP_DIR / "config.py").read_text(encoding="utf-8")

    def test_the_test_database_gets_the_same_pragmas_as_the_real_one(self):
        assert "install_sqlite_pragmas(engine)" in (APP_DIR / "test_main.py").read_text(encoding="utf-8")

    def test_runtime_files_are_ignored_by_git(self):
        ignore = (REPO / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("*.db", "*.db-wal", "*.db-shm", "backups/"):
            assert pattern in ignore, pattern

    def test_no_secret_or_user_path_is_written_into_the_example_configuration(self):
        text = (REPO / ".env.example").read_text(encoding="utf-8")
        assert "NAILSYSTEM_MODE" in text and "C:\\Users" not in text and "AppData" not in text

    def test_logs_carry_ids_not_customer_names(self):
        source = (APP_DIR / "main.py").read_text(encoding="utf-8")
        assert "earned a %s%% loyalty discount" in source and "customer.full_name,\n" not in source[source.index("loyalty discount (visit"):][:200]

    def test_the_two_copies_of_the_shared_files_are_identical(self):
        sibling = REPO.parent / "Nail-System-owner-dashboard-git" / "backend"
        if not sibling.is_dir():
            pytest.skip("the Owner repository is not next to this one")
        for name in ("nailsystem_runtime.py", "nailsystem_backup.py", "test_nailsystem_runtime.py", "test_nailsystem_backup.py"):
            assert (APP_DIR / name).read_bytes() == (sibling / name).read_bytes(), f"{name} differs between the repositories"
