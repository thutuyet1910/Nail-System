"""
Test suite for Nail Salon Check-In System
Covers: Registration, Check-In, Referrals, Birthday Discounts,
        Loyalty Visits, Profile Updates, Phone Validation, Today's Queue

Run with:
    pytest app/test_checkin_system.py -v
"""

import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite:///./test_checkin.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from .database import Base, get_db
from .main import app
from . import models

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app, raise_server_exceptions=True)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


# ── Shared helpers ────────────────────────────────────────────────────────────

def register(phone, name, dob, email=None, referral_code=None):
    payload = {"full_name": name, "phone_number": phone, "date_of_birth": dob}
    if email:
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


def _get_first_service_id():
    services = client.get("/services").json()
    if services:
        return [services[0]["id"]]
    return [1]


def _set_dob_to_today(phone):
    today = date.today()
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    customer.date_of_birth = date(1990, today.month, today.day)
    db.commit()
    db.close()


def _give_referral_code(phone, code="ALICE"):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    customer.referral_code = code
    db.commit()
    db.close()


def _set_visit_cycle(phone, cycle, clear_today=True):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    if clear_today:
        db.query(models.Visit).filter(
            models.Visit.customer_id == customer.id,
            models.Visit.visit_date == date.today(),
        ).delete()
    customer.visit_count_cycle = cycle
    db.commit()
    db.close()


def _set_referral_discount_pending(phone, pending=True, percent=10):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    customer.referral_discount_pending = pending
    customer.referral_discount_percent = percent
    db.commit()
    db.close()


def _set_visit_discount_pending(phone, pending=True):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    customer.visit_discount_pending = pending
    db.commit()
    db.close()


def _get_customer(phone):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    db.close()
    return customer


def _move_visits_to_yesterday(phone):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    for visit in db.query(models.Visit).filter(models.Visit.customer_id == customer.id).all():
        visit.visit_date = date.today() - timedelta(days=1)
    db.commit()
    db.close()


def today_dob():
    today = date.today()
    return date(1990, today.month, today.day).isoformat()


def future_dob(days=5):
    target = date.today() + timedelta(days=days)
    return date(1990, target.month, target.day).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# 0. ROOT
# ══════════════════════════════════════════════════════════════════════════════

