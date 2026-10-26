from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from . import communication_preferences as consent
from . import main as main_module
from . import models
from .database import Base, get_db
from .main import app
from . import nailsystem_runtime


@pytest.fixture()
def store():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    nailsystem_runtime.install_sqlite_pragmas(engine)
    Base.metadata.create_all(engine)
    consent.install_immutability_guards(engine)
    sessions = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield engine, sessions
    finally:
        engine.dispose()


@pytest.fixture()
def db(store):
    _engine, sessions = store
    session = sessions()
    try:
        yield session
    finally:
        session.close()


def customer(db, *, phone="6025550100", email="customer@example.test"):
    row = models.Customer(
        full_name="Consent Customer",
        phone_number=phone,
        email=email,
        date_of_birth=date(1990, 1, 2),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def preference(db, row):
    return db.get(models.CustomerCommunicationPreference, row.id)


def decide(db, row, channel, purpose, decision, key):
    event = consent.record_customer_decision(
        db,
        row,
        channel=channel,
        purpose=purpose,
        decision=decision,
        source="customer_explicit_choice",
        policy_version="policy-test-1",
        idempotency_key=key,
        actor_type="customer",
    )
    db.commit()
    return event


class TestLegacyMigration:
    def test_existing_contact_data_stays_unknown_and_customer_is_preserved(self, db):
        row = customer(db)
        original = (row.full_name, row.phone_number, row.email, row.date_of_birth)

        assert consent.migrate_existing_customers(db) == 1
        state = preference(db, row)
        assert (
            state.transactional_email_state,
            state.transactional_sms_state,
            state.marketing_email_state,
            state.marketing_sms_state,
        ) == ("unknown", "unknown", "unknown", "unknown")
        assert (row.full_name, row.phone_number, row.email, row.date_of_birth) == original
        events = db.query(models.CommunicationConsentEvent).filter_by(customer_id=row.id).all()
        assert len(events) == 4
        assert {event.source for event in events} == {"migration_default"}
        assert {event.decision for event in events} == {"unknown"}

    def test_rerun_is_idempotent_and_foreign_keys_are_valid(self, db):
        row = customer(db)
        assert consent.migrate_existing_customers(db) == 1
        assert consent.migrate_existing_customers(db) == 0
        assert db.query(models.CustomerCommunicationPreference).filter_by(customer_id=row.id).count() == 1
        assert db.query(models.CommunicationConsentEvent).filter_by(customer_id=row.id).count() == 4
        assert db.execute(text("PRAGMA foreign_key_check")).fetchall() == []

    def test_consent_history_is_database_immutable(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        event_id = db.query(models.CommunicationConsentEvent.id).filter_by(customer_id=row.id).first()[0]
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE communication_consent_events SET decision='opted_in' WHERE id=:id"), {"id": event_id})
            db.commit()
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(text("DELETE FROM communication_consent_events WHERE id=:id"), {"id": event_id})
            db.commit()
        db.rollback()


class TestPurposeAndChannelSeparation:
    def test_each_purpose_and_channel_is_independent(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        decide(db, row, "email", "transactional", "enabled", "email-transactional")
        state = preference(db, row)
        assert state.transactional_email_state == "enabled"
        assert state.marketing_email_state == "unknown"
        assert state.transactional_sms_state == "unknown"
        assert state.marketing_sms_state == "unknown"

        decide(db, row, "sms", "marketing", "opted_in", "sms-marketing")
        assert state.transactional_email_state == "enabled"
        assert state.marketing_email_state == "unknown"
        assert state.transactional_sms_state == "unknown"
        assert state.marketing_sms_state == "opted_in"

    def test_opt_out_and_reopt_in_append_history(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        decide(db, row, "email", "marketing", "opted_in", "first-opt-in")
        decide(db, row, "email", "marketing", "opted_out", "opt-out")
        decide(db, row, "email", "marketing", "opted_in", "second-opt-in")
        decisions = [
            event.decision
            for event in db.query(models.CommunicationConsentEvent)
            .filter_by(customer_id=row.id, channel="email", purpose="marketing")
            .order_by(models.CommunicationConsentEvent.id)
        ]
        assert decisions == ["unknown", "opted_in", "opted_out", "opted_in"]

    def test_idempotent_retry_does_not_duplicate_and_collision_is_rejected(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        first = decide(db, row, "email", "marketing", "opted_in", "stable-key")
        again = decide(db, row, "email", "marketing", "opted_in", "stable-key")
        assert again.id == first.id
        assert db.query(models.CommunicationConsentEvent).filter_by(idempotency_key="stable-key").count() == 1
        with pytest.raises(ValueError, match="different decision"):
            consent.record_customer_decision(
                db,
                row,
                channel="email",
                purpose="marketing",
                decision="opted_out",
                source="customer_explicit_choice",
                policy_version="policy-test-1",
                idempotency_key="stable-key",
            )


class TestContactChange:
    def test_email_change_versions_and_invalidates_only_email(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        decide(db, row, "email", "transactional", "enabled", "email-tx")
        decide(db, row, "email", "marketing", "opted_in", "email-mkt")
        decide(db, row, "sms", "marketing", "opted_in", "sms-mkt")

        changed = consent.invalidate_changed_contacts(
            db, row, new_email="new@example.test", new_phone_number=row.phone_number
        )
        row.email = "new@example.test"
        db.commit()

        state = preference(db, row)
        assert changed == ["email"]
        assert state.email_contact_version == 2 and state.phone_contact_version == 1
        assert state.transactional_email_state == state.marketing_email_state == "unknown"
        assert state.marketing_sms_state == "opted_in"
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["reason"] == "unknown"
        history = db.query(models.CommunicationConsentEvent).filter_by(
            customer_id=row.id, channel="email", purpose="marketing"
        ).all()
        assert [event.contact_version for event in history] == [1, 1, 2]
        assert [event.decision for event in history] == ["unknown", "opted_in", "unknown"]

    def test_phone_change_versions_and_invalidates_sms(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        decide(db, row, "sms", "transactional", "enabled", "sms-tx")
        changed = consent.invalidate_changed_contacts(
            db, row, new_email=row.email, new_phone_number="6025550199"
        )
        row.phone_number = "6025550199"
        db.commit()
        state = preference(db, row)
        assert changed == ["sms"]
        assert state.phone_contact_version == 2
        assert state.transactional_sms_state == state.marketing_sms_state == "unknown"
        assert db.query(models.CommunicationConsentEvent).filter_by(
            customer_id=row.id, channel="sms", contact_version=1, decision="enabled"
        ).count() == 1


class TestSuppressionAndEligibility:
    def test_suppression_overrides_opt_in_and_lift_restores_preference(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        decide(db, row, "email", "marketing", "opted_in", "allow-email")
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["eligible"] is True
        suppression = consent.add_suppression(db, row, channel="email", reason="manual", source="owner")
        db.commit()
        result = consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")
        assert result == {"eligible": False, "reason": "active_suppression", "contact_version": 1}
        consent.lift_suppression(db, suppression)
        db.commit()
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["eligible"] is True

    def test_duplicate_active_suppression_is_not_created(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        first = consent.add_suppression(db, row, channel="sms", reason="manual", source="owner")
        db.commit()
        second = consent.add_suppression(db, row, channel="sms", reason="manual", source="owner")
        db.commit()
        assert second.id == first.id
        assert db.query(models.CommunicationSuppression).count() == 1

        duplicate = models.CommunicationSuppression(
            customer_id=row.id,
            channel="sms",
            contact_version=1,
            reason="hard_bounce",
            source="provider",
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_suppression_overrides_transactional_enabled(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        decide(db, row, "sms", "transactional", "enabled", "allow-transactional-sms")
        consent.add_suppression(db, row, channel="sms", reason="hard_bounce", source="provider")
        db.commit()
        result = consent.evaluate_eligibility(db, row, channel="sms", purpose="transactional")
        assert result == {"eligible": False, "reason": "active_suppression", "contact_version": 1}

    def test_opt_out_and_unknown_are_ineligible(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["reason"] == "unknown"
        decide(db, row, "email", "marketing", "opted_out", "deny-email")
        result = consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")
        assert result["eligible"] is False and result["reason"] == "opted_out"


class TestInternalEligibilityAPI:
    @pytest.fixture()
    def api(self, store):
        _engine, sessions = store
        previous_override = app.dependency_overrides.get(get_db)

        def override():
            session = sessions()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override
        client = TestClient(app)
        try:
            yield client, sessions
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_override

    def test_requires_internal_auth_and_returns_no_contact(self, api):
        client, sessions = api
        with sessions() as session:
            row = customer(session)
            consent.migrate_existing_customers(session)
            decide(session, row, "email", "marketing", "opted_in", "api-opt-in")
            customer_id = row.id
        path = f"/internal/customers/{customer_id}/communication-eligibility?channel=email&purpose=marketing"
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Internal-Service-Token": "wrong"}).status_code == 401
        response = client.get(path, headers={"X-Internal-Service-Token": "test-internal-token"})
        assert response.status_code == 200
        assert response.json() == {
            "customer_id": customer_id,
            "channel": "email",
            "purpose": "marketing",
            "eligible": True,
            "reason": "eligible",
            "contact_version": 1,
        }
        assert "email" not in response.text.lower().replace('"channel":"email"', "")
        assert "6025550100" not in response.text

    def test_eligibility_does_not_send_or_offer_bulk_mutation(self, api, monkeypatch):
        client, sessions = api
        monkeypatch.setattr(main_module, "send_birthday_email", lambda **_kwargs: pytest.fail("email provider called"))
        monkeypatch.setattr(main_module, "send_referral_discount_email", lambda **_kwargs: pytest.fail("email provider called"))
        with sessions() as session:
            row = customer(session)
            consent.migrate_existing_customers(session)
            customer_id = row.id
        response = client.get(
            f"/internal/customers/{customer_id}/communication-eligibility?channel=sms&purpose=marketing",
            headers={"X-Internal-Service-Token": "test-internal-token"},
        )
        assert response.status_code == 200
        assert response.json()["reason"] == "unknown"
        communication_routes = [
            route for route in app.routes if "communication" in getattr(route, "path", "")
        ]
        assert [(route.path, route.methods) for route in communication_routes] == [
            ("/internal/customers/{customer_id}/communication-eligibility", {"GET"})
        ]
