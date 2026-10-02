from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas


class BusinessRuleError(ValueError):
    """A request that breaks a salon rule. main.py turns it into an HTTP 400."""


# ----------------------------
# Constants
# ----------------------------
ACTIVE_TURN_STATUSES = ("waiting", "assigned", "in_service")
FINISHED_TURN_STATUSES = ("done", "cancelled")

# A turn only moves forward: waiting -> assigned -> in_service -> done.
# Skipping forward is allowed (front desk may skip a click); going back never is.
# "cancelled" is reachable from any open status. "done" and "cancelled" are final.
ALLOWED_TURN_TRANSITIONS = {
    "waiting": {"assigned", "in_service", "done", "cancelled"},
    "assigned": {"in_service", "done", "cancelled"},
    "in_service": {"done", "cancelled"},
    "done": set(),
    "cancelled": set(),
}

TECHNICIAN_RATE = Decimal("0.60")

SERVICE_TO_SPECIALTIES = {
    "manicure": ["manicure / pedicure"],
    "pedicure": ["manicure / pedicure"],
    "classic manicure": ["manicure / pedicure"],
    "deluxe manicure": ["manicure / pedicure"],
    "classic pedicure": ["manicure / pedicure"],
    "deluxe pedicure": ["manicure / pedicure"],
    "spa pedicure": ["manicure / pedicure"],
    "jelly pedicure": ["manicure / pedicure"],
    "gel manicure": ["manicure / pedicure", "gel"],
    "gel pedicure": ["manicure / pedicure", "gel"],
    "paraffin treatment": ["manicure / pedicure"],
    "polish change": ["manicure / pedicure"],
    "acrylic": ["acrylic"],
    "acrylic full set": ["acrylic"],
    "acrylic fill": ["acrylic"],
    "pink and white": ["acrylic", "nail art"],
    "nail repair": ["nail repair / removal", "acrylic", "gel", "builder / hard gel"],
    "dipping": ["dip powder"],
    "dip powder": ["dip powder"],
    "gel full set": ["gel"],
    "gel fill": ["gel"],
    "hard gel": ["builder / hard gel", "gel"],
    "builder gel": ["builder / hard gel"],
    "gel x": ["gel"],
    "nail art": ["nail art"],
    "french tip": ["nail art"],
    "ombre": ["nail art"],
    "chrome": ["nail art"],
    "cat eye": ["nail art"],
    "waxing": ["waxing"],
    "eyebrows": ["waxing"],
    "chin": ["waxing"],
    "lip": ["waxing"],
    "facial": ["facial"],
    "removal": ["nail repair / removal", "acrylic", "dip powder", "gel", "builder / hard gel"],
}


def _now() -> datetime:
    return datetime.now()


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    return datetime.combine(day, time.min), datetime.combine(day, time.max)


def _today_bounds() -> tuple[datetime, datetime]:
    return _day_bounds(date.today())


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


# ----------------------------
# Technicians
# ----------------------------
def _ensure_technician_is_unique(
    db: Session, full_name: str | None, employee_id: str | None, exclude_id: int | None = None
) -> None:
    if full_name:
        query = db.query(models.Technician).filter(
            func.lower(models.Technician.full_name) == full_name.lower()
        )
        if exclude_id:
            query = query.filter(models.Technician.id != exclude_id)
        if query.first():
            raise BusinessRuleError("A technician with this name already exists")

    if employee_id:
        query = db.query(models.Technician).filter(models.Technician.employee_id == employee_id)
        if exclude_id:
            query = query.filter(models.Technician.id != exclude_id)
        if query.first():
            raise BusinessRuleError("Employee ID already exists")


def create_technician(db: Session, technician: schemas.TechnicianCreate):
    _ensure_technician_is_unique(db, technician.full_name, technician.employee_id)

    db_technician = models.Technician(**technician.model_dump())
    db.add(db_technician)
    db.commit()
    db.refresh(db_technician)
    return db_technician


def get_technicians(
    db: Session,
    search: str | None = None,
    specialty: str | None = None,
    status: str | None = None,
    sort_by: str = "name",
    include_inactive: bool = False,
):
    query = db.query(models.Technician)

    if not include_inactive:
        query = query.filter(models.Technician.is_active.is_(True))
    if search:
        query = query.filter(models.Technician.full_name.ilike(f"%{search}%"))
    if specialty:
        query = query.filter(models.Technician.specialties.ilike(f"%{specialty}%"))
    if status:
        query = query.filter(models.Technician.status == status)

    if sort_by == "newest":
        query = query.order_by(models.Technician.id.desc())
    elif sort_by == "oldest":
        query = query.order_by(models.Technician.id.asc())
    else:
        query = query.order_by(models.Technician.full_name.asc())

    return query.all()


