"""Pilot: the kiosk recognises a customer's appointment from the phone number, before any walk-in question.

The Owner is faked (conftest-style) at the one place the Check-In backend talks to it for appointments. All data is fake.
"""

import logging
import urllib.error

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.schema import CreateIndex, CreateTable

from . import kiosk_security, models, owner_appointments, schema_upgrade
from .database import Base
from .kiosk_security import DEVICE_TOKEN_HEADER
from .main import app
from .test_main import (  # noqa: F401  (autouse fixtures come from test_main)
    TestingSessionLocal,
    client,
    fake_emails,
    make_paired_device,
    register,
    reset_db,
)
from . import main as main_module

PHONE = "6025551234"
E164 = "+16025551234"
CODE = "APPT-PILOT-1"


class FakeOwnerAppointments:
    """What the Owner's GET /internal/appointments/lookup answers, per phone number."""

    def __init__(self):
        self.answers, self.calls, self.error = {}, [], None

    def fetch(self, base_url, token, phone_e164):
        self.calls.append((base_url, token, phone_e164))
        if self.error:
            raise self.error
        return self.answers.get(phone_e164, {"outcome": "none", "appointment": None})

    def one(self, phone=E164, *, code=CODE, name="Ana Test", services=((10, "Gel Manicure"),), technician="Amy", time="2030-01-01T14:00", status="scheduled"):
        self.answers[phone] = {"outcome": "one", "appointment": {
            "code": code, "appointment_time": time, "status": status, "customer_name": name,
            "services": [{"id": sid, "name": sname} for sid, sname in services], "technician_name": technician}}


@pytest.fixture
def ow(monkeypatch):
    fake = FakeOwnerAppointments()
    monkeypatch.setattr(owner_appointments.appointments_client, "fetcher", fake.fetch)
    monkeypatch.setenv("OWNER_API_BASE", "http://owner.test")
    return fake


def lookup(phone=PHONE, **kw):
    return client.post("/appointments/lookup", json={"phone_number": phone}, **kw)


def confirm(phone=PHONE, code=CODE):
    return client.post("/appointments/check-in", json={"phone_number": phone, "appointment_code": code})


def rows(model):
    db = TestingSessionLocal()
    try:
        return db.query(model).all()
    finally:
        db.close()


# ====================================================================================================== what the tablet is told
class TestLookup:

    def test_one_appointment_is_summarised_for_the_tablet(self, ow):
        ow.one()
        body = lookup().json()
        assert body == {"outcome": "one", "already_checked_in": False, "appointment": {
            "code": CODE, "time": "2030-01-01T14:00", "first_name": "Ana", "services": ["Gel Manicure"], "technician_name": "Amy"}}

    def test_the_owner_is_asked_with_the_normalised_number_and_the_service_token(self, ow):
        lookup("(602) 555-1234")
        assert ow.calls == [("http://owner.test", "test-internal-token", E164)]

    @pytest.mark.parametrize("typed", ["6025551234", "(602) 555-1234", "602-555-1234", "602.555.1234", "+16025551234"])
    def test_every_way_of_typing_the_same_number_asks_for_the_same_one(self, ow, typed):
        ow.one()
        assert lookup(typed).json()["appointment"]["code"] == CODE
        assert ow.calls[-1][2] == E164

    def test_any_technician_is_reported_as_none(self, ow):
        ow.one(technician=None)
        assert lookup().json()["appointment"]["technician_name"] is None

    def test_no_appointment(self, ow):
        assert lookup().json() == {"outcome": "none", "already_checked_in": False, "appointment": None}

    def test_several_appointments_are_never_guessed_and_none_is_shown(self, ow):
        ow.answers[E164] = {"outcome": "multiple", "appointment": None}
        assert lookup().json() == {"outcome": "multiple", "already_checked_in": False, "appointment": None}

    def test_an_appointment_without_service_ids_goes_to_staff(self, ow):
        ow.answers[E164] = {"outcome": "incomplete", "appointment": {"code": CODE, "appointment_time": "2030-01-01T14:00", "status": "scheduled", "customer_name": "Old", "services": [], "technician_name": None}}
        body = lookup().json()
        assert body["outcome"] == "staff" and body["appointment"] is None

    def test_the_answer_is_small_and_private(self, ow):
        ow.one(name="Ana Maria Test")
        register(PHONE, "Ana Maria Test", "1990-03-15", email="ana@example.com")
        text_ = lookup().text.lower()
        for private in ("1990", "ana@example.com", "maria", "test", "email", "date_of_birth", "customer_id", "visit"):
            assert private not in text_, private

    def test_already_checked_in_is_reported(self, ow):
        ow.one()
        assert confirm().status_code == 200
        assert lookup().json()["already_checked_in"] is True

    def test_it_needs_a_paired_tablet(self, ow):
        ow.one()
        browser = TestClient(app)
        assert browser.post("/appointments/lookup", json={"phone_number": PHONE}).status_code == 401
        assert browser.post("/appointments/check-in", json={"phone_number": PHONE, "appointment_code": CODE}).status_code == 401

    def test_it_is_rate_limited_per_tablet(self, ow):
        limit = kiosk_security.LIMITS["appointment_lookup"][0]
        codes = [lookup().status_code for _ in range(limit + 1)]
        assert codes[:limit] == [200] * limit and codes[-1] == 429

    def test_a_bad_phone_number_is_refused(self, ow):
        assert lookup("12345").status_code == 422
        assert client.post("/appointments/lookup", json={"phone_number": PHONE, "extra": 1}).status_code == 422


