"""Authoritative customer communication preferences and consent history.

This module does not send messages or call a provider.  It only records explicit
decisions, contact-version changes and suppressions, then evaluates eligibility.
"""

import re
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models


CHANNELS = {"email", "sms"}
PURPOSES = {"transactional", "marketing"}
TRANSACTIONAL_DECISIONS = {"enabled", "disabled"}
MARKETING_DECISIONS = {"opted_in", "opted_out"}
DEFAULT_POLICY_VERSION = "v0.3-consent-foundation"
_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _validate_channel_purpose(channel: str, purpose: str) -> None:
    if channel not in CHANNELS:
        raise ValueError("Unsupported communication channel")
    if purpose not in PURPOSES:
        raise ValueError("Unsupported communication purpose")


def _state_field(channel: str, purpose: str) -> str:
    _validate_channel_purpose(channel, purpose)
    return f"{purpose}_{channel}_state"


def _contact_version(preference: models.CustomerCommunicationPreference, channel: str) -> int:
    return getattr(preference, "email_contact_version" if channel == "email" else "phone_contact_version")


def _append_event(
    db: Session,
    *,
    customer_id: int,
    channel: str,
    purpose: str,
    decision: str,
    contact_version: int,
    source: str,
    policy_version: str,
    idempotency_key: str,
    actor_type: str | None = None,
    actor_reference: str | None = None,
) -> models.CommunicationConsentEvent:
    existing = db.query(models.CommunicationConsentEvent).filter_by(idempotency_key=idempotency_key).first()
    if existing:
        expected = (customer_id, channel, purpose, decision, contact_version, source, policy_version)
        actual = (
            existing.customer_id,
            existing.channel,
            existing.purpose,
            existing.decision,
            existing.contact_version,
            existing.source,
            existing.policy_version,
        )
        if actual != expected:
            raise ValueError("Consent idempotency key was already used for a different decision")
        return existing
    event = models.CommunicationConsentEvent(
        customer_id=customer_id,
        channel=channel,
        purpose=purpose,
        decision=decision,
        contact_version=contact_version,
        source=source,
        policy_version=policy_version,
        occurred_at_utc=utc_now_naive(),
        actor_type=actor_type,
        actor_reference=actor_reference,
        idempotency_key=idempotency_key,
    )
    db.add(event)
    return event


def ensure_customer_preferences(
    db: Session,
    customer: models.Customer,
    *,
    source: str,
    policy_version: str = DEFAULT_POLICY_VERSION,
) -> models.CustomerCommunicationPreference:
    """Create fail-closed defaults and their four audit events once."""
    preference = db.get(models.CustomerCommunicationPreference, customer.id)
    if preference is not None:
        return preference
    preference = models.CustomerCommunicationPreference(customer_id=customer.id, updated_at_utc=utc_now_naive())
    db.add(preference)
    db.flush()
    for channel in sorted(CHANNELS):
        for purpose in sorted(PURPOSES):
            _append_event(
                db,
                customer_id=customer.id,
                channel=channel,
                purpose=purpose,
                decision="unknown",
                contact_version=_contact_version(preference, channel),
                source=source,
                policy_version=policy_version,
                idempotency_key=f"default:{source}:{customer.id}:{channel}:{purpose}:v1",
                actor_type="system",
            )
    return preference


def migrate_existing_customers(db: Session) -> int:
    """Add conservative defaults to legacy customers in one transaction. Safe to rerun."""
    created = 0
    try:
        for customer in db.query(models.Customer).order_by(models.Customer.id).all():
            if db.get(models.CustomerCommunicationPreference, customer.id) is None:
                ensure_customer_preferences(db, customer, source="migration_default")
                created += 1
        db.commit()
        return created
    except Exception:
        db.rollback()
        raise


