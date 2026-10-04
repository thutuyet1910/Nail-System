from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

import models
from phone_normalization import PhoneNormalizationError, normalize_us_phone


ARRIVAL_APPOINTMENT_STATUSES = ("scheduled", "checked_in")


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
