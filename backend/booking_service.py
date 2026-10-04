import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from phone_normalization import PhoneNormalizationError, normalize_us_phone
from database import IS_SQLITE
import timeutils
from timeutils import as_salon_datetime, local_to_utc_naive, salon_zone, utc_naive_to_local, utc_now_naive


class BookingRuleError(ValueError):
    pass


class IdempotencyConflictError(BookingRuleError):
    """The idempotency key was already used for a different logical request."""


# Turn statuses that mean a customer is still being served; mirrors crud.ACTIVE_TURN_STATUSES
# (crud imports this module, so the tuple is repeated here instead of imported).
ACTIVE_TURN_STATUSES = ("waiting", "assigned", "in_service")
RESCHEDULABLE_STATUSES = ("scheduled",)
CANCELLABLE_STATUSES = ("scheduled", "checked_in", "assigned")


def current_salon_time(timezone_name: str) -> datetime:
    """Authoritative 'now' for booking rules: salon-local (America/Phoenix), never host or browser time."""
    return timeutils.salon_now(timezone_name)


@dataclass(frozen=True)
class ServicePlan:
    services: list[models.BookingService]
    total_duration_minutes: int


def get_salon_settings(db: Session) -> models.SalonSettings:
    settings = db.get(models.SalonSettings, 1)
    if not settings or not settings.is_active:
        raise BookingRuleError("Salon booking settings are not active")
    return settings


def get_active_services(db: Session) -> list[models.BookingService]:
    return (
        db.query(models.BookingService)
        .filter(models.BookingService.is_active.is_(True))
        .order_by(models.BookingService.category, models.BookingService.name)
        .all()
    )


def calculate_service_plan(db: Session, service_ids: list[int]) -> ServicePlan:
    ordered_ids = list(dict.fromkeys(service_ids or []))
    if not ordered_ids:
        raise BookingRuleError("At least one booking service is required")
    rows = (
        db.query(models.BookingService)
        .filter(
            models.BookingService.id.in_(ordered_ids),
            models.BookingService.is_active.is_(True),
        )
        .all()
    )
    by_id = {row.id: row for row in rows}
    if any(service_id not in by_id for service_id in ordered_ids):
        raise BookingRuleError("One or more booking services are missing or inactive")
    services = [by_id[service_id] for service_id in ordered_ids]
    total = sum(
        row.buffer_before_minutes + row.duration_minutes + row.buffer_after_minutes
        for row in services
    )
    if total <= 0:
        raise BookingRuleError("The selected services do not have a valid duration")
    return ServicePlan(services=services, total_duration_minutes=total)


def resolve_service_ids_from_legacy_names(db: Session, value: str | None) -> list[int]:
    names = [part.strip().lower() for part in (value or "").split(",") if part.strip()]
    if not names:
        raise BookingRuleError("At least one booking service is required")
    services = get_active_services(db)
    by_name = {service.name.strip().lower(): service.id for service in services}
    missing = [name for name in names if name not in by_name]
    if missing:
        raise BookingRuleError(f"Unknown or inactive booking service: {', '.join(missing)}")
    return [by_name[name] for name in names]


def _eligible_technicians(db: Session, service_ids: list[int]) -> list[models.Technician]:
    technicians = (
        db.query(models.Technician)
        .options(joinedload(models.Technician.service_eligibilities))
        .filter(models.Technician.is_active.is_(True))
        .order_by(models.Technician.id)
        .all()
    )
    required = set(service_ids)
    return [
        technician
        for technician in technicians
        if required.issubset({item.service_id for item in technician.service_eligibilities})
    ]


def _business_hours_for(db: Session, local_start: datetime, local_end: datetime) -> bool:
    if local_start.date() != local_end.date():
        return False
    hours = (
        db.query(models.BusinessHour)
        .filter(models.BusinessHour.day_of_week == local_start.weekday())
        .first()
    )
    if not hours or hours.is_closed or not hours.opens_at or not hours.closes_at:
        return False
    return local_start.time().replace(tzinfo=None) >= hours.opens_at and local_end.time().replace(tzinfo=None) <= hours.closes_at


