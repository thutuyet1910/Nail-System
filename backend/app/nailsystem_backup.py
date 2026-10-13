"""Safe local backups and restore validation for the two SQLite databases.

THIS FILE IS IDENTICAL IN BOTH REPOSITORIES (Owner: backend/nailsystem_backup.py, Check-In:
backend/app/nailsystem_backup.py). Standard library only; no relative imports.

* A backup is made with SQLite's online backup API while the app keeps running. An open database file is NEVER
  raw-copied (that can capture a half-written state).
* Every backup is verified before it is kept: it is opened, `PRAGMA integrity_check` must say "ok", the core
  tables must exist, and a checksum sidecar (<name>.json) is written. A backup that fails is deleted, not kept.
* Backups are separate per app and named  owner-20261013T031500Z.db  (UTC), optionally  ...-pre-upgrade.db.
* Retention: the newest `keep` regular backups (default 14) and the newest `keep_pre_upgrade` (default 3)
  pre-upgrade backups are kept; nothing else in the folder is ever touched.
* Restoring is deliberately NOT automatic. `restore_preflight()` only reports whether a backup is safe to restore and
  whether the live database looks in use; the future launcher stops the services, makes a safety backup and swaps files.

Command line (run from the app's backend folder; works with NAILSYSTEM_MODE=product or --db/--dir):
    python nailsystem_backup.py backup  --app owner [--keep 14] [--label pre-upgrade]
    python nailsystem_backup.py verify  --app owner --file PATH
    python nailsystem_backup.py list    --app owner
    python nailsystem_backup.py prune   --app owner [--keep 14]
    python nailsystem_backup.py preflight --app owner --file PATH
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

APPS = ("owner", "checkin")
DEFAULT_KEEP = 14
DEFAULT_KEEP_PRE_UPGRADE = 3

# A backup older than the current code may lack newer (additive) tables, so only the long-standing core is required.
CORE_TABLES = {
    "owner": ("technicians", "appointments", "booking_services", "business_hours", "owner_credentials", "turns", "checkouts", "inventory_items"),
    "checkin": ("customers", "visits", "referral_usages", "visit_owner_services"),
}

_NAME = re.compile(r"^(?P<app>owner|checkin)-(?P<stamp>\d{8}T\d{6}Z)(?:-(?P<label>[a-z0-9][a-z0-9-]{0,23}))?\.db$")
_SQLITE_MAGIC = b"SQLite format 3\x00"


class BackupError(Exception):
    """A backup could not be made, or is not safe to use. The message is meant to be shown to a person."""


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    app: str
    created_at: datetime
    label: str | None
    size_bytes: int


@dataclass
class VerifyReport:
    path: Path
    ok: bool
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    foreign_key_violations: int = 0
    sha256: str = ""

    def raise_if_bad(self) -> "VerifyReport":
        if not self.ok:
            raise BackupError(f"{self.path.name} is not a usable backup: " + "; ".join(self.problems))
        return self


@dataclass
class BackupResult:
    info: BackupInfo
    report: VerifyReport
    pruned: list = field(default_factory=list)


def _check_app(app: str) -> str:
    if app not in APPS:
        raise BackupError(f"Unknown app {app!r}; expected one of {APPS}.")
    return app


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readonly_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?immutable=1"  # read-only, no -wal/-shm files are created next to a backup


def parse_backup_name(path: Path) -> BackupInfo | None:
    match = _NAME.match(path.name)
    if not match:
        return None
    created = datetime.strptime(match["stamp"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return BackupInfo(path, match["app"], created, match["label"], size)


def list_backups(backup_dir: Path, app: str) -> list[BackupInfo]:
    """This app's backups, newest first. Files that do not follow the naming pattern are ignored."""
    _check_app(app)
    if not backup_dir.is_dir():
        return []
    found = [info for info in (parse_backup_name(p) for p in backup_dir.iterdir() if p.is_file()) if info and info.app == app]
    return sorted(found, key=lambda info: (info.created_at, info.path.name), reverse=True)


