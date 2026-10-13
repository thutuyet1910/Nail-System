"""LAN proof of concept guards.

The tablet reaches the Check-In kiosk through a Caddy reverse proxy on the salon PC. These tests keep three
things in step so nobody can widen the exposure by accident:

    frontend/script.js  <->  deploy/lan-poc/README.md allowlist table  <->  deploy/lan-poc/Caddyfile

and they pin the small cross-app contract that must survive in both repositories (see TestOwnerContract).
"""

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from . import owner_catalog, schemas
from .main import app
from .security import INTERNAL_TOKEN_HEADER
from .test_main import TestingSessionLocal, checkin, client, fake_emails, register, reset_db  # noqa: F401  (autouse fixtures come from test_main)

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
CADDYFILE = ROOT / "deploy" / "lan-poc" / "Caddyfile"
POC_README = ROOT / "deploy" / "lan-poc" / "README.md"

# The single source of truth for what a tablet may call. The README table and the Caddyfile must match it.
KIOSK_ALLOWLIST = {
    ("GET", "/services"),
    ("GET", "/queue-status"),
    ("GET", "/customers/by-phone/{phone}"),
    ("GET", "/customers/check-in-status/{phone}"),
    ("POST", "/customers/new"),
    ("POST", "/customers/check-in/{phone}"),
    ("POST", "/referrals/validate"),
    ("POST", "/referrals/apply"),
    ("PATCH", "/customers/{phone}/profile"),
}
KIOSK_ASSETS = {"index.html", "config.js", "script.js", "style.css", "translations.js"}


def _normalise(route: str) -> str:
    """/customers/{phone_number}/profile and /customers/${encodeURIComponent(phone)}/profile -> /customers/{}/profile"""
    route = re.sub(r"\$\{[^}]*\}", "{}", route)
    return re.sub(r"\{[^}]*\}", "{}", route)


def _block(text: str, header: str) -> str:
    """The brace-balanced body of the first block that starts with `header` (e.g. 'http://:8080')."""
    start = text.index(header)
    open_at = text.index("{", start)
    depth = 0
    for index in range(open_at, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:index]
    raise AssertionError(f"unbalanced block after {header}")


def _caddy_kiosk_matchers() -> list[tuple[str, re.Pattern]]:
    text = CADDYFILE.read_text(encoding="utf-8")
    found = re.findall(r"@kiosk_\w+\s*\{\s*method\s+(\w+)\s+path_regexp\s+(\S+)\s*\}", text)
    assert found, "no kiosk matchers found in the Caddyfile"
    return [(method, re.compile(pattern)) for method, pattern in found]


def _caddy_allows(method: str, path: str) -> bool:
    return any(method == m and pattern.match(path) for m, pattern in _caddy_kiosk_matchers())


def _concrete(route: str) -> str:
    return re.sub(r"\{[^}]*\}", "x1", route)


class TestRelativeApiBase:

    def test_the_kiosk_calls_a_same_origin_path_and_hard_codes_no_host_or_port(self):
        config = (FRONTEND / "config.js").read_text(encoding="utf-8")
        assert re.search(r'const\s+API_BASE\s*=\s*"/api/checkin"\s*;', config)
        for name in ("script.js", "config.js", "index.html", "translations.js"):
            text = (FRONTEND / name).read_text(encoding="utf-8")
            assert not re.search(r"127\.0\.0\.1|localhost|0\.0\.0\.0", text), name
            assert not re.search(r":(8000|8001|8080|8081|5500|5501)\b", text), name
            assert not re.search(r"\b192\.168\.|\b10\.\d+\.\d+\.\d+", text), name

    def test_script_uses_the_base_and_does_not_define_its_own(self):
        script = (FRONTEND / "script.js").read_text(encoding="utf-8")
        assert not re.search(r"\b(const|let|var)\s+API_BASE\b", script)
        assert "${API_BASE}" in script
        assert not re.search(r'fetch\(\s*["\'`]https?://', script)

    def test_the_page_loads_config_before_the_script_that_uses_it(self):
        html = (FRONTEND / "index.html").read_text(encoding="utf-8")
        order = [m.group(1) for m in re.finditer(r'<script src="([^"]+)"', html)]
        assert order.index("config.js") < order.index("script.js")

    def test_no_browser_file_holds_the_internal_token_or_an_internal_route(self):
        text = "".join(p.read_text(encoding="utf-8") for p in FRONTEND.iterdir() if p.is_file())
        for needle in (INTERNAL_TOKEN_HEADER, "CHECKIN_INTERNAL_SERVICE_TOKEN", "/internal/", "OWNER_API_BASE"):
            assert needle not in text