def get_technician(db: Session, technician_id: int):
    return db.query(models.Technician).filter(models.Technician.id == technician_id).first()


def _ensure_technician_exists(db: Session, technician_id: int | None, label: str = "Technician") -> None:
    """With foreign keys on, a bad id would be a database error. Give a clear 400 instead."""
    if technician_id is not None and not get_technician(db, technician_id):
        raise BusinessRuleError(f"{label} not found")


def update_technician(db: Session, technician_id: int, payload: schemas.TechnicianUpdate):
    db_technician = get_technician(db, technician_id)
    if not db_technician:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    _ensure_technician_is_unique(
        db, update_data.get("full_name"), update_data.get("employee_id"), exclude_id=technician_id
    )

    for key, value in update_data.items():
        setattr(db_technician, key, value)

    db.commit()
    db.refresh(db_technician)
    return db_technician


def technician_has_history(db: Session, technician_id: int) -> bool:
    """True if the technician appears in any appointment, turn or checkout."""
    appointment = (
        db.query(models.Appointment.id)
        .filter(
            or_(
                models.Appointment.technician_id == technician_id,
                models.Appointment.preferred_technician_id == technician_id,
            )
        )
        .first()
    )
    turn = (
        db.query(models.Turn.id)
        .filter(
            or_(
                models.Turn.technician_id == technician_id,
                models.Turn.preferred_technician_id == technician_id,
            )
        )
        .first()
    )
    checkout = db.query(models.Checkout.id).filter(models.Checkout.technician_id == technician_id).first()
    return any((appointment, turn, checkout))


def deactivate_technician(db: Session, technician_id: int):
    db_technician = get_technician(db, technician_id)
    if not db_technician:
        return None

    if _get_technician_active_turn_today(db, technician_id):
        raise BusinessRuleError(
            "This technician has an open turn today. Complete or reassign it before deactivating."
        )

    db_technician.is_active = False
    db_technician.status = "off"
    db_technician.availability = "off today"

    db.commit()
    db.refresh(db_technician)
    return db_technician


def reactivate_technician(db: Session, technician_id: int):
    """Brings a technician back. Status stays "off" until the manager sets them to active."""
    db_technician = get_technician(db, technician_id)
    if not db_technician:
        return None

    db_technician.is_active = True
    db.commit()
    db.refresh(db_technician)
    return db_technician


def delete_technician(db: Session, technician_id: int):
    """Removes a technician. History is never deleted:
    - no history at all (e.g. added by mistake) -> really deleted, returns "deleted"
    - has history                              -> deactivated instead, returns "deactivated"
    - not found                                -> None
    """
    db_technician = get_technician(db, technician_id)
    if not db_technician:
        return None

    if technician_has_history(db, technician_id):
        deactivate_technician(db, technician_id)
        return "deactivated"

    db.delete(db_technician)
    db.commit()
    return "deleted"


def ensure_technician_active(technician: models.Technician) -> None:
    if not technician.is_active:
        raise BusinessRuleError("This technician has been deactivated")


def _is_bookable(technician: models.Technician) -> bool:
    """Active employee, marked active, and available today."""
    return (
        technician.is_active
        and technician.status == "active"
        and technician.availability == "available today"
    )


def _technician_appointment_filter(technician_id: int):
    """Appointments assigned to the technician, or unassigned ones that asked for them."""
    return or_(
        models.Appointment.technician_id == technician_id,
        models.Appointment.technician_id.is_(None)
        & (models.Appointment.preferred_technician_id == technician_id),
    )


def get_technician_cards(
    db: Session,
    search: str | None = None,
    specialty: str | None = None,
    status: str | None = None,
    sort_by: str = "name",
    include_inactive: bool = False,
):
    technicians = get_technicians(
        db,
        search=search,
        specialty=specialty,
        status=status,
        sort_by=sort_by,
        include_inactive=include_inactive,
    )
    start_dt, end_dt = _today_bounds()

    cards = []
    for tech in technicians:
        appointments_today = (
            db.query(func.count(models.Appointment.id))
            .filter(
                _technician_appointment_filter(tech.id),
                models.Appointment.appointment_time >= start_dt,
                models.Appointment.appointment_time <= end_dt,
            )
            .scalar()
        )
        turns_today = (
            db.query(func.count(models.Turn.id))
            .filter(
                models.Turn.technician_id == tech.id,
                models.Turn.created_at >= start_dt,
                models.Turn.created_at <= end_dt,
            )
            .scalar()
        )

        cards.append(
            {
                "id": tech.id,
                "employee_id": tech.employee_id,
                "full_name": tech.full_name,
                "phone": tech.phone,
                "skills": tech.skills,
                "specialties": tech.specialties,
                "start_date": tech.start_date,
                "status": tech.status,
                "availability": tech.availability,
                "work_schedule": tech.work_schedule,
                "notes": tech.notes,
                "profile_photo": tech.profile_photo,
                "today_appointments_count": appointments_today or 0,
                "today_turns_count": turns_today or 0,
            }
        )

    return cards


