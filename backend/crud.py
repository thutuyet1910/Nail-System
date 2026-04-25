from datetime import datetime, date, time
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas


def _generate_appointment_code(db: Session) -> str:
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = f"APT-{today_str}-"

    last_today = (
        db.query(models.Appointment)
        .filter(models.Appointment.appointment_code.like(f"{prefix}%"))
        .order_by(models.Appointment.id.desc())
        .first()
    )

    if not last_today or not last_today.appointment_code:
        next_number = 1
    else:
        try:
            next_number = int(last_today.appointment_code.split("-")[-1]) + 1
        except Exception:
            next_number = 1

    return f"{prefix}{next_number:03d}"


# ----------------------------
# Technicians
# ----------------------------
def create_technician(db: Session, technician: schemas.TechnicianCreate):
    existing_name = (
        db.query(models.Technician)
        .filter(func.lower(models.Technician.full_name) == technician.full_name.lower())
        .first()
    )
    if existing_name:
        raise ValueError("A technician with this name already exists")

    if technician.employee_id:
        existing_employee_id = (
            db.query(models.Technician)
            .filter(models.Technician.employee_id == technician.employee_id)
            .first()
        )
        if existing_employee_id:
            raise ValueError("Employee ID already exists")

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
):
    query = db.query(models.Technician)

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


def update_technician(db: Session, technician_id: int, payload: schemas.TechnicianUpdate):
    db_technician = get_technician(db, technician_id)
    if not db_technician:
        return None

    update_data = payload.model_dump(exclude_unset=True)

    if "full_name" in update_data and update_data["full_name"]:
        existing_name = (
            db.query(models.Technician)
            .filter(
                func.lower(models.Technician.full_name) == update_data["full_name"].lower(),
                models.Technician.id != technician_id,
            )
            .first()
        )
        if existing_name:
            raise ValueError("A technician with this name already exists")

    if "employee_id" in update_data and update_data["employee_id"]:
        existing_employee_id = (
            db.query(models.Technician)
            .filter(
                models.Technician.employee_id == update_data["employee_id"],
                models.Technician.id != technician_id,
            )
            .first()
        )
        if existing_employee_id:
            raise ValueError("Employee ID already exists")

    for key, value in update_data.items():
        setattr(db_technician, key, value)

    db.commit()
    db.refresh(db_technician)
    return db_technician


def delete_technician(db: Session, technician_id: int):
    db_technician = get_technician(db, technician_id)
    if not db_technician:
        return False
    db.delete(db_technician)
    db.commit()
    return True


def get_technician_cards(
    db: Session,
    search: str | None = None,
    specialty: str | None = None,
    status: str | None = None,
    sort_by: str = "name",
):
    technicians = get_technicians(db, search=search, specialty=specialty, status=status, sort_by=sort_by)

    today = date.today()
    start_dt = datetime.combine(today, time.min)
    end_dt = datetime.combine(today, time.max)

    result = []
    for tech in technicians:
        today_appointments_count = (
            db.query(func.count(models.Appointment.id))
            .filter(
                models.Appointment.technician_id == tech.id,
                models.Appointment.appointment_time >= start_dt,
                models.Appointment.appointment_time <= end_dt,
            )
            .scalar()
        )

        today_turns_count = (
            db.query(func.count(models.Turn.id))
            .filter(
                models.Turn.technician_id == tech.id,
                models.Turn.created_at >= start_dt,
                models.Turn.created_at <= end_dt,
            )
            .scalar()
        )

        result.append({
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
            "today_appointments_count": today_appointments_count or 0,
            "today_turns_count": today_turns_count or 0,
        })

    return result


