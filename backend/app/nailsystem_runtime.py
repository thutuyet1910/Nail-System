"""NailSystem runtime layout, configuration, secrets and logging.

THIS FILE IS IDENTICAL IN BOTH REPOSITORIES (Owner: backend/nailsystem_runtime.py, Check-In:
backend/app/nailsystem_runtime.py). It only uses the standard library and has no relative imports, so each
copy works wherever it sits. Change one, change the other (a test compares them when the sibling checkout exists).

Two modes, chosen explicitly (never inferred from the current directory):

    development (default)  Run from the repositories as before. Nothing outside the repo is touched unless the
                           developer opts in by setting NAILSYSTEM_HOME.
    product                The installed layout under C:\\ProgramData\\NailSystem (or NAILSYSTEM_HOME):

        config\\salon.json            non-secret deployment settings (validated, strict)
        secrets\\secrets.dat          Windows DPAPI-protected secrets (names only are ever listed)
        data\\owner\\owner.db          data\\checkin\\checkin.db
        backups\\owner\\  backups\\checkin\\
        logs\\owner\\  logs\\checkin\\  logs\\launcher\\ (reserved)

Precedence
----------
development:  1. process environment   2. .env (Check-In only, never overrides 1)
              3. salon.json (only when NAILSYSTEM_HOME is set)   4. built-in defaults
product:      1. protected secrets store (secrets)   2. salon.json / the installed layout (everything else managed)
              3. process environment, ONLY when NAILSYSTEM_ALLOW_ENV_OVERRIDE=true (support/debug; logged)
              4. built-in safe defaults.
              In product mode a stray environment variable or a forgotten .env can never replace an installed
              value: managed names are overwritten (or removed) at start-up and each ignored value is logged by NAME.

The application code keeps reading os.environ; `bootstrap()` is the single place that fills it, before any
other module reads its settings.
"""

from __future__ import annotations

import ctypes
import json
import logging
import logging.handlers
import os
import re
import secrets as _secrets
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

APPS = ("owner", "checkin")
SCHEMA_VERSION = 1

MODE_ENV = "NAILSYSTEM_MODE"
HOME_ENV = "NAILSYSTEM_HOME"
OVERRIDE_ENV = "NAILSYSTEM_ALLOW_ENV_OVERRIDE"
MODES = ("development", "product")

BACKEND_PORTS = {"checkin": 8000, "owner": 8001}  # loopback only; the proxy ports live in salon.json

# Names this layer manages. Anything not listed here keeps behaving exactly as before (plain environment).
SECRET_NAMES = {
    "owner": (
        "CHECKIN_INTERNAL_SERVICE_TOKEN",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "OWNER_BOOTSTRAP_PASSWORD",
        "OWNER_PASSWORD_HASH",
    ),
    "checkin": ("CHECKIN_INTERNAL_SERVICE_TOKEN", "EMAIL_PASSWORD"),
}
REQUIRED_SECRETS = ("CHECKIN_INTERNAL_SERVICE_TOKEN",)
ALL_SECRET_NAMES = tuple(sorted({name for names in SECRET_NAMES.values() for name in names}))
# Decided explicitly: the Twilio phone NUMBER is public (it is shown in Salon Settings) so it is configuration,
# not a secret; it stays an environment setting until the voice settings move into salon.json. The Twilio account
# SID is treated as a secret (it identifies the account).


class RuntimeConfigError(Exception):
    """A clear, user-presentable problem with the installed layout, salon.json or a secret."""


class SecretsError(RuntimeConfigError):
    pass


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


# ------------------------------------------------------------------------------------------------
# Mode and paths
# ------------------------------------------------------------------------------------------------
def current_mode(environ=None) -> str:
    environ = os.environ if environ is None else environ
    mode = str(environ.get(MODE_ENV, "development")).strip().lower() or "development"
    if mode not in MODES:
        raise RuntimeConfigError(f"{MODE_ENV}={mode!r} is not valid. Use 'development' or 'product'.")
    return mode


def _inside_git_checkout(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in [path, *path.parents])