def _technician_is_scheduled(
    db: Session, technician_id: int, local_start: datetime, local_end: datetime
) -> bool:
    schedule = (
        db.query(models.TechnicianWorkSchedule)
        .filter(
            models.TechnicianWorkSchedule.technician_id == technician_id,
            models.TechnicianWorkSchedule.day_of_week == local_start.weekday(),
        )
        .first()
    )
    if (
        not schedule
        or not schedule.is_working
        or not schedule.starts_at
        or not schedule.ends_at
        or local_start.date() != local_end.date()
    ):
        return False
    return local_start.time().replace(tzinfo=None) >= schedule.starts_at and local_end.time().replace(tzinfo=None) <= schedule.ends_at


def _has_block_conflict(db: Session, technician_id: int, start_utc: datetime, end_utc: datetime) -> bool:
    return (
        db.query(models.TechnicianBlockedTime.id)
        .filter(
            models.TechnicianBlockedTime.technician_id == technician_id,
            models.TechnicianBlockedTime.starts_at_utc < end_utc,
            models.TechnicianBlockedTime.ends_at_utc > start_utc,
        )
        .first()
        is not None
    )


def _appointment_interval(appointment: models.Appointment, timezone_name: str) -> tuple[datetime, datetime]:
    if appointment.starts_at_utc and appointment.ends_at_utc:
        return appointment.starts_at_utc, appointment.ends_at_utc
    start = local_to_utc_naive(appointment.appointment_time, timezone_name)
    duration = appointment.duration_minutes or 60
    return start, start + timedelta(minutes=duration)


def _has_appointment_conflict(
    db: Session,
    technician_id: int,
    start_utc: datetime,
    end_utc: datetime,
    timezone_name: str,
    exclude_appointment_id: int | None = None,
) -> bool:
    query = db.query(models.Appointment).filter(
        models.Appointment.technician_id == technician_id,
        models.Appointment.status != "cancelled",
    )
    if exclude_appointment_id:
        query = query.filter(models.Appointment.id != exclude_appointment_id)
    for appointment in query.all():
        existing_start, existing_end = _appointment_interval(appointment, timezone_name)
        if existing_start < end_utc and existing_end > start_utc:
            return True
    return False


def technician_is_available(
    db: Session,
    technician: models.Technician,
    start_local: datetime,
    end_local: datetime,
    timezone_name: str,
    exclude_appointment_id: int | None = None,
) -> bool:
    if not technician.is_active:
        return False
    if not _technician_is_scheduled(db, technician.id, start_local, end_local):
        return False
    start_utc = local_to_utc_naive(start_local, timezone_name)
    end_utc = local_to_utc_naive(end_local, timezone_name)
    if _has_block_conflict(db, technician.id, start_utc, end_utc):
        return False
    return not _has_appointment_conflict(
        db,
        technician.id,
        start_utc,
        end_utc,
        timezone_name,
        exclude_appointment_id,
    )


def available_technicians_for_interval(
    db: Session,
    service_ids: list[int],
    requested_start: datetime,
    technician_id: int | None = None,
    exclude_appointment_id: int | None = None,
) -> tuple[ServicePlan, datetime, list[models.Technician]]:
    settings = get_salon_settings(db)
    plan = calculate_service_plan(db, service_ids)
    start_local = as_salon_datetime(requested_start, settings.timezone)
    end_local = start_local + timedelta(minutes=plan.total_duration_minutes)
    if not _business_hours_for(db, start_local, end_local):
        raise BookingRuleError("Requested appointment is outside salon business hours")
    if start_local < current_salon_time(settings.timezone):
        raise BookingRuleError("Requested appointment start is in the past")
    if (start_local.hour * 60 + start_local.minute) % settings.slot_interval_minutes != 0:
        raise BookingRuleError(
            f"Appointment start must align to {settings.slot_interval_minutes}-minute booking intervals"
        )

    candidates = _eligible_technicians(db, service_ids)
    if technician_id is not None:
        candidates = [item for item in candidates if item.id == technician_id]
        if not candidates:
            raise BookingRuleError("Requested technician is inactive or not eligible for every selected service")
    available = [
        technician
        for technician in candidates
        if technician_is_available(
            db,
            technician,
            start_local,
            end_local,
            settings.timezone,
            exclude_appointment_id,
        )
    ]
    return plan, end_local, available