# ----------------------------
# Appointments
# ----------------------------
def create_appointment(db: Session, appointment: schemas.AppointmentCreate):
    payload = appointment.model_dump()

    payload.pop("status", None)

    if not payload.get("appointment_code"):
        payload["appointment_code"] = _generate_appointment_code(db)

    payload["service_name"] = payload.get("service_category")

    if payload.get("technician_id"):
        technician = get_technician(db, payload["technician_id"])
        if not technician:
            raise ValueError("Assigned technician not found")

    if payload.get("preferred_technician_id"):
        preferred_technician = get_technician(db, payload["preferred_technician_id"])
        if not preferred_technician:
            raise ValueError("Preferred technician not found")

    db_appointment = models.Appointment(**payload)
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    return db_appointment


def get_appointments(
    db: Session,
    date: str | None = None,
    technician_id: int | None = None,
    status: str | None = None,
):
    query = db.query(models.Appointment)

    if date:
        target_day = datetime.strptime(date, "%Y-%m-%d").date()
        start_dt = datetime.combine(target_day, time.min)
        end_dt = datetime.combine(target_day, time.max)
        query = query.filter(
            models.Appointment.appointment_time >= start_dt,
            models.Appointment.appointment_time <= end_dt,
        )

    if technician_id:
        query = query.filter(models.Appointment.technician_id == technician_id)

    return query.order_by(models.Appointment.appointment_time.asc()).all()


def get_appointment(db: Session, appointment_id: int):
    return db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()


def update_appointment(db: Session, appointment_id: int, appointment: schemas.AppointmentUpdate):
    db_appointment = get_appointment(db, appointment_id)
    if not db_appointment:
        return None

    payload = appointment.model_dump(exclude_unset=True)
    payload.pop("status", None)

    if "service_category" in payload:
        payload["service_name"] = payload.get("service_category")

    if payload.get("technician_id"):
        technician = get_technician(db, payload["technician_id"])
        if not technician:
            raise ValueError("Assigned technician not found")

    if payload.get("preferred_technician_id"):
        preferred_technician = get_technician(db, payload["preferred_technician_id"])
        if not preferred_technician:
            raise ValueError("Preferred technician not found")

    if not payload.get("appointment_code"):
        payload["appointment_code"] = db_appointment.appointment_code or _generate_appointment_code(db)

    for key, value in payload.items():
        setattr(db_appointment, key, value)

    db_appointment.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(db_appointment)
    return db_appointment


def delete_appointment(db: Session, appointment_id: int):
    db_appointment = get_appointment(db, appointment_id)
    if not db_appointment:
        return False
    db.delete(db_appointment)
    db.commit()
    return True


# ----------------------------
# Turns / Dispatch
# ----------------------------
def _get_next_turn_number_for_today(db: Session):
    today = date.today()
    start_dt = datetime.combine(today, time.min)
    end_dt = datetime.combine(today, time.max)

    max_turn = (
        db.query(func.max(models.Turn.turn_number))
        .filter(models.Turn.created_at >= start_dt, models.Turn.created_at <= end_dt)
        .scalar()
    )

    return (max_turn or 0) + 1


