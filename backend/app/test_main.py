"""
Test suite for Nail System API
Run with: pytest app/test_main.py -v
"""

import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── In-memory test database ───────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite:///./test_nail.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from .database import Base, get_db
from .main import app
from . import models
import app.main as main_module

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app, raise_server_exceptions=True)


# ── Shared helpers ────────────────────────────────────────────────────────────

def birthday_in_n_days(n: int) -> str:
    target = date.today() + timedelta(days=n)
    return date(1990, target.month, target.day).isoformat()


def register(phone: str, name: str, dob: str, email: str = None):
    payload = {"full_name": name, "phone_number": phone, "date_of_birth": dob}
    if email is not None:
        payload["email"] = email
    return client.post("/customers/new", json=payload)


def checkin(phone: str):
    return client.post(f"/customers/check-in/{phone}")


def apply_referral(phone: str, code: str):
    return client.post("/referrals/apply", json={"phone_number": phone, "referral_code": code})


def update_phone(old: str, new: str):
    return client.patch(f"/customers/{old}/update-phone", json={"new_phone_number": new})


def update_profile(old_phone: str, full_name: str, new_phone: str, email=None):
    return client.patch(
        f"/customers/{old_phone}/profile",
        json={
            "full_name": full_name,
            "phone_number": new_phone,
            "email": email,
        },
    )


def give_referral_code(phone: str, code: str = "ALICE"):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    customer.referral_code = code
    db.commit()
    db.close()


def set_cycle(phone: str, cycle: int):
    """Set visit_count_cycle and wipe today's visits so customer can check in again."""
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    db.query(models.Visit).filter(models.Visit.customer_id == customer.id).delete()
    customer.visit_count_cycle = cycle
    db.commit()
    db.close()


def clear_visits_and_reset_cycle(phone: str):
    set_cycle(phone, 0)


def move_all_customer_visits_to_yesterday(phone: str):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    visits = db.query(models.Visit).filter(models.Visit.customer_id == customer.id).all()
    for visit in visits:
        visit.visit_date = date.today() - timedelta(days=1)
    db.commit()
    db.close()