def resolve_home(environ=None, mode: str | None = None) -> Path | None:
    """The NailSystem data root, or None (development without NAILSYSTEM_HOME)."""
    environ = os.environ if environ is None else environ
    mode = mode or current_mode(environ)
    explicit = str(environ.get(HOME_ENV, "")).strip()
    if explicit:
        home = Path(explicit)
        if not home.is_absolute():
            raise RuntimeConfigError(f"{HOME_ENV} must be an absolute path (got {explicit!r}).")
    elif mode == "product":
        program_data = str(environ.get("PROGRAMDATA", "")).strip()
        if not program_data:
            raise RuntimeConfigError("PROGRAMDATA is not set, so the installed data folder cannot be located. Set " + HOME_ENV + " to the NailSystem data folder.")
        home = Path(program_data) / "NailSystem"
    else:
        return None
    if mode == "product" and _inside_git_checkout(home):
        raise RuntimeConfigError(f"The data folder {home} is inside a Git working copy. Production data never belongs in a repository or the install folder.")
    return home


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def salon_json(self) -> Path:
        return self.config_dir / "salon.json"

    @property
    def secrets_dir(self) -> Path:
        return self.root / "secrets"

    @property
    def secrets_file(self) -> Path:
        return self.secrets_dir / "secrets.dat"

    def data_dir(self, app: str) -> Path:
        return self.root / "data" / _check_app(app)

    def db_path(self, app: str) -> Path:
        return self.data_dir(app) / f"{app}.db"

    def backup_dir(self, app: str) -> Path:
        return self.root / "backups" / _check_app(app)

    def log_dir(self, app: str) -> Path:
        return self.root / "logs" / _check_app(app)

    def ensure(self, apps=APPS, *, include_secrets: bool = True) -> None:
        """Creates every directory the given apps need. A failure names the folder and says what to do."""
        wanted = [self.root, self.config_dir]
        if include_secrets:
            wanted.append(self.secrets_dir)
        for app in apps:
            wanted += [self.data_dir(app), self.backup_dir(app), self.log_dir(app)]
        wanted.append(self.root / "logs" / "launcher")
        for folder in wanted:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise RuntimeConfigError(
                    f"Cannot create the folder {folder}: {exc.strerror or exc}. Run the installer (or create it as an "
                    f"administrator) and give the account that runs NailSystem write access to {self.root}."
                ) from exc
            if not folder.is_dir():
                raise RuntimeConfigError(f"{folder} exists but is not a folder.")


def _check_app(app: str) -> str:
    if app not in APPS:
        raise RuntimeConfigError(f"Unknown app {app!r}; expected one of {APPS}.")
    return app


def sqlite_url(path: Path) -> str:
    return "sqlite:///" + str(path).replace("\\", "/")


def sqlite_path_from_url(url: str) -> Path | None:
    """The file behind a sqlite:/// URL, or None for memory / other databases."""
    if not url.startswith("sqlite:///"):
        return None
    raw = url[len("sqlite:///"):].split("?", 1)[0]
    if not raw or raw == ":memory:":
        return None
    return Path(raw)


# ------------------------------------------------------------------------------------------------
# salon.json (non-secret deployment settings)
# ------------------------------------------------------------------------------------------------
MAX_CONFIG_BYTES = 64 * 1024
_SALON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_TIER = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_SECRET_LOOKING_KEY = re.compile(r"(?i)(secret|token|password|passwd|api[_-]?key|credential|private[_-]?key|auth)")
_SALON_KEYS = {"schema_version", "salon_id", "timezone", "tier", "network"}
_NETWORK_KEYS = {"kiosk_port", "owner_port"}
DEFAULT_PORTS = {"kiosk_port": 8080, "owner_port": 8081}


@dataclass(frozen=True)
class SalonConfig:
    schema_version: int
    salon_id: str
    timezone: str
    tier: str
    kiosk_port: int
    owner_port: int

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "salon_id": self.salon_id,
            "timezone": self.timezone,
            "tier": self.tier,
            "network": {"kiosk_port": self.kiosk_port, "owner_port": self.owner_port},
        }


