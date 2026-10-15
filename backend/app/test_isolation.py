"""The test suite never touches a real database.

Importing the app opens its database and creates tables at import time, so tests must be pointed at a throwaway
database BEFORE the app is imported (backend/conftest.py). These checks prove that, including by running the whole
suite in a separate process and comparing the developer's database files before and after.
"""

import hashlib
import os
import pathlib
import subprocess
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
DEV_DB_NAMES = ("nail_system.db", "nail_system-private-test.db")
IS_NESTED_RUN = bool(os.environ.get("NAILSYSTEM_ISOLATION_CHILD"))


def snapshot():
    """Every database-looking file next to the app: name -> (size, mtime, content hash). New files show up too."""
    state = {}
    for path in sorted(BACKEND.iterdir()):
        if path.is_file() and (".db" in path.name or path.name.endswith(("-wal", "-shm", "-journal"))):
            data = path.read_bytes()
            state[path.name] = (len(data), path.stat().st_mtime_ns, hashlib.sha256(data).hexdigest())
    return state


def loaded_conftest_env(**extra):
    """Environment variables after backend/conftest.py has run in a fresh process, and whether its folder was cleaned up."""
    code = (
        "import importlib.util, json, os, pathlib\n"
        f"spec = importlib.util.spec_from_file_location('isolation_conftest', r'{BACKEND / 'conftest.py'}')\n"
        "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
        "print(json.dumps({k: os.environ.get(k) for k in ('DATABASE_URL', 'NAILSYSTEM_MODE', 'NAILSYSTEM_HOME', 'NAILSYSTEM_TEST_DB_DIR', 'CHECKIN_ENV_FILE')}))\n"
    )
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **extra}
    import json
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


class TestTheSuiteIsIsolated:

    def test_the_app_is_attached_to_a_temporary_database_not_the_developers(self):
        from . import database

        folder = pathlib.Path(os.environ["NAILSYSTEM_TEST_DB_DIR"]).resolve()
        attached = pathlib.Path(database.engine.url.database).resolve()
        assert folder in attached.parents and folder.name.startswith("nailsystem-checkin-tests-")
        assert attached.parent != BACKEND.resolve() and attached.name not in DEV_DB_NAMES
        assert not str(attached).lower().startswith(os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "NailSystem").lower())

    def test_the_test_engine_is_in_the_same_temporary_folder_and_not_in_the_working_directory(self):
        from . import test_main

        folder = pathlib.Path(os.environ["NAILSYSTEM_TEST_DB_DIR"]).resolve()
        used = pathlib.Path(test_main.engine.url.database).resolve()
        assert used.parent == folder and used.name == "test_checkin.db"

    def test_the_installed_layout_is_off_for_every_test(self):
        for name in ("NAILSYSTEM_MODE", "NAILSYSTEM_HOME", "NAILSYSTEM_ALLOW_ENV_OVERRIDE"):
            assert name not in os.environ, name
        assert not pathlib.Path(os.environ["CHECKIN_ENV_FILE"]).exists(), "a developer's .env is not read by tests"

    def test_each_run_gets_its_own_folder_and_removes_it_afterwards(self):
        first, second = loaded_conftest_env(), loaded_conftest_env()
        assert first["NAILSYSTEM_TEST_DB_DIR"] != second["NAILSYSTEM_TEST_DB_DIR"], "parallel or repeated runs cannot collide"
        assert not pathlib.Path(first["NAILSYSTEM_TEST_DB_DIR"]).exists(), "the folder is deleted when the run ends"

    def test_the_developers_environment_cannot_redirect_a_test_run(self, tmp_path):
        seen = loaded_conftest_env(DATABASE_URL="sqlite:///C:/real/salon.db", NAILSYSTEM_MODE="product", NAILSYSTEM_HOME=str(tmp_path / "ProgramDataLike"))
        assert pathlib.Path(seen["NAILSYSTEM_TEST_DB_DIR"]).as_posix() in seen["DATABASE_URL"] and "salon.db" not in seen["DATABASE_URL"]
        assert seen["NAILSYSTEM_MODE"] is None and seen["NAILSYSTEM_HOME"] is None

    def test_a_run_that_bypasses_the_root_conftest_is_stopped_before_any_test(self, tmp_path):
        """Simulates the old failure mode (the root conftest not loaded): the guard refuses to run."""
        env = {k: v for k, v in os.environ.items() if k not in ("NAILSYSTEM_TEST_DB_DIR", "NAILSYSTEM_ISOLATION_CHILD")}
        env.update({"DATABASE_URL": "sqlite:///" + (tmp_path / "stand-in.db").as_posix(), "PYTHONDONTWRITEBYTECODE": "1"})
        out = subprocess.run([sys.executable, "-m", "pytest", "--confcutdir=app", "app/test_nailsystem_backup.py", "-q", "-p", "no:cacheprovider"],
                             cwd=str(BACKEND), capture_output=True, text=True, env=env, timeout=180)
        assert out.returncode == 3, out.stdout[-800:] + out.stderr[-800:]
        assert "Refusing to run" in out.stdout + out.stderr

    @pytest.mark.skipif(IS_NESTED_RUN, reason="this check runs the suite itself")
    def test_the_whole_suite_leaves_the_developers_database_files_untouched(self):
        before = snapshot()
        env = {**os.environ, "NAILSYSTEM_ISOLATION_CHILD": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("NAILSYSTEM_TEST_DB_DIR", None)
        out = subprocess.run([sys.executable, "-m", "pytest", "app", "-q", "-p", "no:cacheprovider", "--ignore=app/test_isolation.py"],
                             cwd=str(BACKEND), capture_output=True, text=True, env=env, timeout=900)
        assert out.returncode == 0, out.stdout[-1500:]
        after = snapshot()
        assert after == before, {name: (before.get(name), after.get(name)) for name in set(before) | set(after) if before.get(name) != after.get(name)}
