from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

import models
from phone_normalization import PhoneNormalizationError, normalize_us_phone


ARRIVAL_APPOINTMENT_STATUSES = ("scheduled", "checked_in")
MAX_VISIT_SERVICE_IDS = 20


def parse_service_ids(value) -> list[int]:
    """Check-In's service_ids: absent/None/[] = legacy visit (name path). Anything else must be a
    list of at most 20 positive integers; a malformed payload is rejected, never guessed at."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_VISIT_SERVICE_IDS:
        raise ValueError("Check-in service returned malformed service ids")
    parsed: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError("Check-in service returned malformed service ids")
        if item not in parsed:
            parsed.append(item)
    return parsed


def visit_service_availability(db: Session, service_ids: list[int]) -> tuple[list[int], list[int] | None]:
    """(unavailable_ids, eligible_technician_ids). Legacy visits (no ids) -> ([], None).
    If any id is unknown or was deactivated after check-in, nobody is eligible: the visit is kept in
    the queue and flagged, and the assignment endpoints refuse it (no name fallback)."""
    if not service_ids:
        return [], None
    active = {
        row[0] for row in db.query(models.BookingService.id)
        .filter(models.BookingService.id.in_(service_ids), models.BookingService.is_active.is_(True)).all()
    }
    unavailable = [service_id for service_id in service_ids if service_id not in active]
    if unavailable:
        return unavailable, []
    required = set(service_ids)
    technicians = db.query(models.Technician).filter(models.Technician.is_active.is_(True)).order_by(models.Technician.id).all()
    return [], [
        technician.id for technician in technicians
        if required.issubset({item.service_id for item in technician.service_eligibilities})
    ]


@dataclass(frozen=True)
class AppointmentMatch:
    outcome: str
    appointment: models.Appointment | None = None
    candidate_ids: tuple[int, ...] = ()
    reason: str | None = None


def match_checkin_to_appointment(
    db: Session,
    *,
    customer_phone: str,
    checked_in_at: datetime,
    customer_name: str | None = None,
) -> AppointmentMatch:
    """Match by US phone and local calendar date; never use name to defeat a phone mismatch."""
    try:
        phone_e164 = normalize_us_phone(customer_phone).e164
    except PhoneNormalizationError:
        return AppointmentMatch("no_match", reason="invalid_phone")

    day = checked_in_at.date()
    candidates = []
    for appointment in (
        db.query(models.Appointment)
        .filter(models.Appointment.status.in_(ARRIVAL_APPOINTMENT_STATUSES))
        .order_by(models.Appointment.appointment_time.asc(), models.Appointment.id.asc())
        .all()
    ):
        if appointment.appointment_time.date() != day:
            continue
        stored_e164 = appointment.customer_phone_e164
        if not stored_e164:
            try:
                stored_e164 = normalize_us_phone(appointment.customer_phone).e164
            except PhoneNormalizationError:
                continue
        if stored_e164 == phone_e164:
            candidates.append(appointment)

    if not candidates:
        return AppointmentMatch("no_match", reason="no_eligible_appointment")
    if len(candidates) > 1:
        ordered = sorted(
            candidates,
            key=lambda item: (abs((item.appointment_time - checked_in_at.replace(tzinfo=None)).total_seconds()), item.id),
        )
        return AppointmentMatch("ambiguous", candidate_ids=tuple(item.id for item in ordered), reason="multiple_phone_matches")
    return AppointmentMatch("exact_match", appointment=candidates[0], candidate_ids=(candidates[0].id,))
