"""
Test suite for Nail Salon Check-In System (updated for the cleaned-up backend)

Covers: Registration, Check-In, Today's Queue, Birthday, Referrals (incl. validate
and the referred customer's 10%), Loyalty, Visit History, Profile Updates,
Phone/Email/DOB validation, Birthday Reminders (once per birthday), Feb 29.

Run from the folder that CONTAINS the `app` package:
    pytest app/test_checkin_system.py -v
"""

from datetime import date, timedelta
import os

os.environ["CHECKIN_INTERNAL_SERVICE_TOKEN"] = "test-internal-token"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite:///./test_checkin.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from . import main as main_module
from . import models
from .database import Base, get_db
from .main import app
from .timeutils import today_local  # the salon's "today" (not the machine's)
from .phone_normalization import PhoneNormalizationError, normalize_us_phone

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app, raise_server_exceptions=True)
client.headers.update({"X-Internal-Service-Token": "test-internal-token"})


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    """Fresh tables + the default services before every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # /services no longer seeds on every request (only at startup), and TestClient
    # without `with` skips startup, so seed here.
    db = TestingSessionLocal()
    main_module.seed_services(db)
    db.close()
    yield


@pytest.fixture(autouse=True)
def fake_emails(monkeypatch):
    """Never send real emails; record what WOULD have been sent."""
    sent = {"birthday": [], "referral": []}
    monkeypatch.setattr(main_module, "send_birthday_email", lambda **kw: sent["birthday"].append(kw))
    monkeypatch.setattr(main_module, "send_referral_discount_email", lambda **kw: sent["referral"].append(kw))
    return sent


# ── Shared helpers ────────────────────────────────────────────────────────────

def register(phone, name, dob, email=None, referral_code=None):
    payload = {"full_name": name, "phone_number": phone, "date_of_birth": dob}
    if email is not None:
        payload["email"] = email
    if referral_code:
        payload["referral_code"] = referral_code
    return client.post("/customers/new", json=payload)


def checkin(phone, service_ids=None):
    if service_ids is None:
        service_ids = _get_first_service_id()
    return client.post(
        f"/customers/check-in/{phone}",
        json={"selected_service_ids": service_ids},
    )


def apply_referral(phone, code):
    return client.post("/referrals/apply", json={"phone_number": phone, "referral_code": code})


def validate_referral(phone, code):
    return client.post("/referrals/validate", json={"phone_number": phone, "referral_code": code})


def _get_first_service_id():
    services = client.get("/services").json()
    assert services, "No services were seeded"
    return [services[0]["id"]]


def _update_customer(phone, **fields):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    for key, value in fields.items():
        setattr(customer, key, value)
    db.commit()
    db.close()


def _give_referral_code(phone, code="ALICE"):
    _update_customer(phone, referral_code=code)


def _set_visit_cycle(phone, cycle, clear_today=True):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    if clear_today:
        db.query(models.Visit).filter(
            models.Visit.customer_id == customer.id,
            models.Visit.visit_date == today_local(),
        ).delete()
    customer.visit_count_cycle = cycle
    db.commit()
    db.close()


def _set_referral_discount_pending(phone, pending=True, percent=10):
    _update_customer(phone, referral_discount_pending=pending, referral_discount_percent=percent)


def _set_visit_discount_pending(phone, pending=True):
    _update_customer(phone, visit_discount_pending=pending)


def _get_customer(phone):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    db.close()
    return customer


def _move_visits_to_yesterday(phone):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    for visit in db.query(models.Visit).filter(models.Visit.customer_id == customer.id).all():
        visit.visit_date = today_local() - timedelta(days=1)
    db.commit()
    db.close()


def _dob_for(target: date) -> str:
    # Year 2000 is a leap year, so Feb 29 is always a valid date here.
    return date(2000, target.month, target.day).isoformat()


def today_dob():
    return _dob_for(today_local())


def future_dob(days=5):
    return _dob_for(today_local() + timedelta(days=days))


def types_of(response):
    return [d["type"] for d in response.json()["discounts_applied"]]


# ══════════════════════════════════════════════════════════════════════════════
# 0. ROOT
# ══════════════════════════════════════════════════════════════════════════════

class TestRoot:

    def test_root_returns_running_message(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "running" in r.json()["message"].lower()


class TestCanonicalPhoneNormalization:

    @pytest.mark.parametrize(
        "value",
        ["6025551234", "(602) 555-1234", "602-555-1234", "+16025551234"],
    )
    def test_equivalent_us_formats(self, value):
        normalized = normalize_us_phone(value)
        assert normalized.national_digits == "6025551234"
        assert normalized.e164 == "+16025551234"

    @pytest.mark.parametrize("value", ["123", "+442071838750", "602-CALL-NOW", "+26025551234"])
    def test_invalid_or_unsupported_phone(self, value):
        with pytest.raises(PhoneNormalizationError):
            normalize_us_phone(value)

    def test_customer_lookup_accepts_e164_and_keeps_national_storage(self):
        assert register("(602) 555-1234", "Phone Test", "1990-01-01").status_code == 201
        response = client.get("/customers/by-phone/+16025551234")
        assert response.status_code == 200
        assert response.json()["phone_number"] == "6025551234"
        assert response.json()["phone_e164"] == "+16025551234"

    def test_today_checkin_exposes_stable_ids_and_e164(self):
        customer = register("6025551234", "Queue Test", "1990-01-01").json()
        assert checkin("+16025551234").status_code == 200
        item = client.get("/today-checkins").json()["checkins"][0]
        assert item["customer_id"] == customer["id"]
        assert item["visit_id"] > 0
        assert item["phone_e164"] == "+16025551234"


class TestInternalServiceAuthentication:

    def test_today_checkins_requires_internal_token(self):
        anonymous = TestClient(app)
        assert anonymous.get("/today-checkins").status_code == 401
        assert anonymous.get("/today-checkins", headers={"X-Internal-Service-Token": "wrong"}).status_code == 401

    def test_valid_internal_token_and_public_checkin(self):
        anonymous = TestClient(app)
        assert anonymous.get("/today-checkins", headers={"X-Internal-Service-Token": "test-internal-token"}).status_code == 200
        assert anonymous.get("/services").status_code == 200

    def test_internal_customer_candidate_is_protected_and_minimal(self):
        customer = register("6025551234", "Private Customer", "1990-01-01", email="private@example.com").json()
        anonymous = TestClient(app)
        path = "/internal/customers/by-phone/6025551234"
        assert anonymous.get(path).status_code == 401
        response = anonymous.get(path, headers={"X-Internal-Service-Token": "test-internal-token"})
        assert response.status_code == 200
        assert response.json() == {"id": customer["id"], "full_name": "Private Customer", "phone_e164": "+16025551234"}
        assert "email" not in response.json()
        assert "date_of_birth" not in response.json()
        assert "referral_code" not in response.json()

    def test_secret_is_not_exposed(self):
        assert "test-internal-token" not in str(client.get("/").json())
        assert "test-internal-token" not in str(client.get("/queue-status").json())

    def test_services_are_seeded_and_listed(self):
        r = client.get("/services")
        assert r.status_code == 200
        names = [s["name"] for s in r.json()]
        assert "Gel Manicure" in names
        assert len(names) == len(main_module.DEFAULT_SERVICES)


# ══════════════════════════════════════════════════════════════════════════════
# 1. REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

class TestRegistration:

    def test_register_success(self):
        r = register("5550000001", "Alice", "1990-03-15", email="alice@example.com")
        assert r.status_code == 201
        data = r.json()
        assert data["full_name"] == "Alice"
        assert data["phone_number"] == "5550000001"
        assert data["email"] == "alice@example.com"
        assert data["date_of_birth"] == "1990-03-15"

    def test_register_defaults(self):
        data = register("5550000001", "Alice", "1990-03-15").json()
        assert data["visit_count_cycle"] == 0
        assert data["referral_code"] is None
        assert data["referral_discount_pending"] is False
        assert data["visit_discount_pending"] is False
        assert data["birthday_discount_amount"] == 10
        assert data["used_referral_code"] is None

    def test_register_duplicate_phone_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        r = register("5550000001", "Alice2", "1991-04-20")
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"].lower()

    def test_register_phone_normalized_from_dashes(self):
        r = register("555-000-0001", "Alice", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000001"

    def test_register_phone_normalized_from_spaces(self):
        r = register("555 000 0001", "Alice", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000001"

    def test_register_phone_too_short_fails(self):
        assert register("12345", "Alice", "1990-03-15").status_code == 422

    def test_register_phone_too_long_fails(self):
        assert register("55500000011111", "Alice", "1990-03-15").status_code == 422

    def test_register_strips_name_whitespace(self):
        r = register("5550000001", "  Alice  ", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["full_name"] == "Alice"

    def test_register_empty_name_fails(self):
        assert register("5550000001", "   ", "1990-03-15").status_code == 422

    def test_register_email_optional(self):
        r = register("5550000001", "Alice", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["email"] is None

    def test_register_ignores_referral_code_field(self):
        """The code is applied through /referrals/apply, never stored at registration."""
        r = register("5550000001", "Alice", "1990-03-15", referral_code="ABCDE")
        assert r.status_code == 201
        assert r.json()["referral_code"] is None
        assert r.json()["used_referral_code"] is None

    def test_get_all_customers(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        r = client.get("/customers")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_customer_by_phone(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.get("/customers/by-phone/5550000001")
        assert r.status_code == 200
        assert r.json()["full_name"] == "Alice"

    def test_get_customer_by_phone_not_found_returns_404(self):
        assert client.get("/customers/by-phone/5550000001").status_code == 404

    def test_get_customer_phone_formatted(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.get("/customers/by-phone/5550000001")
        assert r.json()["phone_number_formatted"] == "(555) 000-0001"


# ══════════════════════════════════════════════════════════════════════════════
# 2. CHECK-IN
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckIn:

    def test_checkin_success(self):
        register("5550000001", "Alice", "1990-03-15")
        r = checkin("5550000001")
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Alice"
        assert data["visit_count"] == 1
        assert data["visit_count_cycle"] == 1

    def test_checkin_visit_is_dated_with_salon_today(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        visit = client.get("/customers/5550000001/visits").json()["visits"][0]
        assert visit["visit_date"] == today_local().isoformat()

    def test_checkin_increments_visit_cycle(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        _move_visits_to_yesterday("5550000001")
        checkin("5550000001")
        assert _get_customer("5550000001").visit_count_cycle == 2

    def test_checkin_twice_same_day_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        r = checkin("5550000001")
        assert r.status_code == 400
        assert "already checked in" in r.json()["detail"].lower()

    def test_checkin_nonexistent_customer_returns_404(self):
        assert checkin("5550000001").status_code == 404

    def test_checkin_requires_valid_service_ids(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.post("/customers/check-in/5550000001", json={"selected_service_ids": [99999]})
        assert r.status_code == 404
        assert "service" in r.json()["detail"].lower()

    def test_checkin_requires_at_least_one_service(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.post("/customers/check-in/5550000001", json={"selected_service_ids": []})
        assert r.status_code == 422

    def test_checkin_ignores_duplicate_service_ids(self):
        register("5550000001", "Alice", "1990-03-15")
        sid = _get_first_service_id()[0]
        r = checkin("5550000001", [sid, sid])
        assert r.status_code == 200
        assert len(r.json()["selected_services"]) == 1

    def test_checkin_response_includes_selected_services(self):
        register("5550000001", "Alice", "1990-03-15")
        r = checkin("5550000001")
        assert r.status_code == 200
        assert len(r.json()["selected_services"]) >= 1

    def test_checkin_generates_referral_code_at_5_visits(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 4)
        checkin("5550000001")
        customer = _get_customer("5550000001")
        assert customer.referral_code is not None
        assert len(customer.referral_code) == 5

    def test_checkin_no_referral_code_before_5_visits(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 3)
        checkin("5550000001")
        assert _get_customer("5550000001").referral_code is None

    def test_referral_code_not_regenerated_once_set(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 4)
        checkin("5550000001")
        first_code = _get_customer("5550000001").referral_code
        _move_visits_to_yesterday("5550000001")
        checkin("5550000001")
        assert _get_customer("5550000001").referral_code == first_code

    def test_checkin_already_checked_in_status(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        r = client.get("/customers/check-in-status/5550000001")
        assert r.status_code == 200
        assert r.json()["already_checked_in_today"] is True

    def test_checkin_status_false_before_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.get("/customers/check-in-status/5550000001")
        assert r.json()["already_checked_in_today"] is False

    def test_checkin_status_unknown_customer_404(self):
        assert client.get("/customers/check-in-status/5559999999").status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 3. TODAY'S QUEUE
# ══════════════════════════════════════════════════════════════════════════════

class TestTodayQueue:

    def test_today_queue_empty_at_start(self):
        r = client.get("/today-checkins")
        assert r.status_code == 200
        assert r.json()["checkins"] == []

    def test_today_queue_shows_checked_in_customers(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        checkin("5550000001")
        checkin("5550000002")
        checkins = client.get("/today-checkins").json()["checkins"]
        assert len(checkins) == 2

    def test_today_queue_ordered_by_checkin_time(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        checkin("5550000001")
        checkin("5550000002")
        checkins = client.get("/today-checkins").json()["checkins"]
        assert checkins[0]["full_name"] == "Alice"
        assert checkins[1]["full_name"] == "Bob"

    def test_today_queue_shows_position_numbers(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        checkin("5550000001")
        checkin("5550000002")
        checkins = client.get("/today-checkins").json()["checkins"]
        assert checkins[0]["position"] == 1
        assert checkins[1]["position"] == 2

    def test_today_queue_excludes_yesterdays_visits(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        _move_visits_to_yesterday("5550000001")
        assert client.get("/today-checkins").json()["checkins"] == []

    def test_today_queue_shows_birthday_discount_for_birthday_customer(self):
        register("5550000001", "Alice", today_dob())
        checkin("5550000001")
        checkins = client.get("/today-checkins").json()["checkins"]
        assert checkins[0]["discount_type"] == "fixed"
        assert checkins[0]["discount_value"] == 10

    def test_today_queue_no_discount_for_non_birthday(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        assert client.get("/today-checkins").json()["checkins"][0]["discount_type"] is None

    def test_today_queue_label_lists_every_discount(self):
        """Birthday ($10) + loyalty (10%) must BOTH appear in the saved label."""
        register("5550000001", "Alice", today_dob())
        _set_visit_discount_pending("5550000001")
        checkin("5550000001")
        item = client.get("/today-checkins").json()["checkins"][0]
        assert item["discount_type"] == "fixed"
        assert "birthday" in item["discount_label"].lower()
        assert "loyalty" in item["discount_label"].lower()

    def test_today_queue_percent_discounts_add_up(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_referral_discount_pending("5550000001", True, 15)
        _set_visit_discount_pending("5550000001")
        checkin("5550000001")
        item = client.get("/today-checkins").json()["checkins"][0]
        assert item["discount_type"] == "percent"
        assert item["discount_value"] == 25  # 15% referral + 10% loyalty


# ══════════════════════════════════════════════════════════════════════════════
# 4. BIRTHDAY DISCOUNT
# ══════════════════════════════════════════════════════════════════════════════

class TestBirthdayDiscount:

    def test_birthday_discount_applied_on_birthday(self):
        register("5550000001", "Alice", today_dob())
        r = checkin("5550000001")
        assert r.status_code == 200
        assert "birthday" in types_of(r)

    def test_birthday_discount_not_applied_on_non_birthday(self):
        register("5550000001", "Alice", "1990-03-15")
        assert "birthday" not in types_of(checkin("5550000001"))

    def test_birthday_discount_not_applied_day_before_or_after(self):
        register("5550000001", "Alice", _dob_for(today_local() + timedelta(days=1)))
        register("5550000002", "Bob", _dob_for(today_local() - timedelta(days=1)))
        assert "birthday" not in types_of(checkin("5550000001"))
        assert "birthday" not in types_of(checkin("5550000002"))

    def test_birthday_discount_marks_used_month(self):
        register("5550000001", "Alice", today_dob())
        checkin("5550000001")
        expected_key = today_local().strftime("%Y-%m")
        assert _get_customer("5550000001").birthday_discount_used_month == expected_key

    def test_birthday_discount_not_applied_twice_same_month(self):
        register("5550000001", "Alice", today_dob())
        checkin("5550000001")
        _move_visits_to_yesterday("5550000001")
        assert "birthday" not in types_of(checkin("5550000001"))

    def test_birthday_discount_available_flag_false_after_use(self):
        register("5550000001", "Alice", today_dob())
        r = checkin("5550000001")
        assert r.json()["birthday_discount_available"] is False

    def test_birthday_discount_amount_in_response(self):
        register("5550000001", "Alice", today_dob())
        r = checkin("5550000001")
        birthday = next(d for d in r.json()["discounts_applied"] if d["type"] == "birthday")
        assert birthday["amount"] == 10


# ══════════════════════════════════════════════════════════════════════════════
# 5. REFERRAL SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

class TestReferrals:

    def test_apply_referral_code_success(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")
        r = apply_referral("5550000002", "ALICE")
        assert r.status_code == 200
        data = r.json()
        assert data["used_referral_code"] == "ALICE"
        assert data["referral_from_customer_name"] == "Alice"
        assert data["discount_percent"] == 10

    def test_apply_referral_is_case_insensitive(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")
        r = apply_referral("5550000002", "  alice ")
        assert r.status_code == 200
        assert r.json()["used_referral_code"] == "ALICE"

    def test_apply_referral_increments_owner_count(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")
        apply_referral("5550000002", "ALICE")
        assert _get_customer("5550000001").referral_count == 1

    def test_apply_referral_records_who_referred_whom(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")
        apply_referral("5550000002", "ALICE")
        bob = _get_customer("5550000002")
        assert bob.used_referral_code == "ALICE"
        assert bob.used_referral_from_customer_id == _get_customer("5550000001").id

    def test_apply_own_referral_code_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        r = apply_referral("5550000001", "ALICE")
        assert r.status_code == 400
        assert "own" in r.json()["detail"].lower()

    def test_apply_referral_twice_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        register("5550000003", "Carol", "1993-07-10")
        _give_referral_code("5550000001", "ALICE")
        _give_referral_code("5550000003", "CAROL")
        apply_referral("5550000002", "ALICE")
        r = apply_referral("5550000002", "CAROL")
        assert r.status_code == 400
        assert "already used" in r.json()["detail"].lower()
        assert _get_customer("5550000003").referral_count == 0  # Carol gets no credit

    def test_apply_nonexistent_code_returns_404(self):
        register("5550000001", "Alice", "1990-03-15")
        assert apply_referral("5550000001", "BADCD").status_code == 404

    def test_apply_referral_for_unknown_customer_returns_404(self):
        assert apply_referral("5559999999", "ALICE").status_code == 404

    def test_referral_discount_pending_after_3_referrals(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        for i in range(3):
            phone = f"555000000{i + 2}"
            register(phone, f"User{i}", "1990-01-01")
            apply_referral(phone, "ALICE")
        customer = _get_customer("5550000001")
        assert customer.referral_discount_pending is True
        assert customer.referral_discount_percent == 10

    def test_no_reward_before_3_referrals(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        for i in range(2):
            phone = f"555000000{i + 2}"
            register(phone, f"User{i}", "1990-01-01")
            apply_referral(phone, "ALICE")
        assert _get_customer("5550000001").referral_discount_pending is False

    def test_referral_discount_pending_after_8_referrals(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        _update_customer("5550000001", referral_count=7)
        register("5550000009", "Eighth", "1990-01-01")
        apply_referral("5550000009", "ALICE")
        customer = _get_customer("5550000001")
        assert customer.referral_discount_pending is True
        assert customer.referral_discount_percent == 15

    def test_referral_discount_pending_after_18_referrals(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        _update_customer("5550000001", referral_count=17)
        register("5550000009", "Eighteenth", "1990-01-01")
        apply_referral("5550000009", "ALICE")
        customer = _get_customer("5550000001")
        assert customer.referral_discount_pending is True
        assert customer.referral_discount_percent == 20

    def test_milestone_upgrades_unused_reward_instead_of_being_lost(self):
        """NEW: owner still has the unused 10% from 3 referrals and reaches 8."""
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        _update_customer("5550000001", referral_count=7,
                         referral_discount_pending=True, referral_discount_percent=10)
        register("5550000009", "Eighth", "1990-01-01")
        apply_referral("5550000009", "ALICE")
        customer = _get_customer("5550000001")
        assert customer.referral_discount_pending is True
        assert customer.referral_discount_percent == 15

    def test_milestone_never_downgrades_a_bigger_unused_reward(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        _update_customer("5550000001", referral_count=2,
                         referral_discount_pending=True, referral_discount_percent=20)
        register("5550000009", "Third", "1990-01-01")
        apply_referral("5550000009", "ALICE")  # 3rd referral would be 10%
        assert _get_customer("5550000001").referral_discount_percent == 20

    def test_referral_discount_applied_on_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_referral_discount_pending("5550000001", pending=True, percent=10)
        assert "referral" in types_of(checkin("5550000001"))

    def test_referral_discount_uses_stored_percent(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_referral_discount_pending("5550000001", pending=True, percent=15)
        r = checkin("5550000001")
        referral = next(d for d in r.json()["discounts_applied"] if d["type"] == "referral")
        assert referral["percent"] == 15

    def test_referral_discount_cleared_after_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_referral_discount_pending("5550000001", pending=True, percent=10)
        checkin("5550000001")
        assert _get_customer("5550000001").referral_discount_pending is False

    def test_referral_discount_not_applied_when_not_pending(self):
        register("5550000001", "Alice", "1990-03-15")
        assert "referral" not in types_of(checkin("5550000001"))

    def test_referral_usage_unique_per_customer_in_database(self):
        """NEW: the database itself refuses a second code for the same customer."""
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter_by(phone_number="5550000001").first()
        bob = db.query(models.Customer).filter_by(phone_number="5550000002").first()
        for code in ("AAAAA", "BBBBB"):
            db.add(models.ReferralUsage(
                code=code,
                code_owner_customer_id=alice.id,
                used_by_customer_id=bob.id,
                used_on=today_local(),
            ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.close()

    def test_referral_email_sent_to_referred_customer(self, fake_emails):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20", email="bob@example.com")
        _give_referral_code("5550000001", "ALICE")
        apply_referral("5550000002", "ALICE")
        assert len(fake_emails["referral"]) == 1
        assert fake_emails["referral"][0]["to_email"] == "bob@example.com"
        assert fake_emails["referral"][0]["referrer_name"] == "Alice"

    def test_referral_email_failure_does_not_break_apply(self, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("smtp down")
        monkeypatch.setattr(main_module, "send_referral_discount_email", boom)
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20", email="bob@example.com")
        _give_referral_code("5550000001", "ALICE")
        assert apply_referral("5550000002", "ALICE").status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 6. REFERRAL VALIDATE  (new route)
# ══════════════════════════════════════════════════════════════════════════════

class TestReferralValidate:

    def test_validate_works_before_customer_exists(self):
        """New-customer flow: the code is checked BEFORE the customer is created."""
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        r = validate_referral("5550000077", "ALICE")
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_validate_does_not_use_the_code(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")
        validate_referral("5550000002", "ALICE")
        assert _get_customer("5550000001").referral_count == 0
        assert _get_customer("5550000002").used_referral_code is None

    def test_validate_unknown_code_404(self):
        assert validate_referral("5550000002", "ZZZZZ").status_code == 404

    def test_validate_own_code_400(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        r = validate_referral("5550000001", "ALICE")
        assert r.status_code == 400
        assert "own" in r.json()["detail"].lower()

    def test_validate_customer_who_already_used_a_code_400(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")
        apply_referral("5550000002", "ALICE")
        r = validate_referral("5550000002", "ALICE")
        assert r.status_code == 400
        assert "already used" in r.json()["detail"].lower()

    def test_validate_is_case_insensitive(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        assert validate_referral("5550000077", "alice").status_code == 200

    def test_validate_invalid_phone_422(self):
        assert validate_referral("123", "ALICE").status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 7. REFERRED CUSTOMER'S 10%  (new behavior)
# ══════════════════════════════════════════════════════════════════════════════

class TestReferredCustomerDiscount:

    def _setup_pair(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")

    def test_referred_customer_gets_10_percent_on_checkin(self):
        self._setup_pair()
        apply_referral("5550000002", "ALICE")
        r = checkin("5550000002")
        referred = next(d for d in r.json()["discounts_applied"] if d["type"] == "referral_used")
        assert referred["percent"] == 10

    def test_referred_discount_uses_its_own_type(self):
        """'referral' is the owner's reward; the welcome 10% must not reuse that type."""
        self._setup_pair()
        apply_referral("5550000002", "ALICE")
        assert "referral" not in types_of(checkin("5550000002"))

    def test_referred_discount_is_one_time(self):
        self._setup_pair()
        apply_referral("5550000002", "ALICE")
        checkin("5550000002")
        assert _get_customer("5550000002").referred_discount_pending is False
        _move_visits_to_yesterday("5550000002")
        assert "referral_used" not in types_of(checkin("5550000002"))

    def test_referred_discount_waits_if_checkin_has_not_happened_yet(self):
        self._setup_pair()
        apply_referral("5550000002", "ALICE")
        assert _get_customer("5550000002").referred_discount_pending is True

    def test_referred_discount_saved_in_todays_queue(self):
        self._setup_pair()
        apply_referral("5550000002", "ALICE")
        checkin("5550000002")
        item = client.get("/today-checkins").json()["checkins"][0]
        assert item["discount_type"] == "percent"
        assert item["discount_value"] == 10

    def test_no_referred_discount_without_using_a_code(self):
        self._setup_pair()
        assert "referral_used" not in types_of(checkin("5550000002"))

    def test_owner_and_referred_rewards_stack_on_same_visit(self):
        self._setup_pair()
        _set_referral_discount_pending("5550000002", True, 15)
        apply_referral("5550000002", "ALICE")
        types = types_of(checkin("5550000002"))
        assert "referral" in types
        assert "referral_used" in types

    def test_new_customer_full_flow_validate_create_apply_checkin(self):
        """Exactly what the frontend does for a NEW customer with a code."""
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        assert validate_referral("5550000050", "ALICE").status_code == 200
        assert register("5550000050", "Newbie", "1995-05-05").status_code == 201
        assert apply_referral("5550000050", "ALICE").status_code == 200
        r = checkin("5550000050")
        assert r.status_code == 200
        assert "referral_used" in types_of(r)


