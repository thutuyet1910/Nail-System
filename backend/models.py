from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Time, UniqueConstraint, true
from sqlalchemy.orm import relationship

from database import Base
from timeutils import salon_naive_now


def _utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Technician(Base):
    __tablename__ = "technicians"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, unique=True, nullable=True, index=True)
    full_name = Column(String, nullable=False, index=True)
    phone = Column(String, nullable=True)
    skills = Column(String, nullable=True)
    specialties = Column(String, nullable=True)  # comma separated, e.g. "Acrylic, Gel"
    start_date = Column(Date, nullable=True)

    status = Column(String, nullable=False, default="off")
    availability = Column(String, nullable=False, default="off today")
    work_schedule = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    profile_photo = Column(String, nullable=True)

   
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())

    appointments = relationship(
        "Appointment",
        foreign_keys="Appointment.technician_id",
        back_populates="technician",
    )
    preferred_appointments = relationship(
        "Appointment",
        foreign_keys="Appointment.preferred_technician_id",
        back_populates="preferred_technician",
    )
    turns = relationship(
        "Turn",
        foreign_keys="Turn.technician_id",
        back_populates="technician",
    )
    preferred_turns = relationship(
        "Turn",
        foreign_keys="Turn.preferred_technician_id",
        back_populates="preferred_technician",
    )
    service_eligibilities = relationship(
        "TechnicianService", back_populates="technician", cascade="all, delete-orphan"
    )
    booking_schedules = relationship(
        "TechnicianWorkSchedule", back_populates="technician", cascade="all, delete-orphan"
    )
    blocked_times = relationship(
        "TechnicianBlockedTime", back_populates="technician", cascade="all, delete-orphan"
    )

    @property
    def service_ids(self):
        return [item.service_id for item in self.service_eligibilities]


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    appointment_code = Column(String, unique=True, nullable=False, index=True)

    customer_name = Column(String, nullable=False, index=True)
    customer_phone = Column(String, nullable=False, index=True)
    customer_phone_e164 = Column(String, nullable=True, index=True)
    external_customer_id = Column(Integer, nullable=True, index=True)

    service_name = Column(String, nullable=False)
    service_category = Column(String, nullable=False)

    appointment_time = Column(DateTime, nullable=False, index=True)
    # Booking authority stores UTC as naive SQLite values. appointment_time remains
    # salon-local for compatibility with the existing owner dashboard.
    starts_at_utc = Column(DateTime, nullable=True, index=True)
    ends_at_utc = Column(DateTime, nullable=True, index=True)
    duration_minutes = Column(Integer, nullable=True)
    legacy_duration_fallback = Column(Boolean, nullable=False, default=False, server_default="0")
    status = Column(String, nullable=False, default="scheduled", server_default="scheduled")

    customer_type = Column(String, nullable=False, default="new")
    note = Column(Text, nullable=True)
    special_requests = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    people_count = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    cancelled_at_utc = Column(DateTime, nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    cancellation_source = Column(String, nullable=True)

    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)
    preferred_technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)

    technician = relationship(
        "Technician", foreign_keys=[technician_id], back_populates="appointments"
    )
    preferred_technician = relationship(
        "Technician", foreign_keys=[preferred_technician_id], back_populates="preferred_appointments"
    )
    appointment_services = relationship(
        "AppointmentService",
        back_populates="appointment",
        cascade="all, delete-orphan",
        order_by="AppointmentService.sort_order",
    )
    events = relationship(
        "AppointmentEvent", back_populates="appointment", cascade="all, delete-orphan"
    )
    turns = relationship("Turn", back_populates="appointment")


class SalonSettings(Base):
    __tablename__ = "salon_settings"

    id = Column(Integer, primary_key=True, default=1)
    salon_name = Column(String, nullable=False, default="Nail Salon")
    timezone = Column(String, nullable=False, default="America/Phoenix")
    business_phone = Column(String, nullable=True)
    address_line1 = Column(String, nullable=True)
    address_line2 = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    slot_interval_minutes = Column(Integer, nullable=False, default=15)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())


class BusinessHour(Base):
    __tablename__ = "business_hours"
    __table_args__ = (UniqueConstraint("day_of_week", name="uq_business_hours_day"),)

    id = Column(Integer, primary_key=True)
    day_of_week = Column(Integer, nullable=False)
    is_closed = Column(Boolean, nullable=False, default=False)
    opens_at = Column(Time, nullable=True)
    closes_at = Column(Time, nullable=True)


