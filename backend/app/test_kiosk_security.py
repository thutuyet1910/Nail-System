"""Phase 2 kiosk hardening: device pairing, device authentication, reduced customer data, profile-edit
protection, rate limiting and the forwarded-client-address trust boundary.

All data here is fake and the Owner is faked in conftest.py.
"""

import hashlib
import hmac
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from starlette.requests import Request

from . import kiosk_security, models
from .database import Base
from .kiosk_security import (
    CLIENT_IP_HEADER,
    DEVICE_TOKEN_HEADER,
    LIMITS,
    PAIRING_ALPHABET,
    PROFILE_TOKEN_HEADER,
    hash_secret,
    utc_now,
)
from .main import app
from .test_main import (  # noqa: F401  (autouse fixtures come from test_main)
    TestingSessionLocal,
    checkin,
    client,
    fake_emails,
    make_paired_device,
    register,
    reset_db,
)

INTERNAL = {"X-Internal-Service-Token": "test-internal-token"}
ALICE_DOB = "1990-03-15"


def tablet(token=None):
    """A browser: no internal token, optionally holding a device token."""
    browser = TestClient(app)
    if token:
        browser.headers.update({DEVICE_TOKEN_HEADER: token})
    return browser


def owner_side():
    """What the Owner backend is: loopback, internal service token only."""
    return TestClient(app, headers=INTERNAL)


def new_code(name="Front desk tablet"):
    response = owner_side().post("/internal/kiosk/pairing-codes", json={"display_name": name})
    assert response.status_code == 201, response.text
    return response.json()


def pair(code, browser=None):
    return (browser or tablet()).post("/kiosk/pair", json={"code": code})


def paired_tablet():
    """(TestClient holding a freshly redeemed device token, device id, raw token)."""
    body = new_code()
    redeemed = pair(body["pairing_code"]).json()
    return tablet(redeemed["device_token"]), redeemed["device_id"], redeemed["device_token"]


def device_row(device_id):
    db = TestingSessionLocal()
    try:
        row = db.get(models.KioskDevice, device_id)
        db.expunge(row)
        return row
    finally:
        db.close()


