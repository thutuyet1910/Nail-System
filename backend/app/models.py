from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, event, text
from sqlalchemy.orm import relationship

from .database import Base
from .timeutils import now_local


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)  # unknown for a customer first recorded from an appointment (see schema_upgrade.py)

    # Referral: this customer's own code and the reward they earn from it
    referral_code = Column(String, unique=True, nullable=True)
    referral_count = Column(Integer, default=0, nullable=False)
    referral_discount_percent = Column(Integer, default=10)
    referral_discount_pending = Column(Boolean, default=False, nullable=False)

    # Referral: the code this customer entered (10% off their visit)
    used_referral_code = Column(String, nullable=True)
    used_referral_from_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    referred_discount_pending = Column(Boolean, default=False, nullable=False)

    # Birthday
    birthday_discount_amount = Column(Integer, default=10)
    birthday_discount_used_month = Column(String, nullable=True)
    birthday_reminder_sent = Column(Boolean, default=False)
    birthday_reminder_sent_date = Column(Date, nullable=True)

    # Loyalty
    visit_count_cycle = Column(Integer, default=0, nullable=False)
    visit_discount_pending = Column(Boolean, default=False, nullable=False)

    visits = relationship("Visit", back_populates="customer", cascade="all, delete-orphan")
    referral_usages_as_owner = relationship(
        "ReferralUsage",
        foreign_keys="ReferralUsage.code_owner_customer_id",
        back_populates="code_owner",
        cascade="all, delete-orphan",
    )
    referral_usages_as_user = relationship(
        "ReferralUsage",
        foreign_keys="ReferralUsage.used_by_customer_id",
        back_populates="used_by_customer",
        cascade="all, delete-orphan",
    )

    communication_preferences = relationship(
        "CustomerCommunicationPreference", back_populates="customer", uselist=False, cascade="all, delete-orphan"
    )
    communication_consent_events = relationship(
        "CommunicationConsentEvent", back_populates="customer", cascade="all, delete-orphan"
    )
    communication_suppressions = relationship(
        "CommunicationSuppression", back_populates="customer", cascade="all, delete-orphan"
    )


class CustomerCommunicationPreference(Base):
    """Current communication eligibility projection. Contact values remain on Customer."""

    __tablename__ = "customer_communication_preferences"
    __table_args__ = (
        CheckConstraint("transactional_email_state IN ('unknown', 'enabled', 'disabled')", name="ck_pref_transactional_email"),
        CheckConstraint("transactional_sms_state IN ('unknown', 'enabled', 'disabled')", name="ck_pref_transactional_sms"),
        CheckConstraint("marketing_email_state IN ('unknown', 'opted_in', 'opted_out')", name="ck_pref_marketing_email"),
        CheckConstraint("marketing_sms_state IN ('unknown', 'opted_in', 'opted_out')", name="ck_pref_marketing_sms"),
        CheckConstraint("email_contact_version >= 1", name="ck_pref_email_contact_version"),
        CheckConstraint("phone_contact_version >= 1", name="ck_pref_phone_contact_version"),
    )

    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    transactional_email_state = Column(String, nullable=False, default="unknown", server_default="unknown")
    transactional_sms_state = Column(String, nullable=False, default="unknown", server_default="unknown")
    marketing_email_state = Column(String, nullable=False, default="unknown", server_default="unknown")
    marketing_sms_state = Column(String, nullable=False, default="unknown", server_default="unknown")
    email_contact_version = Column(Integer, nullable=False, default=1, server_default="1")
    phone_contact_version = Column(Integer, nullable=False, default=1, server_default="1")
    updated_at_utc = Column(DateTime, nullable=False, default=_utc_now_naive)
    marketing_revalidation_required = Column(Boolean, nullable=False, default=True, server_default="1")

    customer = relationship("Customer", back_populates="communication_preferences")


class CommunicationConsentEvent(Base):
    """Immutable consent history. Application and database guards reject updates/deletes."""

    __tablename__ = "communication_consent_events"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'sms')", name="ck_consent_event_channel"),
        CheckConstraint("purpose IN ('transactional', 'marketing')", name="ck_consent_event_purpose"),
        CheckConstraint(
            "decision IN ('unknown', 'enabled', 'disabled', 'opted_in', 'opted_out')",
            name="ck_consent_event_decision",
        ),
        CheckConstraint("contact_version >= 1", name="ck_consent_event_contact_version"),
        CheckConstraint(
            "source IN ('migration_default', 'customer_creation_default', 'contact_change', 'customer_explicit_choice')",
            name="ck_consent_event_source",
        ),
        CheckConstraint("actor_type IS NULL OR actor_type IN ('system', 'customer', 'owner')", name="ck_consent_event_actor_type"),
        CheckConstraint("length(policy_version) BETWEEN 1 AND 128", name="ck_consent_event_policy_version_length"),
        CheckConstraint("actor_reference IS NULL OR length(actor_reference) BETWEEN 1 AND 128", name="ck_consent_event_actor_reference_length"),
        CheckConstraint("length(idempotency_key) BETWEEN 1 AND 128", name="ck_consent_event_idempotency_key_length"),
    )

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String, nullable=False, index=True)
    purpose = Column(String, nullable=False, index=True)
    decision = Column(String, nullable=False)
    contact_version = Column(Integer, nullable=False)
    source = Column(String, nullable=False)
    policy_version = Column(String, nullable=False)
    occurred_at_utc = Column(DateTime, nullable=False, default=_utc_now_naive, index=True)
    actor_type = Column(String, nullable=True)
    actor_reference = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)

    customer = relationship("Customer", back_populates="communication_consent_events")


