"""
Test suite for the Nail Salon backend (updated for v0.4.0).

Covers: Technicians, Appointments, Turns/Dispatch, Checkout, Inventory, Income Reports,
plus the four fixes:
  1. Fair auto-assign (fewest turns first)
  2. Server-calculated checkout math
  3. Ordered turn statuses
  4. SQLite foreign keys enforced

    pip install pytest httpx
    pytest test_main.py -v
"""

import os

# The app must point at a THROWAWAY database before anything imports `database`.
# (reset_db below drops every table, so it must never touch nail_system.db.)
TEST_DB_FILE = "test_main.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_FILE}"

from datetime import date, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

import models  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402

# Safety net: refuse to run (and drop tables) against anything but the test database.
assert TEST_DB_FILE in str(engine.url), (
    f"Tests are pointing at {engine.url}. Another module imported `database` first; "
    "run pytest from the project folder with only this test file."
)

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite.*Decimal")

client = TestClient(app, raise_server_exceptions=True)


# A throwaway route that raises a raw database error, used to test the 409 handler.
@app.get("/__test_integrity_error")
def _raise_integrity_error():
    raise IntegrityError("INSERT ...", {}, Exception("FOREIGN KEY constraint failed"))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(scope="session", autouse=True)
def remove_test_db_file():
    yield
    engine.dispose()
    try:
        os.remove(TEST_DB_FILE)
    except OSError:
        pass


# ── Shared helpers ────────────────────────────────────────────────────────────

def make_tech(
    full_name="Mia",
    status="active",
    availability="available today",
    specialties="acrylic, gel",
    employee_id=None,
):
    return client.post("/technicians", json={
        "full_name": full_name,
        "status": status,
        "availability": availability,
        "specialties": specialties,
        "employee_id": employee_id,
    })


def make_appointment(
    customer_name="Alice",
    customer_phone="5550000001",
    service_category="Gel Manicure",
    appointment_time=None,
    technician_id=None,
):
    if appointment_time is None:
        appointment_time = datetime.now().replace(microsecond=0).isoformat()
    payload = {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service_category": service_category,
        "appointment_time": appointment_time,
    }
    if technician_id:
        payload["technician_id"] = technician_id
    return client.post("/appointments", json=payload)


def make_turn(technician_id, customer_name="Alice", service_name="Acrylic Full Set"):
    """A turn in 'waiting' status (counts as an open turn for that technician)."""
    return client.post("/turns", json={
        "customer_name": customer_name,
        "service_name": service_name,
        "technician_id": technician_id,
        "status": "waiting",
        "source": "checkin",
    })


def give_turn(technician_id, customer_name="Alice", service_name="Acrylic Full Set", complete=True):
    """Assigns a customer to a technician. By default the turn is completed, so the tech is free again."""
    r = client.post("/turns/assign-next", json={
        "customer_name": customer_name,
        "service_name": service_name,
        "technician_id": technician_id,
        "source": "manual",
    })
    assert r.status_code == 200, r.text
    turn = r.json()
    if complete:
        assert client.put(f"/turns/{turn['id']}/complete", json={}).status_code == 200
    return turn


def auto_assign(customer_name="Alice", service_name="Acrylic Full Set", **extra):
    return client.post("/turns/assign-auto", json={
        "customer_name": customer_name,
        "service_name": service_name,
        **extra,
    })


def get_turn_today(turn_id):
    return next(t for t in client.get("/turns/today").json() if t["id"] == turn_id)


def make_checkout(
    customer_name="Alice",
    customer_phone=None,
    service_name="Gel Manicure",
    subtotal=100.0,
    tip_amount=0.0,
    technician_id=None,
    turn_id=None,
    appointment_id=None,
    discount_type="none",
    discount_value=0.0,
    payment_method="cash",
    **extra,
):
    """Sends INPUTS only. Anything in **extra is sent too (used to test forged numbers)."""
    payload = {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service_name": service_name,
        "subtotal": subtotal,
        "tip_amount": tip_amount,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "payment_method": payment_method,
    }
    if technician_id:
        payload["technician_id"] = technician_id
    if turn_id:
        payload["turn_id"] = turn_id
    if appointment_id:
        payload["appointment_id"] = appointment_id
    payload.update(extra)
    return client.post("/checkouts", json=payload)