def _scan_for_secret_keys(value, where: str = "") -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if isinstance(key, str) and _SECRET_LOOKING_KEY.search(key):
                raise RuntimeConfigError(f"salon.json must not hold secrets: the key {where}{key!r} looks like one. Secrets belong in the protected secrets store.")
            _scan_for_secret_keys(inner, f"{where}{key}.")
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            _scan_for_secret_keys(inner, f"{where}[{index}].")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_salon_config(data) -> SalonConfig:
    if not isinstance(data, dict):
        raise RuntimeConfigError("salon.json must contain a JSON object.")
    _scan_for_secret_keys(data)
    unknown = sorted(set(data) - _SALON_KEYS)
    if unknown:
        raise RuntimeConfigError(f"salon.json has unknown setting(s): {', '.join(map(str, unknown))}. Allowed: {', '.join(sorted(_SALON_KEYS))}.")

    version = data.get("schema_version")
    if not _is_int(version):
        raise RuntimeConfigError("salon.json: 'schema_version' is required and must be a whole number.")
    if version != SCHEMA_VERSION:
        raise RuntimeConfigError(f"salon.json: unsupported schema_version {version}. This version of NailSystem understands {SCHEMA_VERSION}.")

    salon_id = data.get("salon_id")
    if not isinstance(salon_id, str) or not _SALON_ID.match(salon_id):
        raise RuntimeConfigError("salon.json: 'salon_id' must be 1-64 letters, digits, '-' or '_' (starting with a letter or digit).")

    timezone = data.get("timezone", "America/Phoenix")
    if not isinstance(timezone, str) or not timezone.strip():
        raise RuntimeConfigError("salon.json: 'timezone' must be a time zone name such as America/Phoenix.")
    try:
        ZoneInfo(timezone)
    except Exception as exc:  # unknown key, bad characters, missing tzdata
        raise RuntimeConfigError(f"salon.json: '{timezone}' is not a known time zone ({type(exc).__name__}).") from exc

    tier = data.get("tier", "development")
    if not isinstance(tier, str) or not _TIER.match(tier):
        raise RuntimeConfigError("salon.json: 'tier' must be lowercase letters, digits, '-' or '_' (up to 32 characters).")

    network = data.get("network", {})
    if not isinstance(network, dict):
        raise RuntimeConfigError("salon.json: 'network' must be an object.")
    bad = sorted(set(network) - _NETWORK_KEYS)
    if bad:
        raise RuntimeConfigError(f"salon.json: unknown network setting(s): {', '.join(map(str, bad))}. Allowed: {', '.join(sorted(_NETWORK_KEYS))}.")
    ports = {}
    for key in ("kiosk_port", "owner_port"):
        port = network.get(key, DEFAULT_PORTS[key])
        if not _is_int(port) or not 1024 <= port <= 65535:
            raise RuntimeConfigError(f"salon.json: network.{key} must be a whole number from 1024 to 65535.")
        if port in BACKEND_PORTS.values():
            raise RuntimeConfigError(f"salon.json: network.{key} {port} is reserved for a backend (loopback) port.")
        ports[key] = port
    if ports["kiosk_port"] == ports["owner_port"]:
        raise RuntimeConfigError("salon.json: network.kiosk_port and network.owner_port must differ.")

    return SalonConfig(version, salon_id, timezone.strip(), tier, ports["kiosk_port"], ports["owner_port"])


def load_salon_config(path: Path) -> SalonConfig:
    try:
        size = path.stat().st_size
        if size > MAX_CONFIG_BYTES:
            raise RuntimeConfigError(f"{path} is too large ({size} bytes) to be a salon.json.")
        text = path.read_bytes().decode("utf-8-sig")  # tolerates the BOM Windows editors add
    except FileNotFoundError as exc:
        raise RuntimeConfigError(f"salon.json was not found at {path}. Create it with: python nailsystem_runtime.py init") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeConfigError(f"Cannot read {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeConfigError(f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}.") from exc
    try:
        return parse_salon_config(data)
    except RuntimeConfigError as exc:
        raise RuntimeConfigError(f"{path}: {exc}") from exc


def default_salon_config(salon_id: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "salon_id": salon_id or "salon-" + _secrets.token_hex(4),
        "timezone": "America/Phoenix",
        "tier": "development",
        "network": dict(DEFAULT_PORTS),
    }


def write_default_salon_config(path: Path, salon_id: str | None = None, *, overwrite: bool = False) -> bool:
    """Creates salon.json if it does not exist (never replaces one unless asked). Returns True if written."""
    if path.exists() and not overwrite:
        return False
    data = default_salon_config(salon_id)
    parse_salon_config(data)
    _atomic_write(path, (json.dumps(data, indent=2) + "\n").encode("utf-8"))
    return True


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


# ------------------------------------------------------------------------------------------------
# Secrets: an interface, an environment backend (development) and a Windows DPAPI backend (product)
# ------------------------------------------------------------------------------------------------
_MAX_SECRET_BYTES = 4096
_FILE_MAGIC = b"NSSECRETS1\n"
_ENTROPY = b"NailSystem secrets v1"


def _check_secret(name: str, value) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", name):
        raise SecretsError(f"{name!r} is not a valid secret name.")
    if not isinstance(value, str) or not value or "\x00" in value or len(value.encode("utf-8")) > _MAX_SECRET_BYTES:
        raise SecretsError(f"The value for {name} is empty, too long, or contains an invalid character.")
    return value


class SecretsProvider:
    """get() returns a value or None. names() never returns values. repr() never contains values."""

    def get(self, name: str) -> str | None:
        raise NotImplementedError

    def names(self) -> list[str]:
        raise NotImplementedError

    def set(self, name: str, value: str) -> None:
        raise NotImplementedError

    def delete(self, name: str) -> bool:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} names={self.names()}>"


