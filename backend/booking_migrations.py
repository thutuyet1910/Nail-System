import json
import re
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

import models
from database import engine
from timeutils import DEFAULT_SALON_TIMEZONE, local_to_utc_naive, utc_now_naive
from phone_normalization import PhoneNormalizationError, normalize_us_phone


LEGACY_DEFAULT_DURATION_MINUTES = 60

# DEVELOPMENT / UNCONFIRMED SEED DATA. The salon name, business hours, service list, durations,
# buffers and technician eligibility below are development placeholders that have NOT been
# confirmed by the salon owner. Review and replace them before any real salon pilot.
# These preserve the existing owner-dashboard names. Prices intentionally remain unknown (NULL).
DEFAULT_BOOKING_SERVICES = [
    ("Acrylic Full Set", "Acrylic", 90),
    ("Acrylic Fill", "Acrylic", 60),
    ("Gel Full Set", "Gel", 75),
    ("Gel Fill", "Gel", 60),
    ("Dip Powder", "Dip Powder", 60),
    ("Pink and White", "Acrylic", 90),
    ("Ombre Nails", "Nail Art", 90),
    ("Builder Gel", "Builder / Hard Gel", 75),
    ("Classic Manicure", "Manicure / Pedicure", 30),
    ("Gel Manicure", "Manicure / Pedicure", 45),
    ("Deluxe Manicure", "Manicure / Pedicure", 45),
    ("Classic Pedicure", "Manicure / Pedicure", 45),
    ("Deluxe Pedicure", "Manicure / Pedicure", 60),
    ("Spa Pedicure", "Manicure / Pedicure", 60),
    ("Jelly Pedicure", "Manicure / Pedicure", 60),
    ("Polish Change - Hands", "Manicure / Pedicure", 20),
    ("Polish Change - Feet", "Manicure / Pedicure", 20),
    ("Nail Repair", "Nail Repair / Removal", 30),
    ("Nail Removal", "Nail Repair / Removal", 30),
    ("French Tip", "Nail Art", 20),
    ("Nail Art", "Nail Art", 30),
    ("Chrome / Cat Eye", "Nail Art", 20),
    ("Paraffin Treatment", "Manicure / Pedicure", 20),
    ("Waxing - Eyebrows", "Waxing", 15),
    ("Waxing - Lip", "Waxing", 15),
    ("Waxing - Chin", "Waxing", 15),
    ("Facial", "Facial", 60),
]

# DEVELOPMENT / UNCONFIRMED placeholder hours (see note above).
DEFAULT_BUSINESS_HOURS = {
    0: (time(9, 0), time(18, 0)),
    1: (time(9, 0), time(18, 0)),
    2: (time(9, 0), time(18, 0)),
    3: (time(9, 0), time(18, 0)),
    4: (time(9, 0), time(18, 0)),
    5: (time(9, 0), time(18, 0)),
    6: None,
}


