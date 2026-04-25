from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import crud
import models
import schemas
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Nail Salon Backend", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    return {"message": "Nail Salon Backend is running"}


# ----------------------------
# Technicians
# ----------------------------
@app.post("/technicians", response_model=schemas.TechnicianOut)
def create_technician(technician: schemas.TechnicianCreate, db: Session = Depends(get_db)):
    try:
        return crud.create_technician(db, technician)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/technicians", response_model=List[schemas.TechnicianOut])
def get_technicians(
    search: Optional[str] = None,
    specialty: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = Query(default="name"),
    db: Session = Depends(get_db),
):
    return crud.get_technicians(db, search=search, specialty=specialty, status=status, sort_by=sort_by)


@app.get("/technicians/cards", response_model=List[schemas.TechnicianCardOut])
def get_technician_cards(
    search: Optional[str] = None,
    specialty: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = Query(default="name"),
    db: Session = Depends(get_db),
):
    return crud.get_technician_cards(db, search=search, specialty=specialty, status=status, sort_by=sort_by)


@app.get("/technicians/{technician_id}", response_model=schemas.TechnicianOut)
def get_technician(technician_id: int, db: Session = Depends(get_db)):
    technician = crud.get_technician(db, technician_id)
    if not technician:
        raise HTTPException(status_code=404, detail="Technician not found")
    return technician