# ----------------------------
# Appointments
# ----------------------------
def _generate_appointment_code(db: Session) -> str:
    prefix = f"APT-{_now().strftime('%Y%m%d')}-"

    last_today = (
        db.query(models.Appointment)
        .filter(models.Appointment.appointment_code.like(f"{prefix}%"))
        .order_by(models.Appointment.id.desc())
        .first()
    )

    next_number = 1
    if last_today and last_today.appointment_code:
        try:
            next_number = int(last_today.appointment_code.split("-")[-1]) + 1
        except ValueError:
            pass

    return f"{prefix}{next_number:03d}"


def _validate_appointment(db: Session, payload: dict, exclude_id: int | None = None) -> None:
    for key, label in (
        ("technician_id", "Assigned technician"),
        ("preferred_technician_id", "Preferred technician"),
    ):
        if payload.get(key):
            technician = get_technician(db, payload[key])
            if not technician:
                raise BusinessRuleError(f"{label} not found")
            if not technician.is_active:
                raise BusinessRuleError(f"{label} has been deactivated")

    code = payload.get("appointment_code")
    if code:
        query = db.query(models.Appointment).filter(models.Appointment.appointment_code == code)
        if exclude_id:
            query = query.filter(models.Appointment.id != exclude_id)
        if query.first():
            raise BusinessRuleError("Appointment code already exists")


def create_appointment(db: Session, appointment: schemas.AppointmentCreate):
    payload = appointment.model_dump()
    payload["service_name"] = payload.get("service_category")
    _validate_appointment(db, payload)

    if not payload.get("appointment_code"):
        payload["appointment_code"] = _generate_appointment_code(db)

    db_appointment = models.Appointment(**payload)
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    return db_appointment


def get_appointments(
    db: Session,
    day: date | None = None,
    technician_id: int | None = None,
    status: str | None = None,
):
    query = db.query(models.Appointment)

    if day:
        start_dt, end_dt = _day_bounds(day)
        query = query.filter(
            models.Appointment.appointment_time >= start_dt,
            models.Appointment.appointment_time <= end_dt,
        )
    if technician_id:
        query = query.filter(_technician_appointment_filter(technician_id))
    if status:
        query = query.filter(models.Appointment.status == status)

    return query.order_by(models.Appointment.appointment_time.asc()).all()


def get_appointment(db: Session, appointment_id: int):
    return db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()


def update_appointment(db: Session, appointment_id: int, appointment: schemas.AppointmentUpdate):
    db_appointment = get_appointment(db, appointment_id)
    if not db_appointment:
        return None

    payload = appointment.model_dump(exclude_unset=True)
    if "service_category" in payload:
        payload["service_name"] = payload["service_category"]
    _validate_appointment(db, payload, exclude_id=appointment_id)

    if not payload.get("appointment_code"):
        payload["appointment_code"] = db_appointment.appointment_code or _generate_appointment_code(db)

    for key, value in payload.items():
        setattr(db_appointment, key, value)
    db_appointment.updated_at = _now()

    db.commit()
    db.refresh(db_appointment)
    return db_appointment


