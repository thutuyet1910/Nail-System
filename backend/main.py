import logging
import os
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import crud
import models
import schemas
from database import engine, get_db

logger = logging.getLogger("nail_salon")

models.Base.metadata.create_all(bind=engine)


# ----------------------------
# Startup migration (SQLite)
# ----------------------------
NEW_INDEXES = [
    ("ix_turns_created_at", "turns", "created_at"),
    ("ix_turns_status", "turns", "status"),
    ("ix_turns_technician_id", "turns", "technician_id"),
    ("ix_checkouts_created_at", "checkouts", "created_at"),
]


def ensure_schema() -> None:
    with engine.begin() as conn:
        appointment_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(appointments)")).fetchall()
        }
        if "status" not in appointment_columns:
            conn.execute(
                text("ALTER TABLE appointments ADD COLUMN status VARCHAR NOT NULL DEFAULT 'scheduled'")
            )

        technician_columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(technicians)")).fetchall()
        }
        if "is_active" not in technician_columns:
            conn.execute(text("ALTER TABLE technicians ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))

        for name, table, column in NEW_INDEXES:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})"))

        # Foreign keys are now enforced. Rows that already point at something that
        # doesn't exist will make later writes to them fail, so warn loudly at startup.
        orphans = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        if orphans:
            logger.warning(
                "foreign_key_check found %d orphaned row(s). Run `PRAGMA foreign_key_check;` "
                "in sqlite3 to see which tables, then fix or delete them.",
                len(orphans),
            )


ensure_schema()


# ----------------------------
# App setup
# ----------------------------
app = FastAPI(title="Nail Salon Backend", version="0.4.0")

