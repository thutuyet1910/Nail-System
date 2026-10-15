"""Runtime layout, salon.json, secrets, precedence, log redaction, SQLite pragmas and ACLs.

THIS FILE IS IDENTICAL IN BOTH REPOSITORIES (Owner: backend/, Check-In: backend/app/). Nothing here touches the real
C:\\ProgramData\\NailSystem: every layout lives in a pytest temporary folder and every environment is a plain dict.
"""

import json
import logging
import os
import pathlib
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

try:  # Check-In: the test sits inside the `app` package
    from . import nailsystem_runtime as rt
except ImportError:  # Owner: a flat folder
    import nailsystem_runtime as rt

WINDOWS = sys.platform == "win32"
needs_windows = pytest.mark.skipif(not WINDOWS, reason="Windows DPAPI / ACLs")
TOKEN = "tok-" + "A1b2C3d4" * 4  # a made-up value, never a real credential


def make_layout(tmp_path, *, salon=None, token=TOKEN, extra_secrets=None, with_salon=True, with_secrets=True):
    home = tmp_path / "NailSystem"
    paths = rt.RuntimePaths(home)
    paths.ensure()
    if with_salon:
        paths.salon_json.write_text(json.dumps(salon if salon is not None else rt.default_salon_config("salon-test")), encoding="utf-8")
    if with_secrets and WINDOWS:
        store = rt.DpapiSecrets(paths.secrets_file)
        if token:
            store.set("CHECKIN_INTERNAL_SERVICE_TOKEN", token)
        for name, value in (extra_secrets or {}).items():
            store.set(name, value)
    return home, paths


def product_env(home, **extra):
    return {"NAILSYSTEM_MODE": "product", "NAILSYSTEM_HOME": str(home), **extra}