def install_immutability_guards(engine) -> None:
    """Database-level append-only enforcement; ORM listeners provide a second guard."""
    if engine.dialect.name != "sqlite":
        return
    statements = (
        """CREATE TRIGGER IF NOT EXISTS communication_consent_events_no_update
           BEFORE UPDATE ON communication_consent_events
           BEGIN SELECT RAISE(ABORT, 'communication consent events are immutable'); END""",
        """CREATE TRIGGER IF NOT EXISTS communication_consent_events_no_delete
           BEFORE DELETE ON communication_consent_events
           BEGIN SELECT RAISE(ABORT, 'communication consent events are immutable'); END""",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def record_customer_decision(
    db: Session,
    customer: models.Customer,
    *,
    channel: str,
    purpose: str,
    decision: str,
    source: str,
    policy_version: str,
    idempotency_key: str,
    actor_type: str | None = None,
    actor_reference: str | None = None,
) -> models.CommunicationConsentEvent:
    """Record one explicit decision. No route exposes this as a bulk mutation."""
    _validate_channel_purpose(channel, purpose)
    allowed = TRANSACTIONAL_DECISIONS if purpose == "transactional" else MARKETING_DECISIONS
    if decision not in allowed:
        raise ValueError("Decision is not valid for this communication purpose")
    if not source or not policy_version or not idempotency_key:
        raise ValueError("Consent source, policy version and idempotency key are required")

    existing = db.query(models.CommunicationConsentEvent).filter_by(idempotency_key=idempotency_key).first()
    if existing:
        expected = (customer.id, channel, purpose, decision, source, policy_version)
        actual = (
            existing.customer_id,
            existing.channel,
            existing.purpose,
            existing.decision,
            existing.source,
            existing.policy_version,
        )
        if actual != expected:
            raise ValueError("Consent idempotency key was already used for a different decision")
        return existing

    preference = ensure_customer_preferences(db, customer, source="customer_creation_default")
    setattr(preference, _state_field(channel, purpose), decision)
    preference.updated_at_utc = utc_now_naive()
    preference.marketing_revalidation_required = (
        preference.marketing_email_state == "unknown" or preference.marketing_sms_state == "unknown"
    )
    return _append_event(
        db,
        customer_id=customer.id,
        channel=channel,
        purpose=purpose,
        decision=decision,
        contact_version=_contact_version(preference, channel),
        source=source,
        policy_version=policy_version,
        idempotency_key=idempotency_key,
        actor_type=actor_type,
        actor_reference=actor_reference,
    )


def invalidate_changed_contacts(
    db: Session,
    customer: models.Customer,
    *,
    new_email: str | None,
    new_phone_number: str,
    policy_version: str = DEFAULT_POLICY_VERSION,
) -> list[str]:
    """Invalidate only channels whose destination changed; prior events/suppressions stay intact."""
    preference = ensure_customer_preferences(db, customer, source="customer_creation_default")
    changed = []
    for channel, old_value, new_value in (
        ("email", customer.email, new_email),
        ("sms", customer.phone_number, new_phone_number),
    ):
        if old_value == new_value:
            continue
        changed.append(channel)
        version_field = "email_contact_version" if channel == "email" else "phone_contact_version"
        new_version = getattr(preference, version_field) + 1
        setattr(preference, version_field, new_version)
        setattr(preference, f"transactional_{channel}_state", "unknown")
        setattr(preference, f"marketing_{channel}_state", "unknown")
        for purpose in sorted(PURPOSES):
            _append_event(
                db,
                customer_id=customer.id,
                channel=channel,
                purpose=purpose,
                decision="unknown",
                contact_version=new_version,
                source="contact_change",
                policy_version=policy_version,
                idempotency_key=f"contact-change:{customer.id}:{channel}:{new_version}:{purpose}",
                actor_type="customer",
            )
    if changed:
        preference.updated_at_utc = utc_now_naive()
        preference.marketing_revalidation_required = True
    return changed


def add_suppression(
    db: Session,
    customer: models.Customer,
    *,
    channel: str,
    reason: str,
    source: str,
    provider_reference: str | None = None,
) -> models.CommunicationSuppression:
    if channel not in CHANNELS:
        raise ValueError("Unsupported communication channel")
    if not reason or not source:
        raise ValueError("Suppression reason and source are required")
    if provider_reference is not None and not _SAFE_REFERENCE.fullmatch(provider_reference):
        raise ValueError("Provider reference is not safe to store")
    preference = ensure_customer_preferences(db, customer, source="customer_creation_default")
    version = _contact_version(preference, channel)
    existing = db.query(models.CommunicationSuppression).filter_by(
        customer_id=customer.id, channel=channel, contact_version=version, lifted_at_utc=None
    ).first()
    if existing:
        return existing
    suppression = models.CommunicationSuppression(
        customer_id=customer.id,
        channel=channel,
        contact_version=version,
        reason=reason[:80],
        source=source[:80],
        provider_reference=provider_reference,
        created_at_utc=utc_now_naive(),
    )
    db.add(suppression)
    return suppression


def lift_suppression(db: Session, suppression: models.CommunicationSuppression) -> None:
    if suppression.lifted_at_utc is None:
        suppression.lifted_at_utc = utc_now_naive()


def evaluate_eligibility(db: Session, customer: models.Customer, *, channel: str, purpose: str) -> dict:
    """Return a contact-free, normalized eligibility decision. No provider is involved."""
    _validate_channel_purpose(channel, purpose)
    preference = db.get(models.CustomerCommunicationPreference, customer.id)
    if preference is None:
        return {"eligible": False, "reason": "preference_missing", "contact_version": None}
    version = _contact_version(preference, channel)
    suppressed = db.query(models.CommunicationSuppression.id).filter_by(
        customer_id=customer.id, channel=channel, contact_version=version, lifted_at_utc=None
    ).first()
    if suppressed:
        return {"eligible": False, "reason": "active_suppression", "contact_version": version}
    if channel == "email" and not customer.email:
        return {"eligible": False, "reason": "missing_contact", "contact_version": version}
    if channel == "sms" and not customer.phone_number:
        return {"eligible": False, "reason": "missing_contact", "contact_version": version}
    state = getattr(preference, _state_field(channel, purpose))
    allowed_state = "enabled" if purpose == "transactional" else "opted_in"
    if state != allowed_state:
        return {"eligible": False, "reason": state, "contact_version": version}
    return {"eligible": True, "reason": "eligible", "contact_version": version}