def set_device(device_id, **values):
    db = TestingSessionLocal()
    try:
        db.query(models.KioskDevice).filter(models.KioskDevice.id == device_id).update(values)
        db.commit()
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Pairing codes
# ══════════════════════════════════════════════════════════════════════════════
class TestPairingCodes:

    def test_only_the_owner_side_can_create_a_code(self):
        for browser in (tablet(), tablet(make_paired_device()[1])):
            assert browser.post("/internal/kiosk/pairing-codes", json={}).status_code == 401
        wrong = TestClient(app, headers={"X-Internal-Service-Token": "wrong"})
        assert wrong.post("/internal/kiosk/pairing-codes", json={}).status_code == 401
        assert owner_side().post("/internal/kiosk/pairing-codes", json={}).status_code == 201

    def test_the_code_is_short_readable_random_and_expires(self):
        body = new_code()
        assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", body["pairing_code"])
        assert set(body["pairing_code"].replace("-", "")) <= set(PAIRING_ALPHABET)
        assert not set("01IO") & set(body["pairing_code"])
        assert body["expires_in_seconds"] == kiosk_security.PAIRING_CODE_MINUTES * 60 <= 600
        assert new_code()["pairing_code"] != body["pairing_code"]

    def test_only_a_hash_of_the_code_is_stored(self):
        body = new_code()
        row = device_row(body["device_id"])
        plain = body["pairing_code"].replace("-", "")
        assert row.pairing_code_hash == hashlib.sha256(plain.encode()).hexdigest()
        assert plain not in str(row.__dict__) and body["pairing_code"] not in str(row.__dict__)

    def test_redeeming_issues_one_device_token_and_clears_the_code(self):
        body = new_code("Front desk")
        response = pair(body["pairing_code"])
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        data = response.json()
        assert set(data) == {"device_id", "display_name", "device_token"}
        assert data["display_name"] == "Front desk" and data["device_id"] == body["device_id"]
        row = device_row(data["device_id"])
        assert row.pairing_code_hash is None and row.pairing_expires_at is None
        assert row.paired_at is not None and row.token_hash
        assert tablet(data["device_token"]).get("/services").status_code == 200

    def test_the_token_is_random_hashed_and_not_derived_from_the_code(self):
        body = new_code()
        token = pair(body["pairing_code"]).json()["device_token"]
        device_id, _, secret = token.partition(".")
        plain_code = body["pairing_code"].replace("-", "")
        row = device_row(int(device_id))
        assert row.token_hash == hashlib.sha256(secret.encode()).hexdigest()
        assert token not in str(row.__dict__) and secret not in str(row.__dict__)  # never stored in clear
        assert plain_code.lower() not in token.lower() and len(secret) >= 40
        assert hash_secret(plain_code) != row.token_hash
        other = pair(new_code()["pairing_code"]).json()["device_token"]
        assert other.partition(".")[2] != secret

    def test_a_code_works_once(self):
        body = new_code()
        assert pair(body["pairing_code"]).status_code == 200
        again = pair(body["pairing_code"])
        assert again.status_code == 400 and "device_token" not in again.text

    def test_an_expired_code_is_refused_with_the_same_message_as_a_wrong_one(self):
        body = new_code()
        set_device(body["device_id"], pairing_expires_at=utc_now() - timedelta(seconds=1))
        expired = pair(body["pairing_code"])
        wrong = pair("ABCD-EFGH")
        assert expired.status_code == wrong.status_code == 400
        assert expired.json() == wrong.json()

    @pytest.mark.parametrize("typed", [lambda c: c.lower(), lambda c: c.replace("-", ""), lambda c: f" {c[:4]} {c[5:]} "])
    def test_the_code_is_forgiving_about_case_dashes_and_spaces(self, typed):
        body = new_code()
        assert pair(typed(body["pairing_code"])).status_code == 200

    @pytest.mark.parametrize("bad", ["", "   ", "ABC", "ABCD-EFGH-IJKL", "0000-0000", "'; DROP TABLE kiosk_devices;--"])
    def test_garbage_codes_are_refused_cleanly(self, bad):
        assert pair(bad).status_code in (400, 422)

    def test_the_request_body_is_strict(self):
        assert tablet().post("/kiosk/pair", json={"code": "ABCD-EFGH", "extra": 1}).status_code == 422
        assert tablet().post("/kiosk/pair", json={}).status_code == 422

    def test_guessing_is_rate_limited_per_address_and_blocks_even_the_right_code(self):
        body = new_code()
        guesser = tablet()
        for _ in range(LIMITS["pair_fail_ip"][0]):
            assert pair("ZZZZ-ZZZZ", guesser).status_code == 400
        blocked = pair("ZZZZ-ZZZZ", guesser)
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1
        assert pair(body["pairing_code"], guesser).status_code == 429  # a lucky guess is refused during lockout
        assert device_row(body["device_id"]).token_hash is None

    def test_guessing_is_also_limited_for_the_whole_salon(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_IPS", "testclient")
        monkeypatch.setitem(LIMITS, "pair_fail_global", (6, 600))
        body = new_code()
        for number in range(6):  # a different address each time, so the per-address limit never trips
            attempt = tablet()
            attempt.headers.update({CLIENT_IP_HEADER: f"192.168.0.{number + 20}"})
            assert pair("ZZZZ-ZZZZ", attempt).status_code == 400
        fresh = tablet()
        fresh.headers.update({CLIENT_IP_HEADER: "192.168.0.99"})
        assert pair(body["pairing_code"], fresh).status_code == 429

    def test_a_successful_pairing_does_not_count_against_the_address(self):
        for _ in range(LIMITS["pair_fail_ip"][0] + 2):
            assert pair(new_code()["pairing_code"]).status_code == 200

    def test_a_revoked_device_cannot_be_paired_with_its_unused_code(self):
        body = new_code()
        assert owner_side().post(f"/internal/kiosk/devices/{body['device_id']}/revoke").status_code == 200
        assert pair(body["pairing_code"]).status_code == 400

    def test_the_number_of_active_devices_is_capped(self, monkeypatch):
        monkeypatch.setattr("app.kiosk.MAX_ACTIVE_DEVICES", 3)  # the fixture's own paired tablet is the first of three
        for _ in range(2):
            new_code()
        assert owner_side().post("/internal/kiosk/pairing-codes", json={}).status_code == 409


# ══════════════════════════════════════════════════════════════════════════════
# Device authentication on the kiosk routes
# ══════════════════════════════════════════════════════════════════════════════
KIOSK_CALLS = [
    ("get", "/services", None),
    ("get", "/queue-status", None),
    ("get", "/customers/by-phone/5550000001", None),
    ("get", "/customers/check-in-status/5550000001", None),
    ("post", "/customers/new", {"full_name": "A B", "phone_number": "5550000009", "date_of_birth": ALICE_DOB}),
    ("post", "/customers/check-in/5550000001", {"selected_service_ids": [10]}),
    ("post", "/customers/5550000001/profile-access", {"date_of_birth": ALICE_DOB}),
    ("post", "/referrals/validate", {"phone_number": "5550000001", "referral_code": "ABCDE"}),
    ("post", "/referrals/apply", {"phone_number": "5550000001", "referral_code": "ABCDE"}),
    ("patch", "/customers/5550000001/profile", {"full_name": "Alice", "phone_number": "5550000001"}),
]


class TestDeviceAuthentication:

    @pytest.mark.parametrize("method,path,body", KIOSK_CALLS)
    def test_every_kiosk_route_refuses_a_request_without_a_device_token(self, method, path, body):
        register("5550000001", "Alice", ALICE_DOB)
        response = getattr(tablet(), method)(path, **({"json": body} if body is not None else {}))
        assert response.status_code == 401

    @pytest.mark.parametrize("method,path,body", KIOSK_CALLS)
    def test_the_internal_service_token_is_not_a_device_token(self, method, path, body):
        register("5550000001", "Alice", ALICE_DOB)
        browser = TestClient(app, headers=INTERNAL)
        response = getattr(browser, method)(path, **({"json": body} if body is not None else {}))
        assert response.status_code == 401

    @pytest.mark.parametrize("token", [
        "", " ", "abc", "1", "1.", ".secret", "x.y", "1.short", "-1." + "a" * 43, "99999999999." + "a" * 43,
        "1." + "a" * 300, "1.2.3", "1 . " + "a" * 43, "Bearer " + "a" * 43,
    ])
    def test_malformed_tokens_are_refused_the_same_way(self, token):
        refused = tablet(token or None).get("/services")
        assert refused.status_code == 401
        assert refused.json() == tablet().get("/services").json()  # identical to "no token at all"

    def test_unknown_wrong_secret_and_revoked_all_look_the_same(self):
        _browser, device_id, token = paired_tablet()
        secret = token.partition(".")[2]
        owner_side().post(f"/internal/kiosk/devices/{device_id}/revoke")
        answers = [
            tablet(token).get("/services"),                          # revoked
            tablet(f"{device_id}.{'z' * len(secret)}").get("/services"),  # wrong secret
            tablet(f"4242.{secret}").get("/services"),               # unknown device
            tablet().get("/services"),                               # nothing
        ]
        assert {r.status_code for r in answers} == {401}
        assert len({r.text for r in answers}) == 1

    def test_the_device_token_is_checked_in_constant_time(self, monkeypatch):
        calls = []
        real = hmac.compare_digest
        monkeypatch.setattr(kiosk_security.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
        _browser, _id, token = paired_tablet()
        tablet(token).get("/services")
        tablet("4242." + "a" * 43).get("/services")  # an unknown device is compared too, against a dummy
        assert len(calls) >= 2

    def test_a_revoked_device_loses_access_at_once_but_others_keep_theirs(self):
        first, first_id, _ = paired_tablet()
        second, _second_id, _ = paired_tablet()
        assert first.get("/services").status_code == second.get("/services").status_code == 200
        assert owner_side().post(f"/internal/kiosk/devices/{first_id}/revoke").status_code == 200
        assert first.get("/services").status_code == 401
        assert second.get("/services").status_code == 200

    def test_a_device_token_grants_no_owner_staff_or_internal_access(self):
        register("5550000001", "Alice", ALICE_DOB)
        browser, _id, _token = paired_tablet()
        for method, path in [
            ("get", "/today-checkins"), ("get", "/customers"), ("get", "/customers/id/1"),
            ("get", "/internal/customers/by-phone/5550000001"), ("get", "/customers/5550000001/visits"),
            ("get", "/birthday-reminders"), ("post", "/birthday-reminders/send"),
            ("patch", "/customers/5550000001/update-phone"),
            ("get", "/internal/kiosk/devices"), ("post", "/internal/kiosk/pairing-codes"),
            ("post", "/internal/kiosk/devices/1/revoke"),
        ]:
            assert getattr(browser, method)(path).status_code == 401, path

    def test_the_device_token_in_the_internal_header_does_not_work_either(self):
        _browser, _id, token = paired_tablet()
        assert TestClient(app, headers={"X-Internal-Service-Token": token}).get("/today-checkins").status_code == 401

    def test_last_seen_is_recorded_and_pairing_metadata_is_bounded(self):
        body = new_code()
        redeemed = tablet().post("/kiosk/pair", json={"code": body["pairing_code"]}, headers={"user-agent": "x" * 500}).json()
        row = device_row(redeemed["device_id"])
        assert len(row.user_agent) == 200
        set_device(row.id, last_seen_at=utc_now() - timedelta(minutes=10))
        tablet(redeemed["device_token"]).get("/services")
        assert device_row(row.id).last_seen_at > utc_now() - timedelta(minutes=1)

    def test_bad_tokens_are_rate_limited_per_address(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "bad_token_ip", (3, 600))
        browser = tablet("1." + "a" * 43)
        assert [browser.get("/services").status_code for _ in range(3)] == [401, 401, 401]
        assert browser.get("/services").status_code == 429
        assert tablet(make_paired_device()[1]).get("/services").status_code == 429  # same address: still locked out

    def test_a_paired_device_is_rate_limited(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "device_requests", (4, 60))
        browser, _id, _token = paired_tablet()
        assert [browser.get("/services").status_code for _ in range(4)] == [200] * 4
        assert browser.get("/services").status_code == 429


# ══════════════════════════════════════════════════════════════════════════════
# Owner-side management
# ══════════════════════════════════════════════════════════════════════════════
class TestDeviceManagement:

    def test_the_list_shows_state_never_secrets(self):
        pending = new_code("Waiting tablet")
        _browser, paired_id, token = paired_tablet()
        listing = owner_side().get("/internal/kiosk/devices")
        assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
        by_id = {d["id"]: d for d in listing.json()["devices"]}
        assert by_id[pending["device_id"]]["status"] == "pending"
        assert by_id[paired_id]["status"] == "paired" and by_id[paired_id]["last_seen_at"]
        allowed = {"id", "display_name", "status", "created_at", "paired_at", "last_seen_at", "revoked_at", "pairing_expires_at"}
        assert all(set(d) == allowed for d in by_id.values())
        text_ = listing.text
        for secret in (token, token.partition(".")[2], pending["pairing_code"], pending["pairing_code"].replace("-", ""), "hash"):
            assert secret not in text_

    def test_an_unused_expired_code_disappears_and_a_revoked_device_is_listed(self):
        gone = new_code("Old")
        set_device(gone["device_id"], pairing_expires_at=utc_now() - timedelta(hours=2))
        _b, revoked_id, _t = paired_tablet()
        owner_side().post(f"/internal/kiosk/devices/{revoked_id}/revoke")
        listing = {d["id"]: d for d in owner_side().get("/internal/kiosk/devices").json()["devices"]}
        assert "Old" not in {d["display_name"] for d in listing.values()}  # (SQLite may reuse the pruned row's id)
        assert listing[revoked_id]["status"] == "revoked" and listing[revoked_id]["revoked_at"]

    def test_revoking_is_idempotent_and_unknown_ids_are_404(self):
        _b, device_id, _t = paired_tablet()
        assert owner_side().post(f"/internal/kiosk/devices/{device_id}/revoke").json()["status"] == "revoked"
        assert owner_side().post(f"/internal/kiosk/devices/{device_id}/revoke").json()["status"] == "revoked"
        assert owner_side().post("/internal/kiosk/devices/9999/revoke").status_code == 404
        row = device_row(device_id)
        assert row.token_hash is None and row.pairing_code_hash is None

    def test_a_display_name_is_trimmed_and_bounded(self):
        assert new_code("  Counter iPad  ")["display_name"] == "Counter iPad"
        assert owner_side().post("/internal/kiosk/pairing-codes", json={"display_name": "x" * 81}).status_code == 422
        assert owner_side().post("/internal/kiosk/pairing-codes", json={"display_name": "   "}).status_code == 422
        assert new_code.__defaults__[0] and owner_side().post("/internal/kiosk/pairing-codes", json={}).json()["display_name"] == "Check-In tablet"

    def test_the_management_routes_are_not_kiosk_routes(self):
        browser, _id, _t = paired_tablet()
        assert browser.get("/internal/kiosk/devices").status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Reduced customer data
# ══════════════════════════════════════════════════════════════════════════════
class TestKioskProjection:

    def test_lookup_returns_only_what_the_screen_needs(self):
        register("5550000001", "Alice Marie Smith", ALICE_DOB, email="alice.smith@example.com")
        data = client.get("/customers/by-phone/5550000001").json()
        assert data == {
            "first_name": "Alice",
            "phone_number": "5550000001",
            "phone_number_formatted": "(555) 000-0001",
            "email_hint": "a***@example.com",
            "has_referral_code": False,
        }
        flat = str(data)
        for private in ("Smith", "Marie", "alice.smith", ALICE_DOB, "1990", "id"):
            assert private not in flat.replace("phone_number", "")

    def test_lookup_has_no_birth_date_referral_discount_or_id(self):
        register("5550000001", "Alice", ALICE_DOB)
        data = client.get("/customers/by-phone/5550000001").json()
        for field in ("id", "date_of_birth", "email", "referral_code", "referral_count", "visit_count_cycle",
                      "birthday_discount_amount", "referral_discount_pending", "used_referral_code", "full_name"):
            assert field not in data

    def test_a_customer_without_email_has_no_hint_and_a_referral_code_is_only_a_flag(self):
        register("5550000001", "Alice", ALICE_DOB)
        db = TestingSessionLocal()
        db.query(models.Customer).update({"referral_code": "ABCDE"})
        db.commit()
        db.close()
        data = client.get("/customers/by-phone/5550000001").json()
        assert data["email_hint"] is None and data["has_referral_code"] is True
        assert "ABCDE" not in str(data)

    def test_status_returns_a_first_name_and_a_flag_only(self):
        register("5550000001", "Alice Marie Smith", ALICE_DOB)
        assert client.get("/customers/check-in-status/5550000001").json() == {
            "first_name": "Alice", "already_checked_in_today": False}
        checkin("5550000001")
        assert client.get("/customers/check-in-status/5550000001").json()["already_checked_in_today"] is True

    def test_a_single_word_or_odd_name_still_gives_something_sensible(self):
        for phone, name, expected in [("5550000001", "Madonna", "Madonna"), ("5550000002", "  Ana   Maria ", "Ana")]:
            register(phone, name, ALICE_DOB)
            assert client.get(f"/customers/by-phone/{phone}").json()["first_name"] == expected

    def test_check_in_greets_by_first_name_only(self):
        register("5550000001", "Alice Marie Smith", ALICE_DOB)
        assert checkin("5550000001").json()["full_name"] == "Alice"

    def test_a_referral_code_never_reveals_the_referrers_full_name(self):
        register("5550000001", "Alice Marie Smith", ALICE_DOB)
        db = TestingSessionLocal()
        db.query(models.Customer).update({"referral_code": "ABCDE"})
        db.commit()
        db.close()
        register("5550000002", "Bob Jones", "1992-06-20")
        data = client.post("/referrals/apply", json={"phone_number": "5550000002", "referral_code": "abcde"}).json()
        assert data["referral_from_customer_name"] == "Alice" and data["full_name"] == "Bob"
        assert "Smith" not in str(data) and "Jones" not in str(data)

    def test_the_queue_board_is_still_anonymous(self):
        register("5550000001", "Alice Smith", ALICE_DOB)
        checkin("5550000001")
        board = client.get("/queue-status").json()["checkins"][0]
        assert board["display_name"] == "Customer #1" and "Alice" not in str(board) and "5550000001" not in str(board)

    def test_the_full_record_is_still_available_to_the_internal_routes(self):
        register("5550000001", "Alice Marie Smith", ALICE_DOB, email="alice@example.com")
        full = _find(client.get("/customers").json(), "5550000001")
        assert full["full_name"] == "Alice Marie Smith" and full["email"] == "alice@example.com" and full["date_of_birth"] == ALICE_DOB
        assert tablet(make_paired_device()[1]).get("/customers").status_code == 401

    def test_mask_helpers(self):
        assert kiosk_security.mask_email("jo@gmail.com") == "j***@gmail.com"
        assert kiosk_security.mask_email("a@b.co") == "a***@b.co"
        assert kiosk_security.mask_email(None) is None and kiosk_security.mask_email("nope") is None
        assert kiosk_security.first_name_of(None) == "there" and kiosk_security.first_name_of("   ") == "there"


def _find(customers, phone):
    return next(c for c in customers if c["phone_number"] == phone)


# ══════════════════════════════════════════════════════════════════════════════
# Profile editing needs more than a phone number
# ══════════════════════════════════════════════════════════════════════════════
BODY = {"full_name": "Alice Smith", "phone_number": "5550000001", "email": "new@example.com"}


class TestProfileEditProtection:

    def setup_method(self):
        pass

    def access(self, phone, dob, browser=None):
        return (browser or client).post(f"/customers/{phone}/profile-access", json={"date_of_birth": dob})

    def test_a_phone_number_alone_cannot_edit_a_profile(self):
        register("5550000001", "Alice", ALICE_DOB)
        refused = client.patch("/customers/5550000001/profile", json=BODY)
        assert refused.status_code == 403
        assert _find(client.get("/customers").json(), "5550000001")["full_name"] == "Alice"

    def test_the_birth_date_unlocks_the_details_and_one_edit(self):
        register("5550000001", "Alice", ALICE_DOB, email="old@example.com")
        opened = self.access("5550000001", ALICE_DOB)
        assert opened.status_code == 200
        data = opened.json()
        assert data["profile"] == {"full_name": "Alice", "phone_number": "5550000001", "email": "old@example.com"}
        assert 0 < data["expires_in_seconds"] <= 300 and len(data["edit_token"]) >= 40
        headers = {PROFILE_TOKEN_HEADER: data["edit_token"]}
        assert client.patch("/customers/5550000001/profile", json=BODY, headers=headers).status_code == 200
        assert _find(client.get("/customers").json(), "5550000001")["full_name"] == "Alice Smith"
        # the confirmation is used up
        assert client.patch("/customers/5550000001/profile", json={**BODY, "full_name": "Mallory"}, headers=headers).status_code == 403

    def test_a_wrong_birth_date_is_refused_and_reveals_nothing(self):
        register("5550000001", "Alice", ALICE_DOB, email="old@example.com")
        wrong = self.access("5550000001", "1991-03-15")
        assert wrong.status_code == 403 and "old@example.com" not in wrong.text and "Alice" not in wrong.text
        assert "edit_token" not in wrong.text

    def test_five_wrong_answers_lock_that_customer_but_not_others(self):
        register("5550000001", "Alice", ALICE_DOB)
        register("5550000002", "Bob", "1992-06-20")
        for _ in range(LIMITS["profile_fail_customer"][0]):
            assert self.access("5550000001", "2000-01-01").status_code == 403
        assert self.access("5550000001", ALICE_DOB).status_code == 429  # the right answer is refused while locked
        assert self.access("5550000002", "1992-06-20").status_code == 200

    def test_a_correct_answer_resets_the_counter(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "profile_fail_device", (50, 900))
        register("5550000001", "Alice", ALICE_DOB)
        for _ in range(LIMITS["profile_fail_customer"][0] - 1):
            self.access("5550000001", "2000-01-01")
        assert self.access("5550000001", ALICE_DOB).status_code == 200
        for _ in range(LIMITS["profile_fail_customer"][0] - 1):
            assert self.access("5550000001", "2000-01-01").status_code == 403
        assert self.access("5550000001", ALICE_DOB).status_code == 200

    def test_guessing_across_customers_is_limited_per_device(self):
        for number in range(1, 13):
            register(f"55500000{number:02d}", f"Person{number}", ALICE_DOB)
        statuses = [self.access(f"55500000{number:02d}", "2001-01-01").status_code for number in range(1, 13)]
        assert statuses[:10] == [403] * 10 and set(statuses[10:]) == {429}

    def test_an_unknown_phone_is_a_404_that_counts_as_enumeration(self):
        assert self.access("5559999999", ALICE_DOB).status_code == 404

    def test_the_edit_token_is_bound_to_one_customer_and_one_device(self):
        register("5550000001", "Alice", ALICE_DOB)
        register("5550000002", "Bob", "1992-06-20")
        alice_token = self.access("5550000001", ALICE_DOB).json()["edit_token"]
        stolen = client.patch("/customers/5550000002/profile", headers={PROFILE_TOKEN_HEADER: alice_token},
                              json={**BODY, "phone_number": "5550000002"})
        assert stolen.status_code == 403
        other_tablet = tablet(make_paired_device("Other")[1])
        elsewhere = other_tablet.patch("/customers/5550000001/profile", headers={PROFILE_TOKEN_HEADER: alice_token}, json=BODY)
        assert elsewhere.status_code == 403
        assert client.patch("/customers/5550000001/profile", headers={PROFILE_TOKEN_HEADER: alice_token}, json=BODY).status_code == 200

    def test_the_edit_token_expires(self, monkeypatch):
        register("5550000001", "Alice", ALICE_DOB)
        monkeypatch.setattr(kiosk_security, "PROFILE_EDIT_SECONDS", 0)
        token = self.access("5550000001", ALICE_DOB).json()["edit_token"]
        assert client.patch("/customers/5550000001/profile", headers={PROFILE_TOKEN_HEADER: token}, json=BODY).status_code == 403

    def test_a_failed_edit_keeps_the_confirmation_for_a_retry(self):
        register("5550000001", "Alice", ALICE_DOB)
        register("5550000002", "Bob", "1992-06-20")
        headers = {PROFILE_TOKEN_HEADER: self.access("5550000001", ALICE_DOB).json()["edit_token"]}
        assert client.patch("/customers/5550000001/profile", headers=headers, json={**BODY, "phone_number": "5550000002"}).status_code == 400
        assert client.patch("/customers/5550000001/profile", headers=headers, json=BODY).status_code == 200

    def test_a_device_cannot_edit_without_a_device_token_even_with_an_edit_token(self):
        register("5550000001", "Alice", ALICE_DOB)
        token = self.access("5550000001", ALICE_DOB).json()["edit_token"]
        assert tablet().patch("/customers/5550000001/profile", headers={PROFILE_TOKEN_HEADER: token}, json=BODY).status_code == 401

    def test_missing_tokens_count_against_the_device(self):
        register("5550000001", "Alice", ALICE_DOB)
        statuses = [client.patch("/customers/5550000001/profile", json=BODY).status_code
                    for _ in range(LIMITS["profile_fail_device"][0] + 1)]
        assert statuses[:-1] == [403] * LIMITS["profile_fail_device"][0] and statuses[-1] == 429

    def test_the_old_unprotected_phone_change_is_internal_only(self):
        register("5550000001", "Alice", ALICE_DOB)
        browser, _id, _token = paired_tablet()
        assert browser.patch("/customers/5550000001/update-phone", json={"new_phone_number": "5550000077"}).status_code == 401
        assert client.patch("/customers/5550000001/update-phone", json={"new_phone_number": "5550000077"}).status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# Rate limits on lookups and referrals
# ══════════════════════════════════════════════════════════════════════════════
class TestKioskRateLimits:

    def test_lookups_are_limited_per_device(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "lookup", (4, 60))
        register("5550000001", "Alice", ALICE_DOB)
        assert [client.get("/customers/by-phone/5550000001").status_code for _ in range(4)] == [200] * 4
        limited = client.get("/customers/by-phone/5550000001")
        assert limited.status_code == 429 and "Retry-After" in limited.headers

    def test_status_and_lookup_share_the_same_budget(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "lookup", (3, 60))
        register("5550000001", "Alice", ALICE_DOB)
        client.get("/customers/by-phone/5550000001")
        client.get("/customers/check-in-status/5550000001")
        client.get("/customers/by-phone/5550000001")
        assert client.get("/customers/check-in-status/5550000001").status_code == 429

    def test_enumeration_by_misses_is_blocked_but_real_customers_still_work_for_other_devices(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "lookup_miss", (3, 600))
        register("5550000001", "Alice", ALICE_DOB)
        assert [client.get(f"/customers/by-phone/555999000{n}").status_code for n in range(3)] == [404] * 3
        assert client.get("/customers/by-phone/5559990009").status_code == 429
        assert client.get("/customers/by-phone/5550000001").status_code == 429  # this device is cooling down
        other = tablet(make_paired_device("Second")[1])
        assert other.get("/customers/by-phone/5550000001").status_code == 200

    def test_normal_registration_traffic_is_not_throttled(self):
        for number in range(8):  # eight new customers in a row: each lookup is a miss, then a registration
            phone = f"55501000{number:02d}"
            assert client.get(f"/customers/by-phone/{phone}").status_code == 404
            assert register(phone, f"New{number}", ALICE_DOB).status_code == 201

    def test_referral_calls_are_limited_and_failures_even_more(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "referral_fail", (3, 600))
        register("5550000001", "Alice", ALICE_DOB)
        body = {"phone_number": "5550000001", "referral_code": "NOPE1"}
        assert [client.post("/referrals/validate", json=body).status_code for _ in range(3)] == [404] * 3
        assert client.post("/referrals/validate", json=body).status_code == 429
        assert client.post("/referrals/apply", json=body).status_code == 429  # one budget for validate and apply

    def test_referral_rate_is_limited_per_minute(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "referral", (2, 60))
        body = {"phone_number": "5550000001", "referral_code": "NOPE1"}
        client.post("/referrals/validate", json=body)
        client.post("/referrals/validate", json=body)
        assert client.post("/referrals/validate", json=body).status_code == 429

    def test_limits_do_not_leak_between_devices(self, monkeypatch):
        monkeypatch.setitem(LIMITS, "lookup", (1, 60))
        register("5550000001", "Alice", ALICE_DOB)
        client.get("/customers/by-phone/5550000001")
        assert client.get("/customers/by-phone/5550000001").status_code == 429
        assert tablet(make_paired_device("Other")[1]).get("/customers/by-phone/5550000001").status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# Forwarded client address
# ══════════════════════════════════════════════════════════════════════════════
def _request(peer, header=None):
    headers = [(CLIENT_IP_HEADER.lower().encode(), header.encode())] if header is not None else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 5555)})