class EnvironmentSecrets(SecretsProvider):
    """Development backend: the process environment. Read-only by design."""

    def __init__(self, environ=None, names=ALL_SECRET_NAMES):
        self._environ = os.environ if environ is None else environ
        self._names = tuple(names)

    def get(self, name):
        value = self._environ.get(name)
        return value if value else None

    def names(self):
        return [name for name in self._names if self._environ.get(name)]

    def set(self, name, value):
        raise SecretsError("Environment secrets are read-only. Use the protected secrets store (secrets.dat).")

    def delete(self, name):
        raise SecretsError("Environment secrets are read-only. Use the protected secrets store (secrets.dat).")


def _dpapi(data: bytes, *, protect: bool, scope: str = "machine", entropy: bytes = _ENTROPY) -> bytes:
    if sys.platform != "win32":
        raise SecretsError("The protected secrets store uses Windows DPAPI and is only available on Windows.")
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.restype = wintypes.BOOL
    function.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ctypes.POINTER(DataBlob)]

    def blob_for(content: bytes):
        buffer = ctypes.create_string_buffer(content, len(content))
        return DataBlob(len(content), ctypes.cast(buffer, ctypes.c_void_p)), buffer

    blob_in, keep_in = blob_for(data)
    blob_entropy, keep_entropy = blob_for(entropy)
    blob_out = DataBlob()
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN: a service must never wait for a prompt
    if protect and scope == "machine":
        flags |= 0x4  # CRYPTPROTECT_LOCAL_MACHINE
    if not function(ctypes.byref(blob_in), None, ctypes.byref(blob_entropy), None, None, flags, ctypes.byref(blob_out)):
        raise SecretsError(f"Windows could not {'protect' if protect else 'unprotect'} the secrets (error {ctypes.get_last_error()}). "
                           "The file may be damaged or was created on another computer or account.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
        del keep_in, keep_entropy


class DpapiSecrets(SecretsProvider):
    """secrets.dat: one DPAPI-protected blob (JSON inside). Machine scope by default: any process on THIS computer
    that can read the file could decrypt it, so the folder ACL is the confidentiality boundary (see apply_acls);
    use scope="user" to additionally bind it to one Windows account."""

    def __init__(self, path: Path, scope: str = "machine", entropy: bytes = _ENTROPY):
        if scope not in ("machine", "user"):
            raise SecretsError("scope must be 'machine' or 'user'.")
        self.path, self.scope, self._entropy = Path(path), scope, entropy
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise SecretsError(f"Cannot read the secrets file {self.path}: {exc}. The account running NailSystem needs read access.") from exc
        if not raw.startswith(_FILE_MAGIC):
            raise SecretsError(f"{self.path} is not a NailSystem secrets file.")
        try:
            payload = json.loads(_dpapi(raw[len(_FILE_MAGIC):], protect=False, scope=self.scope, entropy=self._entropy).decode("utf-8"))
        except SecretsError:
            raise
        except (ValueError, UnicodeDecodeError) as exc:
            raise SecretsError(f"{self.path} is damaged.") from exc
        values = payload.get("values") if isinstance(payload, dict) and payload.get("v") == 1 else None
        if not isinstance(values, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in values.items()):
            raise SecretsError(f"{self.path} has an unexpected format.")
        return values

    def _write(self, values: dict) -> None:
        plain = json.dumps({"v": 1, "values": values}, separators=(",", ":")).encode("utf-8")
        _atomic_write(self.path, _FILE_MAGIC + _dpapi(plain, protect=True, scope=self.scope, entropy=self._entropy))

    def get(self, name):
        with self._lock:
            return self._read().get(name) or None

    def names(self):
        with self._lock:
            return sorted(self._read())

    def set(self, name, value):
        _check_secret(name, value)
        with self._lock:
            values = self._read()
            values[name] = value
            self._write(values)

    def delete(self, name):
        with self._lock:
            values = self._read()
            if name not in values:
                return False
            del values[name]
            self._write(values)
            return True


# ------------------------------------------------------------------------------------------------
# Windows ACLs (directory permissions). Uses icacls with well-known SIDs, so it works on any language of Windows.
# ------------------------------------------------------------------------------------------------
SID_SYSTEM = "S-1-5-18"
SID_ADMINISTRATORS = "S-1-5-32-544"
_FORBIDDEN_PRINCIPALS = ("everyone", "builtin\\users", "nt authority\\authenticated users", "users")


def current_user_sid() -> str:
    if sys.platform != "win32":
        raise RuntimeConfigError("ACLs are managed on Windows only.")
    result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=20)
    match = re.search(r'"(S-1-[0-9-]+)"', result.stdout)
    if result.returncode != 0 or not match:
        raise RuntimeConfigError("Could not determine the current Windows account.")
    return match.group(1)