class TestKioskAllowlist:

    def test_every_call_the_kiosk_makes_is_on_the_allowlist(self):
        script = (FRONTEND / "script.js").read_text(encoding="utf-8")
        used = set()
        used |= {m for m in re.findall(r"api\(\s*[`\"'](/[^`\"']*)[`\"']", script)}
        used |= {m for m in re.findall(r"\$\{API_BASE\}(/[^`\"'?]*)", script)}
        if "CREATE_CUSTOMER_URL" in script:
            used |= {m for m in re.findall(r"CREATE_CUSTOMER_URL\s*=\s*`\$\{API_BASE\}(/[^`]*)`", script)}
        used = {_normalise(route) for route in used}
        allowed = {_normalise(route) for _method, route in KIOSK_ALLOWLIST}
        assert used, "found no API calls in script.js: the extraction pattern is stale"
        assert used <= allowed, f"kiosk calls routes that are not allowlisted: {sorted(used - allowed)}"
        # and nothing on the list is dead weight
        assert allowed <= used, f"allowlisted but never called by the kiosk: {sorted(allowed - used)}"

    def test_the_documented_table_is_exactly_the_allowlist(self):
        text = POC_README.read_text(encoding="utf-8")
        table = text.split("<!-- kiosk-allowlist:start -->")[1].split("<!-- kiosk-allowlist:end -->")[0]
        rows = re.findall(r"^\|\s*(GET|POST|PATCH|PUT|DELETE)\s*\|\s*`([^`]+)`", table, re.M)
        assert {(method, _normalise(route)) for method, route in rows} == \
               {(method, _normalise(route)) for method, route in KIOSK_ALLOWLIST}
        assert len(rows) == len(KIOSK_ALLOWLIST), "duplicate or missing rows in the allowlist table"

    def test_the_caddyfile_forwards_exactly_the_allowlist(self):
        for method, route in KIOSK_ALLOWLIST:
            assert _caddy_allows(method, "/api/checkin" + _concrete(route)), (method, route)

    def test_every_other_checkin_route_is_refused_by_the_proxy(self):
        """Walks the real FastAPI route table, so a route added tomorrow is blocked until someone allowlists it."""
        allowed = {(method, _normalise(route)) for method, route in KIOSK_ALLOWLIST}
        checked = 0
        for route in app.routes:
            methods = getattr(route, "methods", None)
            if not methods:
                continue
            for method in methods - {"HEAD", "OPTIONS"}:
                path = "/api/checkin" + _concrete(route.path)
                permitted = (method, _normalise(route.path)) in allowed
                assert _caddy_allows(method, path) == permitted, (method, route.path)
                checked += 1
        assert checked >= 20

    @pytest.mark.parametrize("method,path", [
        ("GET", "/api/checkin/customers"),
        ("GET", "/api/checkin/customers/id/1"),
        ("GET", "/api/checkin/customers/6025550101/visits"),
        ("PATCH", "/api/checkin/customers/6025550101/update-phone"),
        ("GET", "/api/checkin/today-checkins"),
        ("GET", "/api/checkin/birthday-reminders"),
        ("POST", "/api/checkin/birthday-reminders/send"),
        ("GET", "/api/checkin/internal/customers/by-phone/6025550101"),
        ("GET", "/api/checkin/docs"),
        ("GET", "/api/checkin/openapi.json"),
        ("DELETE", "/api/checkin/customers/new"),
        ("PUT", "/api/checkin/customers/6025550101/profile"),
        ("GET", "/api/checkin/customers/by-phone/a/b"),
        ("GET", "/api/checkin/services/"),
        ("GET", "/api/checkin/../owner/services"),
    ])
    def test_dangerous_or_unrelated_routes_are_not_forwarded(self, method, path):
        assert not _caddy_allows(method, path)

    def test_the_kiosk_asset_list_is_exactly_the_files_the_page_needs(self):
        text = CADDYFILE.read_text(encoding="utf-8")
        line = re.search(r"@assets path (.+)", text).group(1)
        served = {part.lstrip("/") for part in line.split() if part != "/"}
        assert served == KIOSK_ASSETS
        for name in KIOSK_ASSETS:
            assert (FRONTEND / name).is_file(), name
        html = (FRONTEND / "index.html").read_text(encoding="utf-8")
        referenced = set(re.findall(r'(?:src|href)="([^":/]+\.(?:js|css|html))"', html))
        assert referenced <= KIOSK_ASSETS, referenced - KIOSK_ASSETS