def delete_appointment(db: Session, appointment_id: int):
    db_appointment = get_appointment(db, appointment_id)
    if not db_appointment:
        return False

    # A checkout may point at this appointment. With foreign keys on, SQLite refuses
    # the delete, so we turn that into a readable message.
    has_checkout = (
        db.query(models.Checkout.id).filter(models.Checkout.appointment_id == appointment_id).first()
    )
    if has_checkout:
        raise BusinessRuleError("This appointment already has a checkout and cannot be deleted")

    db.delete(db_appointment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BusinessRuleError("This appointment is linked to other records and cannot be deleted")
    return True


# ----------------------------
# Turns: helpers
# ----------------------------
def _get_next_turn_number_for_today(db: Session) -> int:
    start_dt, end_dt = _today_bounds()
    max_turn = (
        db.query(func.max(models.Turn.turn_number))
        .filter(models.Turn.created_at >= start_dt, models.Turn.created_at <= end_dt)
        .scalar()
    )
    return (max_turn or 0) + 1


def _split_csv(text: str) -> list[str]:
    return [part.strip().lower() for part in text.split(",") if part.strip()]


def _specialty_matches(service_name: str, specialties: str | None) -> bool:
    if not specialties or not service_name:
        return False

    specialty_parts = _split_csv(specialties)
    if not specialty_parts:
        return False

    service_items = _split_csv(service_name) or [service_name.strip().lower()]

    if any(item in specialty_parts for item in service_items):
        return True

    required = set()
    for item in service_items:
        for keyword, specialties_for_keyword in SERVICE_TO_SPECIALTIES.items():
            if keyword in item:
                required.update(specialties_for_keyword)

    return bool(required) and any(part in required for part in specialty_parts)


def _apply_status(db_turn: models.Turn, status: str, now: datetime | None = None) -> None:
    """Sets the status and fills in the timestamps that status implies (no commit).

    Low level: it does NOT check that the move is allowed. Use _transition() for that.
    """
    now = now or _now()
    db_turn.status = status

    if status in ("assigned", "in_service", "done") and not db_turn.assigned_at:
        db_turn.assigned_at = now
    if status in ("in_service", "done") and not db_turn.started_at:
        db_turn.started_at = now
    if status == "done" and not db_turn.completed_at:
        db_turn.completed_at = now


def _transition(db_turn: models.Turn, new_status: str) -> None:
    """The single gate for changing the status of an EXISTING turn (no commit).

    - same status      -> nothing to do (a double click is not an error)
    - not allowed move -> BusinessRuleError, e.g. done -> waiting
    """
    if new_status == db_turn.status:
        return

    allowed = ALLOWED_TURN_TRANSITIONS.get(db_turn.status, set())
    if new_status not in allowed:
        raise BusinessRuleError(
            f"A turn cannot go from '{db_turn.status}' to '{new_status}'"
        )

    _apply_status(db_turn, new_status)


def _get_technician_active_turn_today(db: Session, technician_id: int, exclude_turn_id: int | None = None):
    start_dt, end_dt = _today_bounds()

    query = (
        db.query(models.Turn)
        .filter(models.Turn.technician_id == technician_id)
        .filter(models.Turn.created_at >= start_dt, models.Turn.created_at <= end_dt)
        .filter(models.Turn.status.in_(ACTIVE_TURN_STATUSES))
    )
    if exclude_turn_id:
        query = query.filter(models.Turn.id != exclude_turn_id)

    return query.first()


def _is_technician_free_today(db: Session, technician_id: int, exclude_turn_id: int | None = None) -> bool:
    return _get_technician_active_turn_today(db, technician_id, exclude_turn_id) is None


def _get_active_turn_for_customer(db: Session, customer_name: str, customer_phone: str | None = None):
    """The customer's open turn. Matches by phone digits when given, otherwise by name."""
    query = db.query(models.Turn).filter(models.Turn.status.in_(ACTIVE_TURN_STATUSES))

    phone_digits = _digits(customer_phone)
    if phone_digits:
        turns = query.order_by(models.Turn.id.desc()).all()
        return next((turn for turn in turns if _digits(turn.customer_phone) == phone_digits), None)

    return (
        query.filter(func.lower(models.Turn.customer_name) == customer_name.lower())
        .order_by(models.Turn.id.desc())
        .first()
    )


def _move_turn_to_today(db: Session, db_turn: models.Turn):
    """Re-dates an open turn that was NOT created today (e.g. left over from an earlier day)."""
    if db_turn.created_at and db_turn.created_at.date() != date.today():
        now = _now()
        db_turn.created_at = now
        db_turn.turn_number = _get_next_turn_number_for_today(db)
        if db_turn.assigned_at and db_turn.assigned_at.date() != date.today():
            db_turn.assigned_at = now
        if db_turn.started_at and db_turn.started_at.date() != date.today():
            db_turn.started_at = now
        db.commit()
        db.refresh(db_turn)

    return db_turn


def _today_turn_stats(
    db: Session, exclude_turn_id: int | None = None
) -> dict[int, tuple[int, datetime]]:
    """technician_id -> (turns today that were not cancelled, when they were last given a customer).

    One GROUP BY query for everyone, instead of one query per technician.
    """
    start_dt, end_dt = _today_bounds()

    query = (
        db.query(
            models.Turn.technician_id,
            func.count(models.Turn.id),
            func.max(models.Turn.assigned_at),
        )
        .filter(models.Turn.created_at >= start_dt, models.Turn.created_at <= end_dt)
        .filter(models.Turn.status != "cancelled")
    )
    if exclude_turn_id:
        # The turn being assigned right now should not count against its own candidates.
        query = query.filter(models.Turn.id != exclude_turn_id)

    rows = query.group_by(models.Turn.technician_id).all()
    return {tech_id: (count, last or datetime.min) for tech_id, count, last in rows}


def _choose_best_technician(db: Session, service_name: str, exclude_turn_id: int | None = None):
    """Fair auto-assign.

    1. Active?             (is_active)
    2. Available today?    (status == "active" and availability == "available today")
    3. Specialty matches?
    4. Free right now?
    5. Among those left -> fewest turns today
    6. Tie -> longest since last assigned, then name, then id (always one stable winner)
    """
    # Steps 1-2
    technicians = (
        db.query(models.Technician)
        .filter(models.Technician.is_active.is_(True))
        .filter(models.Technician.status == "active")
        .filter(models.Technician.availability == "available today")
        .all()
    )

    # Steps 3-4
    candidates = [
        tech
        for tech in technicians
        if _specialty_matches(service_name, tech.specialties)
        and _is_technician_free_today(db, tech.id, exclude_turn_id)
    ]
    if not candidates:
        return None

    # Steps 5-6
    stats = _today_turn_stats(db, exclude_turn_id)

    def rank(tech: models.Technician):
        count, last_assigned = stats.get(tech.id, (0, datetime.min))
        return (count, last_assigned, tech.full_name.lower(), tech.id)

    return min(candidates, key=rank)


def _assign_existing_turn(
    db: Session,
    db_turn: models.Turn,
    technician: models.Technician,
    payload,
    assigned_by: str,
    update_source_and_notes: bool = False,
):
    _ensure_technician_exists(db, payload.preferred_technician_id, "Preferred technician")

    db_turn.service_name = payload.service_name
    db_turn.technician_id = technician.id
    db_turn.preferred_technician_id = payload.preferred_technician_id
    db_turn.assigned_by = assigned_by
    _transition(db_turn, "assigned")
    db_turn.assigned_at = _now()
    db_turn.discount_type = payload.discount_type
    db_turn.discount_value = payload.discount_value
    db_turn.discount_label = payload.discount_label
    if update_source_and_notes:
        db_turn.source = payload.source
        db_turn.notes = payload.notes

    db.commit()
    db.refresh(db_turn)
    return db_turn


# ----------------------------
# Turns: operations
# ----------------------------
def create_turn(db: Session, turn: schemas.TurnCreate):
    _ensure_technician_exists(db, turn.technician_id)
    _ensure_technician_exists(db, turn.preferred_technician_id, "Preferred technician")

    now = _now()

    db_turn = models.Turn(
        turn_number=_get_next_turn_number_for_today(db),
        customer_name=turn.customer_name,
        customer_phone=turn.customer_phone,
        service_name=turn.service_name,
        source=turn.source,
        preferred_technician_id=turn.preferred_technician_id,
        technician_id=turn.technician_id,
        assigned_by=turn.assigned_by,
        notes=turn.notes,
        discount_type=turn.discount_type,
        discount_value=turn.discount_value,
        discount_label=turn.discount_label,
        created_at=now,
    )
    _apply_status(db_turn, turn.status, now)

    db.add(db_turn)
    db.commit()
    db.refresh(db_turn)
    return db_turn


def assign_next_turn(db: Session, payload: schemas.AssignTurnRequest):
    return create_turn(
        db,
        schemas.TurnCreate(
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            service_name=payload.service_name,
            technician_id=payload.technician_id,
            preferred_technician_id=payload.preferred_technician_id,
            source=payload.source,
            discount_type=payload.discount_type,
            discount_value=payload.discount_value,
            discount_label=payload.discount_label,
            assigned_by=payload.assigned_by or "manual",
            notes=payload.notes,
            status="assigned",
        ),
    )


def assign_turn_auto(db: Session, payload: schemas.AutoAssignTurnRequest):
    existing_turn = _get_active_turn_for_customer(db, payload.customer_name, payload.customer_phone)

    if existing_turn:
        existing_turn = _move_turn_to_today(db, existing_turn)
        if existing_turn.status != "waiting":
            return existing_turn

        technician = _choose_best_technician(db, payload.service_name, exclude_turn_id=existing_turn.id)
        if not technician:
            raise BusinessRuleError("No available technician found for auto assignment")
        return _assign_existing_turn(db, existing_turn, technician, payload, assigned_by="system")

    technician = _choose_best_technician(db, payload.service_name)
    if not technician:
        raise BusinessRuleError("No available technician found for auto assignment")

    return create_turn(
        db,
        schemas.TurnCreate(
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            service_name=payload.service_name,
            technician_id=technician.id,
            preferred_technician_id=payload.preferred_technician_id,
            source=payload.source,
            assigned_by="system",
            notes=payload.notes,
            discount_type=payload.discount_type,
            discount_value=payload.discount_value,
            discount_label=payload.discount_label,
            status="assigned",
        ),
    )


def assign_turn_preferred(db: Session, payload: schemas.AssignPreferredTurnRequest):
    existing_turn = _get_active_turn_for_customer(db, payload.customer_name, payload.customer_phone)
    if existing_turn:
        existing_turn = _move_turn_to_today(db, existing_turn)
        if existing_turn.status != "waiting":
            return existing_turn

    technician = get_technician(db, payload.preferred_technician_id)
    if not technician:
        raise BusinessRuleError("Preferred technician not found")
    if not _is_bookable(technician):
        raise BusinessRuleError("Preferred technician is not available today")
    if not _specialty_matches(payload.service_name, technician.specialties):
        raise BusinessRuleError("Preferred technician does not match the selected service")
    if not _is_technician_free_today(db, technician.id, existing_turn.id if existing_turn else None):
        raise BusinessRuleError("This technician is already assigned to another customer")

    if existing_turn:
        return _assign_existing_turn(
            db, existing_turn, technician, payload, assigned_by="manager", update_source_and_notes=True
        )

    return create_turn(
        db,
        schemas.TurnCreate(
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            service_name=payload.service_name,
            technician_id=technician.id,
            preferred_technician_id=payload.preferred_technician_id,
            source=payload.source,
            assigned_by="manager",
            notes=payload.notes,
            status="assigned",
            discount_type=payload.discount_type,
            discount_value=payload.discount_value,
            discount_label=payload.discount_label,
        ),
    )


def get_turns(db: Session):
    return db.query(models.Turn).order_by(models.Turn.created_at.desc()).all()


def get_today_turns(db: Session):
    start_dt, end_dt = _today_bounds()
    return (
        db.query(models.Turn)
        .filter(models.Turn.created_at >= start_dt, models.Turn.created_at <= end_dt)
        .order_by(models.Turn.turn_number.asc())
        .all()
    )


def get_turn(db: Session, turn_id: int):
    return db.query(models.Turn).filter(models.Turn.id == turn_id).first()


def update_turn_status(db: Session, turn_id: int, status: str):
    db_turn = get_turn(db, turn_id)
    if not db_turn:
        return None

    _transition(db_turn, status)
    db.commit()
    db.refresh(db_turn)
    return db_turn


def reassign_turn(db: Session, turn_id: int, payload: schemas.ReassignTurnRequest):
    db_turn = get_turn(db, turn_id)
    if not db_turn:
        return None

    if db_turn.status in FINISHED_TURN_STATUSES:
        raise BusinessRuleError(f"A {db_turn.status} turn cannot be reassigned")

    technician = get_technician(db, payload.technician_id)
    if not technician:
        raise BusinessRuleError("Technician not found")
    if not _is_bookable(technician):
        raise BusinessRuleError("Technician is not available today")
    if not _specialty_matches(db_turn.service_name, technician.specialties):
        raise BusinessRuleError("Technician does not match this customer's selected service")
    if technician.id != db_turn.technician_id and not _is_technician_free_today(db, technician.id):
        raise BusinessRuleError("This technician is already assigned to another customer")

    db_turn.technician_id = payload.technician_id
    db_turn.assigned_by = payload.assigned_by or "manager"
    if payload.notes is not None:
        db_turn.notes = payload.notes

    # Changing the technician must not move the turn backwards.
    if db_turn.status == "waiting":
        _transition(db_turn, "assigned")
    elif db_turn.status == "assigned":
        db_turn.assigned_at = _now()
    # "in_service" stays "in_service".

    db.commit()
    db.refresh(db_turn)
    return db_turn


def start_turn_service(db: Session, turn_id: int, payload: schemas.TurnStartRequest):
    db_turn = get_turn(db, turn_id)
    if not db_turn:
        return None

    _transition(db_turn, "in_service")
    if payload.notes:
        db_turn.notes = payload.notes

    db.commit()
    db.refresh(db_turn)
    return db_turn


def complete_turn_service(db: Session, turn_id: int, payload: schemas.TurnCompleteRequest):
    db_turn = get_turn(db, turn_id)
    if not db_turn:
        return None

    _transition(db_turn, "done")
    if payload.notes:
        db_turn.notes = payload.notes

    db.commit()
    db.refresh(db_turn)
    return db_turn


# ----------------------------
# Inventory
# ----------------------------
def create_inventory_item(db: Session, payload: schemas.InventoryItemCreate):
    db_item = models.InventoryItem(**payload.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def get_inventory_items(db: Session):
    return db.query(models.InventoryItem).order_by(models.InventoryItem.id.desc()).all()


def get_inventory_item(db: Session, item_id: int):
    return db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id).first()


def update_inventory_item(db: Session, item_id: int, payload: schemas.InventoryItemUpdate):
    db_item = get_inventory_item(db, item_id)
    if not db_item:
        return None

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
    db_item.updated_at = _now()

    db.commit()
    db.refresh(db_item)
    return db_item


def delete_inventory_item(db: Session, item_id: int):
    db_item = get_inventory_item(db, item_id)
    if not db_item:
        return False

    db.delete(db_item)
    db.commit()
    return True


def get_inventory_summary(db: Session):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    total_inventory_value = 0.0
    weekly_expense = monthly_expense = yearly_expense = 0.0
    low_stock_items = 0

    for item in get_inventory_items(db):
        item_total = float(item.quantity or 0) * float(item.unit_price or 0)
        total_inventory_value += item_total

        if (item.quantity or 0) <= (item.low_stock_level or 0):
            low_stock_items += 1

        purchased = item.purchase_date
        if purchased:
            if purchased >= week_start:
                weekly_expense += item_total
            if purchased.year == today.year:
                yearly_expense += item_total
                if purchased.month == today.month:
                    monthly_expense += item_total

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "weekly_expense": round(weekly_expense, 2),
        "monthly_expense": round(monthly_expense, 2),
        "yearly_expense": round(yearly_expense, 2),
        "low_stock_items": low_stock_items,
    }