# "*" keeps local development easy. In production set 
# ALLOWED_ORIGINS="http://192.168.1.50:5500,https://manager.mysalon.com"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False, 
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(crud.BusinessRuleError)
async def business_rule_handler(request, exc: crud.BusinessRuleError):
    """Every salon-rule violation raised in crud.py becomes a clean HTTP 400."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request, exc: IntegrityError):
    """Safety net for the database refusing a write (e.g. a foreign key or unique rule).
    crud.py checks the common cases first, so this should rarely fire."""
    logger.warning("IntegrityError: %s", exc.orig)
    return JSONResponse(
        status_code=409,
        content={"detail": "This change conflicts with existing data (a linked record is missing or still in use)"},
    )


def _or_404(item, name: str):
    if not item:
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return item


@app.get("/")
def root():
    return {"message": "Nail Salon Backend is running"}


# ----------------------------
# Technicians
# ----------------------------
@app.post("/technicians", response_model=schemas.TechnicianOut)
def create_technician(technician: schemas.TechnicianCreate, db: Session = Depends(get_db)):
    return crud.create_technician(db, technician)


@app.get("/technicians", response_model=list[schemas.TechnicianOut])
def get_technicians(
    search: Optional[str] = None,
    specialty: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = Query(default="name"),
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    return crud.get_technicians(
        db, search=search, specialty=specialty, status=status, sort_by=sort_by, include_inactive=include_inactive
    )


@app.get("/technicians/cards", response_model=list[schemas.TechnicianCardOut])
def get_technician_cards(
    search: Optional[str] = None,
    specialty: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = Query(default="name"),
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    return crud.get_technician_cards(
        db, search=search, specialty=specialty, status=status, sort_by=sort_by, include_inactive=include_inactive
    )


@app.get("/technicians/{technician_id}", response_model=schemas.TechnicianOut)
def get_technician(technician_id: int, db: Session = Depends(get_db)):
    return _or_404(crud.get_technician(db, technician_id), "Technician")


@app.put("/technicians/{technician_id}", response_model=schemas.TechnicianOut)
def update_technician(technician_id: int, payload: schemas.TechnicianUpdate, db: Session = Depends(get_db)):
    return _or_404(crud.update_technician(db, technician_id, payload), "Technician")


@app.delete("/technicians/{technician_id}")
def delete_technician(technician_id: int, db: Session = Depends(get_db)):
    """Deletes a technician with no history; otherwise deactivates them (history is kept)."""
    result = _or_404(crud.delete_technician(db, technician_id), "Technician")
    if result == "deactivated":
        return {"message": "Technician has history, so they were deactivated instead of deleted"}
    return {"message": "Technician deleted"}


@app.put("/technicians/{technician_id}/deactivate", response_model=schemas.TechnicianOut)
def deactivate_technician(technician_id: int, db: Session = Depends(get_db)):
    return _or_404(crud.deactivate_technician(db, technician_id), "Technician")


@app.put("/technicians/{technician_id}/reactivate", response_model=schemas.TechnicianOut)
def reactivate_technician(technician_id: int, db: Session = Depends(get_db)):
    return _or_404(crud.reactivate_technician(db, technician_id), "Technician")


# ----------------------------
# Appointments
# ----------------------------
@app.post("/appointments", response_model=schemas.AppointmentOut)
def create_appointment(appointment: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    return crud.create_appointment(db, appointment)


@app.get("/appointments", response_model=list[schemas.AppointmentOut])
def get_appointments(
    day: Optional[date] = Query(default=None, alias="date"),  # still ?date=YYYY-MM-DD
    technician_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return crud.get_appointments(db, day=day, technician_id=technician_id, status=status)


@app.get("/appointments/{appointment_id}", response_model=schemas.AppointmentOut)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    return _or_404(crud.get_appointment(db, appointment_id), "Appointment")


@app.put("/appointments/{appointment_id}", response_model=schemas.AppointmentOut)
def update_appointment(
    appointment_id: int,
    appointment: schemas.AppointmentUpdate,
    db: Session = Depends(get_db),
):
    return _or_404(crud.update_appointment(db, appointment_id, appointment), "Appointment")


@app.delete("/appointments/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    _or_404(crud.delete_appointment(db, appointment_id), "Appointment")
    return {"message": "Appointment deleted"}


# ----------------------------
# Inventory
# ----------------------------
@app.post("/inventory", response_model=schemas.InventoryItemOut)
def create_inventory_item(payload: schemas.InventoryItemCreate, db: Session = Depends(get_db)):
    return crud.create_inventory_item(db, payload)


@app.get("/inventory", response_model=list[schemas.InventoryItemOut])
def get_inventory_items(db: Session = Depends(get_db)):
    return crud.get_inventory_items(db)


@app.get("/inventory/summary")
def get_inventory_summary(db: Session = Depends(get_db)):
    return crud.get_inventory_summary(db)


@app.get("/inventory/{item_id}", response_model=schemas.InventoryItemOut)
def get_inventory_item(item_id: int, db: Session = Depends(get_db)):
    return _or_404(crud.get_inventory_item(db, item_id), "Inventory item")


@app.put("/inventory/{item_id}", response_model=schemas.InventoryItemOut)
def update_inventory_item(item_id: int, payload: schemas.InventoryItemUpdate, db: Session = Depends(get_db)):
    return _or_404(crud.update_inventory_item(db, item_id, payload), "Inventory item")


@app.delete("/inventory/{item_id}")
def delete_inventory_item(item_id: int, db: Session = Depends(get_db)):
    _or_404(crud.delete_inventory_item(db, item_id), "Inventory item")
    return {"message": "Inventory item deleted"}


# ----------------------------
# Checkout
# ----------------------------
@app.post("/checkouts", response_model=schemas.CheckoutOut)
def create_checkout(payload: schemas.CheckoutCreate, db: Session = Depends(get_db)):
    return crud.create_checkout(db, payload)


@app.get("/checkouts", response_model=list[schemas.CheckoutOut])
def get_checkouts(db: Session = Depends(get_db)):
    return crud.get_checkouts(db)


@app.get("/checkouts/{checkout_id}", response_model=schemas.CheckoutOut)
def get_checkout(checkout_id: int, db: Session = Depends(get_db)):
    return _or_404(crud.get_checkout(db, checkout_id), "Checkout")


@app.delete("/checkouts/{checkout_id}")
def delete_checkout(checkout_id: int, db: Session = Depends(get_db)):
    _or_404(crud.delete_checkout(db, checkout_id), "Checkout")
    return {"message": "Checkout deleted"}


# ----------------------------
# Income reports
# ----------------------------
@app.get("/income/tech", response_model=schemas.TechIncomeReport)
def get_tech_income(
    report_date: date = Query(alias="date"),
    technician_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return crud.get_tech_income_report(db, report_date, technician_id=technician_id)


@app.get("/income/salon", response_model=schemas.SalonIncomeReport)
def get_salon_income(report_date: date = Query(alias="date"), db: Session = Depends(get_db)):
    return crud.get_salon_income_report(db, report_date)


# ----------------------------
# Technician turns / dispatch
# ----------------------------
@app.post("/turns", response_model=schemas.TurnOut)
def create_turn(turn: schemas.TurnCreate, db: Session = Depends(get_db)):
    crud.ensure_technician_active(_or_404(crud.get_technician(db, turn.technician_id), "Technician"))
    return crud.create_turn(db, turn)


@app.get("/turns", response_model=list[schemas.TurnOut])
def get_turns(db: Session = Depends(get_db)):
    return crud.get_turns(db)


@app.get("/turns/today", response_model=list[schemas.TurnOut])
def get_today_turns(db: Session = Depends(get_db)):
    return crud.get_today_turns(db)


@app.post("/turns/assign-next", response_model=schemas.TurnOut)
def assign_next_turn(payload: schemas.AssignTurnRequest, db: Session = Depends(get_db)):
    crud.ensure_technician_active(_or_404(crud.get_technician(db, payload.technician_id), "Technician"))
    return crud.assign_next_turn(db, payload)


@app.post("/turns/assign-auto", response_model=schemas.TurnOut)
def assign_turn_auto(payload: schemas.AutoAssignTurnRequest, db: Session = Depends(get_db)):
    return crud.assign_turn_auto(db, payload)


@app.post("/turns/assign-preferred", response_model=schemas.TurnOut)
def assign_turn_preferred(payload: schemas.AssignPreferredTurnRequest, db: Session = Depends(get_db)):
    return crud.assign_turn_preferred(db, payload)


@app.put("/turns/{turn_id}/reassign", response_model=schemas.TurnOut)
def reassign_turn(turn_id: int, payload: schemas.ReassignTurnRequest, db: Session = Depends(get_db)):
    return _or_404(crud.reassign_turn(db, turn_id, payload), "Turn")


@app.put("/turns/{turn_id}/start", response_model=schemas.TurnOut)
def start_turn_service(turn_id: int, payload: schemas.TurnStartRequest, db: Session = Depends(get_db)):
    return _or_404(crud.start_turn_service(db, turn_id, payload), "Turn")


@app.put("/turns/{turn_id}/complete", response_model=schemas.TurnOut)
def complete_turn_service(turn_id: int, payload: schemas.TurnCompleteRequest, db: Session = Depends(get_db)):
    return _or_404(crud.complete_turn_service(db, turn_id, payload), "Turn")


@app.put("/turns/{turn_id}/status", response_model=schemas.TurnOut)
def update_turn_status(turn_id: int, payload: schemas.TurnStatusUpdate, db: Session = Depends(get_db)):
    return _or_404(crud.update_turn_status(db, turn_id, payload.status), "Turn")