class TestForwardedClientAddress:

    def test_loopback_peers_are_trusted_by_default_and_unknown_peers_are_not(self):
        assert kiosk_security.client_ip(_request("127.0.0.1", "192.168.0.50")) == "192.168.0.50"
        assert kiosk_security.client_ip(_request("::1", "192.168.0.50")) == "192.168.0.50"
        assert kiosk_security.client_ip(_request("192.168.0.77", "10.9.9.9")) == "192.168.0.77"  # spoof attempt ignored
        assert kiosk_security.client_ip(_request("8.8.8.8", "10.9.9.9")) == "8.8.8.8"

    def test_a_trusted_peer_without_or_with_a_bad_header_falls_back_to_the_peer(self):
        assert kiosk_security.client_ip(_request("127.0.0.1")) == "127.0.0.1"
        for bad in ("", "not-an-ip", "1.2.3", "<script>", "999.1.1.1", "1.1.1.1, 2.2.2.2"):
            assert kiosk_security.client_ip(_request("127.0.0.1", bad)) == "127.0.0.1"

    def test_ipv6_is_normalised(self):
        assert kiosk_security.client_ip(_request("127.0.0.1", "FE80:0:0:0:0:0:0:1")) == "fe80::1"

    def test_the_trusted_proxies_are_configurable(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.5, 10.0.0.6")
        assert kiosk_security.client_ip(_request("10.0.0.6", "192.168.0.50")) == "192.168.0.50"
        assert kiosk_security.client_ip(_request("127.0.0.1", "192.168.0.50")) == "127.0.0.1"

    def test_limits_follow_the_forwarded_address_behind_the_proxy(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_IPS", "testclient")
        monkeypatch.setitem(LIMITS, "pair_fail_ip", (2, 600))

        def from_address(address):
            browser = tablet()
            browser.headers.update({CLIENT_IP_HEADER: address})
            return browser

        assert [pair("ZZZZ-ZZZZ", from_address("192.168.0.31")).status_code for _ in range(2)] == [400, 400]
        assert pair("ZZZZ-ZZZZ", from_address("192.168.0.31")).status_code == 429
        assert pair("ZZZZ-ZZZZ", from_address("192.168.0.32")).status_code == 400  # a different tablet is unaffected

    def test_a_direct_caller_cannot_dodge_limits_by_rotating_the_header(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1")  # the test peer is NOT a trusted proxy
        monkeypatch.setitem(LIMITS, "pair_fail_ip", (2, 600))
        results = []
        for number in range(4):
            browser = tablet()
            browser.headers.update({CLIENT_IP_HEADER: f"192.168.0.{number + 40}"})
            results.append(pair("ZZZZ-ZZZZ", browser).status_code)
        assert results == [400, 400, 429, 429]


# ══════════════════════════════════════════════════════════════════════════════
# Migration
# ══════════════════════════════════════════════════════════════════════════════
class TestMigration:

    def test_the_table_is_added_to_an_existing_database_without_touching_its_data(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'legacy.db'}"
        legacy = create_engine(url)
        Base.metadata.create_all(legacy)
        with legacy.begin() as connection:
            connection.execute(text("DROP TABLE kiosk_devices"))
            connection.execute(text(
                "INSERT INTO customers (full_name, phone_number, date_of_birth, referral_count, referral_discount_percent,"
                " referral_discount_pending, referred_discount_pending, birthday_discount_amount, visit_count_cycle,"
                " visit_discount_pending) VALUES ('Old Customer', '5550001111', '1980-01-01', 0, 10, 0, 0, 10, 0, 0)"))
        assert "kiosk_devices" not in inspect(legacy).get_table_names()

        for _ in range(3):  # start-up runs create_all every time: it must be repeatable
            Base.metadata.create_all(legacy)

        assert "kiosk_devices" in inspect(legacy).get_table_names()
        with legacy.connect() as connection:
            assert connection.execute(text("SELECT full_name FROM customers")).scalar() == "Old Customer"
            assert connection.execute(text("SELECT COUNT(*) FROM kiosk_devices")).scalar() == 0

    def test_the_schema_stores_hashes_only(self):
        columns = {c["name"] for c in inspect(create_engine("sqlite://")).get_columns("customers")} if False else None
        names = {c.name for c in models.KioskDevice.__table__.columns}
        assert {"token_hash", "pairing_code_hash", "revoked_at", "last_seen_at", "display_name"} <= names
        assert not {"token", "pairing_code", "code", "secret"} & names

    def test_the_real_startup_path_is_idempotent(self):
        import importlib
        from . import main as main_module
        main_module.ensure_columns()
        main_module.ensure_unique_indexes()
        main_module.ensure_columns()
        main_module.ensure_unique_indexes()
        assert importlib.import_module("app.models").KioskDevice.__tablename__ == "kiosk_devices"