class TestRoot:

    def test_root_returns_running_message(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "running" in r.json()["message"].lower()


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
        r = register("5550000001", "Alice", "1990-03-15")
        data = r.json()
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

    def test_register_email_optional(self):
        r = register("5550000001", "Alice", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["email"] is None

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

    def test_checkin_increments_visit_cycle(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        _move_visits_to_yesterday("5550000001")
        checkin("5550000001")
        customer = _get_customer("5550000001")
        assert customer.visit_count_cycle == 2

    def test_checkin_twice_same_day_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        r = checkin("5550000001")
        assert r.status_code == 400
        assert "already checked in" in r.json()["detail"].lower()

    def test_checkin_nonexistent_customer_returns_404(self):
        r = checkin("5550000001")
        assert r.status_code == 404

    def test_checkin_requires_valid_service_ids(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.post("/customers/check-in/5550000001", json={"selected_service_ids": [99999]})
        assert r.status_code == 404
        assert "service" in r.json()["detail"].lower()

    def test_checkin_requires_at_least_one_service(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.post("/customers/check-in/5550000001", json={"selected_service_ids": []})
        assert r.status_code == 422

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
        customer = _get_customer("5550000001")
        assert customer.referral_code is None

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
        r = client.get("/today-checkins")
        assert r.status_code == 200
        checkins = r.json()["checkins"]
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

    def test_today_queue_shows_birthday_discount_for_birthday_customer(self):
        register("5550000001", "Alice", today_dob())
        checkin("5550000001")
        checkins = client.get("/today-checkins").json()["checkins"]
        assert checkins[0]["discount_type"] == "fixed"
        assert checkins[0]["discount_value"] == 10

    def test_today_queue_no_discount_for_non_birthday(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        checkins = client.get("/today-checkins").json()["checkins"]
        assert checkins[0]["discount_type"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 4. BIRTHDAY DISCOUNT
# ══════════════════════════════════════════════════════════════════════════════

class TestBirthdayDiscount:

    def test_birthday_discount_applied_on_birthday(self):
        register("5550000001", "Alice", today_dob())
        r = checkin("5550000001")
        assert r.status_code == 200
        discounts = r.json()["discounts_applied"]
        types = [d["type"] for d in discounts]
        assert "birthday" in types

    def test_birthday_discount_not_applied_on_non_birthday(self):
        register("5550000001", "Alice", "1990-03-15")
        r = checkin("5550000001")
        discounts = r.json()["discounts_applied"]
        types = [d["type"] for d in discounts]
        assert "birthday" not in types

    def test_birthday_discount_marks_used_month(self):
        register("5550000001", "Alice", today_dob())
        checkin("5550000001")
        customer = _get_customer("5550000001")
        expected_key = date.today().strftime("%Y-%m")
        assert customer.birthday_discount_used_month == expected_key

    def test_birthday_discount_not_applied_twice_same_month(self):
        register("5550000001", "Alice", today_dob())
        checkin("5550000001")
        _move_visits_to_yesterday("5550000001")
        r = checkin("5550000001")
        discounts = r.json()["discounts_applied"]
        types = [d["type"] for d in discounts]
        assert "birthday" not in types

    def test_birthday_discount_available_flag_on_birthday(self):
        register("5550000001", "Alice", today_dob())
        r = checkin("5550000001")
        # After applying, birthday_discount_available should be False
        # (used this month already)
        assert r.json()["birthday_discount_available"] is False

    def test_birthday_discount_amount_in_response(self):
        register("5550000001", "Alice", today_dob())
        r = checkin("5550000001")
        discounts = r.json()["discounts_applied"]
        birthday = next(d for d in discounts if d["type"] == "birthday")
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

    def test_apply_referral_increments_owner_count(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-06-20")
        _give_referral_code("5550000001", "ALICE")
        apply_referral("5550000002", "ALICE")
        customer = _get_customer("5550000001")
        assert customer.referral_count == 1

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

    def test_apply_nonexistent_code_returns_404(self):
        register("5550000001", "Alice", "1990-03-15")
        r = apply_referral("5550000001", "BADCD")
        assert r.status_code == 404

    def test_apply_referral_for_unknown_customer_returns_404(self):
        r = apply_referral("5559999999", "ALICE")
        assert r.status_code == 404

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

    def test_referral_discount_pending_after_8_referrals(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        # Seed count to 7 directly, then add one more via API
        db = TestingSessionLocal()
        owner = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        owner.referral_count = 7
        db.commit()
        db.close()
        register("5550000009", "Ninth", "1990-01-01")
        apply_referral("5550000009", "ALICE")
        customer = _get_customer("5550000001")
        assert customer.referral_discount_pending is True
        assert customer.referral_discount_percent == 15

    def test_referral_discount_pending_after_18_referrals(self):
        register("5550000001", "Alice", "1990-03-15")
        _give_referral_code("5550000001", "ALICE")
        db = TestingSessionLocal()
        owner = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        owner.referral_count = 17
        db.commit()
        db.close()
        register("5550000009", "Nineteenth", "1990-01-01")
        apply_referral("5550000009", "ALICE")
        customer = _get_customer("5550000001")
        assert customer.referral_discount_pending is True
        assert customer.referral_discount_percent == 20

    def test_referral_discount_applied_on_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_referral_discount_pending("5550000001", pending=True, percent=10)
        r = checkin("5550000001")
        discounts = r.json()["discounts_applied"]
        types = [d["type"] for d in discounts]
        assert "referral" in types

    def test_referral_discount_cleared_after_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_referral_discount_pending("5550000001", pending=True, percent=10)
        checkin("5550000001")
        customer = _get_customer("5550000001")
        assert customer.referral_discount_pending is False

    def test_referral_discount_not_applied_when_not_pending(self):
        register("5550000001", "Alice", "1990-03-15")
        r = checkin("5550000001")
        types = [d["type"] for d in r.json()["discounts_applied"]]
        assert "referral" not in types


# ══════════════════════════════════════════════════════════════════════════════
# 6. LOYALTY (VISIT) DISCOUNT
# ══════════════════════════════════════════════════════════════════════════════

class TestLoyaltyDiscount:

    def test_visit_discount_earned_at_10th_visit(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 9)
        checkin("5550000001")
        customer = _get_customer("5550000001")
        assert customer.visit_discount_pending is True

    def test_visit_discount_not_earned_before_10th_visit(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 8)
        checkin("5550000001")
        customer = _get_customer("5550000001")
        assert customer.visit_discount_pending is False

    def test_visit_discount_earned_at_20th_visit(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_cycle("5550000001", 19)
        checkin("5550000001")
        customer = _get_customer("5550000001")
        assert customer.visit_discount_pending is True

    def test_visit_discount_applied_on_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_discount_pending("5550000001", pending=True)
        r = checkin("5550000001")
        types = [d["type"] for d in r.json()["discounts_applied"]]
        assert "loyalty" in types

    def test_visit_discount_cleared_after_checkin(self):
        register("5550000001", "Alice", "1990-03-15")
        _set_visit_discount_pending("5550000001", pending=True)
        checkin("5550000001")
        customer = _get_customer("5550000001")
        assert customer.visit_discount_pending is False

    def test_visit_discount_not_applied_when_not_pending(self):
        register("5550000001", "Alice", "1990-03-15")
        r = checkin("5550000001")
        types = [d["type"] for d in r.json()["discounts_applied"]]
        assert "loyalty" not in types

    def test_multiple_discounts_can_stack(self):
        # Birthday + loyalty both pending at same time
        register("5550000001", "Alice", today_dob())
        _set_visit_discount_pending("5550000001", pending=True)
        r = checkin("5550000001")
        types = [d["type"] for d in r.json()["discounts_applied"]]
        assert "birthday" in types
        assert "loyalty" in types


# ══════════════════════════════════════════════════════════════════════════════
# 7. VISIT HISTORY
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
        r = client.get("/customers/5550000001/visits")
        assert r.status_code == 200
        assert r.json()["visit_count"] == 1

    def test_visit_history_includes_services(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        r = client.get("/customers/5550000001/visits")
        visits = r.json()["visits"]
        assert len(visits[0]["services"]) >= 1

    def test_visit_history_not_found_returns_404(self):
        r = client.get("/customers/5559999999/visits")
        assert r.status_code == 404

    def test_visit_history_accumulates_over_multiple_days(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        _move_visits_to_yesterday("5550000001")
        checkin("5550000001")
        r = client.get("/customers/5550000001/visits")
        assert r.json()["visit_count"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# 8. PROFILE UPDATES
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


# ══════════════════════════════════════════════════════════════════════════════
# 9. PHONE VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestPhoneValidation:

    def test_10_digit_phone_accepted(self):
        assert register("5550000001", "Alice", "1990-03-15").status_code == 201

    def test_phone_with_dashes_accepted(self):
        r = register("555-000-0001", "Alice", "1990-03-15")
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


# ══════════════════════════════════════════════════════════════════════════════
# 10. BIRTHDAY REMINDERS
# ══════════════════════════════════════════════════════════════════════════════

class TestBirthdayReminders:

    def test_upcoming_birthday_reminders_includes_birthday_today(self):
        register("5550000001", "Alice", today_dob(), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        phones = [c["phone_number"] for c in r.json()]
        assert "5550000001" in phones

    def test_upcoming_birthday_reminders_includes_within_5_days(self):
        register("5550000001", "Alice", future_dob(3), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_upcoming_birthday_reminders_excludes_beyond_5_days(self):
        register("5550000001", "Alice", future_dob(6))
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        assert len(r.json()) == 0

    def test_birthday_reminder_response_includes_days_until(self):
        register("5550000001", "Alice", future_dob(3))
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        if r.json():
            assert r.json()[0]["days_until_birthday"] == 3

    def test_birthday_reminder_includes_discount_amount(self):
        register("5550000001", "Alice", today_dob())
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        if r.json():
            assert r.json()[0]["birthday_discount_amount"] == 10