# ====================================================================================================== failures
class TestOwnerUnavailable:

    @pytest.mark.parametrize("error", [urllib.error.URLError("refused"), TimeoutError(), OSError("down"), ValueError("bad json")])
    def test_a_failure_is_never_reported_as_no_appointment(self, ow, error):
        ow.error = error
        response = lookup()
        assert response.status_code == 503
        assert response.json()["detail"] == "We couldn't check your appointment right now. Please ask a staff member for help."
        assert confirm().status_code == 503
        assert rows(models.Visit) == [] and rows(models.Customer) == []

    def test_an_unusable_answer_counts_as_a_failure(self, ow):
        for junk in (None, [], {"outcome": "maybe"}, {"outcome": "one", "appointment": None}, {"outcome": "one", "appointment": {"code": "x"}},
                     {"outcome": "one", "appointment": {"code": "c", "appointment_time": "t", "status": "scheduled", "customer_name": "n", "services": [{"id": True, "name": "x"}]}}):
            ow.answers[E164] = junk
            assert lookup().status_code == 503, junk

    def test_nothing_internal_leaks_to_the_log_or_the_screen(self, ow, caplog):
        ow.error = urllib.error.HTTPError("http://owner.test/x", 500, "Internal Server Error with secret detail", {}, None)
        with caplog.at_level(logging.INFO):
            response = lookup()
        assert response.status_code == 503
        assert PHONE not in caplog.text and E164 not in caplog.text and "secret detail" not in caplog.text and "test-internal-token" not in caplog.text
        assert "owner.test" not in response.text and "secret" not in response.text

    def test_not_configured_is_the_same_safe_failure(self, ow, monkeypatch):
        monkeypatch.delenv("OWNER_API_BASE")
        assert lookup().status_code == 503