def generate_available_slots(
    db: Session,
    day: date,
    service_ids: list[int],
    technician_id: int | None = None,
    people_count: int = 1,
) -> list[dict]:
    if people_count != 1:
        raise BookingRuleError("Multi-person resource scheduling is not supported yet")
    settings = get_salon_settings(db)
    plan = calculate_service_plan(db, service_ids)
    hours = db.query(models.BusinessHour).filter(models.BusinessHour.day_of_week == day.weekday()).first()
    if not hours or hours.is_closed or not hours.opens_at or not hours.closes_at:
        return []
    zone = salon_zone(settings.timezone)
    cursor = datetime.combine(day, hours.opens_at, tzinfo=zone)
    closing = datetime.combine(day, hours.closes_at, tzinfo=zone)
    slots = []
    while cursor + timedelta(minutes=plan.total_duration_minutes) <= closing:
        try:
            _, end_local, available = available_technicians_for_interval(
                db, service_ids, cursor, technician_id
            )
        except BookingRuleError:
            available = []
            end_local = cursor + timedelta(minutes=plan.total_duration_minutes)
        if available:
            slots.append(
                {
                    "start": cursor,
                    "end": end_local,
                    "timezone": settings.timezone,
                    "eligible_technician_ids": [item.id for item in available],
                    "selected_technician_id": technician_id,
                    "total_duration_minutes": plan.total_duration_minutes,
                }
            )
        cursor += timedelta(minutes=settings.slot_interval_minutes)
    return slots


def _begin_write(db: Session) -> None:
    if IS_SQLITE:
        try:
            db.execute(text("BEGIN IMMEDIATE"))
        except OperationalError as exc:
            db.rollback()
            raise BookingRuleError("Booking database is temporarily busy; retry the request") from exc


def _fingerprint(parts: dict) -> str:
    """Stable hash of the logical request (canonical JSON). Contains booking fields only, no secrets."""
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _norm_start(value: datetime, timezone_name: str) -> str:
    return local_to_utc_naive(as_salon_datetime(value, timezone_name), timezone_name).isoformat()


def _norm_phone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return normalize_us_phone(value).e164
    except PhoneNormalizationError:
        return str(value)


def _idempotent_result(
    db: Session,
    key: str | None,
    operation: str,
    fingerprint: str,
    legacy_match: Callable[[models.BookingIdempotencyRecord, models.Appointment], bool] | None = None,
):
    if not key:
        return None
    record = (
        db.query(models.BookingIdempotencyRecord)
        .filter(models.BookingIdempotencyRecord.idempotency_key == key)
        .first()
    )
    if not record:
        return None
    if record.operation != operation:
        raise IdempotencyConflictError("Idempotency key was already used for a different operation")
    if record.request_hash is not None:
        if record.request_hash != fingerprint:
            raise IdempotencyConflictError("Idempotency key was already used for a different request")
        return db.get(models.Appointment, record.appointment_id)

    appointment = db.get(models.Appointment, record.appointment_id)
    if not appointment or legacy_match is None or not legacy_match(record, appointment):
        raise IdempotencyConflictError("Idempotency key was already used for a different request")

    # A pre-binding row is upgraded only after its stored result proves that the current
    # logical request is the one that produced it. Rows that cannot be proven remain NULL.
    record.request_hash = fingerprint
    db.commit()
    db.refresh(appointment)
    return appointment


def _record_idempotency(
    db: Session, key: str | None, operation: str, appointment_id: int, fingerprint: str
) -> None:
    if key:
        db.add(
            models.BookingIdempotencyRecord(
                idempotency_key=key,
                operation=operation,
                appointment_id=appointment_id,
                request_hash=fingerprint,
                created_at_utc=utc_now_naive(),
            )
        )


def _new_appointment_code(db: Session) -> str:
    local_day = utc_naive_to_local(utc_now_naive(), get_salon_settings(db).timezone).strftime("%Y%m%d")
    for _ in range(10):
        candidate = f"APT-{local_day}-{secrets.token_hex(4).upper()}"
        if not db.query(models.Appointment.id).filter(models.Appointment.appointment_code == candidate).first():
            return candidate
    raise BookingRuleError("Could not generate a unique appointment code")


def _validate_customer(name: str, phone: str) -> tuple[str, str, str]:
    clean_name = (name or "").strip()
    if not clean_name:
        raise BookingRuleError("Customer name is required")
    try:
        normalized = normalize_us_phone(phone)
    except PhoneNormalizationError as exc:
        raise BookingRuleError(str(exc)) from exc
    return clean_name, normalized.national_digits, normalized.e164


