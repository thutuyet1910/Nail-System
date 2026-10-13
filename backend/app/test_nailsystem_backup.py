"""Backups of the live SQLite databases: online copy, verification, retention, restore validation.

THIS FILE IS IDENTICAL IN BOTH REPOSITORIES (Owner: backend/, Check-In: backend/app/). All databases are temporary
and nothing here touches a real one.
"""

import hashlib
import json
import os
import pathlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

try:  # Check-In: inside the `app` package
    from . import nailsystem_backup as bk
except ImportError:  # Owner: a flat folder
    import nailsystem_backup as bk

BASE = datetime(2026, 10, 13, 3, 15, 0, tzinfo=timezone.utc)


def at(minutes):
    return BASE + timedelta(minutes=minutes)


def make_db(path, app="owner", rows=25, wal=True):
    """A small database with the app's core tables and some data (WAL, like the real thing)."""
    connection = sqlite3.connect(str(path))
    if wal:
        connection.execute("PRAGMA journal_mode=WAL")
    for table in bk.CORE_TABLES[app]:
        connection.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, note TEXT)')
        connection.executemany(f'INSERT INTO "{table}"(note) VALUES (?)', [(f"{table}-{n}",) for n in range(rows)])
    connection.commit()
    return connection


def count(path, table, app="owner"):
    connection = sqlite3.connect(bk._readonly_uri(pathlib.Path(path)), uri=True)
    try:
        return connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        connection.close()


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# Making a backup
# ══════════════════════════════════════════════════════════════════════════════
class TestCreateBackup:

    def test_a_backup_is_a_verified_self_contained_file_with_a_checksum_file(self, tmp_path):
        make_db(tmp_path / "live.db").close()
        result = bk.create_backup(tmp_path / "live.db", tmp_path / "backups" / "owner", "owner", now=at(0))
        path = result.info.path
        assert path.name == "owner-20261013T031500Z.db" and path.is_file() and result.info.app == "owner"
        assert result.report.ok and result.report.tables and result.report.sha256 == sha(path)
        side = json.loads(path.with_suffix(".json").read_text())
        assert side["sha256"] == sha(path) and side["size"] == path.stat().st_size and side["integrity"] == "ok" and side["app"] == "owner"
        assert count(path, "technicians") == 25
        assert not list(path.parent.glob("*.partial")) and not list(path.parent.glob("*-wal")) and not list(path.parent.glob("*-shm"))

    def test_the_backup_is_not_in_wal_mode_so_it_can_be_moved_around_as_one_file(self, tmp_path):
        make_db(tmp_path / "live.db").close()
        path = bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0)).info.path
        connection = sqlite3.connect(str(path))
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
        connection.close()

    def test_it_works_while_the_database_is_open_and_includes_uncheckpointed_data(self, tmp_path):
        live = make_db(tmp_path / "live.db")
        live.execute("PRAGMA wal_autocheckpoint=0")           # keep new rows only in the -wal file
        live.execute("INSERT INTO technicians(note) VALUES ('only in the WAL')")
        live.commit()
        raw_copy = tmp_path / "raw.db"
        raw_copy.write_bytes((tmp_path / "live.db").read_bytes())  # what a file copy would capture
        backup = bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0)).info.path
        try:
            raw_rows = count(raw_copy, "technicians")
        except sqlite3.OperationalError:  # the whole schema was still only in the -wal file
            raw_rows = 0
        assert raw_rows < 26, "a raw copy of an open WAL database misses recent commits"
        assert count(backup, "technicians") == 26, "the online backup includes them"
        live.close()

    def test_the_module_never_raw_copies_a_database_file(self):
        source = pathlib.Path(bk.__file__).read_text(encoding="utf-8")
        for forbidden in ("shutil", "copyfile", "copy2", "copyfileobj"):
            assert forbidden not in source, forbidden

    def test_writes_that_happen_during_the_backup_do_not_corrupt_it(self, tmp_path):
        live = make_db(tmp_path / "live.db", rows=4000)
        live.close()
        stop = threading.Event()
        errors = []

        def writer():
            connection = sqlite3.connect(str(tmp_path / "live.db"), timeout=10)
            try:
                while not stop.is_set():
                    connection.execute("INSERT INTO appointments(note) VALUES ('x' || hex(randomblob(200)))")
                    connection.commit()
            except Exception as exc:  # pragma: no cover
                errors.append(exc)
            finally:
                connection.close()

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            result = bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0))
        finally:
            stop.set()
            thread.join()
        assert not errors and result.report.ok
        assert count(result.info.path, "appointments") >= 4000

    def test_a_separate_folder_and_name_per_app(self, tmp_path):
        make_db(tmp_path / "o.db", "owner").close()
        make_db(tmp_path / "c.db", "checkin").close()
        owner = bk.create_backup(tmp_path / "o.db", tmp_path / "backups" / "owner", "owner", now=at(0)).info.path
        checkin = bk.create_backup(tmp_path / "c.db", tmp_path / "backups" / "checkin", "checkin", now=at(0)).info.path
        assert owner.name.startswith("owner-") and checkin.name.startswith("checkin-") and owner.parent != checkin.parent

    def test_a_label_is_part_of_the_name_and_validated(self, tmp_path):
        make_db(tmp_path / "live.db").close()
        path = bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0), label="pre-upgrade").info.path
        assert path.name == "owner-20261013T031500Z-pre-upgrade.db" and bk.parse_backup_name(path).label == "pre-upgrade"
        for bad in ("Has Space", "../x", "UPPER", "", "x" * 30):
            with pytest.raises(bk.BackupError, match="label"):
                bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(1), label=bad)

    def test_a_missing_database_a_bad_app_or_a_bad_keep_are_clear_errors(self, tmp_path):
        with pytest.raises(bk.BackupError, match="does not exist"):
            bk.create_backup(tmp_path / "nope.db", tmp_path / "b", "owner")
        make_db(tmp_path / "live.db").close()
        with pytest.raises(bk.BackupError, match="Unknown app"):
            bk.create_backup(tmp_path / "live.db", tmp_path / "b", "voice")
        with pytest.raises(bk.BackupError, match="at least 1"):
            bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", keep=0)
        assert not (tmp_path / "b").exists(), "nothing was created for a refused request"

    def test_an_unwritable_backup_folder_is_a_clear_error(self, tmp_path):
        make_db(tmp_path / "live.db").close()
        (tmp_path / "blocker").write_text("a file where the folder should be")
        with pytest.raises(bk.BackupError, match="backup folder"):
            bk.create_backup(tmp_path / "live.db", tmp_path / "blocker" / "owner", "owner")

    def test_two_backups_in_the_same_second_do_not_overwrite_each_other(self, tmp_path):
        make_db(tmp_path / "live.db").close()
        first = bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0)).info.path
        before = sha(first)
        with pytest.raises(bk.BackupError, match="already exists"):
            bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0))
        assert sha(first) == before

    def test_the_source_database_is_never_changed(self, tmp_path):
        make_db(tmp_path / "live.db").close()
        before = (sha(tmp_path / "live.db"), count(tmp_path / "live.db", "turns"))
        bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0))
        assert (sha(tmp_path / "live.db"), count(tmp_path / "live.db", "turns")) == before

    def test_a_backup_that_fails_verification_is_discarded_and_leaves_nothing_behind(self, tmp_path):
        make_db(tmp_path / "live.db").close()
        with pytest.raises(bk.BackupError, match="failed verification"):
            bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0), core_tables=("a_table_that_is_not_there",))
        assert list((tmp_path / "b").iterdir()) == []

    def test_a_file_that_is_not_a_database_cannot_be_backed_up(self, tmp_path):
        (tmp_path / "live.db").write_bytes(b"this is not sqlite" * 100)
        with pytest.raises(bk.BackupError):
            bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0))
        assert [p for p in (tmp_path / "b").iterdir()] == []