def _specialty_matches(service_name: str, specialties: str | None) -> bool:
    if not specialties or not service_name:
        return False

    specialty_parts = [part.strip().lower() for part in specialties.split(",") if part.strip()]
    if not specialty_parts:
        return False

    service_items = [part.strip().lower() for part in service_name.split(",") if part.strip()]
    if not service_items:
        service_items = [service_name.strip().lower()]

    service_map = {
        "manicure": ["manicure / pedicure (gel)"],
        "pedicure": ["manicure / pedicure (gel)"],
        "classic manicure": ["manicure / pedicure (gel)"],
        "classic pedicure": ["manicure / pedicure (gel)"],
        "spa pedicure": ["manicure / pedicure (gel)"],
        "gel manicure": ["manicure / pedicure (gel)"],
        "gel pedicure": ["manicure / pedicure (gel)"],
        "paraffin treatment": ["manicure / pedicure (gel)"],

        "acrylic": ["acrylic", "acrylic (nail art)"],
        "acrylic full set": ["acrylic", "acrylic (nail art)"],
        "pink and white": ["acrylic", "acrylic (nail art)"],
        "fill": ["acrylic", "acrylic (nail art)"],
        "nail repair": ["acrylic", "acrylic (nail art)", "hard gel", "builder gel"],

        "dipping": ["dipping"],

        "hard gel": ["hard gel"],
        "builder gel": ["builder gel"],
        "gel x": ["gel x"],

        "nail art": ["acrylic (nail art)", "gel x", "hard gel", "builder gel"],
        "chrome": ["acrylic (nail art)", "gel x", "hard gel", "builder gel"],
        "cat eye": ["acrylic (nail art)", "gel x", "hard gel", "builder gel"],
        "polish change": ["manicure / pedicure (gel)"],

        "waxing": ["waxing"],
        "eyebrows": ["waxing"],
        "chin": ["waxing"],
        "lip": ["waxing"],

        "facial": ["facial"],

        "removal": ["acrylic", "dipping", "gel x", "hard gel", "builder gel"],
    }

    required_specialties = set()

    for item in service_items:
        for keyword, mapped_specialties in service_map.items():
            if keyword in item:
                required_specialties.update(mapped_specialties)

    if not required_specialties:
        return False

    return any(specialty in required_specialties for specialty in specialty_parts)


def _get_technician_active_turn_today(db: Session, technician_id: int):
    today = date.today()
    start_dt = datetime.combine(today, time.min)
    end_dt = datetime.combine(today, time.max)

    return (
        db.query(models.Turn)
        .filter(models.Turn.technician_id == technician_id)
        .filter(models.Turn.created_at >= start_dt, models.Turn.created_at <= end_dt)
        .filter(models.Turn.status.in_(["waiting", "assigned", "in_service"]))
        .first()
    )


def _is_technician_free_today(db: Session, technician_id: int) -> bool:
    return _get_technician_active_turn_today(db, technician_id) is None


def _get_candidate_technicians_for_service(db: Session, service_name: str):
    technicians = (
        db.query(models.Technician)
        .filter(models.Technician.status == "active")
        .filter(models.Technician.availability == "available today")
        .all()
    )

    matched = [tech for tech in technicians if _specialty_matches(service_name, tech.specialties)]
    free_matched = [tech for tech in matched if _is_technician_free_today(db, tech.id)]

    return free_matched


def _choose_best_technician(db: Session, service_name: str):
    candidates = _get_candidate_technicians_for_service(db, service_name)
    if not candidates:
        return None

    ranked = sorted(candidates, key=lambda tech: tech.full_name.lower())
    return ranked[0]


def create_turn(db: Session, turn: schemas.TurnCreate):
    next_turn = _get_next_turn_number_for_today(db)
    now = datetime.utcnow()

    db_turn = models.Turn(
        turn_number=next_turn,
        customer_name=turn.customer_name,
        customer_phone=turn.customer_phone,
        service_name=turn.service_name,
        status=turn.status,
        source=turn.source,
        preferred_technician_id=turn.preferred_technician_id,
        technician_id=turn.technician_id,
        assigned_by=turn.assigned_by,
        notes=turn.notes,
        discount_type=turn.discount_type,
        discount_value=turn.discount_value,
        discount_label=turn.discount_label,
        created_at=now,
        assigned_at=now if turn.status in ["assigned", "in_service", "done"] else None,
        started_at=now if turn.status in ["in_service", "done"] else None,
        completed_at=now if turn.status == "done" else None,
    )
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
    technician = _choose_best_technician(db, payload.service_name)
    if not technician:
        raise ValueError("No available technician found for auto assignment")

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
    technician = get_technician(db, payload.preferred_technician_id)
    if not technician:
        raise ValueError("Preferred technician not found")

    if technician.status != "active" or technician.availability != "available today":
        raise ValueError("Preferred technician is not available today")

    if not _is_technician_free_today(db, technician.id):
        raise ValueError("This technician is already assigned to another customer")

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
    today = date.today()
    start_dt = datetime.combine(today, time.min)
    end_dt = datetime.combine(today, time.max)

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

    db_turn.status = status

    now = datetime.utcnow()
    if status == "assigned" and not db_turn.assigned_at:
        db_turn.assigned_at = now
    if status == "in_service" and not db_turn.started_at:
        db_turn.started_at = now
        if not db_turn.assigned_at:
            db_turn.assigned_at = now
    if status == "done" and not db_turn.completed_at:
        db_turn.completed_at = now
        if not db_turn.started_at:
            db_turn.started_at = now
        if not db_turn.assigned_at:
            db_turn.assigned_at = now

    db.commit()
    db.refresh(db_turn)
    return db_turn