def _ordered_appointment_service_ids(appointment: models.Appointment) -> list[int] | None:
    snapshots = sorted(appointment.appointment_services, key=lambda item: item.sort_order)
    if not snapshots or any(item.booking_service_id is None for item in snapshots):
        return None
    return [item.booking_service_id for item in snapshots]


def _legacy_create_matches(
    db: Session,
    record: models.BookingIdempotencyRecord,
    appointment: models.Appointment,
    payload: schemas.AppointmentCreate,
    timezone_name: str,
) -> bool:
    """Prove a legacy create from its stored appointment and immutable service snapshots."""
    created = db.query(models.AppointmentEvent).filter(
        models.AppointmentEvent.appointment_id == appointment.id,
        models.AppointmentEvent.event_type == "created",
        models.AppointmentEvent.created_at_utc <= record.created_at_utc,
    ).order_by(models.AppointmentEvent.id).first()
    if not created:
        return False
    # Service/customer fields have no immutable history after a reschedule, so do not guess.
    if db.query(models.AppointmentEvent.id).filter(
        models.AppointmentEvent.appointment_id == appointment.id,
        models.AppointmentEvent.event_type.in_(("rescheduled", "cancelled")),
    ).first():
        return False
    try:
        requested_services = payload.service_ids or resolve_service_ids_from_legacy_names(
            db, payload.service_category or payload.service_name
        )
        requested_start = local_to_utc_naive(
            as_salon_datetime(payload.appointment_time, timezone_name), timezone_name
        )
    except (BookingRuleError, ValueError, TypeError):
        return False
    stored_phone = appointment.customer_phone_e164 or _norm_phone(appointment.customer_phone)
    return (
        created.new_starts_at_utc == requested_start
        and appointment.starts_at_utc == requested_start
        and _ordered_appointment_service_ids(appointment) == list(requested_services)
        and appointment.customer_name == (payload.customer_name or "").strip()
        and stored_phone == _norm_phone(payload.customer_phone)
        and appointment.external_customer_id == payload.external_customer_id
        and appointment.people_count == payload.people_count
        and appointment.note == payload.note
        and appointment.special_requests == payload.special_requests
        and appointment.allergies == payload.allergies
        and appointment.preferred_technician_id == payload.preferred_technician_id
        and (payload.technician_id is None or appointment.technician_id == payload.technician_id)
        and (payload.appointment_code is None or appointment.appointment_code == payload.appointment_code)
    )


def _legacy_reschedule_matches(
    db: Session,
    record: models.BookingIdempotencyRecord,
    appointment: models.Appointment,
    appointment_id: int,
    payload: schemas.AppointmentReschedule,
    timezone_name: str,
) -> bool:
    """Prove a legacy reschedule from its linked result and final recorded target state."""
    if record.appointment_id != appointment_id:
        return False
    try:
        requested_start = local_to_utc_naive(
            as_salon_datetime(payload.appointment_time, timezone_name), timezone_name
        )
    except (ValueError, TypeError):
        return False
    events = db.query(models.AppointmentEvent).filter(
        models.AppointmentEvent.appointment_id == appointment_id,
        models.AppointmentEvent.event_type == "rescheduled",
    ).order_by(models.AppointmentEvent.id).all()
    # Without an event-to-key link, more than one historical reschedule is ambiguous.
    # Refuse it rather than guessing which request created this legacy key.
    if (
        len(events) != 1
        or events[0].created_at_utc > record.created_at_utc
        or events[0].new_starts_at_utc != requested_start
        or appointment.starts_at_utc != requested_start
        or db.query(models.AppointmentEvent.id).filter(
            models.AppointmentEvent.appointment_id == appointment_id,
            models.AppointmentEvent.event_type == "cancelled",
        ).first()
    ):
        return False
    sent = payload.model_fields_set
    if payload.service_ids and _ordered_appointment_service_ids(appointment) != list(payload.service_ids):
        return False
    if "technician_id" in sent and appointment.technician_id != payload.technician_id:
        return False
    if "preferred_technician_id" in sent and appointment.preferred_technician_id != payload.preferred_technician_id:
        return False
    if payload.people_count is not None and appointment.people_count != payload.people_count:
        return False
    if payload.customer_name is not None and appointment.customer_name != payload.customer_name.strip():
        return False
    stored_phone = appointment.customer_phone_e164 or _norm_phone(appointment.customer_phone)
    if payload.customer_phone is not None and stored_phone != _norm_phone(payload.customer_phone):
        return False
    return all(
        field not in sent or getattr(appointment, field) == getattr(payload, field)
        for field in ("special_requests", "allergies", "note")
    )


