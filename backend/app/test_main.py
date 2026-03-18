"""
Test suite for Nail System API
Run with:  pytest app/test_main.py -v
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

# Import AFTER defining the engine so the override works
from .database import Base, get_db      # same package → relative import
from .main import app                   # same package → relative import
from . import models                    # same package → relative import

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
    """DOB string whose month/day lands exactly n days from today."""
    target = date.today() + timedelta(days=n)
    return date(1990, target.month, target.day).isoformat()


def register(phone: str, name: str, dob: str, email: str = None):
    payload = {"full_name": name, "phone_number": phone, "date_of_birth": dob}
    if email:
        payload["email"] = email
    return client.post("/customers/new", json=payload)


def checkin(phone: str):
    return client.post(f"/customers/check-in/{phone}")


def apply_referral(phone: str, code: str):
    return client.post("/referrals/apply", json={"phone_number": phone, "referral_code": code})


def update_phone(old: str, new: str):
    return client.patch(f"/customers/{old}/update-phone", json={"new_phone_number": new})


def give_referral_code(phone: str, code: str = "ALICE"):
    """Directly set a referral code on a customer via DB (bypasses 5-visit rule)."""
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    customer.referral_code = code
    db.commit()
    db.close()


def clear_visits_and_reset_cycle(phone: str):
    """Remove all visit records and reset cycle counter so a customer can check in again."""
    db = TestingSessionLocal()
    customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
    db.query(models.Visit).filter(models.Visit.customer_id == customer.id).delete()
    customer.visit_count_cycle = 0
    db.commit()
    db.close()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    """Fresh tables before every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


# ══════════════════════════════════════════════════════════════════════════════
# 1. REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