# ====================================================================================================== the check-in itself
class TestCheckIn:

    def test_a_customer_known_only_from_the_appointment_is_checked_in_without_name_or_services(self, ow):
        ow.one(name="Ana Test", services=((10, "Gel Manicure"), (11, "Classic Pedicure")))
        response = confirm()
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["selected_service_ids"] == [10, 11] and body["selected_services"] == ["Gel Manicure", "Classic Pedicure"] and body["full_name"] == "Ana"
        customers, visits = rows(models.Customer), rows(models.Visit)
        assert len(customers) == 1 and len(visits) == 1
        assert customers[0].full_name == "Ana Test" and customers[0].phone_number == PHONE and customers[0].date_of_birth is None and customers[0].email is None
        assert visits[0].customer_id == customers[0].id and visits[0].appointment_code == CODE
        assert [(s.owner_service_id, s.service_name) for s in sorted(rows(models.VisitOwnerService), key=lambda s: s.id)] == [(10, "Gel Manicure"), (11, "Classic Pedicure")]

    def test_the_owner_queue_sees_the_visit_tied_to_the_appointment_with_its_services(self, ow):
        ow.one(services=((10, "Gel Manicure"),))
        confirm()
        item = client.get("/today-checkins").json()["checkins"][0]
        assert item["appointment_code"] == CODE and item["service_ids"] == [10] and item["services"] == ["Gel Manicure"] and item["phone_e164"] == E164

    def test_the_services_come_from_the_appointment_even_if_the_picker_would_not_offer_them(self, ow):
        ow.one(services=((99, "Retired Service"),))
        assert confirm().status_code == 200
        assert [s.owner_service_id for s in rows(models.VisitOwnerService)] == [99]

    def test_an_existing_customer_is_used_and_their_profile_is_never_changed(self, ow):
        register(PHONE, "Ana Original", "1990-03-15", email="ana@example.com")
        before = rows(models.Customer)[0]
        snapshot = (before.id, before.full_name, before.email, before.date_of_birth, before.referral_code, before.used_referral_code)
        ow.one(name="Ana Different Name")
        assert confirm().status_code == 200
        customers = rows(models.Customer)
        assert len(customers) == 1, "no duplicate customer"
        after = customers[0]
        assert (after.id, after.full_name, after.email, after.date_of_birth, after.referral_code, after.used_referral_code) == snapshot
        assert rows(models.Visit)[0].customer_id == after.id

    def test_tapping_twice_makes_one_visit_and_changes_nothing_more(self, ow):
        ow.one()
        first = confirm()
        cycle = rows(models.Customer)[0].visit_count_cycle
        again = confirm()
        third = confirm()
        assert first.status_code == again.status_code == third.status_code == 200
        assert len(rows(models.Visit)) == 1 and len(rows(models.Customer)) == 1
        assert rows(models.Customer)[0].visit_count_cycle == cycle == 1
        assert again.json()["selected_service_ids"] == first.json()["selected_service_ids"] and again.json()["discounts_applied"] == []

    def test_the_server_asks_the_owner_again_and_will_not_trust_the_browser(self, ow):
        ow.one(code=CODE)
        assert confirm(code="SOMEONE-ELSES-CODE").status_code == 409
        ow.answers[E164] = {"outcome": "multiple", "appointment": None}
        assert confirm().status_code == 409
        ow.answers.pop(E164)
        assert confirm().status_code == 409
        assert rows(models.Visit) == [] and rows(models.Customer) == []

    def test_a_staff_only_appointment_cannot_be_checked_in_at_the_kiosk(self, ow):
        ow.answers[E164] = {"outcome": "incomplete", "appointment": {"code": CODE, "appointment_time": "2030-01-01T14:00", "status": "scheduled", "customer_name": "Old", "services": [], "technician_name": None}}
        assert confirm().status_code == 409 and rows(models.Visit) == []

    def test_a_walk_in_still_works_exactly_as_before(self, ow):
        assert lookup().json()["outcome"] == "none"
        assert register(PHONE, "Walk In", "1991-02-03").status_code == 201
        done = client.post(f"/customers/check-in/{PHONE}", json={"selected_service_ids": [10]})
        assert done.status_code == 200 and done.json()["selected_service_ids"] == [10]
        assert rows(models.Visit)[0].appointment_code is None

    def test_the_customer_who_said_it_is_not_their_appointment_can_continue_normally(self, ow):
        ow.one()
        assert lookup().json()["outcome"] == "one"            # the tablet showed it...
        register(PHONE, "Someone Else", "1985-05-05")           # ...and the customer carried on as a walk-in
        assert client.post(f"/customers/check-in/{PHONE}", json={"selected_service_ids": [12]}).status_code == 200
        assert rows(models.Visit)[0].appointment_code is None and ow.calls[-1][2] == E164

    def test_the_first_tap_is_rate_limited_per_tablet(self, ow):
        ow.one()
        limit = kiosk_security.LIMITS["appointment_checkin"][0]
        codes = [confirm(code=f"X{i}").status_code for i in range(limit + 1)]
        assert codes[-1] == 429


# ====================================================================================================== customers without a birth date
class TestCustomerWithoutBirthDate:

    def make(self, ow):
        ow.one()
        assert confirm().status_code == 200
        return rows(models.Customer)[0]

    def test_a_returning_lookup_still_works_for_them(self, ow):
        self.make(ow)
        body = client.get(f"/customers/by-phone/{PHONE}").json()
        assert body["first_name"] == "Ana" and set(body) == {"first_name", "phone_number", "phone_number_formatted", "email_hint", "has_referral_code"}

    def test_the_tablet_cannot_open_their_profile(self, ow):
        self.make(ow)
        response = client.post(f"/customers/{PHONE}/profile-access", json={"date_of_birth": "1990-01-01"})
        assert response.status_code == 403 and "staff" in response.json()["detail"].lower()

    def test_birthday_logic_skips_them_without_errors(self, ow):
        self.make(ow)
        assert client.get("/birthday-reminders").status_code == 200 and client.get("/birthday-reminders").json() == []
        assert client.post("/birthday-reminders/send").status_code == 200
        assert main_module.days_until_next_birthday(None) == -1 and main_module.is_exact_birthday(None) is False

    def test_the_internal_customer_record_serialises(self, ow):
        customer = self.make(ow)
        record = client.get(f"/customers/id/{customer.id}").json()
        assert record["date_of_birth"] is None and record["full_name"] == "Ana Test"

    def test_a_normal_check_in_works_for_them_on_a_later_day(self, ow):
        self.make(ow)
        db = TestingSessionLocal()
        for visit in db.query(models.Visit).all():
            visit.visit_date = visit.visit_date.replace(year=2000)
        db.commit()
        db.close()
        assert client.post(f"/customers/check-in/{PHONE}", json={"selected_service_ids": [10]}).status_code == 200

    def test_a_name_with_markup_is_never_stored_as_is(self, ow):
        ow.one(name="<script>alert(1)</script> Eve")
        assert confirm().status_code == 200
        assert "<" not in rows(models.Customer)[0].full_name