def restrict_directory(path: Path, *, runtime_sid: str | None = None, runtime_access: str = "M") -> None:
    """Removes inherited permissions and grants only SYSTEM and Administrators (full control) and the account that
    runs NailSystem (`runtime_access`: M = modify, RX = read and execute). Nobody else, in particular not
    Everyone, Users or Authenticated Users. Safe to call repeatedly."""
    if sys.platform != "win32":
        raise RuntimeConfigError("ACLs are managed on Windows only.")
    if runtime_access not in ("M", "RX"):
        raise RuntimeConfigError("runtime_access must be 'M' or 'RX'.")
    sid = runtime_sid or current_user_sid()
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise RuntimeConfigError(f"{sid!r} is not a Windows SID.")
    grants = [f"*{SID_SYSTEM}:(OI)(CI)F", f"*{SID_ADMINISTRATORS}:(OI)(CI)F", f"*{sid}:(OI)(CI){runtime_access}"]
    command = ["icacls", str(path), "/inheritance:r", "/grant:r", *grants]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeConfigError(f"Could not restrict {path}: {(result.stdout + result.stderr).strip()[:300]}. Run this as an administrator.")


def apply_acls(paths: RuntimePaths, *, runtime_sid: str | None = None) -> None:
    """The product permission model: the whole data root is private to SYSTEM, Administrators and the runtime
    account (modify); the secrets folder is tighter still: the runtime account may only READ it, so a compromised
    app cannot rewrite its own secrets and only an administrator (the installer) can change them."""
    restrict_directory(paths.root, runtime_sid=runtime_sid, runtime_access="M")
    if paths.secrets_dir.exists():
        restrict_directory(paths.secrets_dir, runtime_sid=runtime_sid, runtime_access="RX")


def readable_by_everyone(path: Path) -> list[str]:
    """Principals on `path` that should never be there (Everyone, Users, Authenticated Users)."""
    result = subprocess.run(["icacls", str(path)], capture_output=True, text=True, timeout=60)
    found = []
    for line in result.stdout.splitlines():
        lowered = line.lower()
        for principal in _FORBIDDEN_PRINCIPALS:
            if re.search(rf"(^|[\s\\]){re.escape(principal)}:", lowered) or lowered.strip().startswith(principal + ":"):
                found.append(line.strip())
    return found