# ------------------------------------------------------------------------------------------------
# Verification
# ------------------------------------------------------------------------------------------------
def verify_backup(path: Path, app: str | None = None, *, core_tables=None, check_sidecar: bool = True) -> VerifyReport:
    """Never raises for a bad file: the problems are in the report. raise_if_bad() turns them into a BackupError."""
    path = Path(path)
    report = VerifyReport(path=path, ok=False)
    if not path.is_file():
        report.problems.append("the file does not exist")
        return report
    if path.stat().st_size == 0:
        report.problems.append("the file is empty")
        return report
    try:
        with open(path, "rb") as handle:
            header = handle.read(len(_SQLITE_MAGIC))
    except OSError as exc:
        report.problems.append(f"cannot read the file ({exc.strerror or exc})")
        return report
    if header != _SQLITE_MAGIC:
        report.problems.append("it is not an SQLite database")
        return report
    report.sha256 = _sha256(path)

    info = parse_backup_name(path)
    if app is not None:
        _check_app(app)
        if info is not None and info.app != app:
            report.problems.append(f"it is a {info.app} backup, not a {app} backup")

    connection = None
    try:
        connection = sqlite3.connect(_readonly_uri(path), uri=True, timeout=5)
        rows = connection.execute("PRAGMA integrity_check").fetchall()
        if [row[0] for row in rows] != ["ok"]:
            report.problems.append("the database failed its integrity check (" + "; ".join(str(r[0]) for r in rows[:3]) + ")")
        report.tables = sorted(r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        required = core_tables if core_tables is not None else (CORE_TABLES[app] if app else ())
        missing = [t for t in required if t not in report.tables]
        if missing:
            report.problems.append("these tables are missing: " + ", ".join(missing))
        for table in report.tables:
            if not re.fullmatch(r"[A-Za-z0-9_]+", table):
                continue
            try:
                connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()
            except sqlite3.DatabaseError as exc:
                report.problems.append(f"the table {table} cannot be read ({exc})")
        report.foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        if report.foreign_key_violations:
            report.warnings.append(f"{report.foreign_key_violations} row(s) refer to records that do not exist (foreign-key check)")
    except sqlite3.DatabaseError as exc:
        report.problems.append(f"the database cannot be opened ({exc})")
    finally:
        if connection is not None:
            connection.close()

    sidecar = path.with_suffix(".json")
    if check_sidecar and sidecar.exists():
        try:
            recorded = json.loads(sidecar.read_text(encoding="utf-8"))
            if recorded.get("sha256") != report.sha256 or recorded.get("size") != path.stat().st_size:
                report.problems.append("it does not match the checksum recorded when it was made (the file changed or is damaged)")
        except (OSError, ValueError):
            report.warnings.append("its checksum file is unreadable")
    report.ok = not report.problems
    return report


# ------------------------------------------------------------------------------------------------
# Creating and pruning
# ------------------------------------------------------------------------------------------------
def create_backup(db_path: Path, backup_dir: Path, app: str, *, keep: int = DEFAULT_KEEP, keep_pre_upgrade: int = DEFAULT_KEEP_PRE_UPGRADE,
                  label: str | None = None, now: datetime | None = None, core_tables=None) -> BackupResult:
    """Online backup of a SQLite database (the app may keep running), verified before it is kept."""
    _check_app(app)
    db_path, backup_dir = Path(db_path), Path(backup_dir)
    if keep < 1 or keep_pre_upgrade < 0:
        raise BackupError("keep must be at least 1.")
    if label is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,23}", label):
        raise BackupError("A label may only contain lowercase letters, digits and '-'.")
    if not db_path.is_file():
        raise BackupError(f"The database {db_path} does not exist, so there is nothing to back up.")
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"Cannot create the backup folder {backup_dir}: {exc.strerror or exc}") from exc

    moment = now or datetime.now(timezone.utc)
    final = backup_dir / f"{app}-{_stamp(moment)}{'-' + label if label else ''}.db"
    if final.exists():
        raise BackupError(f"A backup named {final.name} already exists; wait a second and try again.")
    partial = backup_dir / f".{final.name}.partial"

    source = destination = None
    try:
        source = sqlite3.connect(str(db_path), timeout=30)
        source.execute("PRAGMA query_only=ON")  # this connection can only read
        destination = sqlite3.connect(str(partial))
        source.backup(destination, pages=256, sleep=0.005)  # online: writers are not blocked for the whole copy
        destination.execute("PRAGMA journal_mode=DELETE")    # a single self-contained file
        destination.commit()
    except sqlite3.Error as exc:
        _close_all(destination, source)  # Windows cannot delete a file that is still open
        _quietly_unlink(partial)
        raise BackupError(f"The backup could not be made ({exc}).") from exc
    finally:
        _close_all(destination, source)

    report = verify_backup(partial, app, core_tables=core_tables, check_sidecar=False)
    if not report.ok:
        _quietly_unlink(partial)
        raise BackupError("The new backup failed verification and was discarded: " + "; ".join(report.problems))

    sidecar = final.with_suffix(".json")
    size = partial.stat().st_size
    with open(partial, "r+b") as handle:  # push the finished file to disk before it is given its final name
        os.fsync(handle.fileno())
    metadata = {"app": app, "created_at": moment.astimezone(timezone.utc).isoformat(), "label": label, "source": db_path.name,
                "size": size, "sha256": report.sha256, "integrity": "ok", "tables": len(report.tables)}
    try:
        sidecar.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        os.replace(partial, final)
    except OSError as exc:
        _quietly_unlink(partial)
        _quietly_unlink(sidecar)
        raise BackupError(f"The backup could not be saved: {exc.strerror or exc}") from exc

    info = parse_backup_name(final)
    pruned = prune_backups(backup_dir, app, keep=keep, keep_pre_upgrade=keep_pre_upgrade)
    return BackupResult(info=info, report=report, pruned=pruned)