def _legacy_cancel_matches(
    db: Session,
    record: models.BookingIdempotencyRecord,
    appointment: models.Appointment,
    appointment_id: int,
    payload: schemas.AppointmentCancel,
) -> bool:
    """Cancellation retains every fingerprinted field, so an exact legacy replay is provable."""
    if record.appointment_id != appointment_id or appointment.status != "cancelled":
        return False
    event = db.query(models.AppointmentEvent.id).filter(
        models.AppointmentEvent.appointment_id == appointment_id,
        models.AppointmentEvent.event_type == "cancelled",
        models.AppointmentEvent.created_at_utc <= record.created_at_utc,
        models.AppointmentEvent.note == payload.reason,
    ).first()
    return bool(
        event
        and appointment.cancellation_reason == payload.reason
        and appointment.cancellation_source == payload.source
    )


def create_booking(db: Session, payload: schemas.AppointmentCreate) -> models.Appointment:
    _begin_write(db)
    timezone_name = get_salon_settings(db).timezone
    fingerprint = _fingerprint({
        "op": "create",
        "customer_name": (payload.customer_name or "").strip(),
        "customer_phone": _norm_phone(payload.customer_phone),
        "external_customer_id": payload.external_customer_id,
        "services": list(payload.service_ids) if payload.service_ids else (payload.service_category or payload.service_name or "").strip().lower(),
        "technician_id": payload.technician_id,
        "preferred_technician_id": payload.preferred_technician_id,
        "start_utc": _norm_start(payload.appointment_time, timezone_name),
        "people_count": payload.people_count,
        "note": payload.note, "special_requests": payload.special_requests, "allergies": payload.allergies,
        "appointment_code": payload.appointment_code,
    })
    replay = _idempotent_result(
        db, payload.idempotency_key, "create", fingerprint,
        lambda record, appointment: _legacy_create_matches(
            db, record, appointment, payload, timezone_name
        ),
    )
    if replay:
        return replay
    name, phone, phone_e164 = _validate_customer(payload.customer_name, payload.customer_phone)
    if payload.people_count != 1:
        raise BookingRuleError("Multi-person resource scheduling is not supported yet")
    service_ids = payload.service_ids or resolve_service_ids_from_legacy_names(
        db, payload.service_category or payload.service_name
    )
    requested_technician_id = payload.technician_id or payload.preferred_technician_id
    plan, end_local, available = available_technicians_for_interval(
        db, service_ids, payload.appointment_time, requested_technician_id
    )
    if not available:
        raise BookingRuleError("No eligible technician is available for the requested time")
    technician = available[0]
    settings = get_salon_settings(db)
    start_local = as_salon_datetime(payload.appointment_time, settings.timezone)
    appointment = models.Appointment(
        appointment_code=payload.appointment_code or _new_appointment_code(db),
        customer_name=name,
        customer_phone=phone,
        customer_phone_e164=phone_e164,
        external_customer_id=payload.external_customer_id,
        service_name=", ".join(service.name for service in plan.services),
        service_category=", ".join(service.name for service in plan.services),
        appointment_time=start_local.replace(tzinfo=None),
        starts_at_utc=local_to_utc_naive(start_local, settings.timezone),
        ends_at_utc=local_to_utc_naive(end_local, settings.timezone),
        duration_minutes=plan.total_duration_minutes,
        legacy_duration_fallback=False,
        status="scheduled",
        customer_type=payload.customer_type,
        note=payload.note,
        special_requests=payload.special_requests,
        allergies=payload.allergies,
        people_count=1,
        technician_id=technician.id,
        preferred_technician_id=payload.preferred_technician_id,
        created_at=utc_now_naive(),
        updated_at=utc_now_naive(),
    )
    db.add(appointment)
    db.flush()
    for index, service in enumerate(plan.services):
        appointment.appointment_services.append(
            models.AppointmentService(
                booking_service_id=service.id,
                service_name_snapshot=service.name,
                duration_minutes_snapshot=service.duration_minutes,
                price_snapshot=service.price,
                buffer_before_minutes_snapshot=service.buffer_before_minutes,
                buffer_after_minutes_snapshot=service.buffer_after_minutes,
                sort_order=index,
            )
        )
    appointment.events.append(
        models.AppointmentEvent(
            event_type="created",
            new_starts_at_utc=appointment.starts_at_utc,
            new_ends_at_utc=appointment.ends_at_utc,
            created_at_utc=utc_now_naive(),
        )
    )
    _record_idempotency(db, payload.idempotency_key, "create", appointment.id, fingerprint)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BookingRuleError("Booking conflicts with existing data; retry availability") from exc
    db.refresh(appointment)
    return appointment