# ══════════════════════════════════════════════════════════════════════════════
# 8. LOYALTY (VISIT) DISCOUNT
# ══════════════════════════════════════════════════════════════════════════════

class TestLoyaltyDiscount:

    def test_visit_discount_earned_at_10th_visit(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 9)
        checkin("5550000001")
        assert _get_customer("5550000001").visit_discount_pending is True

    def test_visit_discount_not_applied_on_the_same_visit_it_is_earned(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 9)
        r = checkin("5550000001")
        assert "loyalty" not in types_of(r)

    def test_visit_discount_applied_on_the_following_visit(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 9)
        checkin("5550000001")              # visit 10: earns it
        _move_visits_to_yesterday("5550000001")
        r = checkin("5550000001")          # visit 11: uses it
        assert "loyalty" in types_of(r)
        assert _get_customer("5550000001").visit_discount_pending is False

    def test_visit_discount_not_earned_before_10th_visit(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 8)
        checkin("5550000001")
        assert _get_customer("5550000001").visit_discount_pending is False

    def test_visit_discount_earned_at_20th_visit(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 19)
        checkin("5550000001")
        assert _get_customer("5550000001").visit_discount_pending is True

    def test_visit_discount_applied_on_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_discount_pending("5550000001", pending=True)
        assert "loyalty" in types_of(checkin("5550000001"))

    def test_visit_discount_is_10_percent(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_discount_pending("5550000001", pending=True)
        r = checkin("5550000001")
        loyalty = next(d for d in r.json()["discounts_applied"] if d["type"] == "loyalty")
        assert loyalty["percent"] == 10

    def test_visit_discount_cleared_after_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_discount_pending("5550000001", pending=True)
        checkin("5550000001")
        assert _get_customer("5550000001").visit_discount_pending is False

    def test_visit_discount_not_applied_when_not_pending(self):
        register("5550000001", "Alice", "1990-03-15")
        assert "loyalty" not in types_of(checkin("5550000001"))

    def test_multiple_discounts_can_stack(self):
        register("5550000001", "Alice", today_dob())
        _set_visit_discount_pending("5550000001", pending=True)
        types = types_of(checkin("5550000001"))
        assert "birthday" in types
        assert "loyalty" in types

    def test_all_three_reward_types_stack(self):
        register("5550000001", "Alice", today_dob())
        _set_visit_discount_pending("5550000001", pending=True)
        _set_referral_discount_pending("5550000001", True, 15)
        types = types_of(checkin("5550000001"))
        assert set(["birthday", "referral", "loyalty"]).issubset(types)


# ══════════════════════════════════════════════════════════════════════════════
# 9. VISIT HISTORY
# ══════════════════════════════════════════════════════════════════════════════

class TestVisitHistory:

    def test_visit_history_empty_before_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.get("/customers/5550000001/visits")
        assert r.status_code == 200
        assert r.json()["visit_count"] == 0
        assert r.json()["visits"] == []

    def test_visit_history_shows_after_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        assert client.get("/customers/5550000001/visits").json()["visit_count"] == 1

    def test_visit_history_includes_services(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        visits = client.get("/customers/5550000001/visits").json()["visits"]
        assert len(visits[0]["services"]) >= 1

    def test_visit_history_not_found_returns_404(self):
        assert client.get("/customers/5559999999/visits").status_code == 404

    def test_visit_history_accumulates_over_multiple_days(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        _move_visits_to_yesterday("5550000001")
        checkin("5550000001")
        assert client.get("/customers/5550000001/visits").json()["visit_count"] == 2

    def test_visit_history_shows_referral_info(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")
        apply_referral("5550000002", "ALICE")
        data = client.get("/customers/5550000002/visits").json()
        assert data["used_referral_code"] == "ALICE"
        owner = client.get("/customers/5550000001/visits").json()
        assert owner["referral_count"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# 10. PROFILE UPDATES
# ══════════════════════════════════════════════════════════════════════════════

class TestProfileUpdates:

    def test_update_phone_success(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.patch("/customers/5550000001/update-phone", json={"new_phone_number": "5550000099"})
        assert r.status_code == 200
        assert r.json()["phone_number"] == "5550000099"

    def test_update_phone_same_number_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.patch("/customers/5550000001/update-phone", json={"new_phone_number": "5550000001"})
        assert r.status_code == 400
        assert "same" in r.json()["detail"].lower()

    def test_update_phone_conflict_with_existing_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        r = client.patch("/customers/5550000001/update-phone", json={"new_phone_number": "5550000002"})
        assert r.status_code == 400
        assert "already in use" in r.json()["detail"].lower()

    def test_update_phone_not_found_returns_404(self):
        r = client.patch("/customers/5559999999/update-phone", json={"new_phone_number": "5550000099"})
        assert r.status_code == 404

    def test_update_phone_invalid_number_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.patch("/customers/5550000001/update-phone", json={"new_phone_number": "123"})
        assert r.status_code == 422

    def test_update_profile_success(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.patch("/customers/5550000001/profile", json={
            "full_name": "Alice Smith",
            "phone_number": "5550000001",
            "email": "alice@new.com",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Alice Smith"
        assert data["email"] == "alice@new.com"

    def test_update_profile_can_change_phone(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.patch("/customers/5550000001/profile", json={
            "full_name": "Alice",
            "phone_number": "5550000099",
        })
        assert r.status_code == 200
        assert r.json()["phone_number"] == "5550000099"

    def test_update_profile_keeps_rewards_and_history_on_same_account(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_discount_pending("5550000001")
        checkin("5550000001")
        client.patch("/customers/5550000001/profile", json={
            "full_name": "Alice", "phone_number": "5550000099",
        })
        data = client.get("/customers/5550000099/visits").json()
        assert data["visit_count"] == 1
        assert data["visit_count_cycle"] == 1

    def test_update_profile_phone_conflict_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        r = client.patch("/customers/5550000001/profile", json={
            "full_name": "Alice",
            "phone_number": "5550000002",
        })
        assert r.status_code == 400
        assert "already in use" in r.json()["detail"].lower()

    def test_update_profile_not_found_returns_404(self):
        r = client.patch("/customers/5559999999/profile", json={
            "full_name": "Ghost",
            "phone_number": "5559999999",
        })
        assert r.status_code == 404

    def test_update_profile_clears_email_when_empty(self):
        register("5550000001", "Alice", "1990-03-15", email="alice@example.com")
        r = client.patch("/customers/5550000001/profile", json={
            "full_name": "Alice",
            "phone_number": "5550000001",
            "email": "",
        })
        assert r.status_code == 200
        assert r.json()["email"] is None

    def test_update_profile_rejects_bad_email(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.patch("/customers/5550000001/profile", json={
            "full_name": "Alice",
            "phone_number": "5550000001",
            "email": "not-an-email",
        })
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 11. INPUT VALIDATION  (phone, email, date of birth)
# ══════════════════════════════════════════════════════════════════════════════

class TestPhoneValidation:

    def test_10_digit_phone_accepted(self):
        assert register("5550000001", "Alice", "1990-03-15").status_code == 201

    def test_phone_with_dashes_accepted(self):
        r = register("555-000-0001", "Alice", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000001"

    def test_phone_with_parentheses_accepted(self):
        r = register("(555) 000-0001", "Alice", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000001"

    def test_phone_with_spaces_accepted(self):
        r = register("555 000 0001", "Alice", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000001"

    def test_phone_too_short_rejected(self):
        assert register("12345", "Alice", "1990-03-15").status_code == 422

    def test_phone_too_long_rejected(self):
        assert register("55500000011111", "Alice", "1990-03-15").status_code == 422

    def test_lookup_with_invalid_phone_is_422(self):
        assert client.get("/customers/by-phone/123").status_code == 422

    def test_referral_apply_invalid_phone_rejected(self):
        r = client.post("/referrals/apply", json={"phone_number": "123", "referral_code": "ALICE"})
        assert r.status_code == 422

    def test_update_phone_invalid_rejected(self):
        register("5550000001", "Alice", "1990-03-15")
        assert client.patch(
            "/customers/5550000001/update-phone",
            json={"new_phone_number": "123"},
        ).status_code == 422

    def test_update_profile_invalid_phone_rejected(self):
        register("5550000001", "Alice", "1990-03-15")
        assert client.patch(
            "/customers/5550000001/profile",
            json={"full_name": "Alice", "phone_number": "123"},
        ).status_code == 422


class TestEmailAndDobValidation:

    def test_bad_email_rejected(self):
        assert register("5550000001", "Alice", "1990-03-15", email="nope").status_code == 422

    def test_email_without_domain_dot_rejected(self):
        assert register("5550000001", "Alice", "1990-03-15", email="a@b").status_code == 422

    def test_email_is_trimmed(self):
        r = register("5550000001", "Alice", "1990-03-15", email="  alice@example.com  ")
        assert r.status_code == 201
        assert r.json()["email"] == "alice@example.com"

    def test_blank_email_becomes_none(self):
        r = register("5550000001", "Alice", "1990-03-15", email="   ")
        assert r.status_code == 201
        assert r.json()["email"] is None

    def test_future_dob_rejected(self):
        tomorrow = (today_local() + timedelta(days=1)).isoformat()
        assert register("5550000001", "Alice", tomorrow).status_code == 422

    def test_dob_before_1900_rejected(self):
        assert register("5550000001", "Alice", "1899-12-31").status_code == 422

    def test_dob_1900_01_01_accepted(self):
        assert register("5550000001", "Alice", "1900-01-01").status_code == 201

    def test_dob_today_accepted(self):
        assert register("5550000001", "Alice", today_local().isoformat()).status_code == 201

    def test_invalid_dob_format_rejected(self):
        assert register("5550000001", "Alice", "03-15-1990").status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 12. BIRTHDAY REMINDERS
# ══════════════════════════════════════════════════════════════════════════════

class TestBirthdayReminders:

    def test_upcoming_birthday_reminders_includes_birthday_today(self):
        register("5550000001", "Alice", today_dob(), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        assert "5550000001" in [c["phone_number"] for c in r.json()]

    def test_upcoming_birthday_reminders_includes_within_5_days(self):
        register("5550000001", "Alice", future_dob(3), email="alice@example.com")
        assert len(client.get("/birthday-reminders").json()) == 1

    def test_upcoming_birthday_reminders_includes_exactly_5_days(self):
        register("5550000001", "Alice", future_dob(5))
        assert len(client.get("/birthday-reminders").json()) == 1

    def test_upcoming_birthday_reminders_excludes_beyond_5_days(self):
        register("5550000001", "Alice", future_dob(6))
        assert len(client.get("/birthday-reminders").json()) == 0

    def test_birthday_reminder_response_includes_days_until(self):
        register("5550000001", "Alice", future_dob(3))
        assert client.get("/birthday-reminders").json()[0]["days_until_birthday"] == 3

    def test_birthday_reminder_includes_discount_amount(self):
        register("5550000001", "Alice", today_dob())
        assert client.get("/birthday-reminders").json()[0]["birthday_discount_amount"] == 10

    # ── sending (emails are faked, see the fake_emails fixture) ──────────────

    def test_send_reminders_sends_to_customers_with_email(self, fake_emails):
        register("5550000001", "Alice", future_dob(2), email="alice@example.com")
        r = client.post("/birthday-reminders/send")
        assert r.status_code == 200
        assert r.json()["sent"] == 1
        assert fake_emails["birthday"][0]["to_email"] == "alice@example.com"

    def test_send_reminders_skips_customers_without_email(self, fake_emails):
        register("5550000001", "Alice", future_dob(2))
        r = client.post("/birthday-reminders/send")
        assert r.json()["sent"] == 0
        assert fake_emails["birthday"] == []

    def test_send_reminders_skips_birthdays_too_far_away(self, fake_emails):
        register("5550000001", "Alice", future_dob(30), email="alice@example.com")
        assert client.post("/birthday-reminders/send").json()["sent"] == 0

    def test_reminder_sent_only_once_per_birthday_not_daily(self, fake_emails):
        """NEW: before, the same customer got an email on each of the 6 days."""
        register("5550000001", "Alice", future_dob(3), email="alice@example.com")
        assert client.post("/birthday-reminders/send").json()["sent"] == 1
        assert client.post("/birthday-reminders/send").json()["sent"] == 0
        assert len(fake_emails["birthday"]) == 1

    def test_reminder_not_repeated_on_later_days_of_same_window(self, fake_emails):
        register("5550000001", "Alice", future_dob(3), email="alice@example.com")
        client.post("/birthday-reminders/send")
        # pretend the email went out 2 days ago (still inside the same birthday window)
        _update_customer("5550000001", birthday_reminder_sent_date=today_local() - timedelta(days=2))
        assert client.post("/birthday-reminders/send").json()["sent"] == 0

    def test_reminder_sent_again_next_year(self, fake_emails):
        register("5550000001", "Alice", future_dob(3), email="alice@example.com")
        _update_customer("5550000001",
                         birthday_reminder_sent=True,
                         birthday_reminder_sent_date=today_local() - timedelta(days=365))
        assert client.post("/birthday-reminders/send").json()["sent"] == 1

    def test_reminder_marks_customer_as_sent(self, fake_emails):
        register("5550000001", "Alice", future_dob(3), email="alice@example.com")
        client.post("/birthday-reminders/send")
        customer = _get_customer("5550000001")
        assert customer.birthday_reminder_sent is True
        assert customer.birthday_reminder_sent_date == today_local()

    def test_email_failure_is_skipped_and_not_marked_sent(self, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("smtp down")
        monkeypatch.setattr(main_module, "send_birthday_email", boom)
        register("5550000001", "Alice", future_dob(3), email="alice@example.com")
        r = client.post("/birthday-reminders/send")
        assert r.status_code == 200
        assert r.json()["sent"] == 0
        assert r.json()["skipped"] == 1
        assert _get_customer("5550000001").birthday_reminder_sent_date is None

    def test_scheduled_job_uses_the_same_logic(self, fake_emails, monkeypatch):
        """The 9am job and the manual endpoint share process_birthday_reminders()."""
        monkeypatch.setattr(main_module, "SessionLocal", TestingSessionLocal)
        register("5550000001", "Alice", future_dob(1), email="alice@example.com")
        main_module.run_scheduled_birthday_reminders()
        assert len(fake_emails["birthday"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# 13. FEB 29 BIRTHDAYS  (used to crash)
# ══════════════════════════════════════════════════════════════════════════════

class TestLeapDayBirthdays:

    def test_birthday_in_non_leap_year_falls_back_to_feb_28(self):
        assert main_module._birthday_in_year(date(2000, 2, 29), 2026) == date(2026, 2, 28)

    def test_birthday_in_leap_year_stays_feb_29(self):
        assert main_module._birthday_in_year(date(2000, 2, 29), 2028) == date(2028, 2, 29)

    def test_regular_birthday_unchanged(self):
        assert main_module._birthday_in_year(date(1990, 7, 4), 2026) == date(2026, 7, 4)

    def test_days_until_next_birthday_does_not_crash_for_feb_29(self):
        days = main_module.days_until_next_birthday(date(2000, 2, 29))
        assert 0 <= days <= 366

    def test_reminders_endpoint_survives_a_feb_29_customer(self):
        assert register("5550000001", "Leap", "2000-02-29").status_code == 201
        assert client.get("/birthday-reminders").status_code == 200

    def test_send_endpoint_survives_a_feb_29_customer(self, fake_emails):
        register("5550000001", "Leap", "2000-02-29", email="leap@example.com")
        assert client.post("/birthday-reminders/send").status_code == 200

    def test_feb_29_customer_can_check_in(self):
        register("5550000001", "Leap", "2000-02-29")
        assert checkin("5550000001").status_code == 200

    def test_is_exact_birthday_today(self):
        assert main_module.is_exact_birthday(date(2000, today_local().month, today_local().day)) is True

    def test_is_exact_birthday_false_for_other_day(self):
        other = today_local() + timedelta(days=10)
        assert main_module.is_exact_birthday(date(2000, other.month, other.day)) is False
