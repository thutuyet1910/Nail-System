"""Environment loading for the Check-In backend.

Imported by `app/__init__.py`, so it runs before any submodule (database.py, security.py,
timeutils.py, ...) reads its settings, regardless of which module is imported first.

Development precedence: variables already set in the process / Windows User environment ALWAYS win;
`backend/.env` (or the file named by CHECKIN_ENV_FILE) only fills in variables that are missing.

Product mode (NAILSYSTEM_MODE=product) ignores .env completely: a forgotten file must never override the installed
configuration (see nailsystem_runtime.py for the full precedence).
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from . import nailsystem_runtime

DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path=None) -> bool:
    """Loads a .env file without overriding existing variables. Returns True if a file was read."""
    env_file = Path(path or os.getenv("CHECKIN_ENV_FILE") or DEFAULT_ENV_FILE)
    if not nailsystem_runtime.should_load_dotenv():
        if env_file.exists():
            logging.getLogger("nailsystem.runtime").warning(".env found at %s but ignored: product mode uses the installed configuration.", env_file)
        return False
    return load_dotenv(env_file, override=False)