def _appointment_service_ids(appointment: models.Appointment, db: Session) -> list[int]:
    ids = [item.booking_service_id for item in appointment.appointment_services if item.booking_service_id]
    return ids or resolve_service_ids_from_legacy_names(
        db, appointment.service_category or appointment.service_name
    )


def reschedule_booking(
    db: Session, appointment_id: int, payload: schemas.AppointmentReschedule
) -> models.Appointment | None:
    _begin_write(db)
    timezone_name = get_salon_settings(db).timezone
    sent = payload.model_fields_set
    fingerprint = _fingerprint({
        "op": "reschedule",
        "appointment_id": appointment_id,
        "services": list(payload.service_ids) if payload.service_ids else None,
        "technician_id": payload.technician_id if "technician_id" in sent else "unset",
        "preferred_technician_id": payload.preferred_technician_id if "preferred_technician_id" in sent else "unset",
        "start_utc": _norm_start(payload.appointment_time, timezone_name),
        "people_count": payload.people_count,
        "customer_name": (payload.customer_name or "").strip() if payload.customer_name is not None else None,
        "customer_phone": _norm_phone(payload.customer_phone),
        "special_requests": payload.special_requests if "special_requests" in sent else "unset",
        "allergies": payload.allergies if "allergies" in sent else "unset",
        "note": payload.note if "note" in sent else "unset",
    })
    replay = _idempotent_result(
        db, payload.idempotency_key, "reschedule", fingerprint,
        lambda record, appointment: _legacy_reschedule_matches(
            db, record, appointment, appointment_id, payload, timezone_name
        ),
    )
    if replay:
        return replay
    appointment = (
        db.query(models.Appointment)
        .options(joinedload(models.Appointment.appointment_services))
        .filter(models.Appointment.id == appointment_id)
        .first()
    )
    if not appointment:
        return None
    if appointment.status not in RESCHEDULABLE_STATUSES:
        raise BookingRuleError(
            f"A {appointment.status} appointment cannot be rescheduled; "
            "only appointments that have not checked in can be moved"
        )
    service_ids = payload.service_ids or _appointment_service_ids(appointment, db)
    technician_id = payload.technician_id if "technician_id" in payload.model_fields_set else appointment.technician_id
    preferred_id = payload.preferred_technician_id if "preferred_technician_id" in payload.model_fields_set else appointment.preferred_technician_id
    requested_technician_id = technician_id or preferred_id
    people_count = payload.people_count if payload.people_count is not None else appointment.people_count
    if people_count != 1:
        raise BookingRuleError("Multi-person resource scheduling is not supported yet")
    plan, end_local, available = available_technicians_for_interval(
        db,
        service_ids,
        payload.appointment_time,
        requested_technician_id,
        exclude_appointment_id=appointment.id,
    )
    if not available:
        raise BookingRuleError("No eligible technician is available for the requested time")
    old_start, old_end = appointment.starts_at_utc, appointment.ends_at_utc
    settings = get_salon_settings(db)
    start_local = as_salon_datetime(payload.appointment_time, settings.timezone)
    appointment.appointment_time = start_local.replace(tzinfo=None)
    appointment.starts_at_utc = local_to_utc_naive(start_local, settings.timezone)
    appointment.ends_at_utc = local_to_utc_naive(end_local, settings.timezone)
    appointment.duration_minutes = plan.total_duration_minutes
    appointment.legacy_duration_fallback = False
    appointment.technician_id = available[0].id
    appointment.preferred_technician_id = preferred_id
    appointment.service_name = appointment.service_category = ", ".join(item.name for item in plan.services)
    appointment.people_count = 1
    if payload.customer_name is not None or payload.customer_phone is not None:
        name, phone, phone_e164 = _validate_customer(
            payload.customer_name or appointment.customer_name,
            payload.customer_phone or appointment.customer_phone,
        )
        appointment.customer_name, appointment.customer_phone = name, phone
        appointment.customer_phone_e164 = phone_e164
    for field in ("special_requests", "allergies", "note"):
        if field in payload.model_fields_set:
            setattr(appointment, field, getattr(payload, field))
    appointment.updated_at = utc_now_naive()
    appointment.appointment_services.clear()
    db.flush()
    for index, service in enumerate(plan.services):
        appointment.appointment_services.append(
            models.AppointmentService(
                booking_service_id=service.id,
                service_name_snapshot=service.name,
                duration_minutes_snapshot=service.duration_minutes,
                price_snapshot=service.price,
                buffer_before_minutes_snapshot=service.buffer_before_minutes,
                buffer_after_minutes_snapshot=service.buffer_after_minutes,
                sort_order=index,
            )
        )
    appointment.events.append(
        models.AppointmentEvent(
            event_type="rescheduled",
            old_starts_at_utc=old_start,
            old_ends_at_utc=old_end,
            new_starts_at_utc=appointment.starts_at_utc,
            new_ends_at_utc=appointment.ends_at_utc,
            created_at_utc=utc_now_naive(),
        )
    )
    _record_idempotency(db, payload.idempotency_key, "reschedule", appointment.id, fingerprint)
    db.commit()
    db.refresh(appointment)
    return appointment