@event.listens_for(CommunicationConsentEvent, "before_update")
@event.listens_for(CommunicationConsentEvent, "before_delete")
def _consent_events_are_immutable(_mapper, _connection, _target):
    raise ValueError("Communication consent events are immutable")


class CommunicationSuppression(Base):
    __tablename__ = "communication_suppressions"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'sms')", name="ck_communication_suppression_channel"),
        CheckConstraint("contact_version >= 1", name="ck_communication_suppression_contact_version"),
        CheckConstraint("reason IN ('manual', 'hard_bounce')", name="ck_communication_suppression_reason"),
        CheckConstraint("source IN ('owner', 'provider')", name="ck_communication_suppression_source"),
    )

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String, nullable=False, index=True)
    contact_version = Column(Integer, nullable=False)
    # Nullable only so Phase-1 rows whose historical destination is no longer
    # available can be retained. A database trigger rejects NULL for new rows.
    destination_fingerprint = Column(String(80), nullable=True)
    reason = Column(String, nullable=False)
    source = Column(String, nullable=False)
    created_at_utc = Column(DateTime, nullable=False, default=_utc_now_naive, index=True)
    lifted_at_utc = Column(DateTime, nullable=True, index=True)
    provider_reference = Column(String, nullable=True)

    customer = relationship("Customer", back_populates="communication_suppressions")


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = (
        Index("uq_visit_customer_date", "customer_id", "visit_date", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    visit_date = Column(Date, nullable=False)
    checked_in_at = Column(DateTime, nullable=False, default=now_local)
    appointment_code = Column(String, nullable=True, index=True)  # the Owner appointment the customer confirmed at the kiosk, if any
    discount_type = Column(String, nullable=True)
    discount_value = Column(Float, nullable=True, default=0)
    discount_label = Column(String, nullable=True)

    customer = relationship("Customer", back_populates="visits")
    visit_services = relationship("VisitService", back_populates="visit", cascade="all, delete-orphan")
    owner_services = relationship(
        "VisitOwnerService",
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="VisitOwnerService.id",
    )


class Service(Base):
    """LEGACY local catalog. No longer used for new selections (Owner booking_services is
    authoritative); kept only so historical visit_services rows stay readable."""

    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    visit_services = relationship("VisitService", back_populates="service", cascade="all, delete-orphan")


class VisitService(Base):
    __tablename__ = "visit_services"

    id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(Integer, ForeignKey("visits.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)

    visit = relationship("Visit", back_populates="visit_services")
    service = relationship("Service", back_populates="visit_services")


class VisitOwnerService(Base):
    """A service chosen at check-in, keyed by the Owner's stable BookingService id.

    `service_name` is the display name at check-in time (a snapshot for history); integrations
    should use `owner_service_id`. Legacy visits have rows in `visit_services` instead.
    """

    __tablename__ = "visit_owner_services"
    __table_args__ = (
        Index("uq_visit_owner_service", "visit_id", "owner_service_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(Integer, ForeignKey("visits.id"), nullable=False, index=True)
    owner_service_id = Column(Integer, nullable=False)
    service_name = Column(String, nullable=False)

    visit = relationship("Visit", back_populates="owner_services")


class ReferralUsage(Base):
    __tablename__ = "referral_usages"
    __table_args__ = (
        # A customer can only ever use one referral code.
        Index("uq_referral_used_by", "used_by_customer_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=False)
    code_owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    used_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    used_on = Column(Date, nullable=False)

    code_owner = relationship(
        "Customer",
        foreign_keys=[code_owner_customer_id],
        back_populates="referral_usages_as_owner",
    )
    used_by_customer = relationship(
        "Customer",
        foreign_keys=[used_by_customer_id],
        back_populates="referral_usages_as_user",
    )

class KioskDevice(Base):
    """A paired check-in tablet.

    Created PENDING by the Owner (pairing code), becomes PAIRED when the tablet redeems the code, and
    ends REVOKED. Only SHA-256 hashes are stored: the pairing code and the device token are shown once and
    cannot be recovered from the database. The token grants kiosk routes only (see kiosk_security.py).
    """

    __tablename__ = "kiosk_devices"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String(80), nullable=False)
    created_at = Column(DateTime, nullable=False)
    # pairing (cleared as soon as the code is redeemed or the device is revoked)
    pairing_code_hash = Column(String(64), nullable=True, index=True)
    pairing_expires_at = Column(DateTime, nullable=True)
    # device credential (NULL until paired and again after revocation)
    token_hash = Column(String(64), nullable=True)
    paired_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    user_agent = Column(String(200), nullable=True)