# ====================================================================================================== upgrading an existing database
OLD_CUSTOMERS = None


def _old_style_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    from . import nailsystem_runtime
    nailsystem_runtime.install_sqlite_pragmas(engine)
    ddl = str(CreateTable(models.Customer.__table__).compile(engine)).replace("date_of_birth DATE", "date_of_birth DATE NOT NULL")
    with engine.begin() as connection:
        connection.exec_driver_sql(ddl)
        for index in models.Customer.__table__.indexes:
            connection.execute(CreateIndex(index))
    Base.metadata.create_all(engine)  # visits and the rest (customers already exists)
    return engine


class TestBirthDateUpgrade:

    def test_an_old_database_is_rebuilt_without_losing_a_thing(self, tmp_path):
        engine = _old_style_engine(tmp_path)
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO customers (id, full_name, phone_number, date_of_birth, referral_count, referral_discount_percent, referral_discount_pending, "
                                       "referred_discount_pending, birthday_discount_amount, visit_count_cycle, visit_discount_pending) VALUES "
                                       "(1,'Ann','6025550001','1990-01-02',0,10,0,0,10,3,0),(2,'Bo','6025550002','1985-05-06',2,10,1,0,10,7,1)")
            connection.exec_driver_sql("INSERT INTO visits (id, customer_id, visit_date, checked_in_at) VALUES (1,1,'2026-01-01','2026-01-01 10:00:00'),(2,2,'2026-01-01','2026-01-01 11:00:00')")
            connection.exec_driver_sql("INSERT INTO visit_owner_services (visit_id, owner_service_id, service_name) VALUES (1,10,'Gel Manicure')")
        before = None
        with engine.connect() as connection:
            before = connection.exec_driver_sql("SELECT * FROM customers ORDER BY id").fetchall()
        with pytest.raises(Exception):
            with engine.begin() as connection:
                connection.exec_driver_sql("INSERT INTO customers (full_name, phone_number, date_of_birth) VALUES ('X','6025550009',NULL)")

        assert schema_upgrade.make_birth_date_optional(engine) is True

        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT * FROM customers ORDER BY id").fetchall() == before
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM visits").scalar() == 2 and connection.exec_driver_sql("SELECT COUNT(*) FROM visit_owner_services").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1, "foreign keys are switched back on"
            names = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='customers'")}
            assert "ix_customers_phone_number" in names and "ix_customers_id" in names
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO customers (full_name, phone_number, date_of_birth, referral_count, referral_discount_percent, referral_discount_pending, referred_discount_pending, "
                                       "birthday_discount_amount, visit_count_cycle, visit_discount_pending) VALUES ('Unknown','6025550003',NULL,0,10,0,0,10,0,0)")
        with pytest.raises(Exception):  # the phone number is still unique
            with engine.begin() as connection:
                connection.exec_driver_sql("INSERT INTO customers (full_name, phone_number, date_of_birth, referral_count, referral_discount_percent, referral_discount_pending, referred_discount_pending, "
                                           "birthday_discount_amount, visit_count_cycle, visit_discount_pending) VALUES ('Dup','6025550003',NULL,0,10,0,0,10,0,0)")

    def test_running_it_again_does_nothing(self, tmp_path):
        engine = _old_style_engine(tmp_path)
        assert schema_upgrade.make_birth_date_optional(engine) is True
        assert schema_upgrade.make_birth_date_optional(engine) is False

    def test_a_new_database_is_left_alone(self, tmp_path):
        engine = create_engine(f"sqlite:///{(tmp_path / 'new.db').as_posix()}")
        assert schema_upgrade.make_birth_date_optional(engine) is False  # no tables yet
        Base.metadata.create_all(engine)
        assert schema_upgrade.make_birth_date_optional(engine) is False  # created already optional

    def test_a_problem_rolls_everything_back(self, tmp_path, monkeypatch):
        engine = _old_style_engine(tmp_path)
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO customers (id, full_name, phone_number, date_of_birth, referral_count, referral_discount_percent, referral_discount_pending, "
                                       "referred_discount_pending, birthday_discount_amount, visit_count_cycle, visit_discount_pending) VALUES (1,'Ann','6025550001','1990-01-02',0,10,0,0,10,3,0)")
        monkeypatch.setattr(schema_upgrade.re, "subn", lambda *a, **k: ("", 0))  # an unexpected table definition
        with pytest.raises(RuntimeError):
            schema_upgrade.make_birth_date_optional(engine)
        monkeypatch.undo()
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM customers").scalar() == 1
            assert not connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE name='customers_new'").fetchall()
            assert connection.exec_driver_sql("PRAGMA table_info(customers)").fetchall()[3][3] in (0, 1)
        assert schema_upgrade.make_birth_date_optional(engine) is True, "and it can still be done afterwards"
