import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
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
    consent.install_consent_hardening(engine)
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

    def test_duplicate_insert_and_replace_cannot_change_original_event(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        original = db.query(models.CommunicationConsentEvent).filter_by(
            customer_id=row.id, channel="email", purpose="marketing"
        ).one()
        before = tuple(getattr(original, name) for name in (
            "id", "customer_id", "channel", "purpose", "decision", "contact_version",
            "source", "policy_version", "occurred_at_utc", "actor_type", "actor_reference", "idempotency_key",
        ))
        parameters = {
            "id": original.id + 1000,
            "customer_id": row.id,
            "key": original.idempotency_key,
        }
        for statement in (
            """INSERT INTO communication_consent_events
               (id,customer_id,channel,purpose,decision,contact_version,source,policy_version,occurred_at_utc,actor_type,idempotency_key)
               VALUES (:id,:customer_id,'email','marketing','opted_in',1,'migration_default','attack','2000-01-01','system',:key)""",
            """INSERT OR REPLACE INTO communication_consent_events
               (id,customer_id,channel,purpose,decision,contact_version,source,policy_version,occurred_at_utc,actor_type,idempotency_key)
               VALUES (:id,:customer_id,'email','marketing','opted_in',1,'migration_default','attack','2000-01-01','system',:key)""",
        ):
            with pytest.raises(IntegrityError):
                db.execute(text(statement), parameters)
                db.commit()
            db.rollback()
        preserved = db.get(models.CommunicationConsentEvent, original.id)
        after = tuple(getattr(preserved, name) for name in (
            "id", "customer_id", "channel", "purpose", "decision", "contact_version",
            "source", "policy_version", "occurred_at_utc", "actor_type", "actor_reference", "idempotency_key",
        ))
        assert after == before

    def test_normal_new_event_insert_still_succeeds(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        created = decide(db, row, "email", "marketing", "opted_in", "ordinary-new-event")
        assert created.id is not None


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

    def test_suppression_follows_destination_across_a_b_a_without_affecting_b(self, db):
        row = customer(db, email="person@Example.TEST")
        consent.migrate_existing_customers(db)
        decide(db, row, "email", "marketing", "opted_in", "allow-a")
        suppression = consent.add_suppression(db, row, channel="email", reason="manual", source="owner")
        db.commit()
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["reason"] == "active_suppression"

        consent.invalidate_changed_contacts(db, row, new_email="other@example.test", new_phone_number=row.phone_number)
        row.email = "other@example.test"
        db.commit()
        decide(db, row, "email", "marketing", "opted_in", "allow-b")
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["eligible"] is True

        consent.invalidate_changed_contacts(db, row, new_email="person@example.test", new_phone_number=row.phone_number)
        row.email = "person@example.test"
        db.commit()
        decide(db, row, "email", "marketing", "opted_in", "allow-a-again")
        result = consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")
        assert result["reason"] == "active_suppression"
        assert suppression.destination_fingerprint == consent.destination_fingerprint("email", "person@EXAMPLE.test")

    def test_lifted_destination_suppression_does_not_return_after_a_b_a(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        suppression = consent.add_suppression(db, row, channel="email", reason="manual", source="owner")
        consent.lift_suppression(db, suppression)
        db.commit()
        for address, key in (("other@example.test", "allow-other"), ("customer@example.test", "allow-original")):
            consent.invalidate_changed_contacts(db, row, new_email=address, new_phone_number=row.phone_number)
            row.email = address
            db.commit()
            decide(db, row, "email", "marketing", "opted_in", key)
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["eligible"] is True

    def test_fingerprint_is_keyed_normalized_and_contains_no_destination(self, caplog):
        phone_a = consent.destination_fingerprint("sms", "(602) 555-0100")
        phone_b = consent.destination_fingerprint("sms", "+1 602-555-0100")
        email_a = consent.destination_fingerprint("email", " person@Example.TEST ")
        email_b = consent.destination_fingerprint("email", "person@example.test")
        assert phone_a == phone_b and email_a == email_b
        assert consent.destination_fingerprint("email", "Person@example.test") != email_b
        assert phone_a.startswith("v1:") and len(phone_a) == 80
        combined = phone_a + email_a + caplog.text
        assert "6025550100" not in combined and "person@example.test" not in combined.lower()

    def test_fingerprint_key_rotation_fails_conservatively(self, db, monkeypatch):
        row = customer(db, email="first@example.test")
        consent.migrate_existing_customers(db)
        consent.add_suppression(db, row, channel="email", reason="manual", source="owner")
        db.commit()
        monkeypatch.setenv("CHECKIN_INTERNAL_SERVICE_TOKEN", "different-test-token-value")
        consent.invalidate_changed_contacts(db, row, new_email="different@example.test", new_phone_number=row.phone_number)
        row.email = "different@example.test"
        db.commit()
        decide(db, row, "email", "marketing", "opted_in", "after-key-rotation")
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["reason"] == "active_suppression"

    def test_rotation_preserves_unresolved_and_new_destination_suppression(self, db, monkeypatch):
        row = customer(db, email="person@example.test")
        consent.migrate_existing_customers(db)
        decide(db, row, "email", "marketing", "opted_in", "rotation-opt-in")
        old = consent.add_suppression(db, row, channel="email", reason="manual", source="owner")
        db.commit()

        monkeypatch.setenv("CHECKIN_INTERNAL_SERVICE_TOKEN", "different-test-token-value")
        new = consent.add_suppression(
            db, row, channel="email", reason="hard_bounce", source="provider", provider_reference="bounce-1"
        )
        db.commit()

        active = db.query(models.CommunicationSuppression).filter_by(
            customer_id=row.id, channel="email", lifted_at_utc=None
        ).order_by(models.CommunicationSuppression.id).all()
        assert [item.id for item in active] == [old.id, new.id]
        assert old.destination_fingerprint != new.destination_fingerprint
        assert (new.reason, new.source, new.provider_reference) == ("hard_bounce", "provider", "bounce-1")

        consent.lift_suppression(db, old)
        db.commit()
        remaining = db.query(models.CommunicationSuppression).filter_by(
            customer_id=row.id, channel="email", lifted_at_utc=None
        ).one()
        assert remaining.id == new.id and remaining.reason == "hard_bounce"
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing")["reason"] == "active_suppression"

    def test_missing_email_remains_a_controlled_ineligible_result(self, db):
        row = customer(db, email=None)
        consent.migrate_existing_customers(db)
        assert consent.evaluate_eligibility(db, row, channel="email", purpose="marketing") == {
            "eligible": False, "reason": "missing_contact", "contact_version": 1,
        }

    def test_metadata_is_allowlisted_and_bounded(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        with pytest.raises(ValueError, match="source"):
            consent.record_customer_decision(
                db, row, channel="email", purpose="marketing", decision="opted_in",
                source="secret customer@example.test", policy_version="policy", idempotency_key="bad-source",
            )
        with pytest.raises(ValueError, match="actor reference"):
            consent.record_customer_decision(
                db, row, channel="email", purpose="marketing", decision="opted_in",
                source="customer_explicit_choice", policy_version="policy", idempotency_key="bad-actor",
                actor_reference="customer@example.test",
            )
        with pytest.raises(ValueError, match="reference"):
            consent.add_suppression(
                db, row, channel="email", reason="hard_bounce", source="provider",
                provider_reference="x" * 129,
            )
        with pytest.raises(ValueError, match="reason"):
            consent.add_suppression(db, row, channel="email", reason="free text", source="owner")
        with pytest.raises(IntegrityError, match="metadata"):
            db.execute(text("""INSERT INTO communication_consent_events
                (customer_id,channel,purpose,decision,contact_version,source,policy_version,occurred_at_utc,actor_type,idempotency_key)
                VALUES (:customer_id,'email','marketing','unknown',1,'free_text','policy','2026-01-01','system','raw-invalid')"""),
                {"customer_id": row.id})
            db.commit()
        db.rollback()
        assert db.query(models.Customer).count() == 1

    def test_atomic_duplicate_suppression_keeps_session_usable(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        first = consent.add_suppression(db, row, channel="sms", reason="manual", source="owner")
        second = consent.add_suppression(db, row, channel="sms", reason="hard_bounce", source="provider")
        db.commit()
        assert first.id == second.id
        assert db.query(models.CommunicationSuppression).filter_by(lifted_at_utc=None).count() == 1
        assert db.query(models.Customer).count() == 1

    def test_concurrent_duplicate_suppression_leaves_one_active_row(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"check_same_thread": False})
        nailsystem_runtime.install_sqlite_pragmas(engine)
        Base.metadata.create_all(engine)
        consent.install_immutability_guards(engine)
        consent.install_consent_hardening(engine)
        sessions = sessionmaker(bind=engine)
        with sessions() as session:
            row = customer(session)
            consent.migrate_existing_customers(session)
            customer_id = row.id
        barrier = threading.Barrier(2)

        def create_duplicate():
            with sessions() as session:
                row = session.get(models.Customer, customer_id)
                barrier.wait(timeout=5)
                suppression = consent.add_suppression(
                    session, row, channel="sms", reason="manual", source="owner"
                )
                session.commit()
                return suppression.id

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = [future.result(timeout=10) for future in (pool.submit(create_duplicate), pool.submit(create_duplicate))]
        with sessions() as session:
            assert ids[0] == ids[1]
            assert session.query(models.CommunicationSuppression).filter_by(lifted_at_utc=None).count() == 1
            assert session.query(models.Customer).count() == 1
        engine.dispose()


class TestPhase2Migration:
    def test_legacy_database_upgrades_directly_without_implicit_consent(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
        nailsystem_runtime.install_sqlite_pragmas(engine)
        consent_names = {
            "customer_communication_preferences", "communication_consent_events", "communication_suppressions"
        }
        Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in consent_names])
        sessions = sessionmaker(bind=engine)
        with sessions() as session:
            row = customer(session)
            customer_id = row.id
        Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in consent_names])
        consent.install_immutability_guards(engine)
        consent.install_consent_hardening(engine)
        with sessions() as session:
            assert consent.migrate_existing_customers(session) == 1
            assert consent.migrate_existing_customers(session) == 0
            state = session.get(models.CustomerCommunicationPreference, customer_id)
            assert (
                state.transactional_email_state, state.transactional_sms_state,
                state.marketing_email_state, state.marketing_sms_state,
            ) == ("unknown", "unknown", "unknown", "unknown")
        engine.dispose()

    def test_phase1_suppression_backfills_and_rerun_is_idempotent(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'phase1.db'}")
        nailsystem_runtime.install_sqlite_pragmas(engine)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, email VARCHAR, phone_number VARCHAR NOT NULL)"))
            connection.execute(text("""CREATE TABLE customer_communication_preferences (
                customer_id INTEGER PRIMARY KEY, email_contact_version INTEGER NOT NULL, phone_contact_version INTEGER NOT NULL)"""))
            connection.execute(text("""CREATE TABLE communication_consent_events (
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, channel VARCHAR NOT NULL, purpose VARCHAR NOT NULL,
                decision VARCHAR NOT NULL, contact_version INTEGER NOT NULL, source VARCHAR NOT NULL, policy_version VARCHAR NOT NULL,
                occurred_at_utc DATETIME NOT NULL, actor_type VARCHAR, actor_reference VARCHAR, idempotency_key VARCHAR NOT NULL UNIQUE)"""))
            connection.execute(text("""CREATE TABLE communication_suppressions (
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, channel VARCHAR NOT NULL, contact_version INTEGER NOT NULL,
                reason VARCHAR NOT NULL, source VARCHAR NOT NULL, created_at_utc DATETIME NOT NULL,
                lifted_at_utc DATETIME, provider_reference VARCHAR)"""))
            connection.execute(text("INSERT INTO customers VALUES (1,'person@example.test','6025550100')"))
            connection.execute(text("INSERT INTO customer_communication_preferences VALUES (1,1,1)"))
            connection.execute(text("""INSERT INTO communication_suppressions
                VALUES (1,1,'email',1,'manual','owner','2026-01-01',NULL,NULL)"""))
        # Mirror application startup: create_all must remain safe before the
        # additive hardening migration adds the new column.
        Base.metadata.create_all(engine, tables=[
            Base.metadata.tables["customer_communication_preferences"],
            Base.metadata.tables["communication_consent_events"],
            Base.metadata.tables["communication_suppressions"],
        ])
        consent.install_immutability_guards(engine)
        consent.install_consent_hardening(engine)
        consent.install_consent_hardening(engine)
        with engine.connect() as connection:
            row = connection.execute(text("SELECT destination_fingerprint FROM communication_suppressions")).one()
            assert row[0] == consent.destination_fingerprint("email", "person@example.test")
            assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        engine.dispose()

    def test_unresolvable_legacy_suppression_fails_conservatively(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'old-suppression.db'}")
        nailsystem_runtime.install_sqlite_pragmas(engine)
        Base.metadata.create_all(engine)
        consent.install_immutability_guards(engine)
        # Simulate a Phase-1 row predating the fingerprint trigger.
        with engine.begin() as connection:
            connection.execute(text("DROP TRIGGER IF EXISTS communication_suppressions_require_fingerprint"))
            connection.execute(text("INSERT INTO customers (id,full_name,phone_number,email,date_of_birth,referral_count,referral_discount_percent,referral_discount_pending,referred_discount_pending,birthday_discount_amount,birthday_reminder_sent,visit_count_cycle,visit_discount_pending) VALUES (1,'Legacy','6025550100','new@example.test','1990-01-01',0,10,0,0,10,0,0,0)"))
            connection.execute(text("INSERT INTO customer_communication_preferences (customer_id,email_contact_version,phone_contact_version,updated_at_utc) VALUES (1,2,1,'2026-01-01')"))
            connection.execute(text("INSERT INTO communication_suppressions (id,customer_id,channel,contact_version,destination_fingerprint,reason,source,created_at_utc) VALUES (1,1,'email',1,NULL,'manual','owner','2026-01-01')"))
        consent.install_consent_hardening(engine)
        sessions = sessionmaker(bind=engine)
        with sessions() as session:
            row = session.get(models.Customer, 1)
            assert consent.evaluate_eligibility(session, row, channel="email", purpose="marketing")["reason"] == "active_suppression"
            consent.record_customer_decision(
                session,
                row,
                channel="email",
                purpose="marketing",
                decision="opted_in",
                source="customer_explicit_choice",
                policy_version="policy-test-1",
                idempotency_key="migrated-current-opt-in",
                actor_type="customer",
            )
            new = consent.add_suppression(
                session, row, channel="email", reason="hard_bounce", source="provider", provider_reference="bounce-migrated"
            )
            session.commit()
            active = session.query(models.CommunicationSuppression).filter_by(
                customer_id=row.id, channel="email", lifted_at_utc=None
            ).order_by(models.CommunicationSuppression.id).all()
            assert len(active) == 2
            unresolved = next(item for item in active if item.destination_fingerprint is None)
            assert (new.reason, new.source, new.provider_reference) == ("hard_bounce", "provider", "bounce-migrated")
            consent.lift_suppression(session, unresolved)
            session.commit()
            remaining = session.query(models.CommunicationSuppression).filter_by(lifted_at_utc=None).one()
            assert remaining.id == new.id
            assert consent.evaluate_eligibility(session, row, channel="email", purpose="marketing")["reason"] == "active_suppression"
        engine.dispose()

    def test_failed_hardening_rolls_back_backfill_and_rerun_recovers(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'failed-migration.db'}")
        nailsystem_runtime.install_sqlite_pragmas(engine)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, email VARCHAR, phone_number VARCHAR NOT NULL)"))
            connection.execute(text("""CREATE TABLE customer_communication_preferences (
                customer_id INTEGER PRIMARY KEY, email_contact_version INTEGER NOT NULL, phone_contact_version INTEGER NOT NULL)"""))
            connection.execute(text("""CREATE TABLE communication_consent_events (
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, channel VARCHAR NOT NULL, purpose VARCHAR NOT NULL,
                decision VARCHAR NOT NULL, contact_version INTEGER NOT NULL, source VARCHAR NOT NULL, policy_version VARCHAR NOT NULL,
                occurred_at_utc DATETIME NOT NULL, actor_type VARCHAR, actor_reference VARCHAR, idempotency_key VARCHAR NOT NULL UNIQUE)"""))
            connection.execute(text("""CREATE TABLE communication_suppressions (
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, channel VARCHAR NOT NULL, contact_version INTEGER NOT NULL,
                reason VARCHAR NOT NULL, source VARCHAR NOT NULL, created_at_utc DATETIME NOT NULL,
                lifted_at_utc DATETIME, provider_reference VARCHAR)"""))
            connection.execute(text("INSERT INTO customers VALUES (1,'person@example.test','6025550100')"))
            connection.execute(text("INSERT INTO customer_communication_preferences VALUES (1,1,1)"))
            connection.execute(text("INSERT INTO communication_suppressions VALUES (1,1,'email',1,'manual','owner','2026-01-01',NULL,NULL)"))
        consent.install_immutability_guards(engine)

        def fail_on_index(_connection, _cursor, statement, _parameters, _context, _executemany):
            if "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_destination_suppression" in statement:
                raise RuntimeError("forced migration failure")

        event.listen(engine, "before_cursor_execute", fail_on_index)
        with pytest.raises(RuntimeError, match="forced migration failure"):
            consent.install_consent_hardening(engine)
        event.remove(engine, "before_cursor_execute", fail_on_index)
        with engine.connect() as connection:
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(communication_suppressions)"))}
            assert "destination_fingerprint" not in columns
        consent.install_consent_hardening(engine)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT destination_fingerprint FROM communication_suppressions")).scalar_one()
        engine.dispose()

    def test_customer_with_consent_history_cannot_be_casually_deleted(self, db):
        row = customer(db)
        consent.migrate_existing_customers(db)
        with pytest.raises(IntegrityError, match="anonymization"):
            db.execute(text("DELETE FROM customers WHERE id=:id"), {"id": row.id})
            db.commit()
        db.rollback()
        assert db.get(models.Customer, row.id) is not None


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

    @pytest.mark.parametrize("identifier", ["not-an-integer", "0", "-1", str(2**63), "9" * 1000])
    def test_invalid_and_oversized_ids_are_controlled_after_auth(self, api, identifier):
        client, _sessions = api
        path = f"/internal/customers/{identifier}/communication-eligibility?channel=email&purpose=marketing"
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"X-Internal-Service-Token": "test-internal-token"})
        assert response.status_code == 422
        assert "sqlite" not in response.text.lower() and "overflow" not in response.text.lower()

    def test_valid_unknown_id_remains_not_found(self, api):
        client, _sessions = api
        response = client.get(
            "/internal/customers/9223372036854775807/communication-eligibility?channel=email&purpose=marketing",
            headers={"X-Internal-Service-Token": "test-internal-token"},
        )
        assert response.status_code == 404