def make_inventory(
    item_name="Acrylic Powder",
    category="Supplies",
    quantity=10,
    unit_price=15.0,
    purchase_date=None,
    low_stock_level=3,
):
    return client.post("/inventory", json={
        "item_name": item_name,
        "category": category,
        "quantity": quantity,
        "unit_price": unit_price,
        "purchase_date": purchase_date or date.today().isoformat(),
        "low_stock_level": low_stock_level,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 1. TECHNICIANS
# ══════════════════════════════════════════════════════════════════════════════

class TestTechnicians:

    def test_create_technician_success(self):
        r = make_tech("Mia")
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Mia"
        assert data["status"] == "active"
        assert data["availability"] == "available today"
        assert data["id"] is not None

    def test_create_duplicate_name_fails(self):
        make_tech("Mia")
        r = make_tech("Mia")
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"].lower()

    def test_create_duplicate_name_case_insensitive(self):
        make_tech("Mia")
        r = make_tech("mia")
        assert r.status_code == 400

    def test_create_duplicate_employee_id_fails(self):
        make_tech("Mia", employee_id="EMP001")
        r = make_tech("Lisa", employee_id="EMP001")
        assert r.status_code == 400
        assert "employee id" in r.json()["detail"].lower()

    def test_create_with_invalid_status_fails(self):
        r = client.post("/technicians", json={
            "full_name": "Mia",
            "status": "unknown_status",
            "availability": "available today",
        })
        assert r.status_code == 422

    def test_create_with_invalid_availability_fails(self):
        r = client.post("/technicians", json={
            "full_name": "Mia",
            "status": "active",
            "availability": "flying",
        })
        assert r.status_code == 422

    def test_create_with_invalid_phone_fails(self):
        r = client.post("/technicians", json={
            "full_name": "Mia",
            "status": "active",
            "availability": "available today",
            "phone": "12345",
        })
        assert r.status_code == 422

    def test_get_all_technicians(self):
        make_tech("Mia")
        make_tech("Lisa")
        r = client.get("/technicians")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_technician_by_id(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.get(f"/technicians/{tech_id}")
        assert r.status_code == 200
        assert r.json()["full_name"] == "Mia"

    def test_get_nonexistent_technician_returns_404(self):
        assert client.get("/technicians/9999").status_code == 404

    def test_search_technician_by_name(self):
        make_tech("Mia")
        make_tech("Lisa")
        r = client.get("/technicians?search=mi")
        assert r.status_code == 200
        names = [t["full_name"] for t in r.json()]
        assert "Mia" in names
        assert "Lisa" not in names

    def test_filter_technician_by_status(self):
        make_tech("Mia", status="active")
        make_tech("Lisa", status="off", availability="off today")
        r = client.get("/technicians?status=active")
        assert r.status_code == 200
        assert all(t["status"] == "active" for t in r.json())

    def test_filter_technician_by_specialty(self):
        make_tech("Mia", specialties="acrylic")
        make_tech("Lisa", specialties="waxing")
        r = client.get("/technicians?specialty=acrylic")
        assert r.status_code == 200
        names = [t["full_name"] for t in r.json()]
        assert "Mia" in names
        assert "Lisa" not in names

    def test_update_technician_name(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.put(f"/technicians/{tech_id}", json={"full_name": "Mia Updated"})
        assert r.status_code == 200
        assert r.json()["full_name"] == "Mia Updated"

    def test_update_technician_name_to_existing_fails(self):
        tech_id = make_tech("Mia").json()["id"]
        make_tech("Lisa")
        r = client.put(f"/technicians/{tech_id}", json={"full_name": "Lisa"})
        assert r.status_code == 400

    def test_update_nonexistent_technician_returns_404(self):
        assert client.put("/technicians/9999", json={"full_name": "Ghost"}).status_code == 404

    def test_delete_technician_without_history_really_deletes(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.delete(f"/technicians/{tech_id}")
        assert r.status_code == 200
        assert client.get(f"/technicians/{tech_id}").status_code == 404

    def test_delete_technician_with_history_deactivates_instead(self):
        tech_id = make_tech("Mia").json()["id"]
        give_turn(tech_id)  # a finished turn = history
        r = client.delete(f"/technicians/{tech_id}")
        assert r.status_code == 200
        assert "deactivated" in r.json()["message"].lower()
        tech = client.get(f"/technicians/{tech_id}").json()
        assert tech["is_active"] is False

    def test_deactivate_with_open_turn_fails(self):
        tech_id = make_tech("Mia").json()["id"]
        make_turn(tech_id)  # waiting = open
        r = client.put(f"/technicians/{tech_id}/deactivate")
        assert r.status_code == 400
        assert "open turn" in r.json()["detail"].lower()

    def test_reactivate_technician(self):
        tech_id = make_tech("Mia").json()["id"]
        client.put(f"/technicians/{tech_id}/deactivate")
        r = client.put(f"/technicians/{tech_id}/reactivate")
        assert r.status_code == 200
        assert r.json()["is_active"] is True

    def test_delete_nonexistent_technician_returns_404(self):
        assert client.delete("/technicians/9999").status_code == 404

    def test_technician_cards_include_today_counts(self):
        tech_id = make_tech("Mia").json()["id"]
        make_appointment(technician_id=tech_id)
        make_turn(tech_id)
        r = client.get("/technicians/cards")
        assert r.status_code == 200
        card = r.json()[0]
        assert card["today_appointments_count"] == 1
        assert card["today_turns_count"] == 1

    def test_technician_cards_count_preferred_appointments(self):
        tech_id = make_tech("Mia").json()["id"]
        client.post("/appointments", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel",
            "appointment_time": datetime.now().isoformat(),
            "preferred_technician_id": tech_id,
        })
        card = client.get("/technicians/cards").json()[0]
        assert card["today_appointments_count"] == 1

    def test_technician_cards_zero_counts_when_no_activity(self):
        make_tech("Mia")
        r = client.get("/technicians/cards")
        assert r.status_code == 200
        card = r.json()[0]
        assert card["today_appointments_count"] == 0
        assert card["today_turns_count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. APPOINTMENTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAppointments:

    def test_create_appointment_success(self):
        r = make_appointment()
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Alice"
        assert data["customer_phone"] == "5550000001"
        assert data["appointment_code"].startswith("APT-")
        assert data["id"] is not None

    def test_appointment_code_auto_increments(self):
        code1 = make_appointment(customer_name="Alice", customer_phone="5550000001").json()["appointment_code"]
        code2 = make_appointment(customer_name="Bob", customer_phone="5550000002").json()["appointment_code"]
        assert int(code2.split("-")[-1]) == int(code1.split("-")[-1]) + 1

    def test_create_appointment_invalid_phone_fails(self):
        assert make_appointment(customer_phone="123").status_code == 422

    def test_create_appointment_invalid_status_fails(self):
        r = client.post("/appointments", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel",
            "appointment_time": datetime.now().isoformat(),
            "status": "not_a_status",
        })
        assert r.status_code == 422

    def test_create_appointment_with_nonexistent_tech_fails(self):
        r = make_appointment(technician_id=9999)
        assert r.status_code == 400
        assert "technician" in r.json()["detail"].lower()

    def test_create_appointment_with_valid_tech(self):
        tech_id = make_tech("Mia").json()["id"]
        r = make_appointment(technician_id=tech_id)
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id

    def test_service_name_is_set_from_service_category(self):
        assert make_appointment(service_category="Dip Powder").json()["service_name"] == "Dip Powder"

    def test_get_all_appointments(self):
        make_appointment(customer_name="Alice", customer_phone="5550000001")
        make_appointment(customer_name="Bob", customer_phone="5550000002")
        r = client.get("/appointments")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_filter_appointments_by_date(self):
        make_appointment()
        r = client.get(f"/appointments?date={date.today().isoformat()}")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_filter_appointments_by_technician_id(self):
        tech_id = make_tech("Mia").json()["id"]
        make_appointment(technician_id=tech_id)
        make_appointment(customer_name="Bob", customer_phone="5550000002")
        r = client.get(f"/appointments?technician_id={tech_id}")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert all(a["technician_id"] == tech_id for a in r.json())

    def test_filter_appointments_by_preferred_technician_when_unassigned(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.post("/appointments", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel",
            "appointment_time": datetime.now().isoformat(),
            "preferred_technician_id": tech_id,
        })
        assert r.status_code == 200
        assert r.json()["technician_id"] is None
        assert r.json()["preferred_technician_id"] == tech_id

        filtered = client.get(f"/appointments?technician_id={tech_id}")
        assert filtered.status_code == 200
        assert len(filtered.json()) == 1

    def test_get_appointment_by_id(self):
        apt_id = make_appointment().json()["id"]
        r = client.get(f"/appointments/{apt_id}")
        assert r.status_code == 200
        assert r.json()["id"] == apt_id

    def test_get_nonexistent_appointment_returns_404(self):
        assert client.get("/appointments/9999").status_code == 404

    def test_update_appointment_customer_name(self):
        apt_id = make_appointment().json()["id"]
        r = client.put(f"/appointments/{apt_id}", json={
            "customer_name": "Alice Updated",
            "customer_phone": "5550000001",
            "service_category": "Gel",
            "appointment_time": datetime.now().isoformat(),
        })
        assert r.status_code == 200
        assert r.json()["customer_name"] == "Alice Updated"

    def test_update_appointment_preserves_code(self):
        apt = make_appointment().json()
        r = client.put(f"/appointments/{apt['id']}", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel",
            "appointment_time": datetime.now().isoformat(),
        })
        assert r.json()["appointment_code"] == apt["appointment_code"]

    def test_update_nonexistent_appointment_returns_404(self):
        r = client.put("/appointments/9999", json={
            "customer_name": "Ghost",
            "customer_phone": "5550000001",
            "service_category": "Gel",
            "appointment_time": datetime.now().isoformat(),
        })
        assert r.status_code == 404

    def test_delete_appointment_success(self):
        apt_id = make_appointment().json()["id"]
        assert client.delete(f"/appointments/{apt_id}").status_code == 200
        assert client.get(f"/appointments/{apt_id}").status_code == 404

    def test_delete_nonexistent_appointment_returns_404(self):
        assert client.delete("/appointments/9999").status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 3. TURNS / DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

class TestTurns:

    def test_create_turn_success(self):
        tech_id = make_tech("Mia").json()["id"]
        r = make_turn(tech_id)
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Alice"
        assert data["status"] == "waiting"
        assert data["turn_number"] == 1

    def test_turn_numbers_increment_per_day(self):
        tech_id = make_tech("Mia").json()["id"]
        t1 = make_turn(tech_id, customer_name="Alice").json()["turn_number"]
        t2 = make_turn(tech_id, customer_name="Bob").json()["turn_number"]
        assert t2 == t1 + 1

    def test_create_turn_with_nonexistent_tech_returns_404(self):
        r = client.post("/turns", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "technician_id": 9999,
            "status": "waiting",
            "source": "checkin",
        })
        assert r.status_code == 404

    def test_get_turns(self):
        make_turn(make_tech("Mia").json()["id"])
        r = client.get("/turns")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_get_today_turns(self):
        make_turn(make_tech("Mia").json()["id"])
        r = client.get("/turns/today")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_start_turn_sets_in_service(self):
        turn_id = make_turn(make_tech("Mia").json()["id"]).json()["id"]
        r = client.put(f"/turns/{turn_id}/start", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "in_service"
        assert r.json()["started_at"] is not None

    def test_complete_turn_sets_done(self):
        turn_id = make_turn(make_tech("Mia").json()["id"]).json()["id"]
        r = client.put(f"/turns/{turn_id}/complete", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "done"
        assert r.json()["completed_at"] is not None

    def test_start_and_complete_save_notes(self):
        turn_id = make_turn(make_tech("Mia").json()["id"]).json()["id"]
        r = client.put(f"/turns/{turn_id}/start", json={"notes": "allergic to latex"})
        assert r.json()["notes"] == "allergic to latex"

    def test_assign_next_turn_manually(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.post("/turns/assign-next", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "technician_id": tech_id,
            "source": "manual",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "assigned"
        assert r.json()["assigned_at"] is not None

    def test_assign_next_turn_with_nonexistent_tech_returns_404(self):
        r = client.post("/turns/assign-next", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "technician_id": 9999,
        })
        assert r.status_code == 404

    def test_auto_assign_picks_available_tech(self):
        make_tech("Mia", specialties="acrylic")
        r = auto_assign()
        assert r.status_code == 200
        assert r.json()["status"] == "assigned"

    def test_auto_assign_fails_when_no_available_tech(self):
        r = auto_assign()
        assert r.status_code == 400
        assert "no available technician" in r.json()["detail"].lower()

    def test_auto_assign_fails_when_tech_has_active_turn(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        make_turn(tech_id, customer_name="Bob")
        assert auto_assign().status_code == 400

    def test_auto_assign_returns_existing_active_turn(self):
        make_tech("Mia", specialties="acrylic")
        r1 = auto_assign(customer_phone="5550000001")
        assert r1.status_code == 200
        r2 = auto_assign(customer_phone="5550000001")
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]

    def test_assign_preferred_turn_success(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        r = client.post("/turns/assign-preferred", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "preferred_technician_id": tech_id,
        })
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id
        assert r.json()["status"] == "assigned"

    def test_assign_preferred_fails_when_tech_unavailable(self):
        tech_id = make_tech("Mia", status="off", availability="off today", specialties="acrylic").json()["id"]
        r = client.post("/turns/assign-preferred", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "preferred_technician_id": tech_id,
        })
        assert r.status_code == 400
        assert "not available" in r.json()["detail"].lower()

    def test_assign_preferred_fails_when_service_does_not_match(self):
        tech_id = make_tech("Mia", specialties="waxing").json()["id"]
        r = client.post("/turns/assign-preferred", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "preferred_technician_id": tech_id,
        })
        assert r.status_code == 400
        assert "does not match" in r.json()["detail"].lower()

    def test_reassign_turn_success(self):
        tech1_id = make_tech("Mia", specialties="acrylic").json()["id"]
        tech2_id = make_tech("Lisa", specialties="acrylic").json()["id"]
        turn_id = make_turn(tech1_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech2_id

    def test_reassign_to_busy_tech_fails(self):
        tech1_id = make_tech("Mia", specialties="acrylic").json()["id"]
        tech2_id = make_tech("Lisa", specialties="acrylic").json()["id"]
        make_turn(tech2_id, customer_name="Carol")  # Lisa is busy
        turn_id = make_turn(tech1_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 400
        assert "already assigned" in r.json()["detail"].lower()

    def test_reassign_to_wrong_specialty_fails(self):
        tech1_id = make_tech("Mia", specialties="acrylic").json()["id"]
        tech2_id = make_tech("Lisa", specialties="waxing").json()["id"]
        turn_id = make_turn(tech1_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 400
        assert "does not match" in r.json()["detail"].lower()

    def test_reassign_nonexistent_turn_returns_404(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        assert client.put("/turns/9999/reassign", json={"technician_id": tech_id}).status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 3a. FIX 1: FAIR AUTO-ASSIGN
# ══════════════════════════════════════════════════════════════════════════════

class TestFairAutoAssign:
    """Active -> available today -> specialty -> free -> fewest turns -> stable tie-breaker."""

    def test_picks_tech_with_fewest_turns_not_first_alphabetically(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(amy, "Customer 1")  # Amy now has 1 turn, Bea has 0

        r = auto_assign("Customer 2")
        assert r.status_code == 200
        assert r.json()["technician_id"] == bea  # old code would have picked Amy

    def test_work_is_shared_evenly(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]

        order = []
        for i in range(1, 5):
            turn = auto_assign(f"Customer {i}").json()
            order.append(turn["technician_id"])
            client.put(f"/turns/{turn['id']}/complete", json={})  # free the tech again

        assert order == [amy, bea, amy, bea]

    def test_tie_goes_to_whoever_waited_longest(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(bea, "Customer 1")  # Bea was assigned first
        give_turn(amy, "Customer 2")  # Amy later; both now have 1 turn

        r = auto_assign("Customer 3")
        assert r.json()["technician_id"] == bea  # idle longest, even though Amy is first by name

    def test_final_tie_break_is_name_and_is_stable(self):
        zoe = make_tech("Zoe", specialties="acrylic").json()["id"]  # created first, so lowest id
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        r = auto_assign("Customer 1")
        assert r.json()["technician_id"] == amy
        assert amy != zoe

    def test_cancelled_turns_do_not_count(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(bea, "Customer 1")  # Bea: 1 done turn (older)
        cancelled = give_turn(amy, "Customer 2", complete=False)  # Amy: 1 turn, later...
        assert client.put(f"/turns/{cancelled['id']}/status", json={"status": "cancelled"}).status_code == 200

        # ...but it was cancelled, so Amy has 0 real turns vs Bea's 1.
        # If cancelled turns were counted this would be a tie and Bea (idle longer) would win.
        r = auto_assign("Customer 3")
        assert r.json()["technician_id"] == amy

    def test_skips_busy_off_and_deactivated_techs(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        make_tech("Bea", status="off", availability="off today", specialties="acrylic")
        dan = make_tech("Dan", specialties="acrylic").json()["id"]
        cat = make_tech("Cat", specialties="acrylic").json()["id"]

        make_turn(amy, "Busy customer")  # Amy is busy
        client.put(f"/technicians/{dan}/deactivate")  # Dan is deactivated
        give_turn(cat, "Customer 1")  # Cat is free, with 1 turn: the only eligible tech

        r = auto_assign("Customer 2")
        assert r.status_code == 200
        assert r.json()["technician_id"] == cat

    def test_only_considers_techs_with_matching_specialty(self):
        make_tech("Amy", specialties="waxing")  # 0 turns, wrong specialty
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(bea, "Customer 1")

        r = auto_assign("Customer 2", service_name="Acrylic Full Set")
        assert r.json()["technician_id"] == bea

    def test_waiting_turn_is_not_counted_against_its_own_candidates(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(bea, "Customer 1")  # Bea: 1 turn
        waiting = make_turn(amy, customer_name="Alice").json()  # Alice waiting, parked on Amy

        r = auto_assign("Alice")
        assert r.status_code == 200
        assert r.json()["id"] == waiting["id"]  # re-uses her waiting turn
        assert r.json()["status"] == "assigned"
        assert r.json()["technician_id"] == amy  # Amy: 0 other turns vs Bea's 1


# ══════════════════════════════════════════════════════════════════════════════
# 3b. FIX 3: ORDERED TURN STATUSES
# ══════════════════════════════════════════════════════════════════════════════

class TestTurnStatusFlow:

    def _new_turn(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        return tech_id, make_turn(tech_id).json()["id"]

    def _set(self, turn_id, status):
        return client.put(f"/turns/{turn_id}/status", json={"status": status})

    def test_normal_forward_flow(self):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "assigned").json()["status"] == "assigned"
        assert self._set(turn_id, "in_service").json()["status"] == "in_service"
        done = self._set(turn_id, "done").json()
        assert done["status"] == "done"
        assert done["assigned_at"] and done["started_at"] and done["completed_at"]

    def test_waiting_can_jump_straight_to_in_service(self):
        _, turn_id = self._new_turn()
        r = self._set(turn_id, "in_service")
        assert r.status_code == 200
        assert r.json()["started_at"] is not None

    def test_waiting_can_jump_straight_to_done_and_fills_timestamps(self):
        _, turn_id = self._new_turn()
        data = self._set(turn_id, "done").json()
        assert data["status"] == "done"
        assert data["assigned_at"] and data["started_at"] and data["completed_at"]

    def test_invalid_status_value_is_422(self):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "flying").status_code == 422

    def test_nonexistent_turn_is_404(self):
        assert self._set(9999, "done").status_code == 404

    def test_done_cannot_go_back_to_waiting(self):
        _, turn_id = self._new_turn()
        completed_at = self._set(turn_id, "done").json()["completed_at"]

        r = self._set(turn_id, "waiting")
        assert r.status_code == 400
        assert "done" in r.json()["detail"] and "waiting" in r.json()["detail"]

        turn = get_turn_today(turn_id)
        assert turn["status"] == "done"
        assert turn["completed_at"] == completed_at  # untouched

    @pytest.mark.parametrize("target", ["waiting", "assigned", "in_service", "cancelled"])
    def test_done_is_final(self, target):
        _, turn_id = self._new_turn()
        self._set(turn_id, "done")
        assert self._set(turn_id, target).status_code == 400

    @pytest.mark.parametrize("target", ["waiting", "assigned", "in_service", "done"])
    def test_cancelled_is_final(self, target):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "cancelled").status_code == 200
        assert self._set(turn_id, target).status_code == 400

    def test_in_service_cannot_go_backwards(self):
        _, turn_id = self._new_turn()
        self._set(turn_id, "in_service")
        assert self._set(turn_id, "assigned").status_code == 400
        assert self._set(turn_id, "waiting").status_code == 400

    def test_open_turn_can_be_cancelled(self):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "cancelled").json()["status"] == "cancelled"

    def test_same_status_twice_is_not_an_error(self):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "in_service").status_code == 200
        assert self._set(turn_id, "in_service").status_code == 200

    def test_completing_twice_keeps_original_completed_at(self):
        _, turn_id = self._new_turn()
        first = client.put(f"/turns/{turn_id}/complete", json={}).json()
        second = client.put(f"/turns/{turn_id}/complete", json={})
        assert second.status_code == 200
        assert second.json()["completed_at"] == first["completed_at"]

    def test_cannot_start_a_done_turn(self):
        _, turn_id = self._new_turn()
        client.put(f"/turns/{turn_id}/complete", json={})
        assert client.put(f"/turns/{turn_id}/start", json={}).status_code == 400

    def test_cannot_complete_a_cancelled_turn(self):
        _, turn_id = self._new_turn()
        self._set(turn_id, "cancelled")
        assert client.put(f"/turns/{turn_id}/complete", json={}).status_code == 400

    def test_reassign_keeps_in_service_status(self):
        mia = make_tech("Mia", specialties="acrylic").json()["id"]
        lisa = make_tech("Lisa", specialties="acrylic").json()["id"]
        turn_id = make_turn(mia).json()["id"]
        started = client.put(f"/turns/{turn_id}/start", json={}).json()

        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": lisa})
        assert r.status_code == 200
        assert r.json()["technician_id"] == lisa
        assert r.json()["status"] == "in_service"  # must not drop back to "assigned"
        assert r.json()["started_at"] == started["started_at"]

    def test_reassign_moves_waiting_turn_to_assigned(self):
        mia = make_tech("Mia", specialties="acrylic").json()["id"]
        lisa = make_tech("Lisa", specialties="acrylic").json()["id"]
        turn_id = make_turn(mia).json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": lisa})
        assert r.json()["status"] == "assigned"
        assert r.json()["assigned_at"] is not None

    @pytest.mark.parametrize("final_status", ["done", "cancelled"])
    def test_finished_turn_cannot_be_reassigned(self, final_status):
        mia = make_tech("Mia", specialties="acrylic").json()["id"]
        lisa = make_tech("Lisa", specialties="acrylic").json()["id"]
        turn_id = make_turn(mia).json()["id"]
        self._set(turn_id, final_status)
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": lisa})
        assert r.status_code == 400
        assert "cannot be reassigned" in r.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# 4. CHECKOUT
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckout:

    def test_create_checkout_success(self):
        r = make_checkout()
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Alice"
        assert data["subtotal"] == 100.0
        assert data["id"] is not None

    def test_create_checkout_links_to_technician(self):
        tech_id = make_tech("Mia").json()["id"]
        r = make_checkout(technician_id=tech_id)
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id

    def test_create_checkout_with_turn_marks_turn_done(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        assert make_checkout(technician_id=tech_id, turn_id=turn_id).status_code == 200
        turn = get_turn_today(turn_id)
        assert turn["status"] == "done"
        assert turn["completed_at"] is not None

    def test_checkout_of_already_completed_turn_works(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        client.put(f"/turns/{turn_id}/complete", json={})  # tech taps "done" first
        assert make_checkout(technician_id=tech_id, turn_id=turn_id).status_code == 200

    def test_auto_assign_checkout_flow_moves_customer_to_history(self):
        make_tech("Mia", specialties="acrylic")

        assigned = auto_assign(
            "Alice",
            customer_phone="5550000001",
            discount_type="fixed",
            discount_value=10.0,
            discount_label="$10 birthday discount",
        )
        assert assigned.status_code == 200
        turn = assigned.json()
        assert turn["status"] == "assigned"
        assert turn["discount_type"] == "fixed"

        ready = [t for t in client.get("/turns/today").json() if t["status"] in {"assigned", "in_service"}]
        assert [t["id"] for t in ready] == [turn["id"]]

        checkout = make_checkout(
            customer_name="Alice",
            customer_phone="5550000001",
            service_name="Acrylic Full Set",
            subtotal=100.0,
            tip_amount=15.0,
            technician_id=turn["technician_id"],
            turn_id=turn["id"],
            discount_type="fixed",
            discount_value=10.0,
        )
        assert checkout.status_code == 200

        today_turns = client.get("/turns/today").json()
        completed = next(t for t in today_turns if t["id"] == turn["id"])
        assert completed["status"] == "done"
        assert completed["completed_at"] is not None
        assert not [t for t in today_turns if t["status"] in {"assigned", "in_service"}]

        history = client.get("/checkouts").json()
        assert len(history) == 1
        assert history[0]["customer_name"] == "Alice"
        assert history[0]["customer_phone"] == "5550000001"
        assert history[0]["discount_amount"] == 10.0
        assert history[0]["tip_amount"] == 15.0

    def test_create_checkout_invalid_payment_method_fails(self):
        assert make_checkout(payment_method="bitcoin").status_code == 422

    def test_create_checkout_invalid_discount_type_fails(self):
        assert make_checkout(discount_type="unknown").status_code == 422

    def test_get_all_checkouts(self):
        make_checkout(customer_name="Alice")
        make_checkout(customer_name="Bob")
        r = client.get("/checkouts")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_checkout_by_id(self):
        checkout_id = make_checkout().json()["id"]
        r = client.get(f"/checkouts/{checkout_id}")
        assert r.status_code == 200
        assert r.json()["id"] == checkout_id

    def test_get_nonexistent_checkout_returns_404(self):
        assert client.get("/checkouts/9999").status_code == 404

    def test_delete_checkout_success(self):
        checkout_id = make_checkout().json()["id"]
        assert client.delete(f"/checkouts/{checkout_id}").status_code == 200
        assert client.get(f"/checkouts/{checkout_id}").status_code == 404

    def test_delete_nonexistent_checkout_returns_404(self):
        assert client.delete("/checkouts/9999").status_code == 404

    # ── Fix 2: the server does the math ──────────────────────────────────────

    def test_server_calculates_split_without_discount(self):
        data = make_checkout(subtotal=100.0, tip_amount=20.0).json()
        assert data["discount_amount"] == 0.0
        assert data["net_service"] == 100.0
        assert data["technician_share"] == 60.0
        assert data["salon_share"] == 40.0
        assert data["salon_actual_revenue"] == 40.0
        assert data["technician_total"] == 80.0  # 60 + 20 tip
        assert data["customer_pays"] == 120.0  # 100 + 20 tip
        assert data["discount_paid_by"] == "owner"

    def test_fixed_discount_is_calculated_by_server(self):
        data = make_checkout(subtotal=100.0, discount_type="fixed", discount_value=15.0).json()
        assert data["discount_amount"] == 15.0
        assert data["net_service"] == 85.0
        assert data["technician_share"] == 60.0  # 60% of the $100 price: the discount doesn't touch it
        assert data["salon_share"] == 40.0
        assert data["salon_actual_revenue"] == 25.0  # the owner absorbs the whole $15 discount
        assert data["technician_total"] == 60.0
        assert data["customer_pays"] == 85.0

    def test_discount_never_reduces_technician_pay(self):
        no_discount = make_checkout(subtotal=100.0, tip_amount=10.0).json()
        with_discount = make_checkout(
            subtotal=100.0, tip_amount=10.0, discount_type="percent", discount_value=50.0
        ).json()
        assert with_discount["technician_share"] == no_discount["technician_share"] == 60.0
        assert with_discount["technician_total"] == no_discount["technician_total"] == 70.0

    def test_discount_bigger_than_salon_share_makes_salon_revenue_negative(self):
        # Owner pays the discount, so a 50% discount on $100 costs the salon $10 on this customer.
        data = make_checkout(subtotal=100.0, discount_type="percent", discount_value=50.0).json()
        assert data["salon_actual_revenue"] == -10.0

    def test_percent_discount_is_calculated_by_server(self):
        data = make_checkout(
            subtotal=100.0, tip_amount=15.0, discount_type="percent", discount_value=10.0
        ).json()
        assert data["discount_amount"] == 10.0
        assert data["net_service"] == 90.0
        assert data["technician_share"] == 60.0  # 60% of the $100 price
        assert data["salon_share"] == 40.0
        assert data["salon_actual_revenue"] == 30.0  # 40 - 10 discount
        assert data["technician_total"] == 75.0  # 60 + 15 tip
        assert data["customer_pays"] == 105.0  # 90 + 15 tip

    def test_forged_client_numbers_are_ignored(self):
        r = make_checkout(
            subtotal=100.0,
            tip_amount=10.0,
            # An old or tampered client tries to rewrite the books:
            discount_amount=100.0,
            net_service=0.0,
            technician_share=100.0,
            salon_share=0.0,
            salon_actual_revenue=999.0,
            technician_total=500.0,
            customer_pays=1.0,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["discount_amount"] == 0.0
        assert data["net_service"] == 100.0
        assert data["technician_share"] == 60.0
        assert data["salon_share"] == 40.0
        assert data["salon_actual_revenue"] == 40.0
        assert data["technician_total"] == 70.0
        assert data["customer_pays"] == 110.0

    def test_forged_numbers_do_not_reach_income_report(self):
        make_checkout(subtotal=100.0, tip_amount=0.0, salon_actual_revenue=999.0, technician_share=1.0)
        day = client.get(f"/income/salon?date={date.today().isoformat()}").json()["day"]
        assert day["tech_60_percent_total"] == 60.0
        assert day["salon_income_after_techs"] == 40.0

    def test_money_is_rounded_to_cents_and_shares_add_up(self):
        data = make_checkout(subtotal=33.33).json()
        assert data["technician_share"] == 20.0  # 19.998 rounds to 20.00
        assert data["salon_share"] == 13.33
        assert data["technician_share"] + data["salon_share"] == pytest.approx(data["subtotal"])

    def test_percent_discount_rounds_half_up(self):
        data = make_checkout(subtotal=0.05, discount_type="percent", discount_value=10.0).json()
        assert data["discount_amount"] == 0.01  # 0.005 -> 0.01 (not banker's rounding to 0.00)

    def test_percent_discount_over_100_rejected(self):
        assert make_checkout(discount_type="percent", discount_value=101.0).status_code == 422

    def test_fixed_discount_above_subtotal_rejected(self):
        assert make_checkout(subtotal=50.0, discount_type="fixed", discount_value=60.0).status_code == 422

    def test_negative_tip_rejected(self):
        assert make_checkout(tip_amount=-5.0).status_code == 422

    def test_negative_subtotal_rejected(self):
        assert make_checkout(subtotal=-1.0).status_code == 422

    # ── Links to turns, technicians, appointments ────────────────────────────

    def test_technician_is_filled_in_from_turn_when_missing(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        r = make_checkout(turn_id=turn_id)  # no technician_id sent
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id

    def test_technician_must_match_turn(self):
        mia = make_tech("Mia").json()["id"]
        lisa = make_tech("Lisa").json()["id"]
        turn_id = make_turn(mia).json()["id"]
        r = make_checkout(technician_id=lisa, turn_id=turn_id)
        assert r.status_code == 400
        assert "does not match" in r.json()["detail"].lower()

    def test_turn_cannot_be_checked_out_twice(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        assert make_checkout(technician_id=tech_id, turn_id=turn_id).status_code == 200
        r = make_checkout(technician_id=tech_id, turn_id=turn_id)
        assert r.status_code == 400
        assert "already" in r.json()["detail"].lower()
        assert len(client.get("/checkouts").json()) == 1

    def test_cancelled_turn_cannot_be_checked_out(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        client.put(f"/turns/{turn_id}/status", json={"status": "cancelled"})
        r = make_checkout(technician_id=tech_id, turn_id=turn_id)
        assert r.status_code == 400
        assert "cancelled" in r.json()["detail"].lower()
        assert client.get("/checkouts").json() == []  # nothing was saved
        assert get_turn_today(turn_id)["status"] == "cancelled"  # and the turn is untouched

    def test_checkout_with_unknown_turn_fails(self):
        r = make_checkout(turn_id=9999)
        assert r.status_code == 400
        assert "turn not found" in r.json()["detail"].lower()

    def test_checkout_with_unknown_technician_fails(self):
        r = make_checkout(technician_id=9999)
        assert r.status_code == 400
        assert "technician not found" in r.json()["detail"].lower()

    def test_checkout_with_unknown_appointment_fails(self):
        r = make_checkout(appointment_id=9999)
        assert r.status_code == 400
        assert "appointment not found" in r.json()["detail"].lower()

    def test_checkout_with_valid_appointment(self):
        apt_id = make_appointment().json()["id"]
        r = make_checkout(appointment_id=apt_id)
        assert r.status_code == 200
        assert r.json()["appointment_id"] == apt_id


# ══════════════════════════════════════════════════════════════════════════════
# 4b. FIX 4: FOREIGN KEYS
# ══════════════════════════════════════════════════════════════════════════════

class TestForeignKeys:

    def test_foreign_keys_pragma_is_on(self):
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

    def test_database_rejects_a_turn_for_a_missing_technician(self):
        db = SessionLocal()
        try:
            db.add(models.Turn(turn_number=1, customer_name="X", service_name="Y", technician_id=9999))
            with pytest.raises(IntegrityError):
                db.commit()
        finally:
            db.rollback()
            db.close()

    def test_database_rejects_a_checkout_for_a_missing_turn(self):
        db = SessionLocal()
        try:
            db.add(models.Checkout(customer_name="X", service_name="Y", turn_id=9999))
            with pytest.raises(IntegrityError):
                db.commit()
        finally:
            db.rollback()
            db.close()

    def test_unknown_preferred_technician_on_new_turn_is_400_not_500(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.post("/turns", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "technician_id": tech_id,
            "preferred_technician_id": 9999,
        })
        assert r.status_code == 400
        assert "preferred technician not found" in r.json()["detail"].lower()

    def test_unknown_preferred_technician_on_auto_assign_is_400_not_500(self):
        make_tech("Mia", specialties="acrylic")
        r = auto_assign("Alice", preferred_technician_id=9999)
        assert r.status_code == 400
        assert "preferred technician not found" in r.json()["detail"].lower()

    def test_cannot_delete_appointment_that_has_a_checkout(self):
        apt_id = make_appointment().json()["id"]
        assert make_checkout(appointment_id=apt_id).status_code == 200

        r = client.delete(f"/appointments/{apt_id}")
        assert r.status_code == 400
        assert "checkout" in r.json()["detail"].lower()
        assert client.get(f"/appointments/{apt_id}").status_code == 200  # still there

    def test_integrity_error_becomes_409_not_a_crash(self):
        r = client.get("/__test_integrity_error")
        assert r.status_code == 409
        assert "conflicts" in r.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# 5. INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

class TestInventory:

    def test_create_inventory_item_success(self):
        r = make_inventory()
        assert r.status_code == 200
        data = r.json()
        assert data["item_name"] == "Acrylic Powder"
        assert data["quantity"] == 10
        assert data["unit_price"] == 15.0
        assert data["id"] is not None

    def test_negative_quantity_rejected(self):
        assert make_inventory(quantity=-1).status_code == 422

    def test_get_all_inventory_items(self):
        make_inventory("Acrylic Powder")
        make_inventory("Acetone", category="Liquids", quantity=5, unit_price=8.0)
        r = client.get("/inventory")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_inventory_item_by_id(self):
        item_id = make_inventory().json()["id"]
        r = client.get(f"/inventory/{item_id}")
        assert r.status_code == 200
        assert r.json()["id"] == item_id

    def test_get_nonexistent_inventory_item_returns_404(self):
        assert client.get("/inventory/9999").status_code == 404

    def test_update_inventory_item_quantity(self):
        item_id = make_inventory(quantity=10).json()["id"]
        r = client.put(f"/inventory/{item_id}", json={"quantity": 25})
        assert r.status_code == 200
        assert r.json()["quantity"] == 25

    def test_update_inventory_item_price(self):
        item_id = make_inventory(unit_price=10.0).json()["id"]
        r = client.put(f"/inventory/{item_id}", json={"unit_price": 20.0})
        assert r.status_code == 200
        assert r.json()["unit_price"] == 20.0

    def test_update_nonexistent_inventory_item_returns_404(self):
        assert client.put("/inventory/9999", json={"quantity": 5}).status_code == 404

    def test_delete_inventory_item_success(self):
        item_id = make_inventory().json()["id"]
        assert client.delete(f"/inventory/{item_id}").status_code == 200
        assert client.get(f"/inventory/{item_id}").status_code == 404

    def test_delete_nonexistent_inventory_item_returns_404(self):
        assert client.delete("/inventory/9999").status_code == 404

    def test_inventory_summary_total_value(self):
        make_inventory(quantity=10, unit_price=15.0)  # $150
        make_inventory("Acetone", category="Liquids", quantity=5, unit_price=8.0)  # $40
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["total_inventory_value"] == 190.0

    def test_inventory_summary_low_stock_flag(self):
        make_inventory(quantity=2, unit_price=15.0, low_stock_level=3)  # 2 <= 3 -> low stock
        make_inventory("Acetone", category="Liquids", quantity=10, unit_price=8.0, low_stock_level=3)
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["low_stock_items"] == 1

    def test_inventory_summary_weekly_expense(self):
        make_inventory(quantity=4, unit_price=25.0, purchase_date=date.today().isoformat())
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["weekly_expense"] == 100.0

    def test_inventory_summary_excludes_old_purchase_from_weekly(self):
        old_date = (date.today() - timedelta(days=14)).isoformat()
        make_inventory(quantity=4, unit_price=25.0, purchase_date=old_date)
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["weekly_expense"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 6. INCOME REPORTS
# ══════════════════════════════════════════════════════════════════════════════

class TestIncomeReports:

    def _seed_checkout(self, tech_id, subtotal=100.0, tip=20.0, discount=0.0):
        """discount is a fixed amount in dollars; the server works out everything else."""
        return make_checkout(
            technician_id=tech_id,
            subtotal=subtotal,
            tip_amount=tip,
            discount_type="fixed" if discount else "none",
            discount_value=discount,
        )

    def test_tech_income_report_returns_correct_date(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id)
        today = date.today().isoformat()
        r = client.get(f"/income/tech?date={today}")
        assert r.status_code == 200
        assert r.json()["date"] == today

    def test_tech_income_report_groups_by_technician(self):
        tech1_id = make_tech("Mia").json()["id"]
        tech2_id = make_tech("Lisa").json()["id"]
        self._seed_checkout(tech1_id)
        self._seed_checkout(tech2_id)
        r = client.get(f"/income/tech?date={date.today().isoformat()}")
        assert r.status_code == 200
        assert len(r.json()["technicians"]) == 2

    def test_tech_income_report_sums_correctly(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=10.0)
        self._seed_checkout(tech_id, subtotal=80.0, tip=5.0)
        r = client.get(f"/income/tech?date={date.today().isoformat()}")
        summary = r.json()["technicians"][0]
        assert summary["gross_before_60"] == 180.0
        assert summary["tech_after_60"] == 108.0
        assert summary["tip_total"] == 15.0
        assert summary["tech_total"] == 123.0
        assert summary["turns"] == 2

    def test_tech_income_report_filters_by_technician_id(self):
        tech1_id = make_tech("Mia").json()["id"]
        tech2_id = make_tech("Lisa").json()["id"]
        self._seed_checkout(tech1_id)
        self._seed_checkout(tech2_id)
        r = client.get(f"/income/tech?date={date.today().isoformat()}&technician_id={tech1_id}")
        assert r.status_code == 200
        techs = r.json()["technicians"]
        assert len(techs) == 1
        assert techs[0]["technician_id"] == tech1_id

    def test_tech_income_report_empty_when_no_checkouts(self):
        r = client.get(f"/income/tech?date={date.today().isoformat()}")
        assert r.status_code == 200
        assert r.json()["technicians"] == []

    def test_tech_income_report_technicians_sorted_alphabetically(self):
        zoe_id = make_tech("Zoe").json()["id"]
        amy_id = make_tech("Amy").json()["id"]
        self._seed_checkout(zoe_id)
        self._seed_checkout(amy_id)
        r = client.get(f"/income/tech?date={date.today().isoformat()}")
        names = [t["technician_name"] for t in r.json()["technicians"]]
        assert names == ["Amy", "Zoe"]

    def test_salon_income_report_day_totals(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=20.0)
        r = client.get(f"/income/salon?date={date.today().isoformat()}")
        assert r.status_code == 200
        day = r.json()["day"]
        assert day["income_before_discount"] == 100.0
        assert day["income_after_discount"] == 100.0
        assert day["tech_60_percent_total"] == 60.0
        assert day["salon_income_after_techs"] == 40.0
        assert day["tech_tip_total"] == 20.0
        assert day["total_paid_to_techs"] == 80.0
        assert day["turns"] == 1

    def test_salon_income_report_with_discount(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=0.0, discount=10.0)
        day = client.get(f"/income/salon?date={date.today().isoformat()}").json()["day"]
        assert day["income_before_discount"] == 100.0
        assert day["total_discount"] == 10.0
        assert day["income_after_discount"] == 90.0
        assert day["tech_60_percent_total"] == 60.0  # 60% of the $100 price
        assert day["salon_income_after_techs"] == 30.0  # 40 salon share - 10 discount (owner pays it)

    def test_salon_income_report_includes_day_week_year_periods(self):
        r = client.get(f"/income/salon?date={date.today().isoformat()}")
        assert r.status_code == 200
        data = r.json()
        assert "day" in data and "week" in data and "year" in data

    def test_salon_income_report_week_and_year_include_today(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=0.0)
        data = client.get(f"/income/salon?date={date.today().isoformat()}").json()
        assert data["week"]["income_before_discount"] == 100.0
        assert data["year"]["income_before_discount"] == 100.0

    def test_salon_income_report_includes_details(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id)
        details = client.get(f"/income/salon?date={date.today().isoformat()}").json()["details"]
        assert len(details) == 1
        assert details[0]["technician_id"] == tech_id

    def test_salon_income_report_empty_day_when_no_checkouts(self):
        r = client.get(f"/income/salon?date={date.today().isoformat()}")
        assert r.status_code == 200
        day = r.json()["day"]
        assert day["income_before_discount"] == 0.0
        assert day["turns"] == 0
        assert r.json()["details"] == []