class TestCaddyLanConfig:

    def setup_method(self):
        raw = CADDYFILE.read_text(encoding="utf-8")
        lines = [line for line in raw.splitlines() if not line.strip().startswith("#")]  # comments are not config
        self.text = chr(10).join(lines)
        self.lan = _block(self.text, "http://:8080")
        self.loopback = _block(self.text, "http://127.0.0.1:8081")

    def test_the_lan_listener_is_the_kiosk_and_nothing_else(self):
        assert "bind 0.0.0.0" in self.lan
        assert "import kiosk" in self.lan
        assert "8001" not in self.lan and "OWNER_FRONTEND_DIR" not in self.lan
        assert "reverse_proxy" not in self.lan  # proxying happens only inside the shared allowlist snippet
        assert re.search(r"handle\s*\{\s*respond 404\s*\}\s*$", self.lan.strip())  # unmatched = 404

    def test_the_lan_listener_denies_owner_internal_and_management_paths_explicitly(self):
        denied = re.search(r"@private_paths path (.+)", self.lan).group(1).split()
        for needed in ("/owner", "/owner/*", "/api/owner", "/api/owner/*", "/internal/*", "/auth/*",
                       "/settings/*", "/voice/*", "/docs"):
            assert needed in denied, needed

    def test_the_owner_listener_is_loopback_only_and_keeps_internal_routes_off_the_proxy(self):
        assert "bind 127.0.0.1" in self.loopback
        assert "OWNER_FRONTEND_DIR" in self.loopback
        assert "/api/owner/internal/*" in self.loopback and "/api/owner/voice/*" in self.loopback
        assert "0.0.0.0" not in self.loopback
        # the only place the owner backend is proxied is the loopback listener
        assert self.text.count("127.0.0.1:8001") == 1 and "127.0.0.1:8001" in self.loopback

    def test_the_two_backends_are_only_ever_proxied_on_loopback(self):
        assert set(re.findall(r"reverse_proxy\s+(\S+)", self.text)) == {"127.0.0.1:8000", "127.0.0.1:8001"}

    def test_no_wildcard_cors_no_admin_api_no_access_log_no_secret(self):
        assert "Access-Control-Allow-Origin" not in self.text
        assert re.search(r"^\s*admin off\s*$", self.text, re.M)
        assert not re.search(r"^\s*log\b", self.text, re.M), "an access log would record customer phone numbers"
        assert "header_up -X-Internal-Service-Token" in self.text
        assert not re.search(r"X-Internal-Service-Token +\S{8,}", self.text)  # never sets the token, only strips it
        assert "test-internal-token" not in self.text

    def test_requests_are_size_limited_and_https_redirects_are_off_for_the_plain_http_poc(self):
        assert re.search(r"max_size\s+64KB", self.text)
        assert "auto_https off" in self.text

    def test_the_poc_documents_how_to_run_it_without_exposing_the_backends(self):
        doc = POC_README.read_text(encoding="utf-8")
        assert doc.count("--host 127.0.0.1") >= 2 and "--host 0.0.0.0" not in doc
        assert "-LocalPort 8080" in doc
        assert not re.search(r"-LocalPort\s+(8000|8001|8081)", doc)
        assert "Remove-NetFirewallRule" in doc