def ensure_booking_columns() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("appointments")}
    additions = {
        "starts_at_utc": "DATETIME",
        "ends_at_utc": "DATETIME",
        "duration_minutes": "INTEGER",
        "legacy_duration_fallback": "BOOLEAN NOT NULL DEFAULT 0",
        "cancelled_at_utc": "DATETIME",
        "cancellation_reason": "TEXT",
        "cancellation_source": "VARCHAR",
        "customer_phone_e164": "VARCHAR",
        "external_customer_id": "INTEGER",
    }
    with engine.begin() as connection:
        for name, ddl in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE appointments ADD COLUMN {name} {ddl}"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_appointments_interval ON appointments (technician_id, starts_at_utc, ends_at_utc)")
        )
        turn_columns = {column[1] for column in connection.execute(text("PRAGMA table_info(turns)")).fetchall()}
        turn_additions = {
            "customer_phone_e164": "VARCHAR",
            "checkin_customer_id": "INTEGER",
            "checkin_visit_id": "INTEGER",
            "appointment_id": "INTEGER REFERENCES appointments(id)",
        }
        for name, ddl in turn_additions.items():
            if name not in turn_columns:
                connection.execute(text(f"ALTER TABLE turns ADD COLUMN {name} {ddl}"))
        idem_columns = {column[1] for column in connection.execute(text("PRAGMA table_info(booking_idempotency_records)")).fetchall()}
        if idem_columns and "request_hash" not in idem_columns:
            connection.execute(text("ALTER TABLE booking_idempotency_records ADD COLUMN request_hash VARCHAR"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_appointments_phone_e164 ON appointments (customer_phone_e164)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_turns_phone_e164 ON turns (customer_phone_e164)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_turns_appointment_id ON turns (appointment_id)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_turn_checkin_visit ON turns (checkin_visit_id) WHERE checkin_visit_id IS NOT NULL"))


def seed_booking_reference_data(db: Session) -> None:
    settings = db.get(models.SalonSettings, 1)
    if not settings:
        db.add(
            models.SalonSettings(
                id=1,
                salon_name="Nail Salon",
                timezone=DEFAULT_SALON_TIMEZONE,
                slot_interval_minutes=15,
                is_active=True,
            )
        )

    existing_days = {row.day_of_week for row in db.query(models.BusinessHour).all()}
    for day, hours in DEFAULT_BUSINESS_HOURS.items():
        if day in existing_days:
            continue
        db.add(
            models.BusinessHour(
                day_of_week=day,
                is_closed=hours is None,
                opens_at=hours[0] if hours else None,
                closes_at=hours[1] if hours else None,
            )
        )

    existing_services = {
        row.name.strip().lower(): row for row in db.query(models.BookingService).all()
    }
    for name, category, duration in DEFAULT_BOOKING_SERVICES:
        if name.lower() not in existing_services:
            db.add(
                models.BookingService(
                    name=name,
                    category=category,
                    duration_minutes=duration,
                    price=None,
                    buffer_before_minutes=0,
                    buffer_after_minutes=0,
                    is_active=True,
                )
            )
    db.commit()


def _schedule_payload(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def sync_technician_schedule_from_legacy(db: Session, technician: models.Technician) -> None:
    parsed = _schedule_payload(technician.work_schedule)
    if not parsed or not isinstance(parsed.get("days"), list):
        return
    day_names = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    try:
        starts_at = time.fromisoformat(parsed.get("start_time", "09:00"))
        ends_at = time.fromisoformat(parsed.get("end_time", "18:00"))
    except ValueError:
        return
    selected = {day_names[str(day).strip().lower()] for day in parsed["days"] if str(day).strip().lower() in day_names}
    db.query(models.TechnicianWorkSchedule).filter(
        models.TechnicianWorkSchedule.technician_id == technician.id
    ).delete(synchronize_session=False)
    for day in range(7):
        db.add(
            models.TechnicianWorkSchedule(
                technician_id=technician.id,
                day_of_week=day,
                is_working=day in selected,
                starts_at=starts_at if day in selected else None,
                ends_at=ends_at if day in selected else None,
            )
        )


def _specialty_matches(service: models.BookingService, specialties: str | None) -> bool:
    values = {part.strip().lower() for part in (specialties or "").split(",") if part.strip()}
    if not values:
        return False
    candidates = {service.name.lower(), (service.category or "").lower()}
    return bool(values & candidates) or any(
        value in service.name.lower() or value in (service.category or "").lower()
        for value in values
    )


def sync_technician_eligibility_from_legacy(db: Session, technician: models.Technician) -> None:
    services = db.query(models.BookingService).filter(models.BookingService.is_active.is_(True)).all()
    eligible_ids = [service.id for service in services if _specialty_matches(service, technician.specialties)]
    db.query(models.TechnicianService).filter(
        models.TechnicianService.technician_id == technician.id
    ).delete(synchronize_session=False)
    for service_id in eligible_ids:
        db.add(models.TechnicianService(technician_id=technician.id, service_id=service_id))


def sync_technician_date_off_from_legacy(
    db: Session, technician: models.Technician, timezone_name: str
) -> None:
    match = re.match(
        r"^date off:\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})$",
        (technician.availability or "").strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return
    try:
        first_day = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        last_day = datetime.strptime(match.group(2), "%Y-%m-%d").date()
    except ValueError:
        return
    if last_day < first_day:
        return
    starts_at_utc = local_to_utc_naive(datetime.combine(first_day, time.min), timezone_name)
    ends_at_utc = local_to_utc_naive(
        datetime.combine(last_day + timedelta(days=1), time.min), timezone_name
    )
    exists = (
        db.query(models.TechnicianBlockedTime.id)
        .filter(
            models.TechnicianBlockedTime.technician_id == technician.id,
            models.TechnicianBlockedTime.starts_at_utc == starts_at_utc,
            models.TechnicianBlockedTime.ends_at_utc == ends_at_utc,
            models.TechnicianBlockedTime.block_type == "date_off",
        )
        .first()
    )
    if not exists:
        db.add(
            models.TechnicianBlockedTime(
                technician_id=technician.id,
                starts_at_utc=starts_at_utc,
                ends_at_utc=ends_at_utc,
                block_type="date_off",
                reason="Migrated from legacy technician availability",
                created_at_utc=utc_now_naive(),
            )
        )


def backfill_legacy_booking_data(db: Session) -> None:
    seed_booking_reference_data(db)
    for technician in db.query(models.Technician).all():
        if not technician.booking_schedules:
            sync_technician_schedule_from_legacy(db, technician)
        if not technician.service_eligibilities:
            sync_technician_eligibility_from_legacy(db, technician)
    db.flush()

    services_by_name = {
        service.name.strip().lower(): service for service in db.query(models.BookingService).all()
    }
    settings = db.get(models.SalonSettings, 1)
    timezone_name = settings.timezone if settings else DEFAULT_SALON_TIMEZONE
    for technician in db.query(models.Technician).all():
        sync_technician_date_off_from_legacy(db, technician, timezone_name)
    for appointment in db.query(models.Appointment).all():
        if not appointment.customer_phone_e164:
            try:
                appointment.customer_phone_e164 = normalize_us_phone(appointment.customer_phone).e164
            except PhoneNormalizationError:
                pass
        if appointment.starts_at_utc and appointment.ends_at_utc:
            continue
        names = [part.strip() for part in (appointment.service_category or appointment.service_name or "").split(",") if part.strip()]
        matched = [services_by_name[name.lower()] for name in names if name.lower() in services_by_name]
        exact = bool(names) and len(matched) == len(names)
        total = sum(
            item.buffer_before_minutes + item.duration_minutes + item.buffer_after_minutes
            for item in matched
        ) if exact else LEGACY_DEFAULT_DURATION_MINUTES
        appointment.starts_at_utc = local_to_utc_naive(appointment.appointment_time, timezone_name)
        appointment.ends_at_utc = appointment.starts_at_utc + timedelta(minutes=total)
        appointment.duration_minutes = total
        appointment.legacy_duration_fallback = not exact
        if not appointment.appointment_services:
            if exact:
                for order, service in enumerate(matched):
                    appointment.appointment_services.append(
                        models.AppointmentService(
                            booking_service_id=service.id,
                            service_name_snapshot=service.name,
                            duration_minutes_snapshot=service.duration_minutes,
                            price_snapshot=service.price,
                            buffer_before_minutes_snapshot=service.buffer_before_minutes,
                            buffer_after_minutes_snapshot=service.buffer_after_minutes,
                            sort_order=order,
                        )
                    )
            else:
                appointment.appointment_services.append(
                    models.AppointmentService(
                        booking_service_id=None,
                        service_name_snapshot=appointment.service_category or appointment.service_name or "Legacy service",
                        duration_minutes_snapshot=LEGACY_DEFAULT_DURATION_MINUTES,
                        price_snapshot=None,
                        buffer_before_minutes_snapshot=0,
                        buffer_after_minutes_snapshot=0,
                        sort_order=0,
                    )
                )
    db.commit()


def upgrade_booking_schema(db: Session) -> None:
    ensure_booking_columns()
    models.Base.metadata.create_all(bind=engine)
    backfill_legacy_booking_data(db)