def reassign_turn(db: Session, turn_id: int, payload: schemas.ReassignTurnRequest):
    db_turn = get_turn(db, turn_id)
    if not db_turn:
        return None

    technician = get_technician(db, payload.technician_id)
    if not technician:
        raise ValueError("Technician not found")

    if technician.status != "active" or technician.availability != "available today":
        raise ValueError("Technician is not available today")

    if technician.id != db_turn.technician_id and not _is_technician_free_today(db, technician.id):
        raise ValueError("This technician is already assigned to another customer")

    db_turn.technician_id = payload.technician_id
    db_turn.assigned_by = payload.assigned_by or "manager"
    db_turn.notes = payload.notes if payload.notes is not None else db_turn.notes
    db_turn.status = "assigned"
    db_turn.assigned_at = datetime.utcnow()

    db.commit()
    db.refresh(db_turn)
    return db_turn


def start_turn_service(db: Session, turn_id: int, payload: schemas.TurnStartRequest):
    db_turn = get_turn(db, turn_id)
    if not db_turn:
        return None

    now = datetime.utcnow()
    db_turn.status = "in_service"
    if not db_turn.assigned_at:
        db_turn.assigned_at = now
    if not db_turn.started_at:
        db_turn.started_at = now
    if payload.notes:
        db_turn.notes = payload.notes

    db.commit()
    db.refresh(db_turn)
    return db_turn


def complete_turn_service(db: Session, turn_id: int, payload: schemas.TurnCompleteRequest):
    db_turn = get_turn(db, turn_id)
    if not db_turn:
        return None

    now = datetime.utcnow()
    db_turn.status = "done"
    if not db_turn.assigned_at:
        db_turn.assigned_at = now
    if not db_turn.started_at:
        db_turn.started_at = now
    if not db_turn.completed_at:
        db_turn.completed_at = now
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

    update_data = payload.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(db_item, key, value)

    db_item.updated_at = datetime.utcnow()

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
    items = get_inventory_items(db)

    total_inventory_value = 0
    weekly_expense = 0
    monthly_expense = 0
    yearly_expense = 0
    low_stock_items = 0

    today = date.today()
    week_start = today.fromordinal(today.toordinal() - today.weekday())

    for item in items:
        item_total = float(item.quantity or 0) * float(item.unit_price or 0)
        total_inventory_value += item_total

        if (item.quantity or 0) <= (item.low_stock_level or 0):
            low_stock_items += 1

        if item.purchase_date:
            if item.purchase_date >= week_start:
                weekly_expense += item_total

            if item.purchase_date.month == today.month and item.purchase_date.year == today.year:
                monthly_expense += item_total

            if item.purchase_date.year == today.year:
                yearly_expense += item_total

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
def create_checkout(db: Session, payload: schemas.CheckoutCreate):
    checkout_data = payload.model_dump()

    db_checkout = models.Checkout(**checkout_data)
    db.add(db_checkout)
    db.commit()
    db.refresh(db_checkout)

    if db_checkout.turn_id:
        db_turn = get_turn(db, db_checkout.turn_id)
        if db_turn:
            update_turn_status(db, db_turn.id, "done")

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