def get_customer(phone: str):
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    db.close()
    return customer


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    """Fresh tables before every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


# ══════════════════════════════════════════════════════════════════════════════
# 0. ROOT
# ══════════════════════════════════════════════════════════════════════════════

class TestRoot:

    def test_root_success(self):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["message"] == "Nail System API is running"


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
        assert data["date_of_birth"] == "1990-03-15"
        assert data["email"] == "alice@example.com"
        assert data["visit_count_cycle"] == 0
        assert data["referral_code"] is None

    def test_register_sets_defaults(self):
        r = register("5550000001", "Alice", "1990-03-15")
        data = r.json()
        assert data["referral_count"] == 0
        assert data["referral_discount_pending"] is False
        assert data["visit_discount_pending"] is False
        assert data["birthday_discount_used_month"] is None
        assert data["used_referral_code"] is None

    def test_register_phone_formatted_field(self):
        r = register("5550000001", "Alice", "1990-03-15")
        assert r.json()["phone_number_formatted"] == "(555) 000-0001"

    def test_register_duplicate_phone_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        r = register("5550000001", "Alice2", "1991-01-01")
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"]

    def test_register_without_dob_fails(self):
        r = client.post("/customers/new", json={"full_name": "NoDOB", "phone_number": "5550000099"})
        assert r.status_code == 422

    def test_register_email_optional(self):
        r = register("5550000002", "Bob", "1985-06-20")
        assert r.status_code == 201
        assert r.json()["email"] is None

    def test_register_blank_email_becomes_none(self):
        r = register("5550000003", "Carol", "1985-06-20", email="")
        assert r.status_code == 201
        assert r.json()["email"] is None

    def test_register_phone_too_short_rejected(self):
        r = register("12345", "Dave", "1990-03-15")
        assert r.status_code == 422

    def test_register_phone_too_long_rejected(self):
        r = register("55500000011111", "Eve", "1990-03-15")
        assert r.status_code == 422

    def test_register_phone_with_dashes_normalized(self):
        r = register("555-000-0002", "Bob", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000002"

    def test_register_phone_with_spaces_normalized(self):
        r = register("555 000 0003", "Carol", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000003"


# ══════════════════════════════════════════════════════════════════════════════
# 2. CUSTOMER LOOKUP
# ══════════════════════════════════════════════════════════════════════════════

class TestLookup:

    def test_get_by_phone_success(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.get("/customers/by-phone/5550000001")
        assert r.status_code == 200
        assert r.json()["full_name"] == "Alice"

    def test_get_by_phone_not_found(self):
        r = client.get("/customers/by-phone/0000000000")
        assert r.status_code == 404

    def test_get_by_phone_invalid_digits_rejected(self):
        r = client.get("/customers/by-phone/123")
        assert r.status_code == 422

    def test_check_in_status_not_checked_in(self):
        register("5550000001", "Alice", "1990-03-15")
        r = client.get("/customers/check-in-status/5550000001")
        assert r.status_code == 200
        assert r.json()["already_checked_in_today"] is False

    def test_check_in_status_already_checked_in(self):
        register("5550000001", "Alice", "1990-03-15")
        checkin("5550000001")
        r = client.get("/customers/check-in-status/5550000001")
        assert r.status_code == 200
        assert r.json()["already_checked_in_today"] is True

    def test_check_in_status_not_found(self):
        r = client.get("/customers/check-in-status/0000000000")
        assert r.status_code == 404

    def test_get_all_customers(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-05-10")
        r = client.get("/customers")
        assert r.status_code == 200
        assert len(r.json()) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 3. CHECK-IN
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckIn:

    def test_checkin_unknown_phone_returns_404(self):
        r = checkin("0000000000")
        assert r.status_code == 404

    def test_checkin_invalid_phone_returns_422(self):
        r = checkin("123")
        assert r.status_code == 422

    def test_checkin_success(self):
        register("5550000001", "Alice", "1990-06-01")
        r = checkin("5550000001")
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Alice"
        assert data["visit_count"] == 1
        assert data["visit_count_cycle"] == 1
        assert data["discounts_applied"] == []

    def test_checkin_increments_visit_count(self):
        register("5550000001", "Alice", "1990-06-01")
        checkin("5550000001")

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        visit = db.query(models.Visit).filter(models.Visit.customer_id == customer.id).first()
        visit.visit_date = date.today() - timedelta(days=1)
        db.commit()
        db.close()

        checkin("5550000001")
        r = client.get("/customers/5550000001/visits")
        assert r.status_code == 200
        assert r.json()["visit_count"] == 2

    def test_double_checkin_same_day_blocked(self):
        register("5550000001", "Alice", "1990-06-01")
        checkin("5550000001")
        r = checkin("5550000001")
        assert r.status_code == 400
        assert "already checked in" in r.json()["detail"]

    def test_returning_customer_can_check_in_next_day(self):
        register("5550000001", "Alice", "1990-06-01")
        first = checkin("5550000001")
        assert first.status_code == 200

        move_all_customer_visits_to_yesterday("5550000001")

        status = client.get("/customers/check-in-status/5550000001")
        assert status.status_code == 200
        assert status.json()["already_checked_in_today"] is False

        second = checkin("5550000001")
        assert second.status_code == 200
        assert second.json()["visit_count"] == 2

    def test_referral_code_unlocked_after_5_visits(self):
        register("5550000001", "Alice", "1990-06-01")
        for i in range(5):
            set_cycle("5550000001", i)
            checkin("5550000001")

        customer = get_customer("5550000001")
        assert customer.referral_code is not None
        assert len(customer.referral_code) == 5

    def test_referral_code_not_unlocked_before_5_visits(self):
        register("5550000001", "Alice", "1990-06-01")
        for i in range(4):
            set_cycle("5550000001", i)
            checkin("5550000001")

        customer = get_customer("5550000001")
        assert customer.referral_code is None

    def test_today_checkins_list(self):
        register("5550000001", "Alice", "1990-06-01")
        register("5550000002", "Bob", "1992-05-10")
        checkin("5550000001")
        checkin("5550000002")
        r = client.get("/today-checkins")
        assert r.status_code == 200
        checkins = r.json()["checkins"]
        assert len(checkins) == 2
        assert checkins[0]["position"] == 1
        assert checkins[1]["position"] == 2

    def test_today_checkins_empty(self):
        r = client.get("/today-checkins")
        assert r.status_code == 200
        assert r.json()["checkins"] == []


# ══════════════════════════════════════════════════════════════════════════════
# 4. BIRTHDAY DISCOUNT
# ══════════════════════════════════════════════════════════════════════════════

class TestBirthdayDiscount:

    def test_birthday_discount_on_exact_birthday(self):
        register("5550000001", "Alice", birthday_in_n_days(0))
        r = checkin("5550000001")
        assert r.status_code == 200
        birthday_discounts = [d for d in r.json()["discounts_applied"] if d["type"] == "birthday"]
        assert len(birthday_discounts) == 1
        assert birthday_discounts[0]["amount"] == 10

    def test_birthday_discount_description_present(self):
        register("5550000001", "Alice", birthday_in_n_days(0))
        r = checkin("5550000001")
        bd = [d for d in r.json()["discounts_applied"] if d["type"] == "birthday"][0]
        assert "birthday" in bd["description"].lower()

    def test_birthday_discount_not_given_day_before(self):
        register("5550000001", "Alice", birthday_in_n_days(1))
        r = checkin("5550000001")
        birthday_discounts = [d for d in r.json()["discounts_applied"] if d["type"] == "birthday"]
        assert len(birthday_discounts) == 0

    def test_birthday_discount_not_given_day_after(self):
        register("5550000001", "Alice", birthday_in_n_days(-1))
        r = checkin("5550000001")
        birthday_discounts = [d for d in r.json()["discounts_applied"] if d["type"] == "birthday"]
        assert len(birthday_discounts) == 0

    def test_birthday_discount_only_once_per_month_key(self):
        register("5550000001", "Alice", birthday_in_n_days(0))
        checkin("5550000001")
        clear_visits_and_reset_cycle("5550000001")
        r2 = checkin("5550000001")
        birthday_discounts = [d for d in r2.json()["discounts_applied"] if d["type"] == "birthday"]
        assert len(birthday_discounts) == 0

    def test_birthday_discount_resets_when_used_month_changes(self):
        register("5550000001", "Alice", birthday_in_n_days(0))
        checkin("5550000001")

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        customer.birthday_discount_used_month = "2000-03"
        db.commit()
        db.close()

        clear_visits_and_reset_cycle("5550000001")
        r2 = checkin("5550000001")
        birthday_discounts = [d for d in r2.json()["discounts_applied"] if d["type"] == "birthday"]
        assert len(birthday_discounts) == 1

    def test_birthday_discount_marks_used_month(self):
        register("5550000001", "Alice", birthday_in_n_days(0))
        checkin("5550000001")
        customer = get_customer("5550000001")
        expected = date.today().strftime("%Y-%m")
        assert customer.birthday_discount_used_month == expected


# ══════════════════════════════════════════════════════════════════════════════
# 5. REFERRAL SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

class TestReferrals:

    def setup_alice_with_code(self):
        register("5550000001", "Alice", "1990-01-01")
        give_referral_code("5550000001", "ALICE")

    def test_referral_count_increments(self):
        self.setup_alice_with_code()
        register("5550000002", "Bob", "1992-05-10")
        apply_referral("5550000002", "ALICE")
        assert get_customer("5550000001").referral_count == 1

    def test_referral_discount_awarded_at_3(self):
        self.setup_alice_with_code()
        for i, phone in enumerate(["5550000002", "5550000003", "5550000004"]):
            register(phone, f"Person{i}", f"199{i}-05-10")
            apply_referral(phone, "ALICE")

        alice = get_customer("5550000001")
        assert alice.referral_count == 3
        assert alice.referral_discount_pending is True
        assert alice.referral_discount_percent == 10

    def test_referral_discount_not_awarded_before_3(self):
        self.setup_alice_with_code()
        for i, phone in enumerate(["5550000002", "5550000003"]):
            register(phone, f"Person{i}", f"199{i}-05-10")
            apply_referral(phone, "ALICE")

        assert get_customer("5550000001").referral_discount_pending is False

    def test_referral_discount_awarded_at_8(self):
        self.setup_alice_with_code()
        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        alice.referral_count = 7
        db.commit()
        db.close()

        register("5550000002", "Bob", "1992-05-10")
        apply_referral("5550000002", "ALICE")

        alice = get_customer("5550000001")
        assert alice.referral_discount_pending is True
        assert alice.referral_discount_percent == 15

    def test_referral_discount_awarded_at_18(self):
        self.setup_alice_with_code()
        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        alice.referral_count = 17
        db.commit()
        db.close()

        register("5550000002", "Bob", "1992-05-10")
        apply_referral("5550000002", "ALICE")

        alice = get_customer("5550000001")
        assert alice.referral_discount_pending is True
        assert alice.referral_discount_percent == 20

    def test_referral_discount_does_not_stack_while_pending(self):
        self.setup_alice_with_code()
        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        alice.referral_count = 2
        alice.referral_discount_pending = True
        db.commit()
        db.close()

        register("5550000002", "Bob", "1992-05-10")
        apply_referral("5550000002", "ALICE")

        alice = get_customer("5550000001")
        assert alice.referral_count == 3
        assert alice.referral_discount_pending is True

    def test_referral_discount_applied_at_checkin(self):
        self.setup_alice_with_code()
        for i, phone in enumerate(["5550000002", "5550000003", "5550000004"]):
            register(phone, f"Person{i}", f"199{i}-05-10")
            apply_referral(phone, "ALICE")

        r = checkin("5550000001")
        assert r.status_code == 200
        ref_discounts = [d for d in r.json()["discounts_applied"] if d["type"] == "referral"]
        assert len(ref_discounts) == 1
        assert ref_discounts[0]["percent"] == 10

    def test_referral_discount_consumed_after_checkin(self):
        self.setup_alice_with_code()
        for i, phone in enumerate(["5550000002", "5550000003", "5550000004"]):
            register(phone, f"Person{i}", f"199{i}-05-10")
            apply_referral(phone, "ALICE")

        checkin("5550000001")
        assert get_customer("5550000001").referral_discount_pending is False

    def test_cannot_use_own_referral_code(self):
        self.setup_alice_with_code()
        r = apply_referral("5550000001", "ALICE")
        assert r.status_code == 400
        assert "own" in r.json()["detail"]

    def test_cannot_use_referral_code_twice(self):
        self.setup_alice_with_code()
        register("5550000002", "Bob", "1992-05-10")
        apply_referral("5550000002", "ALICE")
        r = apply_referral("5550000002", "ALICE")
        assert r.status_code == 400
        assert "already used" in r.json()["detail"]

    def test_invalid_referral_code_returns_404(self):
        register("5550000002", "Bob", "1992-05-10")
        r = apply_referral("5550000002", "XXXXX")
        assert r.status_code == 404

    def test_referral_code_linked_on_customer(self):
        self.setup_alice_with_code()
        register("5550000002", "Bob", "1992-05-10")
        apply_referral("5550000002", "ALICE")
        bob = get_customer("5550000002")
        assert bob.used_referral_code == "ALICE"
        assert bob.used_referral_from_customer_id is not None


# ══════════════════════════════════════════════════════════════════════════════
# 6. UPDATE PHONE NUMBER
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdatePhone:

    def test_update_phone_success(self):
        register("5550000001", "Alice", "1990-03-15")
        r = update_phone("5550000001", "5559999999")
        assert r.status_code == 200
        assert r.json()["phone_number"] == "5559999999"

    def test_rewards_preserved_after_update(self):
        register("5550000001", "Alice", "1990-03-15")
        give_referral_code("5550000001", "ALICE")

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        customer.referral_count = 2
        customer.visit_count_cycle = 4
        customer.referral_discount_pending = True
        customer.visit_discount_pending = True
        db.commit()
        db.close()

        update_phone("5550000001", "5559999999")
        customer = get_customer("5559999999")
        assert customer.referral_code == "ALICE"
        assert customer.referral_count == 2
        assert customer.visit_count_cycle == 4
        assert customer.referral_discount_pending is True
        assert customer.visit_discount_pending is True

    def test_old_phone_no_longer_works(self):
        register("5550000001", "Alice", "1990-03-15")
        update_phone("5550000001", "5559999999")
        assert client.get("/customers/by-phone/5550000001").status_code == 404

    def test_new_phone_works(self):
        register("5550000001", "Alice", "1990-03-15")
        update_phone("5550000001", "5559999999")
        r = client.get("/customers/by-phone/5559999999")
        assert r.status_code == 200
        assert r.json()["full_name"] == "Alice"

    def test_update_to_same_phone_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        r = update_phone("5550000001", "5550000001")
        assert r.status_code == 400
        assert "same" in r.json()["detail"]

    def test_update_to_taken_phone_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-05-10")
        r = update_phone("5550000001", "5550000002")
        assert r.status_code == 400
        assert "already in use" in r.json()["detail"]

    def test_update_unknown_phone_returns_404(self):
        r = update_phone("0000000000", "5559999999")
        assert r.status_code == 404

    def test_update_phone_invalid_new_number_rejected(self):
        register("5550000001", "Alice", "1990-03-15")
        r = update_phone("5550000001", "123")
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 7. UPDATE PROFILE
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateProfile:

    def test_update_profile_success(self):
        register("5550000001", "Alice", "1990-03-15", email="alice@example.com")
        r = update_profile("5550000001", "Alice Johnson", "5559999999", "newalice@example.com")
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Alice Johnson"
        assert data["phone_number"] == "5559999999"
        assert data["email"] == "newalice@example.com"

    def test_update_profile_keeps_same_rewards_and_history_fields(self):
        register("5550000001", "Alice", "1990-03-15", email="alice@example.com")
        give_referral_code("5550000001", "ALICE")

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        customer.referral_count = 4
        customer.referral_discount_pending = True
        customer.visit_count_cycle = 7
        customer.visit_discount_pending = True
        customer.used_referral_code = "SOME1"
        customer.used_referral_from_customer_id = customer.id
        customer.birthday_discount_used_month = "2026-03"
        customer_id = customer.id
        db.commit()
        db.close()

        r = update_profile("5550000001", "Alice Updated", "5558888888", "updated@example.com")
        assert r.status_code == 200

        db = TestingSessionLocal()
        updated = db.query(models.Customer).filter(models.Customer.phone_number == "5558888888").first()
        db.close()

        assert updated.id == customer_id
        assert updated.referral_code == "ALICE"
        assert updated.referral_count == 4
        assert updated.referral_discount_pending is True
        assert updated.visit_count_cycle == 7
        assert updated.visit_discount_pending is True
        assert updated.used_referral_code == "SOME1"
        assert updated.used_referral_from_customer_id == customer_id
        assert updated.birthday_discount_used_month == "2026-03"

    def test_update_profile_blank_email_becomes_none(self):
        register("5550000001", "Alice", "1990-03-15", email="alice@example.com")
        r = update_profile("5550000001", "Alice", "5550000001", "")
        assert r.status_code == 200
        assert r.json()["email"] is None

    def test_update_profile_can_change_name_only(self):
        register("5550000001", "Alice", "1990-03-15", email="alice@example.com")
        r = update_profile("5550000001", "Alice Smith", "5550000001", "alice@example.com")
        assert r.status_code == 200
        assert r.json()["full_name"] == "Alice Smith"
        assert r.json()["phone_number"] == "5550000001"

    def test_update_profile_can_change_email_only(self):
        register("5550000001", "Alice", "1990-03-15", email="alice@example.com")
        r = update_profile("5550000001", "Alice", "5550000001", "updated@example.com")
        assert r.status_code == 200
        assert r.json()["email"] == "updated@example.com"

    def test_update_profile_old_phone_no_longer_works_when_phone_changed(self):
        register("5550000001", "Alice", "1990-03-15")
        update_profile("5550000001", "Alice", "5557777777", None)
        assert client.get("/customers/by-phone/5550000001").status_code == 404

    def test_update_profile_new_phone_works_when_phone_changed(self):
        register("5550000001", "Alice", "1990-03-15")
        update_profile("5550000001", "Alice", "5557777777", None)
        r = client.get("/customers/by-phone/5557777777")
        assert r.status_code == 200
        assert r.json()["full_name"] == "Alice"

    def test_update_profile_to_taken_phone_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        register("5550000002", "Bob", "1992-05-10")
        r = update_profile("5550000001", "Alice", "5550000002", None)
        assert r.status_code == 400
        assert "already in use" in r.json()["detail"]

    def test_update_profile_unknown_phone_returns_404(self):
        r = update_profile("0000000000", "Ghost", "5559999999", None)
        assert r.status_code == 404

    def test_update_profile_invalid_new_phone_rejected(self):
        register("5550000001", "Alice", "1990-03-15")
        r = update_profile("5550000001", "Alice", "123", None)
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 8. CUSTOMER VISITS ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

class TestCustomerVisits:

    def test_customer_visits_success(self):
        register("5550000001", "Alice", "1990-06-01")
        checkin("5550000001")
        r = client.get("/customers/5550000001/visits")
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Alice"
        assert data["visit_count"] == 1
        assert len(data["visits"]) == 1

    def test_customer_visits_not_found(self):
        r = client.get("/customers/0000000000/visits")
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 9. BIRTHDAY REMINDERS
# ══════════════════════════════════════════════════════════════════════════════

class TestBirthdayReminders:

    def test_appears_within_5_days(self):
        register("5550000001", "Alice", birthday_in_n_days(3), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        assert "Alice" in [c["full_name"] for c in r.json()]

    def test_appears_on_exact_birthday(self):
        register("5550000001", "Alice", birthday_in_n_days(0), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        assert "Alice" in [c["full_name"] for c in r.json()]

    def test_not_in_list_when_birthday_far(self):
        register("5550000001", "Alice", birthday_in_n_days(10), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        assert "Alice" not in [c["full_name"] for c in r.json()]

    def test_reminder_includes_discount_amount(self):
        register("5550000001", "Alice", birthday_in_n_days(1), email="alice@example.com")
        r = client.get("/birthday-reminders")
        alice = next(c for c in r.json() if c["full_name"] == "Alice")
        assert alice["birthday_discount_amount"] == 10
        assert alice["days_until_birthday"] == 1

    def test_send_birthday_reminders_success(self, monkeypatch):
        register("5550000001", "Alice", birthday_in_n_days(1), email="alice@example.com")

        sent = []

        def fake_send_birthday_email(to_email, customer_name, discount_amount):
            sent.append((to_email, customer_name, discount_amount))

        monkeypatch.setattr(main_module, "send_birthday_email", fake_send_birthday_email)

        r = client.post("/birthday-reminders/send")
        assert r.status_code == 200
        data = r.json()
        assert data["sent"] == 1
        assert len(sent) == 1
        assert sent[0][0] == "alice@example.com"

    def test_send_birthday_reminders_skips_without_email(self, monkeypatch):
        register("5550000001", "Alice", birthday_in_n_days(1), email=None)

        sent = []

        def fake_send_birthday_email(to_email, customer_name, discount_amount):
            sent.append((to_email, customer_name, discount_amount))

        monkeypatch.setattr(main_module, "send_birthday_email", fake_send_birthday_email)

        r = client.post("/birthday-reminders/send")
        assert r.status_code == 200
        data = r.json()
        assert data["sent"] == 0
        assert data["skipped"] >= 1
        assert len(sent) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 10. LOYALTY VISIT DISCOUNT
# ══════════════════════════════════════════════════════════════════════════════

class TestLoyaltyDiscount:

    def test_discount_awarded_on_10th_visit(self):
        register("5550000001", "Alice", "1990-06-01")
        set_cycle("5550000001", 9)
        checkin("5550000001")
        assert get_customer("5550000001").visit_discount_pending is True

    def test_discount_applied_on_11th_visit(self):
        register("5550000001", "Alice", "1990-06-01")
        set_cycle("5550000001", 9)
        checkin("5550000001")
        set_cycle("5550000001", 10)
        r = checkin("5550000001")
        assert r.status_code == 200
        loyalty = [d for d in r.json()["discounts_applied"] if d["type"] == "loyalty"]
        assert len(loyalty) == 1
        assert loyalty[0]["percent"] == 10

    def test_discount_consumed_after_use(self):
        register("5550000001", "Alice", "1990-06-01")
        set_cycle("5550000001", 9)
        checkin("5550000001")
        set_cycle("5550000001", 10)
        checkin("5550000001")
        assert get_customer("5550000001").visit_discount_pending is False

    def test_discount_not_awarded_before_10th(self):
        register("5550000001", "Alice", "1990-06-01")
        set_cycle("5550000001", 7)
        checkin("5550000001")
        assert get_customer("5550000001").visit_discount_pending is False

    def test_discount_awarded_again_on_20th_visit(self):
        register("5550000001", "Alice", "1990-06-01")
        set_cycle("5550000001", 19)
        checkin("5550000001")
        assert get_customer("5550000001").visit_discount_pending is True

    def test_10th_visit_does_not_apply_discount_same_visit(self):
        register("5550000001", "Alice", "1990-06-01")
        set_cycle("5550000001", 9)
        r = checkin("5550000001")
        loyalty = [d for d in r.json()["discounts_applied"] if d["type"] == "loyalty"]
        assert len(loyalty) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 11. PHONE VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestPhoneValidation:

    def test_valid_10_digit_phone_accepted(self):
        assert register("5550000001", "Alice", "1990-03-15").status_code == 201

    def test_phone_too_short_rejected(self):
        assert register("12345", "Dave", "1990-03-15").status_code == 422

    def test_phone_too_long_rejected(self):
        assert register("55500000011111", "Eve", "1990-03-15").status_code == 422

    def test_phone_with_dashes_accepted(self):
        r = register("555-000-0002", "Bob", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000002"

    def test_phone_with_spaces_accepted(self):
        r = register("555 000 0003", "Carol", "1990-03-15")
        assert r.status_code == 201
        assert r.json()["phone_number"] == "5550000003"

    def test_checkin_invalid_phone_rejected(self):
        assert client.post("/customers/check-in/123").status_code == 422

    def test_update_phone_invalid_new_number_rejected(self):
        register("5550000001", "Alice", "1990-03-15")
        assert update_phone("5550000001", "123").status_code == 422

    def test_update_profile_invalid_new_number_rejected(self):
        register("5550000001", "Alice", "1990-03-15")
        assert update_profile("5550000001", "Alice", "123", None).status_code == 422

    def test_referral_apply_invalid_phone_rejected(self):
        r = client.post("/referrals/apply", json={"phone_number": "123", "referral_code": "ALICE"})
        assert r.status_code == 422