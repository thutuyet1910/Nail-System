"""
Test suite for Nail Salon Owner Backend
Covers: Technicians, Appointments, Turns/Dispatch, Checkout, Inventory, Income Reports

Run with:
    pytest test_owner_backend.py -v
"""

import pytest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── Test database (file-based so SQLite pragma works) ─────────────────────────
TEST_DATABASE_URL = "sqlite:///./test_owner.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import models
import schemas
import crud
from database import Base, get_db
from main import app

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
    return client.post("/turns", json={
        "customer_name": customer_name,
        "service_name": service_name,
        "technician_id": technician_id,
        "status": "waiting",
        "source": "checkin",
    })


def make_checkout(
    customer_name="Alice",
    customer_phone=None,
    service_name="Gel Manicure",
    subtotal=100.0,
    tip_amount=20.0,
    technician_id=None,
    turn_id=None,
    discount_type="none",
    discount_value=0.0,
    discount_amount=0.0,
    net_service=None,
    technician_share=None,
    salon_share=None,
    salon_actual_revenue=None,
    technician_total=None,
    customer_pays=None,
):
    net = net_service if net_service is not None else subtotal - discount_amount
    tech_share = technician_share if technician_share is not None else round(net * 0.60, 2)
    salon = salon_share if salon_share is not None else round(net * 0.40, 2)
    salon_rev = salon_actual_revenue if salon_actual_revenue is not None else salon
    tech_total = technician_total if technician_total is not None else round(tech_share + tip_amount, 2)
    pays = customer_pays if customer_pays is not None else round(net + tip_amount, 2)

    payload = {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service_name": service_name,
        "subtotal": subtotal,
        "tip_amount": tip_amount,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "discount_amount": discount_amount,
        "net_service": net,
        "technician_share": tech_share,
        "salon_share": salon,
        "salon_actual_revenue": salon_rev,
        "technician_total": tech_total,
        "customer_pays": pays,
        "payment_method": "cash",
        "discount_paid_by": "owner",
    }
    if technician_id:
        payload["technician_id"] = technician_id
    if turn_id:
        payload["turn_id"] = turn_id
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
        r = client.get("/technicians/9999")
        assert r.status_code == 404

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
        r = client.put("/technicians/9999", json={"full_name": "Ghost"})
        assert r.status_code == 404

    def test_delete_technician_success(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.delete(f"/technicians/{tech_id}")
        assert r.status_code == 200
        assert client.get(f"/technicians/{tech_id}").status_code == 404

    def test_delete_nonexistent_technician_returns_404(self):
        r = client.delete("/technicians/9999")
        assert r.status_code == 404

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
        num1 = int(code1.split("-")[-1])
        num2 = int(code2.split("-")[-1])
        assert num2 == num1 + 1

    def test_create_appointment_invalid_phone_fails(self):
        r = make_appointment(customer_phone="123")
        assert r.status_code == 422

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
        r = make_appointment(service_category="Dip Powder")
        assert r.json()["service_name"] == "Dip Powder"

    def test_get_all_appointments(self):
        make_appointment(customer_name="Alice", customer_phone="5550000001")
        make_appointment(customer_name="Bob", customer_phone="5550000002")
        r = client.get("/appointments")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_filter_appointments_by_date(self):
        make_appointment()
        today = date.today().isoformat()
        r = client.get(f"/appointments?date={today}")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_filter_appointments_by_technician_id(self):
        tech_id = make_tech("Mia").json()["id"]
        make_appointment(technician_id=tech_id)
        make_appointment(customer_name="Bob", customer_phone="5550000002")
        r = client.get(f"/appointments?technician_id={tech_id}")
        assert r.status_code == 200
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
        assert filtered.json()[0]["preferred_technician_id"] == tech_id

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
        original_code = apt["appointment_code"]
        r = client.put(f"/appointments/{apt['id']}", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel",
            "appointment_time": datetime.now().isoformat(),
        })
        assert r.json()["appointment_code"] == original_code

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
        make_tech("Lisa", specialties="acrylic")
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
        tech_id = make_tech("Mia").json()["id"]
        make_turn(tech_id)
        r = client.get("/turns")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_get_today_turns(self):
        tech_id = make_tech("Mia").json()["id"]
        make_turn(tech_id)
        r = client.get("/turns/today")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_update_turn_status_to_in_service(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/status", json={"status": "in_service"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "in_service"
        assert data["started_at"] is not None

    def test_update_turn_status_to_done_sets_timestamps(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/status", json={"status": "done"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "done"
        assert data["completed_at"] is not None
        assert data["started_at"] is not None
        assert data["assigned_at"] is not None

    def test_update_turn_status_invalid_value_fails(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/status", json={"status": "flying"})
        assert r.status_code == 422

    def test_update_nonexistent_turn_status_returns_404(self):
        r = client.put("/turns/9999/status", json={"status": "done"})
        assert r.status_code == 404

    def test_start_turn_sets_in_service(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/start", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "in_service"
        assert r.json()["started_at"] is not None

    def test_complete_turn_sets_done(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/complete", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "done"
        assert r.json()["completed_at"] is not None

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
        r = client.post("/turns/assign-auto", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "assigned"

    def test_auto_assign_fails_when_no_available_tech(self):
        # No techs created → no candidates
        r = client.post("/turns/assign-auto", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
        })
        assert r.status_code == 400
        assert "no available technician" in r.json()["detail"].lower()

    def test_auto_assign_fails_when_tech_has_active_turn(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        # Give Mia an active turn so she's no longer free
        make_turn(tech_id, customer_name="Bob", service_name="Acrylic Full Set")
        r = client.post("/turns/assign-auto", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
        })
        assert r.status_code == 400

    def test_auto_assign_returns_existing_active_turn(self):
        make_tech("Mia", specialties="acrylic")
        # First auto-assign creates a turn
        r1 = client.post("/turns/assign-auto", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_name": "Acrylic Full Set",
        })
        assert r1.status_code == 200
        turn_id = r1.json()["id"]

        # Second request for same customer returns same turn
        r2 = client.post("/turns/assign-auto", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_name": "Acrylic Full Set",
        })
        assert r2.status_code == 200
        assert r2.json()["id"] == turn_id

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
        # Mia only does waxing, not acrylic
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
        turn_id = make_turn(tech1_id, service_name="Acrylic Full Set").json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech2_id

    def test_reassign_to_busy_tech_fails(self):
        tech1_id = make_tech("Mia", specialties="acrylic").json()["id"]
        tech2_id = make_tech("Lisa", specialties="acrylic").json()["id"]
        # Give Lisa an active turn so she's busy
        make_turn(tech2_id, customer_name="Carol", service_name="Acrylic Full Set")
        turn_id = make_turn(tech1_id, service_name="Acrylic Full Set").json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 400
        assert "already assigned" in r.json()["detail"].lower()

    def test_reassign_to_wrong_specialty_fails(self):
        tech1_id = make_tech("Mia", specialties="acrylic").json()["id"]
        tech2_id = make_tech("Lisa", specialties="waxing").json()["id"]
        turn_id = make_turn(tech1_id, service_name="Acrylic Full Set").json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 400
        assert "does not match" in r.json()["detail"].lower()

    def test_reassign_nonexistent_turn_returns_404(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        r = client.put("/turns/9999/reassign", json={"technician_id": tech_id})
        assert r.status_code == 404


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
        make_checkout(technician_id=tech_id, turn_id=turn_id)
        turn = client.get(f"/turns/{turn_id}")
        # Turn status updated via internal update_turn_status
        db = TestingSessionLocal()
        turn_obj = db.query(models.Turn).filter(models.Turn.id == turn_id).first()
        db.close()
        assert turn_obj.status == "done"

    def test_auto_assign_checkout_flow_moves_customer_to_history(self):
        make_tech("Mia", specialties="acrylic")

        assigned = client.post("/turns/assign-auto", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_name": "Acrylic Full Set",
            "discount_type": "fixed",
            "discount_value": 10.0,
            "discount_label": "$10 birthday discount",
        })
        assert assigned.status_code == 200
        turn = assigned.json()
        assert turn["status"] == "assigned"
        assert turn["discount_type"] == "fixed"

        ready_turns = [
            item for item in client.get("/turns/today").json()
            if item["status"] in {"assigned", "in_service"}
        ]
        assert [item["id"] for item in ready_turns] == [turn["id"]]

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
            discount_amount=10.0,
            net_service=90.0,
            technician_share=54.0,
            salon_share=36.0,
            salon_actual_revenue=36.0,
            technician_total=69.0,
            customer_pays=105.0,
        )
        assert checkout.status_code == 200

        today_turns = client.get("/turns/today").json()
        completed_turn = next(item for item in today_turns if item["id"] == turn["id"])
        assert completed_turn["status"] == "done"
        assert completed_turn["completed_at"] is not None
        assert not [item for item in today_turns if item["status"] in {"assigned", "in_service"}]

        history = client.get("/checkouts").json()
        assert len(history) == 1
        assert history[0]["customer_name"] == "Alice"
        assert history[0]["customer_phone"] == "5550000001"
        assert history[0]["discount_amount"] == 10.0
        assert history[0]["tip_amount"] == 15.0

    def test_create_checkout_invalid_payment_method_fails(self):
        r = client.post("/checkouts", json={
            "customer_name": "Alice",
            "service_name": "Gel",
            "subtotal": 100,
            "payment_method": "bitcoin",
            "discount_type": "none",
            "discount_value": 0,
            "discount_amount": 0,
            "net_service": 100,
            "technician_share": 60,
            "salon_share": 40,
            "salon_actual_revenue": 40,
            "technician_total": 60,
            "customer_pays": 100,
            "tip_amount": 0,
            "discount_paid_by": "owner",
        })
        assert r.status_code == 422

    def test_create_checkout_invalid_discount_type_fails(self):
        r = client.post("/checkouts", json={
            "customer_name": "Alice",
            "service_name": "Gel",
            "subtotal": 100,
            "payment_method": "cash",
            "discount_type": "unknown",
            "discount_value": 0,
            "discount_amount": 0,
            "net_service": 100,
            "technician_share": 60,
            "salon_share": 40,
            "salon_actual_revenue": 40,
            "technician_total": 60,
            "customer_pays": 100,
            "tip_amount": 0,
            "discount_paid_by": "owner",
        })
        assert r.status_code == 422

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

    def test_fixed_discount_reduces_net_service(self):
        # subtotal=100, discount_amount=15 → net=85, tech=51, salon=34
        r = make_checkout(
            subtotal=100.0,
            discount_type="fixed",
            discount_value=15.0,
            discount_amount=15.0,
            net_service=85.0,
            technician_share=51.0,
            salon_share=34.0,
            salon_actual_revenue=34.0,
            technician_total=51.0,
            customer_pays=85.0,
            tip_amount=0,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["discount_amount"] == 15.0
        assert data["net_service"] == 85.0

    def test_percent_discount_checkout(self):
        # subtotal=100, 10% discount → discount_amount=10, net=90
        r = make_checkout(
            subtotal=100.0,
            discount_type="percent",
            discount_value=10.0,
            discount_amount=10.0,
            net_service=90.0,
            technician_share=54.0,
            salon_share=36.0,
            salon_actual_revenue=36.0,
            technician_total=54.0,
            customer_pays=90.0,
            tip_amount=0,
        )
        assert r.status_code == 200
        assert r.json()["net_service"] == 90.0

    def test_tip_is_included_in_customer_pays(self):
        r = make_checkout(subtotal=100.0, tip_amount=20.0, customer_pays=120.0)
        assert r.status_code == 200
        assert r.json()["tip_amount"] == 20.0
        assert r.json()["customer_pays"] == 120.0


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
        r = client.put("/inventory/9999", json={"quantity": 5})
        assert r.status_code == 404

    def test_delete_inventory_item_success(self):
        item_id = make_inventory().json()["id"]
        assert client.delete(f"/inventory/{item_id}").status_code == 200
        assert client.get(f"/inventory/{item_id}").status_code == 404

    def test_delete_nonexistent_inventory_item_returns_404(self):
        assert client.delete("/inventory/9999").status_code == 404

    def test_inventory_summary_total_value(self):
        make_inventory(quantity=10, unit_price=15.0)   # $150
        make_inventory("Acetone", category="Liquids", quantity=5, unit_price=8.0)  # $40
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["total_inventory_value"] == 190.0

    def test_inventory_summary_low_stock_flag(self):
        make_inventory(quantity=2, unit_price=15.0, low_stock_level=3)  # 2 <= 3 → low stock
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

    def _seed_checkout(self, tech_id, subtotal=100.0, tip=20.0, discount_amount=0.0):
        net = subtotal - discount_amount
        tech_share = round(net * 0.60, 2)
        salon_rev = round(net * 0.40, 2)
        return make_checkout(
            technician_id=tech_id,
            subtotal=subtotal,
            tip_amount=tip,
            discount_amount=discount_amount,
            net_service=net,
            technician_share=tech_share,
            salon_share=salon_rev,
            salon_actual_revenue=salon_rev,
            technician_total=round(tech_share + tip, 2),
            customer_pays=round(net + tip, 2),
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
        today = date.today().isoformat()
        r = client.get(f"/income/tech?date={today}")
        assert r.status_code == 200
        assert len(r.json()["technicians"]) == 2

    def test_tech_income_report_sums_correctly(self):
        tech_id = make_tech("Mia").json()["id"]
        # Two checkouts: $100 + $80 = $180 gross
        self._seed_checkout(tech_id, subtotal=100.0, tip=10.0)
        self._seed_checkout(tech_id, subtotal=80.0, tip=5.0)
        today = date.today().isoformat()
        r = client.get(f"/income/tech?date={today}")
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
        today = date.today().isoformat()
        r = client.get(f"/income/tech?date={today}&technician_id={tech1_id}")
        assert r.status_code == 200
        techs = r.json()["technicians"]
        assert len(techs) == 1
        assert techs[0]["technician_id"] == tech1_id

    def test_tech_income_report_empty_when_no_checkouts(self):
        today = date.today().isoformat()
        r = client.get(f"/income/tech?date={today}")
        assert r.status_code == 200
        assert r.json()["technicians"] == []

    def test_tech_income_report_technicians_sorted_alphabetically(self):
        make_tech("Zoe").json()["id"]
        tech_a_id = make_tech("Amy").json()["id"]
        tech_z_id = client.get("/technicians?search=Zoe").json()[0]["id"]
        self._seed_checkout(tech_z_id)
        self._seed_checkout(tech_a_id)
        today = date.today().isoformat()
        r = client.get(f"/income/tech?date={today}")
        names = [t["technician_name"] for t in r.json()["technicians"]]
        assert names == sorted(names, key=str.lower)

    def test_salon_income_report_day_totals(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=20.0)
        today = date.today().isoformat()
        r = client.get(f"/income/salon?date={today}")
        assert r.status_code == 200
        day = r.json()["day"]
        assert day["income_before_discount"] == 100.0
        assert day["income_after_discount"] == 100.0
        assert day["tech_60_percent_total"] == 60.0
        assert day["salon_income_after_techs"] == 40.0
        assert day["tech_tip_total"] == 20.0
        assert day["turns"] == 1

    def test_salon_income_report_with_discount(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=0.0, discount_amount=10.0)
        today = date.today().isoformat()
        r = client.get(f"/income/salon?date={today}")
        day = r.json()["day"]
        assert day["income_before_discount"] == 100.0
        assert day["total_discount"] == 10.0
        assert day["income_after_discount"] == 90.0
        assert day["tech_60_percent_total"] == 54.0
        assert day["salon_income_after_techs"] == 36.0

    def test_salon_income_report_includes_day_week_year_periods(self):
        today = date.today().isoformat()
        r = client.get(f"/income/salon?date={today}")
        assert r.status_code == 200
        data = r.json()
        assert "day" in data
        assert "week" in data
        assert "year" in data

    def test_salon_income_report_includes_details(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id)
        today = date.today().isoformat()
        r = client.get(f"/income/salon?date={today}")
        details = r.json()["details"]
        assert len(details) == 1
        assert details[0]["technician_id"] == tech_id

    def test_salon_income_report_empty_day_when_no_checkouts(self):
        today = date.today().isoformat()
        r = client.get(f"/income/salon?date={today}")
        assert r.status_code == 200
        day = r.json()["day"]
        assert day["income_before_discount"] == 0.0
        assert day["turns"] == 0
        assert r.json()["details"] == []