# ══════════════════════════════════════════════════════════════════════════════
# Retention
# ══════════════════════════════════════════════════════════════════════════════
class TestRetention:

    def fill(self, tmp_path, n, label=None, start=0):
        make_db(tmp_path / "live.db").close() if not (tmp_path / "live.db").exists() else None
        return [bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", keep=999, keep_pre_upgrade=999, now=at(start + i), label=label).info.path for i in range(n)]

    def test_only_the_newest_fourteen_are_kept_by_default(self, tmp_path):
        self.fill(tmp_path, 16)
        result = bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(100))
        kept = bk.list_backups(tmp_path / "b", "owner")
        assert len(kept) == bk.DEFAULT_KEEP == 14
        assert kept[0].path == result.info.path and len(result.pruned) == 3
        assert all(not (tmp_path / "b" / name).exists() and not (tmp_path / "b" / name).with_suffix(".json").exists() for name in result.pruned)
        assert min(b.created_at for b in kept) == at(3), "the oldest ones went, the newest stayed"

    def test_the_keep_count_is_configurable_and_never_below_one(self, tmp_path):
        self.fill(tmp_path, 5)
        assert len(bk.prune_backups(tmp_path / "b", "owner", keep=2)) == 3
        assert len(bk.list_backups(tmp_path / "b", "owner")) == 2
        with pytest.raises(bk.BackupError, match="at least 1"):
            bk.prune_backups(tmp_path / "b", "owner", keep=0)

    def test_pre_upgrade_backups_are_kept_separately_and_survive_routine_pruning(self, tmp_path):
        pre = self.fill(tmp_path, 2, label="pre-upgrade", start=0)
        self.fill(tmp_path, 6, start=10)
        bk.prune_backups(tmp_path / "b", "owner", keep=2)
        names = {b.path.name for b in bk.list_backups(tmp_path / "b", "owner")}
        assert all(p.name in names for p in pre), "routine pruning never removes a pre-upgrade backup"
        assert len([b for b in bk.list_backups(tmp_path / "b", "owner") if b.label is None]) == 2

    def test_pre_upgrade_backups_have_their_own_limit(self, tmp_path):
        self.fill(tmp_path, 5, label="pre-upgrade")
        bk.prune_backups(tmp_path / "b", "owner", keep=14, keep_pre_upgrade=3)
        assert len(bk.list_backups(tmp_path / "b", "owner")) == 3

    def test_pruning_touches_only_this_apps_backup_files(self, tmp_path):
        self.fill(tmp_path, 4)
        folder = tmp_path / "b"
        (folder / "notes.txt").write_text("keep me")
        (folder / "owner-latest.db").write_bytes(b"not our naming pattern")
        (folder / "checkin-20260101T000000Z.db").write_bytes(b"another app's backup")
        (folder / "owner-20260101T000000Z.sql").write_text("different extension")
        bk.prune_backups(folder, "owner", keep=1)
        assert {p.name for p in folder.iterdir() if not p.name.startswith("owner-2026101")} == {"notes.txt", "owner-latest.db", "checkin-20260101T000000Z.db", "owner-20260101T000000Z.sql"}
        assert len(bk.list_backups(folder, "owner")) == 1

    def test_listing_is_newest_first_and_ignores_strangers(self, tmp_path):
        self.fill(tmp_path, 3)
        (tmp_path / "b" / "random.db").write_bytes(b"x")
        listed = bk.list_backups(tmp_path / "b", "owner")
        assert [b.created_at for b in listed] == [at(2), at(1), at(0)]
        assert bk.list_backups(tmp_path / "does-not-exist", "owner") == []

    def test_the_newest_backup_always_survives_a_prune(self, tmp_path):
        paths = self.fill(tmp_path, 3)
        bk.prune_backups(tmp_path / "b", "owner", keep=1)
        assert paths[-1].exists() and not paths[0].exists()