# ══════════════════════════════════════════════════════════════════════════════
# Mode and paths
# ══════════════════════════════════════════════════════════════════════════════
class TestModeAndPaths:

    def test_development_is_the_default_and_needs_no_data_folder(self):
        assert rt.current_mode({}) == "development"
        assert rt.resolve_home({}) is None

    @pytest.mark.parametrize("bad", ["prod", "installed", "DEBUG", "1"])
    def test_an_unknown_mode_is_an_error_not_a_guess(self, bad):
        with pytest.raises(rt.RuntimeConfigError, match="not valid"):
            rt.current_mode({"NAILSYSTEM_MODE": bad})

    def test_the_mode_is_never_inferred_from_the_working_directory(self, tmp_path, monkeypatch):
        (tmp_path / "ProgramData").mkdir()
        monkeypatch.chdir(tmp_path / "ProgramData")
        assert rt.current_mode({}) == "development"

    def test_product_mode_uses_programdata(self, tmp_path):
        env = {"NAILSYSTEM_MODE": "product", "PROGRAMDATA": str(tmp_path / "ProgramData")}
        assert rt.resolve_home(env) == tmp_path / "ProgramData" / "NailSystem"

    def test_an_explicit_home_wins_in_both_modes(self, tmp_path):
        env = {"NAILSYSTEM_MODE": "product", "NAILSYSTEM_HOME": str(tmp_path / "Elsewhere"), "PROGRAMDATA": str(tmp_path / "pd")}
        assert rt.resolve_home(env) == tmp_path / "Elsewhere"
        assert rt.resolve_home({"NAILSYSTEM_HOME": str(tmp_path / "Dev")}) == tmp_path / "Dev"  # development opt-in

    def test_product_mode_without_any_location_fails_clearly(self):
        with pytest.raises(rt.RuntimeConfigError, match="PROGRAMDATA"):
            rt.resolve_home({"NAILSYSTEM_MODE": "product"})

    def test_a_relative_home_is_refused(self):
        with pytest.raises(rt.RuntimeConfigError, match="absolute"):
            rt.resolve_home({"NAILSYSTEM_HOME": "data\\NailSystem"})

    def test_production_data_never_lives_in_a_git_working_copy(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        with pytest.raises(rt.RuntimeConfigError, match="Git working copy"):
            rt.resolve_home({"NAILSYSTEM_MODE": "product", "NAILSYSTEM_HOME": str(repo / "runtime")})

    def test_the_layout_is_exactly_the_documented_one(self, tmp_path):
        paths = rt.RuntimePaths(tmp_path / "NailSystem")
        root = tmp_path / "NailSystem"
        assert paths.salon_json == root / "config" / "salon.json"
        assert paths.secrets_file == root / "secrets" / "secrets.dat"
        assert paths.db_path("owner") == root / "data" / "owner" / "owner.db"
        assert paths.db_path("checkin") == root / "data" / "checkin" / "checkin.db"
        assert paths.backup_dir("owner") == root / "backups" / "owner"
        assert paths.backup_dir("checkin") == root / "backups" / "checkin"
        assert paths.log_dir("owner") == root / "logs" / "owner" and paths.log_dir("checkin") == root / "logs" / "checkin"
        with pytest.raises(rt.RuntimeConfigError):
            paths.db_path("../evil")

    def test_ensure_creates_every_folder_and_is_repeatable(self, tmp_path):
        paths = rt.RuntimePaths(tmp_path / "NailSystem")
        paths.ensure()
        paths.ensure()
        for folder in ("config", "secrets", "data/owner", "data/checkin", "backups/owner", "backups/checkin", "logs/owner", "logs/checkin", "logs/launcher"):
            assert (paths.root / folder).is_dir(), folder

    def test_ensure_without_secrets_leaves_that_folder_to_the_installer(self, tmp_path):
        paths = rt.RuntimePaths(tmp_path / "NailSystem")
        paths.ensure(("owner",), include_secrets=False)
        assert paths.data_dir("owner").is_dir() and not paths.secrets_dir.exists() and not paths.data_dir("checkin").exists()

    def test_a_folder_that_cannot_be_created_gets_an_actionable_message(self, tmp_path):
        blocker = tmp_path / "NailSystem"
        blocker.write_text("i am a file")  # something other than a folder is in the way
        with pytest.raises(rt.RuntimeConfigError) as caught:
            rt.RuntimePaths(blocker).ensure()
        message = str(caught.value)
        assert str(blocker) in message and ("administrator" in message or "not a folder" in message)

    def test_sqlite_urls_round_trip_windows_paths(self, tmp_path):
        path = tmp_path / "with space" / "owner.db"
        url = rt.sqlite_url(path)
        assert url.startswith("sqlite:///") and "\\" not in url
        assert rt.sqlite_path_from_url(url) == path
        assert rt.sqlite_path_from_url("sqlite://") is None and rt.sqlite_path_from_url("sqlite:///:memory:") is None
        assert rt.sqlite_path_from_url("postgresql://x/y") is None


# ══════════════════════════════════════════════════════════════════════════════
# salon.json
# ══════════════════════════════════════════════════════════════════════════════
def valid(**changes):
    data = rt.default_salon_config("salon-test")
    for key, value in changes.items():
        data[key] = value
    return data


class TestSalonJson:

    def test_the_default_is_valid_and_round_trips(self):
        config = rt.parse_salon_config(rt.default_salon_config())
        assert config.schema_version == 1 and config.timezone == "America/Phoenix" and (config.kiosk_port, config.owner_port) == (8080, 8081)
        assert rt.parse_salon_config(config.as_dict()) == config

    def test_a_missing_optional_part_gets_its_default(self):
        config = rt.parse_salon_config({"schema_version": 1, "salon_id": "abc"})
        assert (config.timezone, config.tier, config.kiosk_port, config.owner_port) == ("America/Phoenix", "development", 8080, 8081)

    def test_write_default_creates_once_and_never_overwrites(self, tmp_path):
        path = tmp_path / "config" / "salon.json"
        assert rt.write_default_salon_config(path, "mine") is True
        original = path.read_text()
        assert rt.write_default_salon_config(path, "other") is False and path.read_text() == original
        assert json.loads(original)["salon_id"] == "mine"
        assert rt.write_default_salon_config(path, "forced", overwrite=True) is True

    def test_a_byte_order_mark_from_a_windows_editor_is_tolerated(self, tmp_path):
        path = tmp_path / "salon.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps(rt.default_salon_config("bom")).encode())
        assert rt.load_salon_config(path).salon_id == "bom"

    def test_malformed_json_names_the_file_and_the_position(self, tmp_path):
        path = tmp_path / "salon.json"
        path.write_text('{\n  "schema_version": 1,\n  "salon_id": "x",\n}')
        with pytest.raises(rt.RuntimeConfigError) as caught:
            rt.load_salon_config(path)
        assert str(path) in str(caught.value) and "line 4" in str(caught.value)

    def test_a_missing_file_says_how_to_create_it(self, tmp_path):
        with pytest.raises(rt.RuntimeConfigError, match="init"):
            rt.load_salon_config(tmp_path / "nope.json")

    def test_a_huge_or_binary_file_is_refused(self, tmp_path):
        big = tmp_path / "big.json"
        big.write_text(" " * (rt.MAX_CONFIG_BYTES + 1))
        with pytest.raises(rt.RuntimeConfigError, match="too large"):
            rt.load_salon_config(big)
        binary = tmp_path / "bin.json"
        binary.write_bytes(b"\xff\xfe\x00\x01")
        with pytest.raises(rt.RuntimeConfigError):
            rt.load_salon_config(binary)

    @pytest.mark.parametrize("data", [[], "text", 5, None])
    def test_it_must_be_a_json_object(self, data):
        with pytest.raises(rt.RuntimeConfigError, match="JSON object"):
            rt.parse_salon_config(data)

    @pytest.mark.parametrize("version", [0, 2, 99, -1, "1", 1.0, True, None])
    def test_unsupported_or_malformed_schema_versions_are_refused(self, version):
        data = valid()
        data["schema_version"] = version
        with pytest.raises(rt.RuntimeConfigError, match="schema_version"):
            rt.parse_salon_config(data)

    def test_a_missing_schema_version_is_refused(self):
        data = valid()
        del data["schema_version"]
        with pytest.raises(rt.RuntimeConfigError, match="schema_version"):
            rt.parse_salon_config(data)

    def test_the_message_for_a_newer_file_says_what_this_build_understands(self):
        with pytest.raises(rt.RuntimeConfigError, match="understands 1"):
            rt.parse_salon_config(valid(schema_version=2))

    def test_unknown_settings_are_errors_so_typos_do_not_pass_silently(self):
        with pytest.raises(rt.RuntimeConfigError, match="unknown setting"):
            rt.parse_salon_config(valid(timzone="America/Phoenix"))
        data = valid()
        data["network"]["kiosk_prot"] = 9000
        with pytest.raises(rt.RuntimeConfigError, match="unknown network setting"):
            rt.parse_salon_config(data)

    @pytest.mark.parametrize("key", ["twilio_auth_token", "OPENAI_API_KEY", "owner_password", "internal_token", "client_secret", "credentials", "private_key"])
    def test_salon_json_refuses_anything_that_looks_like_a_secret(self, key):
        data = valid()
        data[key] = "x"
        with pytest.raises(rt.RuntimeConfigError, match="secrets"):
            rt.parse_salon_config(data)
        nested = valid()
        nested["network"][key] = "x"
        with pytest.raises(rt.RuntimeConfigError, match="secrets"):
            rt.parse_salon_config(nested)

    @pytest.mark.parametrize("salon_id", ["", " ", "-lead", "has space", "a" * 65, "semi;colon", "../x", None, 7])
    def test_salon_id_rules(self, salon_id):
        with pytest.raises(rt.RuntimeConfigError, match="salon_id"):
            rt.parse_salon_config(valid(salon_id=salon_id))

    @pytest.mark.parametrize("zone", ["", "   ", "Mars/Olympus", "../etc/passwd", "America/Phoenix\n", 5, None])
    def test_timezones_must_exist(self, zone):
        with pytest.raises(rt.RuntimeConfigError, match="timezone|time zone"):
            rt.parse_salon_config(valid(timezone=zone))

    def test_a_real_timezone_is_accepted(self):
        assert rt.parse_salon_config(valid(timezone="America/Los_Angeles")).timezone == "America/Los_Angeles"

    @pytest.mark.parametrize("tier", ["", "Pro", "with space", "x" * 33, 3])
    def test_tier_rules(self, tier):
        with pytest.raises(rt.RuntimeConfigError, match="tier"):
            rt.parse_salon_config(valid(tier=tier))

    @pytest.mark.parametrize("port", [0, 80, 1023, 65536, 70000, -1, "8080", 8080.5, True, None])
    def test_port_rules(self, port):
        data = valid()
        data["network"]["kiosk_port"] = port
        with pytest.raises(rt.RuntimeConfigError, match="kiosk_port"):
            rt.parse_salon_config(data)

    def test_the_two_proxy_ports_must_differ_and_must_not_collide_with_a_backend(self):
        data = valid()
        data["network"] = {"kiosk_port": 9000, "owner_port": 9000}
        with pytest.raises(rt.RuntimeConfigError, match="differ"):
            rt.parse_salon_config(data)
        for reserved in (8000, 8001):
            clash = valid()
            clash["network"] = {"kiosk_port": reserved, "owner_port": 9001}
            with pytest.raises(rt.RuntimeConfigError, match="reserved"):
                rt.parse_salon_config(clash)

    def test_a_bad_network_block_type_is_refused(self):
        with pytest.raises(rt.RuntimeConfigError, match="network"):
            rt.parse_salon_config(valid(network=["8080"]))

    def test_errors_from_a_file_start_with_its_path(self, tmp_path):
        path = tmp_path / "salon.json"
        path.write_text(json.dumps(valid(tier="NOPE")))
        with pytest.raises(rt.RuntimeConfigError) as caught:
            rt.load_salon_config(path)
        assert str(caught.value).startswith(str(path))


# ══════════════════════════════════════════════════════════════════════════════
# Secrets
# ══════════════════════════════════════════════════════════════════════════════
class TestSecretsInterface:

    def test_environment_secrets_are_read_only_and_list_names_only(self):
        provider = rt.EnvironmentSecrets({"OPENAI_API_KEY": "tk-not-a-real-key-123456", "PATH": "x"})
        assert provider.get("OPENAI_API_KEY") == "tk-not-a-real-key-123456" and provider.get("TWILIO_AUTH_TOKEN") is None
        assert provider.names() == ["OPENAI_API_KEY"]
        with pytest.raises(rt.SecretsError, match="read-only"):
            provider.set("OPENAI_API_KEY", "x")
        with pytest.raises(rt.SecretsError, match="read-only"):
            provider.delete("OPENAI_API_KEY")
        assert "tk-not-a-real-key" not in repr(provider) and "OPENAI_API_KEY" in repr(provider)

    @needs_windows
    def test_the_dpapi_store_round_trips_and_never_writes_plaintext(self, tmp_path):
        path = tmp_path / "secrets" / "secrets.dat"
        store = rt.DpapiSecrets(path)
        assert store.names() == [] and store.get("OPENAI_API_KEY") is None  # a missing file is simply empty
        store.set("OPENAI_API_KEY", "tk-test-0123456789-abcdef")
        store.set("TWILIO_AUTH_TOKEN", "auth-token-value-9876")
        raw = path.read_bytes()
        assert raw.startswith(b"NSSECRETS1\n")
        for plaintext in (b"tk-test-0123456789", b"auth-token-value", b"OPENAI_API_KEY", b"TWILIO_AUTH_TOKEN", b"values"):
            assert plaintext not in raw
        again = rt.DpapiSecrets(path)  # a fresh instance, as after a restart
        assert again.get("OPENAI_API_KEY") == "tk-test-0123456789-abcdef"
        assert again.names() == ["OPENAI_API_KEY", "TWILIO_AUTH_TOKEN"]
        assert "tk-test" not in repr(again) and "auth-token" not in repr(again)

    @needs_windows
    def test_update_delete_and_atomic_replacement(self, tmp_path):
        store = rt.DpapiSecrets(tmp_path / "s.dat")
        store.set("OPENAI_API_KEY", "first-value-1234")
        store.set("OPENAI_API_KEY", "second-value-5678")
        assert store.get("OPENAI_API_KEY") == "second-value-5678"
        assert store.delete("OPENAI_API_KEY") is True and store.delete("OPENAI_API_KEY") is False
        assert store.names() == []
        assert not list(tmp_path.glob("*.tmp")), "no temporary file is left behind"

    @needs_windows
    @pytest.mark.parametrize("name,value", [("lower", "x" * 10), ("1ABC", "x" * 10), ("OK_NAME", ""), ("OK_NAME", "has\x00nul"), ("OK_NAME", "x" * 5000), ("A", "xx"), ("OK NAME", "xx"), ("OK_NAME", None)])
    def test_invalid_names_and_values_are_refused(self, tmp_path, name, value):
        with pytest.raises(rt.SecretsError):
            rt.DpapiSecrets(tmp_path / "s.dat").set(name, value)

    @needs_windows
    def test_a_tampered_or_foreign_file_is_detected_not_trusted(self, tmp_path):
        path = tmp_path / "s.dat"
        store = rt.DpapiSecrets(path)
        store.set("OPENAI_API_KEY", "value-1234567890")
        raw = bytearray(path.read_bytes())
        raw[-5] ^= 0xFF
        path.write_bytes(bytes(raw))
        with pytest.raises(rt.SecretsError):
            rt.DpapiSecrets(path).get("OPENAI_API_KEY")
        path.write_bytes(b"not a secrets file")
        with pytest.raises(rt.SecretsError, match="not a NailSystem secrets file"):
            rt.DpapiSecrets(path).names()

    @needs_windows
    def test_the_store_is_bound_to_this_application(self, tmp_path):
        path = tmp_path / "s.dat"
        rt.DpapiSecrets(path).set("OPENAI_API_KEY", "value-1234567890")
        with pytest.raises(rt.SecretsError):
            rt.DpapiSecrets(path, entropy=b"some other program").get("OPENAI_API_KEY")

    @needs_windows
    def test_user_scope_also_round_trips(self, tmp_path):
        store = rt.DpapiSecrets(tmp_path / "u.dat", scope="user")
        store.set("OPENAI_API_KEY", "value-1234567890")
        assert rt.DpapiSecrets(tmp_path / "u.dat", scope="user").get("OPENAI_API_KEY") == "value-1234567890"
        with pytest.raises(rt.SecretsError):
            rt.DpapiSecrets(tmp_path / "u.dat", scope="galaxy")

    @needs_windows
    def test_concurrent_writers_do_not_lose_each_other(self, tmp_path):
        store = rt.DpapiSecrets(tmp_path / "s.dat")
        names = [f"SECRET_{n}" for n in range(8)]
        threads = [threading.Thread(target=store.set, args=(name, f"value-number-{name}")) for name in names]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert store.names() == sorted(names)


# ══════════════════════════════════════════════════════════════════════════════
# bootstrap: precedence and what ends up in the environment
# ══════════════════════════════════════════════════════════════════════════════
@needs_windows
class TestProductPrecedence:

    def test_product_mode_fills_the_environment_from_the_installed_layout(self, tmp_path):
        home, paths = make_layout(tmp_path, extra_secrets={"OPENAI_API_KEY": "openai-value-123456"})
        env = product_env(home)
        context = rt.bootstrap("owner", env)
        assert context.mode == "product" and context.salon.salon_id == "salon-test"
        assert env["DATABASE_URL"] == rt.sqlite_url(paths.db_path("owner"))
        assert env["SALON_TIMEZONE"] == "America/Phoenix"
        assert env["ALLOWED_ORIGINS"] == "http://127.0.0.1:8081,http://localhost:8081"
        assert env["CHECKIN_API_BASE"] == "http://127.0.0.1:8000"
        assert env["CHECKIN_INTERNAL_SERVICE_TOKEN"] == TOKEN and env["OPENAI_API_KEY"] == "openai-value-123456"
        assert paths.data_dir("owner").is_dir() and paths.backup_dir("owner").is_dir() and paths.log_dir("owner").is_dir()

    def test_the_ports_in_salon_json_drive_the_allowed_origins(self, tmp_path):
        salon = rt.default_salon_config("p")
        salon["network"] = {"kiosk_port": 9090, "owner_port": 9091}
        home, _ = make_layout(tmp_path, salon=salon)
        env = product_env(home)
        rt.bootstrap("owner", env)
        assert env["ALLOWED_ORIGINS"] == "http://127.0.0.1:9091,http://localhost:9091"

    def test_checkin_gets_its_own_database_its_owner_address_and_only_its_own_secrets(self, tmp_path):
        home, paths = make_layout(tmp_path, extra_secrets={"EMAIL_PASSWORD": "mail-pass-123456", "OPENAI_API_KEY": "openai-value-123456", "TWILIO_AUTH_TOKEN": "twilio-token-1234"})
        env = product_env(home)
        rt.bootstrap("checkin", env)
        assert env["DATABASE_URL"] == rt.sqlite_url(paths.db_path("checkin"))
        assert env["OWNER_API_BASE"] == "http://127.0.0.1:8001" and "CHECKIN_API_BASE" not in env and "ALLOWED_ORIGINS" not in env
        assert env["EMAIL_PASSWORD"] == "mail-pass-123456" and env["CHECKIN_INTERNAL_SERVICE_TOKEN"] == TOKEN
        assert "OPENAI_API_KEY" not in env and "TWILIO_AUTH_TOKEN" not in env  # least privilege: Check-In never receives voice keys

    def test_secrets_that_belong_to_the_other_app_are_removed_from_the_environment(self, tmp_path):
        home, _ = make_layout(tmp_path)
        checkin_env = product_env(home, OPENAI_API_KEY="tk-forgotten-voice-key-123", TWILIO_AUTH_TOKEN="forgotten-twilio-token-1", EMAIL_PASSWORD="mail-pass-in-env-123")
        context = rt.bootstrap("checkin", checkin_env)
        assert "OPENAI_API_KEY" not in checkin_env and "TWILIO_AUTH_TOKEN" not in checkin_env
        assert {"OPENAI_API_KEY", "TWILIO_AUTH_TOKEN"} <= set(context.ignored_env)
        owner_env = product_env(home, EMAIL_PASSWORD="mail-pass-in-env-123", OPENAI_API_KEY="tk-forgotten-voice-key-123")
        rt.bootstrap("owner", owner_env)
        assert "EMAIL_PASSWORD" not in owner_env and "OPENAI_API_KEY" not in owner_env  # the Owner's own, but not in its store

    def test_a_forgotten_environment_value_cannot_replace_an_installed_setting(self, tmp_path):
        home, paths = make_layout(tmp_path)
        env = product_env(home, DATABASE_URL="sqlite:///C:/old/dev.db", SALON_TIMEZONE="Asia/Tokyo",
                          ALLOWED_ORIGINS="http://evil.example", CHECKIN_INTERNAL_SERVICE_TOKEN="stale-token-from-a-dev-session")
        context = rt.bootstrap("owner", env)
        assert env["DATABASE_URL"] == rt.sqlite_url(paths.db_path("owner")) and env["SALON_TIMEZONE"] == "America/Phoenix"
        assert env["ALLOWED_ORIGINS"].startswith("http://127.0.0.1:8081") and env["CHECKIN_INTERNAL_SERVICE_TOKEN"] == TOKEN
        assert {"DATABASE_URL", "SALON_TIMEZONE", "ALLOWED_ORIGINS", "CHECKIN_INTERNAL_SERVICE_TOKEN"} <= set(context.ignored_env)
        assert any("Ignored process-environment values" in w for w in context.warnings)
        assert "stale-token" not in " ".join(context.warnings) and "evil.example" not in " ".join(context.warnings)  # names only

    def test_an_environment_secret_that_the_store_lacks_is_removed_not_trusted(self, tmp_path):
        home, _ = make_layout(tmp_path)
        env = product_env(home, OPENAI_API_KEY="tk-leftover-from-a-test-123456", TWILIO_AUTH_TOKEN="leftover-twilio-token")
        context = rt.bootstrap("owner", env)
        assert "OPENAI_API_KEY" not in env and "TWILIO_AUTH_TOKEN" not in env
        assert "OPENAI_API_KEY" not in context.sources

    def test_support_mode_lets_the_environment_win_and_says_so(self, tmp_path):
        home, paths = make_layout(tmp_path)
        env = product_env(home, NAILSYSTEM_ALLOW_ENV_OVERRIDE="true", SALON_TIMEZONE="America/Los_Angeles",
                          DATABASE_URL=rt.sqlite_url(paths.data_dir("owner") / "debug.db"), OPENAI_API_KEY="debug-openai-key-123")
        context = rt.bootstrap("owner", env)
        assert env["SALON_TIMEZONE"] == "America/Los_Angeles" and env["DATABASE_URL"].endswith("debug.db") and env["OPENAI_API_KEY"] == "debug-openai-key-123"
        assert {"SALON_TIMEZONE", "DATABASE_URL"} <= set(context.overridden)
        assert any("NAILSYSTEM_ALLOW_ENV_OVERRIDE is on" in w for w in context.warnings)
        assert context.sources["SALON_TIMEZONE"] == "process environment" and context.sources["CHECKIN_INTERNAL_SERVICE_TOKEN"] == "secrets store"

    def test_without_the_support_flag_a_database_outside_the_data_folder_cannot_survive(self, tmp_path):
        home, paths = make_layout(tmp_path)
        env = product_env(home, DATABASE_URL=rt.sqlite_url(tmp_path / "somewhere" / "else.db"))
        rt.bootstrap("owner", env)
        assert rt.sqlite_path_from_url(env["DATABASE_URL"]) == paths.db_path("owner")

    def test_a_missing_salon_json_is_a_clear_error_never_a_silent_default(self, tmp_path):
        home, _ = make_layout(tmp_path, with_salon=False)
        with pytest.raises(rt.RuntimeConfigError, match="salon.json was not found"):
            rt.bootstrap("owner", product_env(home))

    def test_a_malformed_salon_json_stops_start_up(self, tmp_path):
        home, paths = make_layout(tmp_path)
        paths.salon_json.write_text("{ not json")
        with pytest.raises(rt.RuntimeConfigError, match="not valid JSON"):
            rt.bootstrap("checkin", product_env(home))

    def test_a_missing_required_secret_stops_start_up_and_names_it_but_not_a_value(self, tmp_path):
        home, _ = make_layout(tmp_path, token=None)
        with pytest.raises(rt.RuntimeConfigError) as caught:
            rt.bootstrap("owner", product_env(home, CHECKIN_INTERNAL_SERVICE_TOKEN="old-dev-token-123456"))
        assert "CHECKIN_INTERNAL_SERVICE_TOKEN" in str(caught.value) and "old-dev-token" not in str(caught.value)

    def test_there_is_no_silent_fallback_to_a_repository_database(self, tmp_path):
        home, paths = make_layout(tmp_path)
        env = product_env(home)
        rt.bootstrap("owner", env)
        assert "nail_system.db" not in env["DATABASE_URL"] and str(paths.root).replace("\\", "/") in env["DATABASE_URL"]

    def test_the_description_names_sources_and_never_a_value(self, tmp_path):
        home, _ = make_layout(tmp_path, extra_secrets={"OPENAI_API_KEY": "openai-value-123456"})
        context = rt.bootstrap("owner", product_env(home, DATABASE_URL="sqlite:///x.db"))
        text = json.dumps(context.describe())
        assert "openai-value-123456" not in text and TOKEN not in text
        assert context.describe()["sources"]["OPENAI_API_KEY"] == "secrets store"
        assert context.sources["DATABASE_URL"] == "installed layout"

    def test_secrets_are_registered_for_log_redaction(self, tmp_path):
        home, _ = make_layout(tmp_path, extra_secrets={"OPENAI_API_KEY": "openai-value-123456"})
        context = rt.bootstrap("owner", product_env(home))
        assert context.redactor(f"calling with {TOKEN} and openai-value-123456").count("[redacted]") == 2


class TestDevelopmentPrecedence:

    def test_with_nothing_configured_the_environment_is_left_exactly_alone(self):
        env = {"DATABASE_URL": "sqlite:///./mine.db", "FOO": "bar"}
        context = rt.bootstrap("owner", env)
        assert env == {"DATABASE_URL": "sqlite:///./mine.db", "FOO": "bar"} and context.mode == "development" and context.paths is None

    def test_the_environment_beats_salon_json_and_salon_json_beats_defaults(self, tmp_path):
        home = tmp_path / "dev"
        paths = rt.RuntimePaths(home)
        paths.ensure()
        salon = rt.default_salon_config("dev")
        salon["timezone"] = "America/Los_Angeles"
        paths.salon_json.write_text(json.dumps(salon))
        env = {"NAILSYSTEM_HOME": str(home), "SALON_TIMEZONE": "America/Denver"}
        context = rt.bootstrap("owner", env)
        assert env["SALON_TIMEZONE"] == "America/Denver"                      # 1. environment wins
        assert rt.sqlite_path_from_url(env["DATABASE_URL"]) == paths.db_path("owner")  # 3. the layout fills what is unset
        assert env["ALLOWED_ORIGINS"].startswith("http://127.0.0.1:8081")
        assert context.sources["SALON_TIMEZONE"] == "process environment" and context.sources["DATABASE_URL"] == "installed layout"
        assert not context.ignored_env, "development never ignores the environment"

    def test_development_does_not_create_data_folders_or_require_salon_json(self, tmp_path):
        home = tmp_path / "opt-in"
        rt.bootstrap("checkin", {"NAILSYSTEM_HOME": str(home)})
        assert not home.exists()

    def test_the_environment_beats_the_dev_database_default(self, tmp_path):
        env = {"NAILSYSTEM_HOME": str(tmp_path / "h"), "DATABASE_URL": "sqlite:///./explicit.db"}
        rt.bootstrap("owner", env)
        assert env["DATABASE_URL"] == "sqlite:///./explicit.db"

    def test_dotenv_is_a_development_convenience_only(self):
        assert rt.should_load_dotenv({}) is True
        assert rt.should_load_dotenv({"NAILSYSTEM_MODE": "product"}) is False
        assert rt.should_load_dotenv({"NAILSYSTEM_MODE": "nonsense"}) is True  # the real error is raised by bootstrap


# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════
class TestRedaction:

    def setup_method(self):
        self.redact = rt.Redactor([TOKEN, "openai-value-123456"])

    def test_exact_secret_values_are_removed_wherever_they_appear(self):
        line = self.redact(f"url=https://x/{TOKEN}/y key=openai-value-123456")
        assert TOKEN not in line and "openai-value-123456" not in line

    @pytest.mark.parametrize("line", [
        "X-Internal-Service-Token: abc123secretvalue",
        "x-kiosk-device-token=7.abcdefghijklmnopqrstuvwxyzABCDEFGHIJ012345678",
        "X-Profile-Edit-Token: zzzzzzzzzzzzzzzzzzzz",
        "X-CSRF-Token: csrfvalue123456",
        "Authorization: Basic dXNlcjpwYXNzd29yZA==",
        "Cookie: owner_session=abc123def456",
        "Set-Cookie: staff_session=abc123def456; HttpOnly",
        "password=hunter2hunter2",
        'api_key: "tk-abcdef0123456789"',
        "auth_token=0123456789abcdef",
        "Bearer " + "abcdefghijklmnopqrst" + "uvwxyz0123456789",  # built from pieces: the repository scanner must never see a whole credential-shaped string
    ])
    def test_credentials_in_headers_and_assignments_are_masked(self, line):
        cleaned = self.redact(line)
        assert "[redacted]" in cleaned
        for leaked in ("abc123secretvalue", "abcdefghijklmnopqrstuvwxyzABCDEFGHIJ", "zzzzzzzz", "csrfvalue", "dXNlcjpwYXNzd29yZA", "abc123def456", "hunter2", "tk-abcdef", "0123456789abcdef", "abcdefghijklmnopqrstuvwxyz0123456789"):
            assert leaked not in cleaned

    def test_a_kiosk_device_token_and_a_pairing_code_are_masked_even_without_a_label(self):
        cleaned = self.redact("paired device 7.abcdefghijklmnopqrstuvwxyzABCDEFGHIJ0123456789 with code K7QM-4TXD")
        assert "abcdefghij" not in cleaned and "K7QM-4TXD" not in cleaned

    @pytest.mark.parametrize("phone", ["6025550177", "(602) 555-0177", "602-555-0177", "+1 602 555 0177", "1-602-555-0177", "602.555.0177"])
    def test_phone_numbers_keep_only_their_last_two_digits(self, phone):
        cleaned = self.redact(f"check-in for {phone} done")
        assert "555" not in cleaned and "0177" not in cleaned and cleaned.endswith("77 done") and "602" not in cleaned

    def test_phone_numbers_in_urls_are_masked_too(self):
        assert "6025550177" not in self.redact("GET /customers/by-phone/6025550177 404")

    def test_email_addresses_are_masked(self):
        cleaned = self.redact("send failed for jane.doe@example.com and bob@mail.co.uk")
        assert "jane.doe" not in cleaned and "bob@" not in cleaned and "j***@example.com" in cleaned and "b***@mail.co.uk" in cleaned

    @pytest.mark.parametrize("line", [
        "Scheduled birthday reminders finished: 3 sent",
        "customer 12 earned a 10% loyalty discount (visit #10)",
        "2026-10-13 03:15:00 INFO started on port 8080 in 1.25s",
        "IntegrityError: UNIQUE constraint failed: customers.phone_number",
        "Voice tool get_available_slots failed: ValueError",
    ])
    def test_ordinary_log_lines_are_not_mangled(self, line):
        assert self.redact(line) == line

    def test_short_secrets_are_not_registered_so_they_cannot_blank_ordinary_words(self):
        redact = rt.Redactor(["abc", "yes", ""])
        assert redact("abc yes") == "abc yes"


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield root
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


class TestLogFiles:

    def test_product_logs_rotate_in_the_log_folder_and_never_hold_secrets_phones_or_emails(self, tmp_path, clean_root_logger):
        redactor = rt.Redactor([TOKEN])
        file_handler, _console = rt.configure_logging("owner", tmp_path / "logs" / "owner", redactor)
        assert isinstance(file_handler, logging.handlers.RotatingFileHandler) and file_handler.maxBytes == 5_000_000 and file_handler.backupCount == 5
        log = logging.getLogger("nailsystem.test")
        log.warning("token %s phone 6025550177 mail jane.doe@example.com X-Internal-Service-Token: %s", TOKEN, TOKEN)
        try:
            raise ValueError(f"boom {TOKEN} 602-555-0177")
        except ValueError:
            log.exception("failed")
        file_handler.flush()
        text = (tmp_path / "logs" / "owner" / "owner.log").read_text(encoding="utf-8")
        assert "phone" in text and "failed" in text and "Traceback" in text
        for leaked in (TOKEN, "6025550177", "0177", "jane.doe", "602-555"):
            assert leaked not in text, leaked

    def test_calling_it_twice_does_not_duplicate_handlers(self, tmp_path, clean_root_logger):
        for _ in range(3):
            rt.configure_logging("checkin", tmp_path / "logs", rt.Redactor())
        assert [h.get_name() for h in clean_root_logger.handlers].count("nailsystem-checkin") == 2  # one file + one console

    def test_unknown_apps_are_refused(self, tmp_path):
        with pytest.raises(rt.RuntimeConfigError):
            rt.configure_logging("../x", tmp_path, rt.Redactor())


# ══════════════════════════════════════════════════════════════════════════════
# SQLite hardening
# ══════════════════════════════════════════════════════════════════════════════
def _pragma(connection, name):
    return connection.execute(f"PRAGMA {name}").fetchone()[0]


class TestSqlitePragmas:

    def connect(self, tmp_path, name="t.db"):
        connection = sqlite3.connect(str(tmp_path / name), timeout=0, check_same_thread=False)  # timeout 0: only the PRAGMA's busy_timeout can make it wait
        rt.configure_sqlite_connection(connection)
        return connection

    def test_every_connection_gets_wal_a_busy_timeout_foreign_keys_and_full_durability(self, tmp_path):
        connection = self.connect(tmp_path)
        assert str(_pragma(connection, "journal_mode")).lower() == "wal"
        assert _pragma(connection, "busy_timeout") == rt.SQLITE_BUSY_TIMEOUT_MS == 5000
        assert _pragma(connection, "foreign_keys") == 1
        assert _pragma(connection, "synchronous") == 2  # FULL
        connection.close()

    def test_foreign_keys_are_really_enforced(self, tmp_path):
        connection = self.connect(tmp_path)
        connection.executescript("CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));")
        connection.execute("INSERT INTO parent(id) VALUES (1)")
        connection.execute("INSERT INTO child(parent_id) VALUES (1)")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute("INSERT INTO child(parent_id) VALUES (999)")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute("DELETE FROM parent WHERE id = 1")
        connection.close()

    def test_a_second_writer_waits_for_the_first_instead_of_failing_at_once(self, tmp_path):
        first = self.connect(tmp_path)
        first.execute("CREATE TABLE t(x)")
        first.commit()
        second = self.connect(tmp_path)
        first.execute("BEGIN IMMEDIATE")
        first.execute("INSERT INTO t VALUES (1)")
        threading.Timer(0.4, first.commit).start()
        started = time.monotonic()
        second.execute("INSERT INTO t VALUES (2)")  # blocked until the first commits, well inside the 5 s timeout
        second.commit()
        assert 0.25 < time.monotonic() - started < 4
        assert sorted(r[0] for r in first.execute("SELECT x FROM t")) == [1, 2]
        first.close()
        second.close()

    def test_readers_are_not_blocked_by_a_writer_in_wal_mode(self, tmp_path):
        writer = self.connect(tmp_path)
        writer.execute("CREATE TABLE t(x)")
        writer.execute("INSERT INTO t VALUES (1)")
        writer.commit()
        reader = self.connect(tmp_path)
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO t VALUES (2)")
        assert [r[0] for r in reader.execute("SELECT x FROM t")] == [1]  # sees the last committed state, does not wait
        writer.rollback()
        writer.close()
        reader.close()

    def test_sqlalchemy_engines_get_the_same_settings(self, tmp_path):
        from sqlalchemy import create_engine, text
        engine = create_engine(rt.sqlite_url(tmp_path / "sa.db"))
        rt.install_sqlite_pragmas(engine)
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert str(connection.execute(text("PRAGMA journal_mode")).scalar()).lower() == "wal"
            assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000
        engine.dispose()

    def test_other_databases_are_left_alone(self):
        from sqlalchemy import create_engine
        engine = create_engine("sqlite://")  # in memory: the hook is harmless
        rt.install_sqlite_pragmas(engine)
        with engine.connect():
            pass


# ══════════════════════════════════════════════════════════════════════════════
# ACLs (Windows)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def acl_dir(tmp_path):
    folder = tmp_path / "acl-test"
    folder.mkdir()
    yield folder
    subprocess.run(["icacls", str(folder), "/reset", "/t", "/q"], capture_output=True)  # let pytest clean up


@needs_windows
class TestAcls:

    def test_a_restricted_folder_has_no_inheritance_and_no_broad_groups(self, acl_dir):
        rt.restrict_directory(acl_dir, runtime_access="M")
        listing = subprocess.run(["icacls", str(acl_dir)], capture_output=True, text=True).stdout
        assert rt.readable_by_everyone(acl_dir) == []
        assert "(I)" not in listing, "inherited permissions were removed"
        assert "SYSTEM" in listing and "Administrators" in listing.replace("BUILTIN\\Administrators", "Administrators")
        (acl_dir / "still-writable.txt").write_text("the runtime account can still work here")

    def test_the_secrets_profile_is_read_only_for_the_runtime_account(self, acl_dir):
        sid = rt.current_user_sid()
        rt.restrict_directory(acl_dir, runtime_sid=sid, runtime_access="RX")
        listing = subprocess.run(["icacls", str(acl_dir)], capture_output=True, text=True).stdout
        user_lines = [line for line in listing.splitlines() if "(RX)" in line]
        assert user_lines and rt.readable_by_everyone(acl_dir) == []
        with pytest.raises(PermissionError):
            (acl_dir / "app-cannot-write-its-own-secrets.txt").write_text("x")

    def test_the_checker_catches_a_loose_folder(self, acl_dir):
        subprocess.run(["icacls", str(acl_dir), "/grant", "*S-1-1-0:(R)"], capture_output=True, check=True)  # Everyone
        assert rt.readable_by_everyone(acl_dir), "Everyone must be reported"

    def test_apply_acls_covers_the_root_and_tightens_the_secrets_folder(self, tmp_path):
        paths = rt.RuntimePaths(tmp_path / "NailSystem")
        paths.ensure()
        try:
            rt.apply_acls(paths)
            assert rt.readable_by_everyone(paths.root) == [] and rt.readable_by_everyone(paths.secrets_dir) == []
            assert "(RX)" in subprocess.run(["icacls", str(paths.secrets_dir)], capture_output=True, text=True).stdout
            assert "(M)" in subprocess.run(["icacls", str(paths.root)], capture_output=True, text=True).stdout
            (paths.data_dir("owner") / "owner.db").write_bytes(b"x")  # the data folders stay writable
        finally:
            subprocess.run(["icacls", str(paths.root), "/reset", "/t", "/q"], capture_output=True)

    def test_a_bad_sid_or_access_level_is_refused_before_anything_is_changed(self, acl_dir):
        with pytest.raises(rt.RuntimeConfigError):
            rt.restrict_directory(acl_dir, runtime_sid="Everyone")
        with pytest.raises(rt.RuntimeConfigError):
            rt.restrict_directory(acl_dir, runtime_access="F")


# ══════════════════════════════════════════════════════════════════════════════
# Command line
# ══════════════════════════════════════════════════════════════════════════════
class TestCommandLine:

    def test_paths_prints_the_layout_and_nothing_secret(self, tmp_path, capsys):
        assert rt.main(["paths"], {"NAILSYSTEM_HOME": str(tmp_path / "NailSystem")}) == 0
        shown = json.loads(capsys.readouterr().out)
        assert shown["owner_db"].endswith("owner.db") and shown["checkin_backups"].endswith("checkin")

    def test_init_creates_the_folders_and_a_valid_salon_json_without_overwriting(self, tmp_path, capsys):
        env = {"NAILSYSTEM_HOME": str(tmp_path / "NailSystem")}
        assert rt.main(["init", "--no-acl", "--salon-id", "cli-salon"], env) == 0
        assert "created" in capsys.readouterr().out
        paths = rt.RuntimePaths(tmp_path / "NailSystem")
        assert rt.load_salon_config(paths.salon_json).salon_id == "cli-salon" and paths.backup_dir("owner").is_dir()
        assert rt.main(["init", "--no-acl", "--salon-id", "changed"], env) == 0
        assert "left unchanged" in capsys.readouterr().out and rt.load_salon_config(paths.salon_json).salon_id == "cli-salon"

    def test_init_refuses_a_git_working_copy(self, tmp_path, capsys):
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        assert rt.main(["init", "--no-acl"], {"NAILSYSTEM_HOME": str(tmp_path / "repo" / "data")}) == 2
        assert "Git working copy" in capsys.readouterr().err

    @needs_windows
    def test_secrets_are_generated_listed_and_deleted_without_ever_printing_a_value(self, tmp_path, capsys):
        env = {"NAILSYSTEM_HOME": str(tmp_path / "NailSystem")}
        rt.main(["init", "--no-acl"], env)
        capsys.readouterr()
        assert rt.main(["secrets", "generate", "CHECKIN_INTERNAL_SERVICE_TOKEN"], env) == 0
        out = capsys.readouterr().out
        value = rt.DpapiSecrets(rt.RuntimePaths(tmp_path / "NailSystem").secrets_file).get("CHECKIN_INTERNAL_SERVICE_TOKEN")
        assert value and len(value) >= 48 and value not in out
        assert rt.main(["secrets", "list"], env) == 0
        listed = capsys.readouterr().out
        assert "CHECKIN_INTERNAL_SERVICE_TOKEN" in listed and value not in listed
        assert rt.main(["secrets", "delete", "CHECKIN_INTERNAL_SERVICE_TOKEN"], env) == 0
        assert "deleted" in capsys.readouterr().out

    def test_a_secrets_command_without_a_name_is_a_clean_error(self, tmp_path, capsys):
        env = {"NAILSYSTEM_HOME": str(tmp_path / "NailSystem")}
        assert rt.main(["secrets", "set"], env) == 2
        assert "NAME" in capsys.readouterr().err

    def test_a_missing_location_is_a_clean_error(self, capsys):
        assert rt.main(["paths"], {"NAILSYSTEM_MODE": "product"}) == 2
        assert "PROGRAMDATA" in capsys.readouterr().err

    @needs_windows
    def test_the_installed_layout_works_end_to_end_through_the_command_line(self, tmp_path, capsys):
        env = {"NAILSYSTEM_HOME": str(tmp_path / "NailSystem")}
        rt.main(["init", "--no-acl"], env)
        rt.main(["secrets", "generate", "CHECKIN_INTERNAL_SERVICE_TOKEN"], env)
        capsys.readouterr()
        app_env = {"NAILSYSTEM_MODE": "product", **env}
        context = rt.bootstrap("owner", app_env)
        assert app_env["CHECKIN_INTERNAL_SERVICE_TOKEN"] and context.sources["CHECKIN_INTERNAL_SERVICE_TOKEN"] == "secrets store"
        assert not os.path.exists(os.path.join("C:\\", "ProgramData", "NailSystem", "tests-were-here"))


class TestCheckCommand:
    """`check` is what the launcher runs in a child process before starting an app: names and sources only."""

    def run_check(self, app, env, capsys):
        code = rt.main(["check", "--app", app], env)
        return code, json.loads(capsys.readouterr().out)

    @needs_windows
    def test_an_installed_layout_that_would_start_passes_and_prints_no_value(self, tmp_path, capsys):
        home, _ = make_layout(tmp_path, extra_secrets={"OPENAI_API_KEY": "openai-value-123456"})
        env = product_env(home)
        code, report = self.run_check("owner", env, capsys)
        assert code == 0 and report["ok"] is True and report["mode"] == "product" and not report["problems"]
        assert report["secrets_present"] == ["CHECKIN_INTERNAL_SERVICE_TOKEN", "OPENAI_API_KEY"] and report["settings"]["DATABASE_URL"] == "installed layout"
        assert TOKEN not in json.dumps(report) and "openai-value-123456" not in json.dumps(report)

    @needs_windows
    def test_it_does_not_change_the_real_environment(self, tmp_path, capsys):
        home, _ = make_layout(tmp_path)
        env = product_env(home)
        before = dict(env)
        self.run_check("checkin", env, capsys)
        assert env == before, "the check works on a copy"

    @needs_windows
    def test_a_missing_required_secret_is_reported_by_name_with_exit_code_2(self, tmp_path, capsys):
        home, _ = make_layout(tmp_path, token=None)
        code, report = self.run_check("owner", product_env(home, CHECKIN_INTERNAL_SERVICE_TOKEN="stale-dev-token-123456"), capsys)
        assert code == 2 and report["ok"] is False and "CHECKIN_INTERNAL_SERVICE_TOKEN" in report["problems"][0]
        assert "stale-dev-token" not in json.dumps(report)

    def test_a_missing_or_bad_salon_json_is_reported_as_a_problem(self, tmp_path, capsys):
        home = tmp_path / "NailSystem"
        code, report = self.run_check("owner", product_env(home), capsys)
        assert code == 2 and "salon.json was not found" in report["problems"][0] and report["mode"] == "product"

    def test_a_bad_mode_is_reported_not_raised(self, capsys):
        code, report = self.run_check("owner", {"NAILSYSTEM_MODE": "nonsense"}, capsys)
        assert code == 2 and "not valid" in report["problems"][0]

    def test_development_without_a_token_passes_with_a_warning(self, capsys):
        code, report = self.run_check("checkin", {}, capsys)
        assert code == 0 and report["mode"] == "development" and any("CHECKIN_INTERNAL_SERVICE_TOKEN" in w for w in report["warnings"])

    def test_development_with_a_token_has_no_warning_and_no_value_in_the_report(self, capsys):
        code, report = self.run_check("owner", {"CHECKIN_INTERNAL_SERVICE_TOKEN": "dev-token-123456789"}, capsys)
        assert code == 0 and not report["warnings"] and report["secrets_present"] == ["CHECKIN_INTERNAL_SERVICE_TOKEN"]
        assert "dev-token-123456789" not in json.dumps(report)

    def test_development_does_not_create_any_folder(self, tmp_path, capsys):
        home = tmp_path / "opt-in"
        self.run_check("owner", {"NAILSYSTEM_HOME": str(home), "CHECKIN_INTERNAL_SERVICE_TOKEN": "dev-token-123456789"}, capsys)
        assert not home.exists()