def prune_backups(backup_dir: Path, app: str, *, keep: int = DEFAULT_KEEP, keep_pre_upgrade: int = DEFAULT_KEEP_PRE_UPGRADE) -> list[str]:
    """Deletes this app's oldest backups beyond the retention counts. Returns the names removed."""
    _check_app(app)
    if keep < 1:
        raise BackupError("keep must be at least 1.")
    backups = list_backups(Path(backup_dir), app)
    regular = [b for b in backups if b.label != "pre-upgrade"]
    protected = [b for b in backups if b.label == "pre-upgrade"]
    doomed = regular[keep:] + protected[keep_pre_upgrade:]
    removed = []
    for backup in doomed:
        _quietly_unlink(backup.path)
        _quietly_unlink(backup.path.with_suffix(".json"))
        removed.append(backup.path.name)
    return removed


def _close_all(*connections) -> None:
    for connection in connections:
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass


def _quietly_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------------------------------------
# Restore validation (advice only: nothing is restored here)
# ------------------------------------------------------------------------------------------------
def restore_preflight(backup_path: Path, live_db_path: Path, app: str, *, core_tables=None) -> dict:
    """Is it safe to restore `backup_path` over `live_db_path`? Does not change either file."""
    _check_app(app)
    report = verify_backup(Path(backup_path), app, core_tables=core_tables)
    live = Path(live_db_path)
    warnings = list(report.warnings)
    problems = list(report.problems)
    live_exists = live.is_file()
    possibly_in_use = False
    if live_exists:
        for suffix in ("-wal", "-shm"):
            sidecar = live.with_name(live.name + suffix)
            if sidecar.exists() and (suffix == "-shm" or sidecar.stat().st_size > 0):
                possibly_in_use = True
        connection = None
        try:
            connection = sqlite3.connect(str(live), timeout=0.5)
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute("ROLLBACK")
        except sqlite3.OperationalError:
            possibly_in_use = True
        except sqlite3.DatabaseError as exc:
            warnings.append(f"the current database cannot be opened ({exc}); restoring may be exactly what is needed")
        finally:
            if connection is not None:
                connection.close()
        if possibly_in_use:
            warnings.append("the current database looks in use or was not closed cleanly: stop NailSystem before restoring")
        elif report.ok:
            try:
                same = os.path.samefile(backup_path, live)
            except OSError:
                same = False
            if same:
                problems.append("the backup and the live database are the same file")
    return {
        "ok": not problems,
        "problems": problems,
        "warnings": warnings,
        "backup_ok": report.ok,
        "live_exists": live_exists,
        "possibly_in_use": possibly_in_use,
        "safety_backup_recommended": live_exists,
        "tables": report.tables,
        "foreign_key_violations": report.foreign_key_violations,
    }


