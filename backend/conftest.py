"""Test isolation. This file is loaded by pytest BEFORE the `app` package is imported.

Importing the app opens its database and creates/updates the tables at import time, so the database location
has to be decided first. Every test run therefore gets its own temporary folder and a database inside it:

* the developer's backend/nail_system.db (and anything under ProgramData) is never opened by a test;
* parallel or repeated runs never share a file (the folder name is unique per process);
* nothing from the developer's environment (a User-level DATABASE_URL, NAILSYSTEM_MODE=product, a .env file)
  can redirect a test at a real database or at the installed layout.

`app/test_isolation.py` proves it; `pytest.ini` makes sure this file is found whichever way pytest is started.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

for _name in ("NAILSYSTEM_MODE", "NAILSYSTEM_HOME", "NAILSYSTEM_ALLOW_ENV_OVERRIDE", "PROGRAMDATA_OVERRIDE"):
    os.environ.pop(_name, None)

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="nailsystem-checkin-tests-"))
os.environ["NAILSYSTEM_TEST_DB_DIR"] = str(_TEST_DB_DIR)
os.environ["DATABASE_URL"] = "sqlite:///" + (_TEST_DB_DIR / "app.db").as_posix()  # unconditional: the environment must not win
os.environ["CHECKIN_ENV_FILE"] = str(_TEST_DB_DIR / "no-such.env")                # a developer's backend/.env must not change tests
os.environ["CHECKIN_INTERNAL_SERVICE_TOKEN"] = "test-internal-token"
atexit.register(shutil.rmtree, str(_TEST_DB_DIR), True)
