"""Authoritative customer communication preferences and consent history.

This module does not send messages or call a provider.  It only records explicit
decisions, contact-version changes and suppressions, then evaluates eligibility.
"""

import hashlib
import hmac
import os
import re
from datetime import datetime, timezone

from sqlalchemy import or_, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import models
from .phone_normalization import normalize_us_phone


CHANNELS = {"email", "sms"}
PURPOSES = {"transactional", "marketing"}
TRANSACTIONAL_DECISIONS = {"enabled", "disabled"}
MARKETING_DECISIONS = {"opted_in", "opted_out"}
DEFAULT_POLICY_VERSION = "v0.3-consent-foundation"
_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
CONSENT_SOURCES = frozenset({"migration_default", "customer_creation_default", "contact_change", "customer_explicit_choice"})
ACTOR_TYPES = frozenset({"system", "customer", "owner"})
SUPPRESSION_REASONS = frozenset({"manual", "hard_bounce"})
SUPPRESSION_SOURCES = frozenset({"owner", "provider"})
_FINGERPRINT_DOMAIN = b"nailsystem:communication-destination:v1\0"


class SuppressionConflict(ValueError):
    """A normalized failure for an unresolved suppression write conflict."""


def _safe_metadata(value: str | None, *, field: str, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not _SAFE_REFERENCE.fullmatch(value):
        raise ValueError(f"{field} is invalid")
    return value


def _canonical_destination(channel: str, value: str | None) -> str:
    if channel == "sms":
        return normalize_us_phone(value or "").e164
    if channel != "email":
        raise ValueError("Unsupported communication channel")
    raw = str(value or "").strip()
    local, separator, domain = raw.rpartition("@")
    if not separator or not local or not domain:
        raise ValueError("Customer has no valid destination for that channel")
    try:
        canonical_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Customer has no valid destination for that channel") from exc
    # SMTP local-parts are not universally case-insensitive. Preserve them;
    # normalize only surrounding whitespace and the case-insensitive domain.
    return f"{local}@{canonical_domain}"


def destination_fingerprint(channel: str, value: str | None) -> str:
    """Return a domain-separated keyed digest; never persist another contact copy."""
    pepper = os.environ.get("CHECKIN_INTERNAL_SERVICE_TOKEN", "")
    if len(pepper) < 16:
        raise RuntimeError("The communication fingerprint secret is unavailable")
    canonical = _canonical_destination(channel, value)
    payload = _FINGERPRINT_DOMAIN + channel.encode("ascii") + b"\0" + canonical.encode("utf-8")
    key_id = hmac.new(pepper.encode("utf-8"), _FINGERPRINT_DOMAIN + b"key-id", hashlib.sha256).hexdigest()[:12]
    digest = hmac.new(pepper.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"v1:{key_id}:{digest}"


def _fingerprint_key_prefix(fingerprint: str) -> str:
    return fingerprint.rsplit(":", 1)[0] + ":"


def _customer_destination(customer: models.Customer, channel: str) -> str | None:
    return customer.email if channel == "email" else customer.phone_number


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
    if source not in CONSENT_SOURCES:
        raise ValueError("Consent source is invalid")
    if actor_type is not None and actor_type not in ACTOR_TYPES:
        raise ValueError("Consent actor type is invalid")
    _safe_metadata(policy_version, field="Consent policy version")
    _safe_metadata(idempotency_key, field="Consent idempotency key")
    _safe_metadata(actor_reference, field="Consent actor reference", required=False)
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
        """CREATE TRIGGER IF NOT EXISTS communication_consent_events_no_collision
           BEFORE INSERT ON communication_consent_events
           WHEN EXISTS (
               SELECT 1 FROM communication_consent_events
               WHERE id = NEW.id OR idempotency_key = NEW.idempotency_key
           )
           BEGIN SELECT RAISE(ABORT, 'communication consent event already exists'); END""",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def install_consent_hardening(engine) -> None:
    """Idempotently harden Phase-1 or newly created SQLite consent tables.

    Historical suppressions are fingerprinted only when their contact version is
    still current and the corresponding destination is therefore known. An
    active unresolved row remains NULL and deliberately blocks that customer's
    channel until it is explicitly lifted.
    """
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        if "communication_suppressions" not in tables:
            return
        # Python's sqlite3 driver otherwise may not BEGIN for DDL, which would
        # let ALTER TABLE survive a later migration failure. Force one atomic
        # write transaction before the first schema or data change.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(communication_suppressions)"))}
        if "destination_fingerprint" not in columns:
            connection.execute(text("ALTER TABLE communication_suppressions ADD COLUMN destination_fingerprint VARCHAR(80)"))

        rows = connection.execute(text("""
            SELECT s.id, s.channel, s.contact_version, c.email, c.phone_number,
                   p.email_contact_version, p.phone_contact_version
            FROM communication_suppressions s
            JOIN customers c ON c.id = s.customer_id
            JOIN customer_communication_preferences p ON p.customer_id = s.customer_id
            WHERE s.destination_fingerprint IS NULL
        """)).mappings().all()
        for row in rows:
            current_version = row["email_contact_version"] if row["channel"] == "email" else row["phone_contact_version"]
            destination = row["email"] if row["channel"] == "email" else row["phone_number"]
            if row["contact_version"] == current_version and destination:
                fingerprint = destination_fingerprint(row["channel"], destination)
                connection.execute(
                    text("UPDATE communication_suppressions SET destination_fingerprint=:fingerprint WHERE id=:id"),
                    {"fingerprint": fingerprint, "id": row["id"]},
                )

        statements = (
            "DROP INDEX IF EXISTS uq_active_communication_suppression",
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_active_destination_suppression
               ON communication_suppressions (customer_id, channel, destination_fingerprint)
               WHERE lifted_at_utc IS NULL AND destination_fingerprint IS NOT NULL""",
            """CREATE TRIGGER IF NOT EXISTS communication_suppressions_require_fingerprint
               BEFORE INSERT ON communication_suppressions
               WHEN NEW.destination_fingerprint IS NULL
               BEGIN SELECT RAISE(ABORT, 'destination fingerprint is required'); END""",
            """CREATE TRIGGER IF NOT EXISTS communication_suppressions_metadata_insert
               BEFORE INSERT ON communication_suppressions
               WHEN NEW.reason NOT IN ('manual','hard_bounce') OR NEW.source NOT IN ('owner','provider')
                    OR (NEW.provider_reference IS NOT NULL AND
                        (length(NEW.provider_reference) NOT BETWEEN 1 AND 128
                         OR NEW.provider_reference GLOB '*[^A-Za-z0-9._:-]*'))
               BEGIN SELECT RAISE(ABORT, 'communication suppression metadata is invalid'); END""",
            """CREATE TRIGGER IF NOT EXISTS communication_suppressions_metadata_update
               BEFORE UPDATE OF reason, source, provider_reference ON communication_suppressions
               WHEN NEW.reason NOT IN ('manual','hard_bounce') OR NEW.source NOT IN ('owner','provider')
                    OR (NEW.provider_reference IS NOT NULL AND
                        (length(NEW.provider_reference) NOT BETWEEN 1 AND 128
                         OR NEW.provider_reference GLOB '*[^A-Za-z0-9._:-]*'))
               BEGIN SELECT RAISE(ABORT, 'communication suppression metadata is invalid'); END""",
            """CREATE TRIGGER IF NOT EXISTS communication_consent_events_metadata_insert
               BEFORE INSERT ON communication_consent_events
               WHEN NEW.source NOT IN ('migration_default','customer_creation_default','contact_change','customer_explicit_choice')
                    OR (NEW.actor_type IS NOT NULL AND NEW.actor_type NOT IN ('system','customer','owner'))
                    OR length(NEW.policy_version) NOT BETWEEN 1 AND 128
                    OR length(NEW.idempotency_key) NOT BETWEEN 1 AND 128
                    OR (NEW.actor_reference IS NOT NULL AND
                        (length(NEW.actor_reference) NOT BETWEEN 1 AND 128
                         OR NEW.actor_reference GLOB '*[^A-Za-z0-9._:-]*'))
               BEGIN SELECT RAISE(ABORT, 'communication consent metadata is invalid'); END""",
            """CREATE TRIGGER IF NOT EXISTS customers_require_consent_anonymization
               BEFORE DELETE ON customers
               WHEN EXISTS (SELECT 1 FROM communication_consent_events WHERE customer_id=OLD.id)
               BEGIN SELECT RAISE(ABORT, 'customer deletion requires an approved consent-history anonymization workflow'); END""",
        )
        for statement in statements:
            connection.execute(text(statement))
        connection.commit()


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
    if reason not in SUPPRESSION_REASONS:
        raise ValueError("Suppression reason is invalid")
    if source not in SUPPRESSION_SOURCES:
        raise ValueError("Suppression source is invalid")
    _safe_metadata(provider_reference, field="Provider reference", required=False)
    preference = ensure_customer_preferences(db, customer, source="customer_creation_default")
    version = _contact_version(preference, channel)
    fingerprint = destination_fingerprint(channel, _customer_destination(customer, channel))
    db.execute(sqlite_insert(models.CommunicationSuppression).values(
        customer_id=customer.id,
        channel=channel,
        contact_version=version,
        destination_fingerprint=fingerprint,
        reason=reason,
        source=source,
        provider_reference=provider_reference,
        created_at_utc=utc_now_naive(),
    ).prefix_with("OR IGNORE"))
    suppression = db.query(models.CommunicationSuppression).filter_by(
        customer_id=customer.id,
        channel=channel,
        destination_fingerprint=fingerprint,
        lifted_at_utc=None,
    ).first()
    if suppression is None:
        raise SuppressionConflict("Suppression could not be recorded")
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
    if channel == "email" and not customer.email:
        return {"eligible": False, "reason": "missing_contact", "contact_version": version}
    if channel == "sms" and not customer.phone_number:
        return {"eligible": False, "reason": "missing_contact", "contact_version": version}
    fingerprint = destination_fingerprint(channel, _customer_destination(customer, channel))
    key_prefix = _fingerprint_key_prefix(fingerprint)
    suppressed = db.query(models.CommunicationSuppression.id).filter_by(
        customer_id=customer.id, channel=channel, lifted_at_utc=None
    ).filter(or_(
        models.CommunicationSuppression.destination_fingerprint == fingerprint,
        models.CommunicationSuppression.destination_fingerprint.is_(None),
        ~models.CommunicationSuppression.destination_fingerprint.like(f"{key_prefix}%"),
    )).first()
    if suppressed:
        return {"eligible": False, "reason": "active_suppression", "contact_version": version}
    state = getattr(preference, _state_field(channel, purpose))
    allowed_state = "enabled" if purpose == "transactional" else "opted_in"
    if state != allowed_state:
        return {"eligible": False, "reason": state, "contact_version": version}
    return {"eligible": True, "reason": "eligible", "contact_version": version}