class TestRegistration:

    def test_register_new_customer_success(self):
        r = register("5550000001", "Alice", "1990-03-15", email="alice@example.com")
        assert r.status_code == 201
        data = r.json()
        assert data["full_name"] == "Alice"
        assert data["phone_number"] == "5550000001"
        assert data["date_of_birth"] == "1990-03-15"

    def test_register_duplicate_phone_fails(self):
        register("5550000001", "Alice", "1990-03-15")
        r = register("5550000001", "Alice2", "1991-01-01")
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"]

    def test_register_without_dob_fails(self):
        r = client.post("/customers/new", json={
            "full_name": "NoDOB",
            "phone_number": "5550000099",
        })
        assert r.status_code == 422   # Pydantic rejects missing required field

    def test_register_email_optional(self):
        r = register("5550000002", "Bob", "1985-06-20")
        assert r.status_code == 201
        assert r.json()["email"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. CHECK-IN
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckIn:

    def test_checkin_unknown_phone_returns_404(self):
        r = checkin("0000000000")
        assert r.status_code == 404

    def test_checkin_success(self):
        register("5550000001", "Alice", "1990-06-01")
        r = checkin("5550000001")
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Alice"
        assert data["visit_count"] == 1
        assert data["visit_count_cycle"] == 1

    def test_double_checkin_same_day_blocked(self):
        register("5550000001", "Alice", "1990-06-01")
        checkin("5550000001")
        r = checkin("5550000001")
        assert r.status_code == 400
        assert "already checked in" in r.json()["detail"]

    def test_referral_code_unlocked_after_5_visits(self):
        register("5550000001", "Alice", "1990-06-01")
        # Simulate 5 separate visits by clearing the visit record each time
        for i in range(5):
            clear_visits_and_reset_cycle("5550000001")
            # Also set visit_count_cycle to i so the 5th checkin tips it over
            db = TestingSessionLocal()
            customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
            customer.visit_count_cycle = i          # will become i+1 after check-in
            db.commit()
            db.close()
            checkin("5550000001")

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert customer.referral_code is not None
        assert len(customer.referral_code) == 5
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# 3. BIRTHDAY DISCOUNT
# ══════════════════════════════════════════════════════════════════════════════

class TestBirthdayDiscount:

    def test_birthday_discount_on_exact_birthday(self):
        register("5550000001", "Alice", birthday_in_n_days(0))
        r = checkin("5550000001")
        assert r.status_code == 200
        birthday_discounts = [d for d in r.json()["discounts_applied"] if d["type"] == "birthday"]
        assert len(birthday_discounts) == 1
        assert birthday_discounts[0]["amount"] == 10

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

    def test_birthday_discount_only_once_per_year(self):
        register("5550000001", "Alice", birthday_in_n_days(0))
        checkin("5550000001")

        # Reset visit but keep birthday_discount_used_month as this month → no second discount
        clear_visits_and_reset_cycle("5550000001")
        r2 = checkin("5550000001")
        birthday_discounts = [d for d in r2.json()["discounts_applied"] if d["type"] == "birthday"]
        assert len(birthday_discounts) == 0

    def test_birthday_discount_resets_next_year(self):
        register("5550000001", "Alice", birthday_in_n_days(0))
        checkin("5550000001")

        # Simulate it was used last year by backdating the used_month field
        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        customer.birthday_discount_used_month = "2000-03"   # old year
        db.commit()
        db.close()

        clear_visits_and_reset_cycle("5550000001")
        r2 = checkin("5550000001")
        birthday_discounts = [d for d in r2.json()["discounts_applied"] if d["type"] == "birthday"]
        assert len(birthday_discounts) == 1    # fires again after reset


# ══════════════════════════════════════════════════════════════════════════════
# 4. REFERRAL SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

class TestReferrals:

    def setup_alice_with_code(self):
        register("5550000001", "Alice", "1990-01-01")
        give_referral_code("5550000001", "ALICE")

    def test_referral_count_increments(self):
        self.setup_alice_with_code()
        register("5550000002", "Bob", "1992-05-10")
        apply_referral("5550000002", "ALICE")

        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert alice.referral_count == 1
        db.close()

    def test_referral_discount_awarded_at_3(self):
        self.setup_alice_with_code()
        for i, phone in enumerate(["5550000002", "5550000003", "5550000004"]):
            register(phone, f"Person{i}", f"199{i}-05-10")
            apply_referral(phone, "ALICE")

        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert alice.referral_count == 3
        assert alice.referral_discount_pending is True
        db.close()

    def test_referral_discount_not_awarded_before_3(self):
        self.setup_alice_with_code()
        for i, phone in enumerate(["5550000002", "5550000003"]):
            register(phone, f"Person{i}", f"199{i}-05-10")
            apply_referral(phone, "ALICE")

        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert alice.referral_discount_pending is False
        db.close()

    def test_referral_discount_does_not_stack(self):
        """Referring 6 people after already earning the discount should not re-award it."""
        self.setup_alice_with_code()
        for i in range(3):
            phone = f"555000000{i + 2}"
            register(phone, f"Person{i}", f"199{i}-05-10")
            apply_referral(phone, "ALICE")

        # Consume the discount
        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        alice.referral_discount_pending = False
        db.commit()
        db.close()

        for i in range(3, 6):
            phone = f"555000000{i + 2}"
            register(phone, f"Person{i}", f"199{i}-05-10")
            apply_referral(phone, "ALICE")

        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert alice.referral_discount_pending is False
        db.close()

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

        db = TestingSessionLocal()
        alice = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert alice.referral_discount_pending is False
        db.close()

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


# ══════════════════════════════════════════════════════════════════════════════
# 5. UPDATE PHONE NUMBER
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdatePhone:

    def test_update_phone_success(self):
        register("5550000001", "Alice", "1990-03-15")
        r = update_phone("5550000001", "5559999999")
        assert r.status_code == 200
        assert r.json()["phone_number"] == "5559999999"

    def test_old_phone_no_longer_works_after_update(self):
        register("5550000001", "Alice", "1990-03-15")
        update_phone("5550000001", "5559999999")
        r = client.get("/customers/by-phone/5550000001")
        assert r.status_code == 404

    def test_new_phone_works_after_update(self):
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


# ══════════════════════════════════════════════════════════════════════════════
# 6. BIRTHDAY REMINDERS
# ══════════════════════════════════════════════════════════════════════════════

class TestBirthdayReminders:

    def test_customer_appears_in_reminder_list_within_5_days(self):
        register("5550000001", "Alice", birthday_in_n_days(3), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert r.status_code == 200
        assert "Alice" in [c["full_name"] for c in r.json()]

    def test_customer_not_in_reminder_list_when_birthday_far(self):
        register("5550000001", "Alice", birthday_in_n_days(10), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert "Alice" not in [c["full_name"] for c in r.json()]

    def test_customer_appears_on_exact_birthday(self):
        register("5550000001", "Alice", birthday_in_n_days(0), email="alice@example.com")
        r = client.get("/birthday-reminders")
        assert "Alice" in [c["full_name"] for c in r.json()]


# ══════════════════════════════════════════════════════════════════════════════
# 7. LOYALTY VISIT DISCOUNT (every 10th visit → 10% off on next check-in)
# ══════════════════════════════════════════════════════════════════════════════

class TestLoyaltyDiscount:

    def prep(self, phone: str, cycle: int):
        """
        Set visit_count_cycle directly and wipe today's visit record
        so the customer can check in again.
        cycle = the value BEFORE the next check-in increments it.
        e.g. cycle=9 → next check-in becomes visit #10.
        """
        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == phone).first()
        db.query(models.Visit).filter(models.Visit.customer_id == customer.id).delete()
        customer.visit_count_cycle = cycle
        db.commit()
        db.close()

    def test_discount_awarded_on_10th_visit(self):
        register("5550000001", "Alice", "1990-06-01")
        self.prep("5550000001", 9)      # next check-in increments to 10 → 10 % 10 == 0
        checkin("5550000001")

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert customer.visit_discount_pending is True
        db.close()

    def test_discount_applied_on_11th_visit(self):
        register("5550000001", "Alice", "1990-06-01")
        self.prep("5550000001", 9)
        checkin("5550000001")           # visit #10 → discount awarded

        self.prep("5550000001", 10)     # cycle stays at 10 (won't re-trigger award on 11)
        r = checkin("5550000001")       # visit #11 → discount applied
        assert r.status_code == 200
        loyalty = [d for d in r.json()["discounts_applied"] if d["type"] == "loyalty"]
        assert len(loyalty) == 1
        assert loyalty[0]["percent"] == 10

    def test_discount_consumed_after_11th_visit(self):
        register("5550000001", "Alice", "1990-06-01")
        self.prep("5550000001", 9)
        checkin("5550000001")           # visit #10 → earns discount

        self.prep("5550000001", 10)
        checkin("5550000001")           # visit #11 → uses discount

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert customer.visit_discount_pending is False
        db.close()

    def test_discount_not_awarded_before_10th(self):
        register("5550000001", "Alice", "1990-06-01")
        self.prep("5550000001", 7)      # next check-in = visit #8
        checkin("5550000001")

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert customer.visit_discount_pending is False
        db.close()

    def test_discount_awarded_again_on_20th_visit(self):
        """Discount repeats every 10 visits — 20th visit should earn it again."""
        register("5550000001", "Alice", "1990-06-01")
        self.prep("5550000001", 19)     # next check-in = visit #20
        checkin("5550000001")

        db = TestingSessionLocal()
        customer = db.query(models.Customer).filter(models.Customer.phone_number == "5550000001").first()
        assert customer.visit_discount_pending is True
        db.close()