# ══════════════════════════════════════════════════════════════════════════════
# Verification and corrupt-backup rejection
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def good_backup(tmp_path):
    make_db(tmp_path / "live.db", rows=300).close()
    return bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0)).info.path


class TestVerify:

    def test_a_good_backup_is_ok(self, good_backup):
        report = bk.verify_backup(good_backup, "owner")
        assert report.ok and not report.problems and "technicians" in report.tables
        assert report.raise_if_bad() is report

    def test_verifying_leaves_no_files_next_to_the_backup_and_does_not_change_it(self, good_backup):
        before = sha(good_backup)
        bk.verify_backup(good_backup, "owner")
        assert sha(good_backup) == before
        assert sorted(p.suffix for p in good_backup.parent.iterdir()) == [".db", ".json"]

    @pytest.mark.parametrize("content,expected", [(b"", "empty"), (b"hello world, definitely not sqlite", "not an SQLite"), (b"SQLite format 3\x00" + b"\x00" * 10, None)])
    def test_empty_and_foreign_files_are_rejected(self, tmp_path, content, expected):
        path = tmp_path / "owner-20261013T031500Z.db"
        path.write_bytes(content)
        report = bk.verify_backup(path, "owner")
        assert not report.ok and report.problems
        if expected:
            assert expected in report.problems[0]

    def test_a_truncated_backup_is_rejected(self, good_backup):
        data = good_backup.read_bytes()
        good_backup.write_bytes(data[: len(data) // 2])
        report = bk.verify_backup(good_backup, "owner", check_sidecar=False)
        assert not report.ok
        with pytest.raises(bk.BackupError, match="not a usable backup"):
            report.raise_if_bad()

    def test_a_damaged_page_is_caught_by_the_integrity_check(self, good_backup):
        data = bytearray(good_backup.read_bytes())
        for offset in range(len(data) // 2, len(data) // 2 + 2000):
            data[offset] ^= 0x5A
        good_backup.write_bytes(bytes(data))
        report = bk.verify_backup(good_backup, "owner", check_sidecar=False)
        assert not report.ok and any("integrity" in p or "cannot" in p or "malformed" in p for p in report.problems)

    def test_a_change_after_the_backup_was_made_is_detected_by_the_checksum(self, good_backup):
        connection = sqlite3.connect(str(good_backup))
        connection.execute("DELETE FROM technicians WHERE id < 10")
        connection.commit()
        connection.close()
        report = bk.verify_backup(good_backup, "owner")
        assert not report.ok and any("checksum" in p for p in report.problems)

    def test_missing_core_tables_are_a_schema_failure(self, tmp_path):
        connection = sqlite3.connect(str(tmp_path / "owner-20261013T031500Z.db"))
        connection.execute("CREATE TABLE only_one (id INTEGER)")
        connection.commit()
        connection.close()
        report = bk.verify_backup(tmp_path / "owner-20261013T031500Z.db", "owner")
        assert not report.ok and any("technicians" in p and "missing" in p for p in report.problems)

    def test_an_owner_backup_is_not_accepted_as_a_checkin_backup(self, good_backup):
        report = bk.verify_backup(good_backup, "checkin")
        assert not report.ok and any("owner backup, not a checkin" in p for p in report.problems)

    def test_a_backup_from_an_older_version_without_newer_tables_is_still_valid(self, tmp_path):
        """Newer tables are added by start-up migrations, so only the long-standing core is required."""
        make_db(tmp_path / "old.db", "checkin").close()
        path = bk.create_backup(tmp_path / "old.db", tmp_path / "b", "checkin", now=at(0)).info.path
        assert bk.verify_backup(path, "checkin").ok
        assert "kiosk_devices" not in bk.CORE_TABLES["checkin"] and "kiosk_devices" not in bk.verify_backup(path, "checkin").tables

    def test_rows_that_point_at_missing_records_are_a_warning_not_a_rejection(self, tmp_path):
        connection = sqlite3.connect(str(tmp_path / "live.db"))
        for table in bk.CORE_TABLES["owner"][1:]:
            connection.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
        connection.execute("CREATE TABLE technicians (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE child (id INTEGER PRIMARY KEY, tech INTEGER REFERENCES technicians(id))")
        connection.execute("INSERT INTO child(tech) VALUES (77)")  # an orphan written while foreign keys were off
        connection.commit()
        connection.close()
        report = bk.create_backup(tmp_path / "live.db", tmp_path / "b", "owner", now=at(0)).report
        assert report.ok and report.foreign_key_violations == 1 and any("foreign-key" in w for w in report.warnings)

    def test_a_missing_file_is_a_report_not_a_crash(self, tmp_path):
        report = bk.verify_backup(tmp_path / "nope.db", "owner")
        assert not report.ok and "does not exist" in report.problems[0]


# ══════════════════════════════════════════════════════════════════════════════
# Restore validation (no restore happens)
# ══════════════════════════════════════════════════════════════════════════════
class TestRestorePreflight:

    def test_a_good_backup_over_a_stopped_database_is_ok(self, tmp_path, good_backup):
        live = tmp_path / "live.db"
        outcome = bk.restore_preflight(good_backup, live, "owner")
        assert outcome["ok"] and outcome["backup_ok"] and outcome["live_exists"] and not outcome["possibly_in_use"]
        assert outcome["safety_backup_recommended"] is True and not outcome["problems"]

    def test_it_changes_nothing(self, tmp_path, good_backup):
        live = tmp_path / "live.db"
        before = (sha(live), sha(good_backup), sorted(p.name for p in tmp_path.rglob("*")))
        bk.restore_preflight(good_backup, live, "owner")
        assert (sha(live), sha(good_backup), sorted(p.name for p in tmp_path.rglob("*"))) == before

    def test_a_corrupt_backup_is_rejected(self, tmp_path, good_backup):
        data = bytearray(good_backup.read_bytes())
        data[len(data) // 2] ^= 0xFF
        data[len(data) // 2 + 1] ^= 0xFF
        good_backup.write_bytes(bytes(data))
        outcome = bk.restore_preflight(good_backup, tmp_path / "live.db", "owner")
        assert not outcome["ok"] and not outcome["backup_ok"] and outcome["problems"]

    def test_the_wrong_apps_backup_is_rejected(self, tmp_path, good_backup):
        outcome = bk.restore_preflight(good_backup, tmp_path / "live.db", "checkin")
        assert not outcome["ok"] and any("owner backup" in p for p in outcome["problems"])

    def test_a_live_database_that_is_in_use_is_flagged(self, tmp_path, good_backup):
        live = sqlite3.connect(str(tmp_path / "live.db"))
        live.execute("INSERT INTO technicians(note) VALUES ('open writer')")  # uncommitted: the -wal file and a write lock exist
        outcome = bk.restore_preflight(good_backup, tmp_path / "live.db", "owner")
        assert outcome["possibly_in_use"] and any("stop NailSystem" in w for w in outcome["warnings"])
        live.rollback()
        live.close()

    def test_a_missing_live_database_is_fine_for_a_fresh_install(self, tmp_path, good_backup):
        outcome = bk.restore_preflight(good_backup, tmp_path / "new" / "owner.db", "owner")
        assert outcome["ok"] and not outcome["live_exists"] and outcome["safety_backup_recommended"] is False

    def test_restoring_a_backup_over_itself_is_refused(self, good_backup):
        outcome = bk.restore_preflight(good_backup, good_backup, "owner")
        assert not outcome["ok"] and any("same file" in p for p in outcome["problems"])

    def test_a_damaged_live_database_is_reported_without_blocking_the_restore(self, tmp_path, good_backup):
        (tmp_path / "live.db").write_bytes(b"garbage" * 500)
        outcome = bk.restore_preflight(good_backup, tmp_path / "live.db", "owner")
        assert outcome["ok"] and any("cannot be opened" in w for w in outcome["warnings"])


# ══════════════════════════════════════════════════════════════════════════════
# Command line
# ══════════════════════════════════════════════════════════════════════════════
class TestCommandLine:

    def test_backup_list_verify_prune_and_preflight(self, tmp_path, capsys):
        make_db(tmp_path / "live.db").close()
        base = ["--app", "owner", "--db", str(tmp_path / "live.db"), "--dir", str(tmp_path / "b")]
        assert bk.main(["backup", *base, "--keep", "5"]) == 0
        assert "integrity ok" in capsys.readouterr().out
        backups = bk.list_backups(tmp_path / "b", "owner")
        assert len(backups) == 1
        assert bk.main(["list", *base]) == 0 and backups[0].path.name in capsys.readouterr().out
        assert bk.main(["verify", *base, "--file", str(backups[0].path)]) == 0
        assert json.loads(capsys.readouterr().out)["ok"] is True
        assert bk.main(["preflight", *base, "--file", str(backups[0].path)]) == 0
        assert json.loads(capsys.readouterr().out)["ok"] is True
        assert bk.main(["prune", *base, "--keep", "1"]) == 0

    def test_failures_are_exit_codes_and_plain_messages(self, tmp_path, capsys):
        base = ["--app", "owner", "--db", str(tmp_path / "missing.db"), "--dir", str(tmp_path / "b")]
        assert bk.main(["backup", *base]) == 2
        assert "does not exist" in capsys.readouterr().err
        bad = tmp_path / "owner-20261013T031500Z.db"
        bad.write_bytes(b"junk")
        assert bk.main(["verify", *base, "--file", str(bad)]) == 1
        assert bk.main(["verify", *base]) == 2

    def test_the_default_locations_come_from_the_installed_layout(self, tmp_path):
        home = tmp_path / "NailSystem"
        db, folder = bk._resolve_locations("checkin", None, None, {"NAILSYSTEM_MODE": "product", "NAILSYSTEM_HOME": str(home)})
        assert db == home / "data" / "checkin" / "checkin.db" and folder == home / "backups" / "checkin"

    def test_in_development_the_default_is_beside_the_database(self, tmp_path):
        db, folder = bk._resolve_locations("owner", None, None, {"DATABASE_URL": f"sqlite:///{(tmp_path / 'dev.db').as_posix()}"})
        assert db == tmp_path / "dev.db" and folder == (tmp_path / "backups" / "owner").resolve()