def cancel_booking(
    db: Session, appointment_id: int, payload: schemas.AppointmentCancel
) -> models.Appointment | None:
    _begin_write(db)
    fingerprint = _fingerprint({
        "op": "cancel", "appointment_id": appointment_id,
        "reason": payload.reason, "source": payload.source,
    })
    replay = _idempotent_result(
        db, payload.idempotency_key, "cancel", fingerprint,
        lambda record, appointment: _legacy_cancel_matches(
            db, record, appointment, appointment_id, payload
        ),
    )
    if replay:
        return replay
    appointment = db.get(models.Appointment, appointment_id)
    if not appointment:
        return None
    if appointment.status == "cancelled":
        raise BookingRuleError("This appointment is already cancelled")
    if appointment.status not in CANCELLABLE_STATUSES:
        status_label = appointment.status.replace("_", " ")
        raise BookingRuleError(f"A {status_label} appointment cannot be cancelled through normal cancellation")
    open_turn = (
        db.query(models.Turn.id)
        .filter(models.Turn.appointment_id == appointment.id, models.Turn.status.in_(ACTIVE_TURN_STATUSES))
        .first()
    )
    if open_turn:
        raise BookingRuleError(
            "This appointment has an open turn. Cancel or finish the turn first so both stay in step"
        )
    appointment.status = "cancelled"
    appointment.cancelled_at_utc = utc_now_naive()
    appointment.cancellation_reason = payload.reason
    appointment.cancellation_source = payload.source
    appointment.updated_at = utc_now_naive()
    appointment.events.append(
        models.AppointmentEvent(
            event_type="cancelled",
            old_starts_at_utc=appointment.starts_at_utc,
            old_ends_at_utc=appointment.ends_at_utc,
            note=payload.reason,
            created_at_utc=utc_now_naive(),
        )
    )
    _record_idempotency(db, payload.idempotency_key, "cancel", appointment.id, fingerprint)
    db.commit()
    db.refresh(appointment)
    return appointment


def create_blocked_time(
    db: Session, technician_id: int, payload: schemas.TechnicianBlockedTimeCreate
) -> models.TechnicianBlockedTime:
    technician = db.get(models.Technician, technician_id)
    if not technician or not technician.is_active:
        raise BookingRuleError("Technician not found or inactive")
    settings = get_salon_settings(db)
    start_local = as_salon_datetime(payload.start, settings.timezone)
    end_local = as_salon_datetime(payload.end, settings.timezone)
    if end_local <= start_local:
        raise BookingRuleError("Blocked time end must be after start")
    item = models.TechnicianBlockedTime(
        technician_id=technician_id,
        starts_at_utc=local_to_utc_naive(start_local, settings.timezone),
        ends_at_utc=local_to_utc_naive(end_local, settings.timezone),
        block_type=payload.block_type,
        reason=payload.reason,
        note=payload.note,
        created_at_utc=utc_now_naive(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