class BookingService(Base):
    __tablename__ = "booking_services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    category = Column(String, nullable=True, index=True)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=True)
    buffer_before_minutes = Column(Integer, nullable=False, default=0)
    buffer_after_minutes = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())

    technician_eligibilities = relationship(
        "TechnicianService", back_populates="service", cascade="all, delete-orphan"
    )


class TechnicianService(Base):
    __tablename__ = "technician_services"
    __table_args__ = (
        UniqueConstraint("technician_id", "service_id", name="uq_technician_service"),
    )

    id = Column(Integer, primary_key=True)
    technician_id = Column(Integer, ForeignKey("technicians.id", ondelete="CASCADE"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("booking_services.id", ondelete="CASCADE"), nullable=False, index=True)
    technician = relationship("Technician", back_populates="service_eligibilities")
    service = relationship("BookingService", back_populates="technician_eligibilities")


class TechnicianWorkSchedule(Base):
    __tablename__ = "technician_work_schedules"
    __table_args__ = (
        UniqueConstraint("technician_id", "day_of_week", name="uq_technician_schedule_day"),
    )

    id = Column(Integer, primary_key=True)
    technician_id = Column(Integer, ForeignKey("technicians.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)
    is_working = Column(Boolean, nullable=False, default=True)
    starts_at = Column(Time, nullable=True)
    ends_at = Column(Time, nullable=True)
    technician = relationship("Technician", back_populates="booking_schedules")


class TechnicianBlockedTime(Base):
    __tablename__ = "technician_blocked_times"

    id = Column(Integer, primary_key=True)
    technician_id = Column(Integer, ForeignKey("technicians.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_at_utc = Column(DateTime, nullable=False, index=True)
    ends_at_utc = Column(DateTime, nullable=False, index=True)
    block_type = Column(String, nullable=False, default="other")
    reason = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    created_at_utc = Column(DateTime, nullable=False)
    technician = relationship("Technician", back_populates="blocked_times")


class AppointmentService(Base):
    __tablename__ = "appointment_services"
    __table_args__ = (
        UniqueConstraint("appointment_id", "sort_order", name="uq_appointment_service_order"),
    )

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_service_id = Column(Integer, ForeignKey("booking_services.id"), nullable=True, index=True)
    service_name_snapshot = Column(String, nullable=False)
    duration_minutes_snapshot = Column(Integer, nullable=False)
    price_snapshot = Column(Numeric(10, 2), nullable=True)
    buffer_before_minutes_snapshot = Column(Integer, nullable=False, default=0)
    buffer_after_minutes_snapshot = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False)
    appointment = relationship("Appointment", back_populates="appointment_services")
    service = relationship("BookingService")


class AppointmentEvent(Base):
    __tablename__ = "appointment_events"

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    old_starts_at_utc = Column(DateTime, nullable=True)
    old_ends_at_utc = Column(DateTime, nullable=True)
    new_starts_at_utc = Column(DateTime, nullable=True)
    new_ends_at_utc = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)
    created_at_utc = Column(DateTime, nullable=False)
    appointment = relationship("Appointment", back_populates="events")


class BookingIdempotencyRecord(Base):
    __tablename__ = "booking_idempotency_records"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    operation = Column(String, nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    # SHA-256 of the canonical logical request. NULL only for rows written before binding existed.
    request_hash = Column(String, nullable=True)
    created_at_utc = Column(DateTime, nullable=False)


class OwnerCredential(Base):
    __tablename__ = "owner_credentials"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True, default="owner")
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime, nullable=False, default=_utc_now_naive)
    updated_at = Column(DateTime, nullable=False, default=_utc_now_naive, onupdate=_utc_now_naive)


class OwnerSession(Base):
    __tablename__ = "owner_sessions"

    id = Column(Integer, primary_key=True)
    credential_id = Column(Integer, ForeignKey("owner_credentials.id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    csrf_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)


class OwnerNotification(Base):
    __tablename__ = "owner_notifications"

    id = Column(Integer, primary_key=True)
    notification_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, default="info", index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    source_type = Column(String, nullable=False, index=True)
    source_id = Column(String, nullable=True)
    event_key = Column(String, nullable=True, unique=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)
    external_customer_id = Column(Integer, nullable=True, index=True)
    read_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now_naive, index=True)
    metadata_json = Column(JSON, nullable=True)


class VoiceCall(Base):
    __tablename__ = "voice_calls"

    id = Column(Integer, primary_key=True)
    call_id = Column(String, nullable=False, unique=True, index=True)
    provider_call_sid = Column(String, nullable=True, unique=True, index=True)
    provider_stream_sid = Column(String, nullable=True, unique=True, index=True)
    # NULL when the provider supplied no usable caller ID (anonymous / unsupported number).
    caller_phone_e164 = Column(String, nullable=True, index=True)
    called_phone_e164 = Column(String, nullable=False)
    call_state = Column(String, nullable=False, default="created", index=True)
    intent = Column(String, nullable=True)
    outcome = Column(String, nullable=True)
    external_customer_id = Column(Integer, nullable=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    needs_owner_attention = Column(Boolean, nullable=False, default=False, server_default="0")
    summary = Column(Text, nullable=True)
    error_code = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now_naive)
    updated_at = Column(DateTime, nullable=False, default=_utc_now_naive, onupdate=_utc_now_naive)


class VoiceCallEvent(Base):
    __tablename__ = "voice_call_events"
    __table_args__ = (UniqueConstraint("call_id", "operation_key", name="uq_voice_call_operation"),)

    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("voice_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    occurred_at = Column(DateTime, nullable=False, index=True)
    operation_key = Column(String, nullable=True)
    related_entity_type = Column(String, nullable=True)
    related_entity_id = Column(String, nullable=True)
    result_status = Column(String, nullable=False, default="success")
    metadata_json = Column(JSON, nullable=True)


class VoiceStreamToken(Base):
    __tablename__ = "voice_stream_tokens"

    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, ForeignKey("voice_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    stream_sid = Column(String, nullable=True, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now_naive)


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (
        UniqueConstraint("checkin_visit_id", name="uq_turn_checkin_visit"),
    )

    id = Column(Integer, primary_key=True, index=True)
    turn_number = Column(Integer, nullable=False)  

    customer_name = Column(String, nullable=False)
    customer_phone = Column(String, nullable=True)
    customer_phone_e164 = Column(String, nullable=True, index=True)
    checkin_customer_id = Column(Integer, nullable=True, index=True)
    checkin_visit_id = Column(Integer, nullable=True, index=True)
    service_name = Column(String, nullable=False)

    discount_type = Column(String, nullable=True)
    discount_value = Column(Numeric(10, 2), nullable=True, default=0)
    discount_label = Column(String, nullable=True)

    status = Column(String, nullable=False, default="waiting", index=True)
    source = Column(String, nullable=False, default="checkin")
    assigned_by = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=salon_naive_now, index=True)
    assigned_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False, index=True)
    preferred_technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, index=True)

    technician = relationship("Technician", foreign_keys=[technician_id], back_populates="turns")
    preferred_technician = relationship(
        "Technician", foreign_keys=[preferred_technician_id], back_populates="preferred_turns"
    )
    appointment = relationship("Appointment", back_populates="turns")


class Checkout(Base):
    __tablename__ = "checkouts"

    id = Column(Integer, primary_key=True, index=True)

    customer_name = Column(String, nullable=False, index=True)
    customer_phone = Column(String, nullable=True, index=True)

    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)
    turn_id = Column(Integer, ForeignKey("turns.id"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)

    payment_method = Column(String, nullable=False, default="cash")
    service_name = Column(String, nullable=False)

    subtotal = Column(Numeric(10, 2), nullable=False, default=0)
    discount_type = Column(String, nullable=False, default="none")
    discount_value = Column(Numeric(10, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0)
    discount_paid_by = Column(String, nullable=False, default="owner")

    tip_amount = Column(Numeric(10, 2), nullable=False, default=0)
    net_service = Column(Numeric(10, 2), nullable=False, default=0)
    technician_share = Column(Numeric(10, 2), nullable=False, default=0)
    salon_share = Column(Numeric(10, 2), nullable=False, default=0)
    salon_actual_revenue = Column(Numeric(10, 2), nullable=False, default=0)
    technician_total = Column(Numeric(10, 2), nullable=False, default=0)
    customer_pays = Column(Numeric(10, 2), nullable=False, default=0)

    note = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=salon_naive_now, index=True)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    supplier = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False, default=0)
    unit_price = Column(Numeric(10, 2), nullable=False, default=0)
    purchase_date = Column(Date, nullable=True)
    low_stock_level = Column(Integer, nullable=False, default=3)

    created_at = Column(DateTime, nullable=False, default=salon_naive_now)
    updated_at = Column(DateTime, nullable=False, default=salon_naive_now, onupdate=salon_naive_now)