# ------------------------------------------------------------------------------------------------
# Command line
# ------------------------------------------------------------------------------------------------
def _resolve_locations(app: str, db: str | None, directory: str | None, environ=None) -> tuple[Path, Path]:
    environ = os.environ if environ is None else environ
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # nailsystem_runtime.py sits next to this file
    import nailsystem_runtime as runtime
    mode = runtime.current_mode(environ)
    home = runtime.resolve_home(environ, mode)
    paths = runtime.RuntimePaths(home) if home else None
    if db:
        db_path = Path(db)
    elif paths:
        db_path = paths.db_path(app)
    else:
        found = runtime.sqlite_path_from_url(environ.get("DATABASE_URL", "sqlite:///./nail_system.db"))
        if found is None:
            raise BackupError("DATABASE_URL does not point at a SQLite file; pass --db.")
        db_path = found
    if directory:
        backup_dir = Path(directory)
    elif paths:
        backup_dir = paths.backup_dir(app)
    else:
        backup_dir = db_path.resolve().parent / "backups" / app
    return db_path, backup_dir


def main(argv=None, environ=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="nailsystem_backup", description="Safe SQLite backups for NailSystem.")
    parser.add_argument("command", choices=["backup", "verify", "list", "prune", "preflight"])
    parser.add_argument("--app", required=True, choices=APPS)
    parser.add_argument("--db")
    parser.add_argument("--dir")
    parser.add_argument("--file")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    parser.add_argument("--keep-pre-upgrade", type=int, default=DEFAULT_KEEP_PRE_UPGRADE)
    parser.add_argument("--label")
    args = parser.parse_args(argv)
    try:
        db_path, backup_dir = _resolve_locations(args.app, args.db, args.dir, environ)
        if args.command == "backup":
            result = create_backup(db_path, backup_dir, args.app, keep=args.keep, keep_pre_upgrade=args.keep_pre_upgrade, label=args.label)
            print(f"backup: {result.info.path} ({result.info.size_bytes} bytes, integrity ok, {len(result.report.tables)} tables)")
            if result.pruned:
                print("removed old backups: " + ", ".join(result.pruned))
        elif args.command == "list":
            for info in list_backups(backup_dir, args.app):
                print(f"{info.created_at.isoformat()}  {info.path.name}  {info.size_bytes} bytes" + (f"  [{info.label}]" if info.label else ""))
        elif args.command == "prune":
            print("removed: " + (", ".join(prune_backups(backup_dir, args.app, keep=args.keep, keep_pre_upgrade=args.keep_pre_upgrade)) or "nothing"))
        else:
            if not args.file:
                raise BackupError("Give --file PATH.")
            if args.command == "verify":
                report = verify_backup(Path(args.file), args.app)
                print(json.dumps({"ok": report.ok, "problems": report.problems, "warnings": report.warnings, "tables": len(report.tables)}, indent=2))
                return 0 if report.ok else 1
            outcome = restore_preflight(Path(args.file), db_path, args.app)
            print(json.dumps(outcome, indent=2))
            return 0 if outcome["ok"] else 1
    except BackupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