@app.put("/technicians/{technician_id}", response_model=schemas.TechnicianOut)
def update_technician(technician_id: int, payload: schemas.TechnicianUpdate, db: Session = Depends(get_db)):
    try:
        updated = crud.update_technician(db, technician_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Technician not found")
    return updated


@app.delete("/technicians/{technician_id}")
def delete_technician(technician_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_technician(db, technician_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Technician not found")
    return {"message": "Technician deleted"}


# ----------------------------
# Appointments
# ----------------------------
@app.post("/appointments", response_model=schemas.AppointmentOut)
def create_appointment(appointment: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    try:
        return crud.create_appointment(db, appointment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/appointments", response_model=List[schemas.AppointmentOut])
def get_appointments(
    date: Optional[str] = None,
    technician_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return crud.get_appointments(db, date=date, technician_id=technician_id, status=status)


@app.get("/appointments/{appointment_id}", response_model=schemas.AppointmentOut)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appointment = crud.get_appointment(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment


@app.put("/appointments/{appointment_id}", response_model=schemas.AppointmentOut)
def update_appointment(
    appointment_id: int,
    appointment: schemas.AppointmentUpdate,
    db: Session = Depends(get_db),
):
    try:
        updated = crud.update_appointment(db, appointment_id, appointment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return updated


@app.delete("/appointments/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_appointment(db, appointment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return {"message": "Appointment deleted"}

# ----------------------------
# Inventory
# ----------------------------
@app.post("/inventory", response_model=schemas.InventoryItemOut)
def create_inventory_item(payload: schemas.InventoryItemCreate, db: Session = Depends(get_db)):
    return crud.create_inventory_item(db, payload)


@app.get("/inventory", response_model=List[schemas.InventoryItemOut])
def get_inventory_items(db: Session = Depends(get_db)):
    return crud.get_inventory_items(db)


@app.get("/inventory/summary")
def get_inventory_summary(db: Session = Depends(get_db)):
    return crud.get_inventory_summary(db)


@app.get("/inventory/{item_id}", response_model=schemas.InventoryItemOut)
def get_inventory_item(item_id: int, db: Session = Depends(get_db)):
    item = crud.get_inventory_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item


@app.put("/inventory/{item_id}", response_model=schemas.InventoryItemOut)
def update_inventory_item(item_id: int, payload: schemas.InventoryItemUpdate, db: Session = Depends(get_db)):
    item = crud.update_inventory_item(db, item_id, payload)
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item


@app.delete("/inventory/{item_id}")
def delete_inventory_item(item_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_inventory_item(db, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return {"message": "Inventory item deleted"}


# ----------------------------
# Checkout
# ----------------------------
@app.post("/checkouts", response_model=schemas.CheckoutOut)
def create_checkout(payload: schemas.CheckoutCreate, db: Session = Depends(get_db)):
    try:
        return crud.create_checkout(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/checkouts", response_model=List[schemas.CheckoutOut])
def get_checkouts(db: Session = Depends(get_db)):
    return crud.get_checkouts(db)


@app.get("/checkouts/{checkout_id}", response_model=schemas.CheckoutOut)
def get_checkout(checkout_id: int, db: Session = Depends(get_db)):
    checkout = crud.get_checkout(db, checkout_id)
    if not checkout:
        raise HTTPException(status_code=404, detail="Checkout not found")
    return checkout


@app.delete("/checkouts/{checkout_id}")
def delete_checkout(checkout_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_checkout(db, checkout_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Checkout not found")
    return {"message": "Checkout deleted"}

# ----------------------------
# Technician Turns / Dispatch
# ----------------------------
@app.post("/turns", response_model=schemas.TurnOut)
def create_turn(turn: schemas.TurnCreate, db: Session = Depends(get_db)):
    technician = crud.get_technician(db, turn.technician_id)
    if not technician:
        raise HTTPException(status_code=404, detail="Technician not found")
    return crud.create_turn(db, turn)


@app.get("/turns", response_model=List[schemas.TurnOut])
def get_turns(db: Session = Depends(get_db)):
    return crud.get_turns(db)


@app.get("/turns/today", response_model=List[schemas.TurnOut])
def get_today_turns(db: Session = Depends(get_db)):
    return crud.get_today_turns(db)


@app.post("/turns/assign-next", response_model=schemas.TurnOut)
def assign_next_turn(payload: schemas.AssignTurnRequest, db: Session = Depends(get_db)):
    technician = crud.get_technician(db, payload.technician_id)
    if not technician:
        raise HTTPException(status_code=404, detail="Technician not found")
    return crud.assign_next_turn(db, payload)


@app.post("/turns/assign-auto", response_model=schemas.TurnOut)
def assign_turn_auto(payload: schemas.AutoAssignTurnRequest, db: Session = Depends(get_db)):
    try:
        return crud.assign_turn_auto(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/turns/assign-preferred", response_model=schemas.TurnOut)
def assign_turn_preferred(payload: schemas.AssignPreferredTurnRequest, db: Session = Depends(get_db)):
    try:
        return crud.assign_turn_preferred(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/turns/{turn_id}/reassign", response_model=schemas.TurnOut)
def reassign_turn(turn_id: int, payload: schemas.ReassignTurnRequest, db: Session = Depends(get_db)):
    try:
        turn = crud.reassign_turn(db, turn_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not turn:
        raise HTTPException(status_code=404, detail="Turn not found")
    return turn


@app.put("/turns/{turn_id}/start", response_model=schemas.TurnOut)
def start_turn_service(turn_id: int, payload: schemas.TurnStartRequest, db: Session = Depends(get_db)):
    turn = crud.start_turn_service(db, turn_id, payload)
    if not turn:
        raise HTTPException(status_code=404, detail="Turn not found")
    return turn


@app.put("/turns/{turn_id}/complete", response_model=schemas.TurnOut)
def complete_turn_service(turn_id: int, payload: schemas.TurnCompleteRequest, db: Session = Depends(get_db)):
    turn = crud.complete_turn_service(db, turn_id, payload)
    if not turn:
        raise HTTPException(status_code=404, detail="Turn not found")
    return turn


@app.put("/turns/{turn_id}/status", response_model=schemas.TurnOut)
def update_turn_status(turn_id: int, payload: schemas.TurnStatusUpdate, db: Session = Depends(get_db)):
    turn = crud.update_turn_status(db, turn_id, payload.status)
    if not turn:
        raise HTTPException(status_code=404, detail="Turn not found")
    return turn