# ------------------------------------------------------------------------------------------------
# Logging: rotating files in product mode, with secrets, tokens, phone numbers and e-mail addresses removed
# ------------------------------------------------------------------------------------------------
_REDACTIONS = [
    (re.compile(r"(?i)\b(x-(?:internal-service|kiosk-device|profile-edit|staff-csrf)-token|x-csrf-token|set-cookie|cookie)\b(\s*[:=]\s*)[^\s,;]+"), r"\1\2[redacted]"),
    # an Authorization value is "<scheme> <credentials>": both words go
    (re.compile(r"(?i)\b(authorization)\b(\s*[:=]\s*)(?:[A-Za-z]+\s+)?[^\s,;]+"), r"\1\2[redacted]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [redacted]"),
    (re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key|auth[_-]?token|account[_-]?sid)\b(['\"]?\s*[:=]\s*['\"]?)[^\s,;'\"&]+"), r"\1\2[redacted]"),
    (re.compile(r"\b\d{1,9}\.[A-Za-z0-9_-]{40,}\b"), "[redacted-device-token]"),
    (re.compile(r"\b[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}\b"), "[redacted-code]"),
    (re.compile(r"(?<![\w.])([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)"), r"\1***@\2"),
    (re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{2}(\d{2})(?!\d)"), r"***-***-**\1"),
]


class Redactor:
    def __init__(self, secret_values=()):
        self._values: list[str] = []
        for value in secret_values:
            self.add_secret(value)

    def add_secret(self, value) -> None:
        if isinstance(value, str) and len(value) >= 8 and value not in self._values:
            self._values.append(value)
            self._values.sort(key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for value in self._values:
            text = text.replace(value, "[redacted]")
        for pattern, replacement in _REDACTIONS:
            text = pattern.sub(replacement, text)
        return text


class RedactingFormatter(logging.Formatter):
    """Redacts the finished line, tracebacks included."""

    def __init__(self, redactor: Redactor, fmt: str | None = None, datefmt: str | None = None):
        super().__init__(fmt or "%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt)
        self._redactor = redactor

    def format(self, record):
        return self._redactor(super().format(record))


def configure_logging(app: str, log_dir: Path, redactor: Redactor, *, level: int = logging.INFO, max_bytes: int = 5_000_000, backups: int = 5):
    """Rotating file log (plus the console) with redaction. Called in product mode; development keeps plain console logs."""
    _check_app(app)
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = RedactingFormatter(redactor)
    file_handler = logging.handlers.RotatingFileHandler(log_dir / f"{app}.log", maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    console = logging.StreamHandler()
    for handler in (file_handler, console):
        handler.setFormatter(formatter)
        handler.set_name(f"nailsystem-{app}")
    root = logging.getLogger()
    for existing in list(root.handlers):
        if existing.get_name() == f"nailsystem-{app}":
            root.removeHandler(existing)
            existing.close()
    root.addHandler(file_handler)
    root.addHandler(console)
    root.setLevel(level)
    return file_handler, console


# ------------------------------------------------------------------------------------------------
# SQLite hardening (used by both apps' database.py)
# ------------------------------------------------------------------------------------------------
SQLITE_BUSY_TIMEOUT_MS = 5000


def configure_sqlite_connection(dbapi_connection) -> None:
    """On every new connection: wait for a locked database instead of failing, enforce foreign keys, use WAL (readers and
    the single writer no longer block each other, and a crash cannot corrupt the file) with full durability."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")  # first, so the next statements can wait too
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL").fetchall()
        cursor.execute("PRAGMA synchronous=FULL")
    finally:
        cursor.close()


def install_sqlite_pragmas(engine) -> None:
    """Attach configure_sqlite_connection to a SQLAlchemy engine (SQLite only)."""
    from sqlalchemy import event

    if engine.url.get_backend_name() != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):  # pragma: no cover - exercised through the engine in tests
        configure_sqlite_connection(dbapi_connection)


# ------------------------------------------------------------------------------------------------
# bootstrap: decide the mode, load salon.json and the secrets, and fill os.environ before anything else reads it
# ------------------------------------------------------------------------------------------------
@dataclass
class RuntimeContext:
    app: str
    mode: str
    home: Path | None
    paths: RuntimePaths | None
    salon: SalonConfig | None
    sources: dict = field(default_factory=dict)       # NAME -> where its value came from (never the value)
    ignored_env: list = field(default_factory=list)   # names whose process-environment value was ignored (product mode)
    overridden: list = field(default_factory=list)    # names the environment overrode (NAILSYSTEM_ALLOW_ENV_OVERRIDE)
    warnings: list = field(default_factory=list)
    redactor: Redactor = field(default_factory=Redactor, repr=False)

    def describe(self) -> dict:
        """Safe to print or log: names and sources only."""
        return {
            "app": self.app, "mode": self.mode, "home": str(self.home) if self.home else None,
            "database": str(self.paths.db_path(self.app)) if self.paths else None,
            "salon_id": self.salon.salon_id if self.salon else None,
            "sources": dict(sorted(self.sources.items())),
            "ignored_environment": sorted(self.ignored_env), "environment_overrides": sorted(self.overridden),
        }


_CONTEXTS: dict[str, RuntimeContext] = {}
_BOOTSTRAP_LOCK = threading.Lock()


def _owner_origins(port: int) -> str:
    return f"http://127.0.0.1:{port},http://localhost:{port}"


def bootstrap(app: str, environ=None, *, force: bool = False, configure_log: bool = True) -> RuntimeContext:
    """Idempotent. Call once, first thing, in each backend's entry point (before other modules read os.environ)."""
    _check_app(app)
    use_process_env = environ is None
    environ = os.environ if use_process_env else environ
    with _BOOTSTRAP_LOCK:
        if use_process_env and not force and app in _CONTEXTS:
            return _CONTEXTS[app]
        context = _bootstrap(app, environ, configure_log=configure_log and use_process_env)
        if use_process_env:
            _CONTEXTS[app] = context
        return context


def _bootstrap(app: str, environ, *, configure_log: bool) -> RuntimeContext:
    mode = current_mode(environ)
    product = mode == "product"
    home = resolve_home(environ, mode)
    paths = RuntimePaths(home) if home else None
    context = RuntimeContext(app=app, mode=mode, home=home, paths=paths, salon=None)
    allow_override = product and _truthy(environ.get(OVERRIDE_ENV))

    if paths and product:
        paths.ensure((app,), include_secrets=False)  # the secrets folder is created, and locked down, by `init`
    if paths and paths.salon_json.exists():
        context.salon = load_salon_config(paths.salon_json)
    elif product:
        raise RuntimeConfigError(f"salon.json was not found at {paths.salon_json}. Run the installer, or create it with: python nailsystem_runtime.py init")

    # ---- non-secret settings
    managed: dict[str, tuple[str, str]] = {}  # NAME -> (value, source)
    if paths:
        managed["DATABASE_URL"] = (sqlite_url(paths.db_path(app)), "installed layout")
        managed["OWNER_API_BASE" if app == "checkin" else "CHECKIN_API_BASE"] = (
            f"http://127.0.0.1:{BACKEND_PORTS['owner' if app == 'checkin' else 'checkin']}", "installed layout")
    if context.salon:
        managed["SALON_TIMEZONE"] = (context.salon.timezone, "salon.json")
        if app == "owner":
            managed["ALLOWED_ORIGINS"] = (_owner_origins(context.salon.owner_port), "salon.json")
    for name, (value, source) in managed.items():
        present = name in environ and str(environ[name]).strip() != ""
        if product and present and not allow_override:
            if environ[name] != value:
                context.ignored_env.append(name)
            environ[name] = value
            context.sources[name] = source
        elif present:
            context.sources[name] = "process environment"
            if allow_override and environ[name] != value:
                context.overridden.append(name)
        else:
            environ[name] = value
            context.sources[name] = source
    if product and not allow_override:
        for name in ("DATABASE_URL",):
            url = environ.get(name, "")
            if sqlite_path_from_url(url) is not None and home is not None:
                try:
                    Path(sqlite_path_from_url(url)).resolve().relative_to(home.resolve())
                except ValueError:
                    raise RuntimeConfigError("In product mode the database must live under the NailSystem data folder.")

    # ---- secrets
    provider: SecretsProvider | None = None
    if product:
        provider = DpapiSecrets(paths.secrets_file)
    elif paths and paths.secrets_file.exists() and sys.platform == "win32":
        provider = DpapiSecrets(paths.secrets_file)
    secret_values = []
    for name in SECRET_NAMES[app]:
        stored = provider.get(name) if provider else None
        present = bool(environ.get(name))
        if product and not allow_override:
            if present and environ.get(name) != stored:
                context.ignored_env.append(name)
            if stored:
                environ[name] = stored
                context.sources[name] = "secrets store"
            else:
                environ.pop(name, None)  # a forgotten environment value must not stand in for a missing secret
        elif present:
            context.sources[name] = "process environment"
            if allow_override and stored and environ[name] != stored:
                context.overridden.append(name)
        elif stored:
            environ[name] = stored
            context.sources[name] = "secrets store"
        if environ.get(name):
            secret_values.append(environ[name])
    if product and not allow_override:
        # least privilege: a secret this app has no use for (the other app's) is not left lying in its environment either
        for name in ALL_SECRET_NAMES:
            if name not in SECRET_NAMES[app] and environ.pop(name, None) is not None:
                context.ignored_env.append(name)
    context.redactor = Redactor(secret_values)
    if product:
        missing = [name for name in REQUIRED_SECRETS if not environ.get(name)]
        if missing:
            raise RuntimeConfigError(f"Required secret(s) missing from the secrets store: {', '.join(missing)}. "
                                     "An administrator can add them with: python nailsystem_runtime.py secrets set NAME")

    if allow_override:
        context.warnings.append("NAILSYSTEM_ALLOW_ENV_OVERRIDE is on: process environment values override the installed configuration "
                                "(support/debug only). Overridden: " + (", ".join(sorted(context.overridden)) or "none"))
    if context.ignored_env:
        context.warnings.append("Ignored process-environment values for installed settings: " + ", ".join(sorted(set(context.ignored_env))))

    if product and configure_log:
        configure_logging(app, paths.log_dir(app), context.redactor)
    for warning in context.warnings:
        logging.getLogger("nailsystem.runtime").warning(warning)
    return context


def should_load_dotenv(environ=None) -> bool:
    """A .env file is a development convenience. In product mode it is ignored, so a forgotten file can never
    override the installed configuration."""
    try:
        return current_mode(environ) != "product"
    except RuntimeConfigError:
        return True


# ------------------------------------------------------------------------------------------------
# Command line (for the installer and the future launcher; never prints a secret value)
#   python nailsystem_runtime.py paths
#   python nailsystem_runtime.py init [--home DIR] [--salon-id ID] [--no-acl] [--runtime-sid SID]
#   python nailsystem_runtime.py secrets list|set NAME|delete NAME|generate NAME
#   python nailsystem_runtime.py acl-check
# ------------------------------------------------------------------------------------------------
def _cli_paths(environ) -> RuntimePaths:
    """The command line always works on the product layout: ProgramData/NailSystem, or NAILSYSTEM_HOME / --home."""
    return RuntimePaths(resolve_home(environ, "product"))


def _cli_check(app: str, environ) -> int:
    """Runs the same start-up resolution the app would (on a COPY of the environment, no logging, no folders created in
    development), and reports whether it would start. Prints names and sources only; exit 0 = would start, 2 = would not."""
    scratch = dict(environ)
    report = {"app": app, "ok": False, "mode": None, "problems": [], "warnings": [], "settings": {}, "secrets_present": [], "ignored_environment": []}
    try:
        context = _bootstrap(app, scratch, configure_log=False)
    except RuntimeConfigError as exc:
        report["problems"].append(str(exc))
        try:
            report["mode"] = current_mode(environ)
        except RuntimeConfigError:
            pass
        print(json.dumps(report, indent=2))
        return 2
    report.update(mode=context.mode, ok=True, settings=dict(sorted(context.sources.items())),
                  ignored_environment=sorted(set(context.ignored_env)), warnings=list(context.warnings))
    report["secrets_present"] = sorted(name for name in SECRET_NAMES[app] if scratch.get(name))
    missing = [name for name in REQUIRED_SECRETS if not scratch.get(name)]
    if missing:  # product mode already refused above; in development this is only a heads-up
        report["warnings"].append("Not set (the two apps cannot talk to each other without it): " + ", ".join(missing))
    print(json.dumps(report, indent=2))
    return 0


def main(argv=None, environ=None) -> int:
    import argparse
    import getpass

    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(prog="nailsystem_runtime", description="NailSystem runtime layout and secrets.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("paths", help="show the resolved layout (no secrets)")
    init = sub.add_parser("init", help="create the folders and a default salon.json (never overwrites)")
    init.add_argument("--home")
    init.add_argument("--salon-id")
    init.add_argument("--no-acl", action="store_true", help="skip Windows permission changes (development)")
    init.add_argument("--runtime-sid", help="SID of the account that runs NailSystem (default: the current account)")
    secrets_cmd = sub.add_parser("secrets", help="manage the protected secrets store")
    secrets_cmd.add_argument("action", choices=["list", "set", "delete", "generate"])
    secrets_cmd.add_argument("name", nargs="?")
    sub.add_parser("acl-check", help="report principals that should not have access")
    check = sub.add_parser("check", help="validate the configuration and secrets an app would start with (names only, never values)")
    check.add_argument("--app", required=True, choices=APPS)
    args = parser.parse_args(argv)

    if args.command == "check":
        return _cli_check(args.app, environ)
    try:
        if args.command == "init" and args.home:
            environ[HOME_ENV] = args.home
        paths = _cli_paths(environ)
        if args.command == "paths":
            print(json.dumps({"root": str(paths.root), "salon_json": str(paths.salon_json), "secrets_file": str(paths.secrets_file),
                              **{f"{app}_db": str(paths.db_path(app)) for app in APPS},
                              **{f"{app}_backups": str(paths.backup_dir(app)) for app in APPS},
                              **{f"{app}_logs": str(paths.log_dir(app)) for app in APPS}}, indent=2))
        elif args.command == "init":
            paths.ensure()
            created = write_default_salon_config(paths.salon_json, args.salon_id)
            print(f"salon.json: {'created' if created else 'already exists (left unchanged)'} at {paths.salon_json}")
            if not args.no_acl:
                apply_acls(paths, runtime_sid=args.runtime_sid)
                print("permissions: data folder private to SYSTEM, Administrators and the runtime account; secrets folder read-only for it")
        elif args.command == "secrets":
            provider = DpapiSecrets(paths.secrets_file)
            if args.action == "list":
                print("\n".join(provider.names()) or "(no secrets stored)")
            else:
                if not args.name:
                    raise RuntimeConfigError("Give the secret's NAME.")
                if args.action == "delete":
                    print("deleted" if provider.delete(args.name) else "not found")
                elif args.action == "generate":
                    provider.set(args.name, _secrets.token_urlsafe(48))
                    print(f"{args.name}: generated and stored (value not shown)")
                else:
                    value = getpass.getpass(f"{args.name} (hidden): ")
                    provider.set(args.name, value)
                    print(f"{args.name}: stored")
        elif args.command == "acl-check":
            problems = {str(p): readable_by_everyone(p) for p in (paths.root, paths.secrets_dir) if p.exists()}
            print(json.dumps(problems, indent=2))
            return 1 if any(problems.values()) else 0
    except RuntimeConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