class TestOwnerContract:
    """What Check-In relies on from the Owner (GET /internal/services) and promises back (service_ids)."""

    def test_the_internal_token_header_name_is_the_agreed_one(self):
        assert INTERNAL_TOKEN_HEADER == "X-Internal-Service-Token"

    def test_the_client_accepts_exactly_the_agreed_fields_and_tolerates_extras(self):
        row = {"id": 10, "name": " Gel Manicure ", "category": "Nails", "duration_minutes": 45, "is_active": True,
               "price": 40, "admin_note": "ignored"}
        parsed = owner_catalog.parse_catalog([row])
        assert [(s.id, s.name, s.category, s.duration_minutes) for s in parsed] == [(10, "Gel Manicure", "Nails", 45)]
        assert set(owner_catalog.CatalogService.__dataclass_fields__) == {"id", "name", "category", "duration_minutes"}

    def test_a_missing_is_active_means_active_and_an_inactive_service_is_never_offered(self):
        parsed = owner_catalog.parse_catalog([
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B", "is_active": False},
        ])
        assert [s.id for s in parsed] == [1]

    @pytest.mark.parametrize("bad", [
        [{"id": True, "name": "x"}],
        [{"id": 0, "name": "x"}],
        [{"id": -3, "name": "x"}],
        [{"id": "7", "name": "x"}],
        [{"id": 1.5, "name": "x"}],
        [{"id": 1, "name": "   "}],
        [{"id": 1, "name": "x", "duration_minutes": "45"}],
        [{"id": 1, "name": "x"}, {"id": 1, "name": "y"}],
        {"id": 1},
    ])
    def test_a_malformed_catalog_is_rejected_as_a_whole(self, bad):
        with pytest.raises(ValueError):
            owner_catalog.parse_catalog(bad)

    def test_a_visit_may_name_at_most_twenty_services(self):
        assert schemas.MAX_SERVICES_PER_VISIT == 20
        schemas.CheckInCreate(selected_service_ids=list(range(1, 21)))
        with pytest.raises(ValueError):
            schemas.CheckInCreate(selected_service_ids=list(range(1, 22)))

    def test_duplicates_collapse_before_the_limit_is_applied(self):
        assert schemas.CheckInCreate(selected_service_ids=[5] * 30 + [6]).selected_service_ids == [5, 6]

    @pytest.mark.parametrize("payload", [{}, {"selected_service_ids": None}, {"selected_service_ids": []},
                                         {"selected_service_ids": [0, -1]}, {"selected_service_ids": ["a"]},
                                         {"selected_service_ids": "10"}])
    def test_a_new_check_in_without_valid_service_ids_is_rejected_never_guessed(self, payload):
        register("5550000011", "Zed", "1990-03-15")
        assert client.post("/customers/check-in/5550000011", json=payload).status_code == 422

    def test_a_new_check_in_reaches_the_owner_queue_with_ids_in_order(self):
        register("5550000012", "Yan", "1990-03-15")
        assert checkin("5550000012", [12, 10]).status_code == 200
        item = client.get("/today-checkins", headers={INTERNAL_TOKEN_HEADER: "test-internal-token"}).json()["checkins"][0]
        assert item["service_ids"] == [12, 10]

    def test_the_owner_queue_endpoint_requires_the_internal_token(self):
        anonymous = TestClient(app)  # the shared test client already carries the token
        assert anonymous.get("/today-checkins").status_code == 401
        assert anonymous.get("/today-checkins", headers={INTERNAL_TOKEN_HEADER: "wrong"}).status_code == 401
        assert anonymous.get("/today-checkins", headers={INTERNAL_TOKEN_HEADER: "test-internal-token"}).status_code == 200

    def test_a_deactivated_service_is_refused_at_check_in_and_is_not_replaced_by_name(self, owner):
        register("5550000013", "Xi", "1990-03-15")
        client.get("/services")
        owner.deactivate(10)
        owner.advance(6)
        response = checkin("5550000013", [10])
        assert response.status_code == 404
        assert client.get("/today-checkins", headers={INTERNAL_TOKEN_HEADER: "test-internal-token"}).json()["checkins"] == []