# ----------------------------
# Checkout
# ----------------------------
def _q(value: Decimal) -> Decimal:
    """Round to cents the way a cash register does (0.005 -> 0.01)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calculate_checkout(payload: schemas.CheckoutCreate) -> dict:
    """All money figures, calculated on the server from the four inputs:
    subtotal, discount_type, discount_value, tip_amount. Never trust the client for these."""
    subtotal = _q(Decimal(str(payload.subtotal)))
    discount_value = Decimal(str(payload.discount_value))
    tip = _q(Decimal(str(payload.tip_amount)))

    if payload.discount_type == "percent":
        discount = subtotal * discount_value / Decimal(100)
    elif payload.discount_type == "fixed":
        discount = discount_value
    else:
        discount = Decimal(0)
    discount = _q(min(discount, subtotal))  

    net_service = subtotal - discount
    technician_share = _q(subtotal * TECHNICIAN_RATE)  
    salon_share = subtotal - technician_share

    return {
        "subtotal": subtotal,
        "tip_amount": tip,
        "discount_amount": discount,
        "discount_paid_by": "owner",
        "net_service": net_service,
        "technician_share": technician_share,
        "salon_share": salon_share,
        "salon_actual_revenue": salon_share - discount,  
        "technician_total": technician_share + tip,
        "customer_pays": net_service + tip,
    }


def _validate_checkout_links(db: Session, payload: schemas.CheckoutCreate):
    """Checks every id in the request. Returns the Turn (or None) so the caller can reuse it."""
    _ensure_technician_exists(db, payload.technician_id)

    if payload.appointment_id and not get_appointment(db, payload.appointment_id):
        raise BusinessRuleError("Appointment not found")

    if not payload.turn_id:
        return None

    turn = get_turn(db, payload.turn_id)
    if not turn:
        raise BusinessRuleError("Turn not found")
    if turn.status == "cancelled":
        raise BusinessRuleError("A cancelled turn cannot be checked out")
    if payload.technician_id and payload.technician_id != turn.technician_id:
        raise BusinessRuleError("Technician does not match the technician on this turn")

    already_paid = db.query(models.Checkout.id).filter(models.Checkout.turn_id == payload.turn_id).first()
    if already_paid:
        raise BusinessRuleError("This turn has already been checked out")

    return turn


def create_checkout(db: Session, payload: schemas.CheckoutCreate):
    turn = _validate_checkout_links(db, payload)

    values = payload.model_dump()
    values.update(_calculate_checkout(payload))
    if turn and not values.get("technician_id"):
        values["technician_id"] = turn.technician_id

    # Mark the turn done in the SAME transaction, so a checkout can't exist without it.
    # Transition first: if it is refused, nothing has been added to the session yet.
    if turn:
        _transition(turn, "done")

    db_checkout = models.Checkout(**values)
    db.add(db_checkout)
    db.commit()
    db.refresh(db_checkout)
    return db_checkout


def get_checkouts(db: Session):
    return db.query(models.Checkout).order_by(models.Checkout.created_at.desc()).all()


def get_checkout(db: Session, checkout_id: int):
    return db.query(models.Checkout).filter(models.Checkout.id == checkout_id).first()


def delete_checkout(db: Session, checkout_id: int):
    db_checkout = get_checkout(db, checkout_id)
    if not db_checkout:
        return False

    db.delete(db_checkout)
    db.commit()
    return True


# ----------------------------
# Income reports
# ----------------------------
def _money(value) -> float:
    return round(float(value or 0), 2)


def _total(checkouts, field: str) -> float:
    return _money(sum(_money(getattr(checkout, field)) for checkout in checkouts))


def _period_range(anchor_date: date, period: str):
    if period == "day":
        return anchor_date, anchor_date
    if period == "week":  # Monday to Sunday
        start_date = anchor_date - timedelta(days=anchor_date.weekday())
        return start_date, start_date + timedelta(days=6)
    if period == "year":
        return anchor_date.replace(month=1, day=1), anchor_date.replace(month=12, day=31)
    raise ValueError("Unsupported income period")


def _checkouts_for_range(db: Session, start_date: date, end_date: date, technician_id: int | None = None):
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    query = (
        db.query(models.Checkout)
        .filter(models.Checkout.created_at >= start_dt)
        .filter(models.Checkout.created_at <= end_dt)
    )
    if technician_id:
        query = query.filter(models.Checkout.technician_id == technician_id)

    return query.order_by(models.Checkout.created_at.desc(), models.Checkout.id.desc()).all()


def _turn_lookup(db: Session, checkouts) -> dict:
    turn_ids = [checkout.turn_id for checkout in checkouts if checkout.turn_id]
    if not turn_ids:
        return {}
    return {turn.id: turn for turn in db.query(models.Turn).filter(models.Turn.id.in_(turn_ids)).all()}


def _technician_lookup(db: Session) -> dict:
    technicians = db.query(models.Technician).order_by(models.Technician.full_name.asc()).all()
    return {technician.id: technician for technician in technicians}


def _income_detail(checkout: models.Checkout, technicians_by_id: dict, turns_by_id: dict) -> dict:
    technician = technicians_by_id.get(checkout.technician_id)
    turn = turns_by_id.get(checkout.turn_id)
    return {
        "checkout_id": checkout.id,
        "turn_id": checkout.turn_id,
        "turn_number": turn.turn_number if turn else None,
        "customer_name": checkout.customer_name,
        "customer_phone": checkout.customer_phone,
        "technician_id": checkout.technician_id,
        "technician_name": technician.full_name if technician else None,
        "service_name": checkout.service_name,
        "payment_method": checkout.payment_method,
        "gross_before_discount": _money(checkout.subtotal),
        "discount_amount": _money(checkout.discount_amount),
        "net_after_discount": _money(checkout.net_service),
        "tech_60_percent": _money(checkout.technician_share),
        "tip_amount": _money(checkout.tip_amount),
        "tech_total": _money(checkout.technician_total),
        "salon_income_after_tech": _money(checkout.salon_actual_revenue),
        "customer_pays": _money(checkout.customer_pays),
        "created_at": checkout.created_at,
        "note": checkout.note,
    }


def _salon_period_summary(db: Session, anchor_date: date, period: str, checkouts=None) -> dict:
    start_date, end_date = _period_range(anchor_date, period)
    if checkouts is None:
        checkouts = _checkouts_for_range(db, start_date, end_date)

    return {
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "income_before_discount": _total(checkouts, "subtotal"),
        "total_discount": _total(checkouts, "discount_amount"),
        "income_after_discount": _total(checkouts, "net_service"),
        "tech_60_percent_total": _total(checkouts, "technician_share"),
        "tech_tip_total": _total(checkouts, "tip_amount"),
        "total_paid_to_techs": _total(checkouts, "technician_total"),
        "salon_income_after_techs": _total(checkouts, "salon_actual_revenue"),
        "turns": len(checkouts),
    }


def get_tech_income_report(db: Session, report_date: date, technician_id: int | None = None):
    checkouts = _checkouts_for_range(db, report_date, report_date, technician_id=technician_id)
    technicians_by_id = _technician_lookup(db)
    turns_by_id = _turn_lookup(db, checkouts)

    grouped: dict[int | None, list] = {}
    for checkout in checkouts:
        grouped.setdefault(checkout.technician_id, []).append(checkout)

    summaries = []
    for group_technician_id, tech_checkouts in grouped.items():
        technician = technicians_by_id.get(group_technician_id)
        summaries.append(
            {
                "technician_id": group_technician_id,
                "technician_name": technician.full_name if technician else "Unassigned Technician",
                "date": report_date,
                "gross_before_60": _total(tech_checkouts, "subtotal"),
                "tech_after_60": _total(tech_checkouts, "technician_share"),
                "tip_total": _total(tech_checkouts, "tip_amount"),
                "tech_total": _total(tech_checkouts, "technician_total"),
                "turns": len(tech_checkouts),
                "details": [
                    _income_detail(checkout, technicians_by_id, turns_by_id)
                    for checkout in tech_checkouts
                ],
            }
        )

    summaries.sort(key=lambda item: item["technician_name"].lower())
    return {"date": report_date, "technicians": summaries}


def get_salon_income_report(db: Session, report_date: date):
    day_checkouts = _checkouts_for_range(db, report_date, report_date)
    technicians_by_id = _technician_lookup(db)
    turns_by_id = _turn_lookup(db, day_checkouts)

    return {
        "date": report_date,
        "day": _salon_period_summary(db, report_date, "day", checkouts=day_checkouts),
        "week": _salon_period_summary(db, report_date, "week"),
        "year": _salon_period_summary(db, report_date, "year"),
        "details": [
            _income_detail(checkout, technicians_by_id, turns_by_id) for checkout in day_checkouts
        ],
    }