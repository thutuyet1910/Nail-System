import logging
import os
from datetime import date, datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import crud
import booking_service
import checkin_service
import models
import schemas
import auth_service
import notification_service
import voice_foundation
from realtime_bridge import run_media_bridge
from twilio_voice import apply_status, build_stream_twiml, validate_called_number, validated_twilio_form
from voice_config import VoiceConfig, VoiceConfigurationError
from customer_gateway import CustomerGatewayError, HttpCustomerGateway
from phone_normalization import normalize_us_phone
from booking_migrations import upgrade_booking_schema
from database import SessionLocal, engine, get_db

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

with SessionLocal() as startup_db:
    upgrade_booking_schema(startup_db)
    auth_service.ensure_owner_credential(startup_db)


# ----------------------------
# App setup
# ----------------------------
app = FastAPI(title="Nail Salon Backend", version="0.5.0")

# "*" keeps local development easy. In production set 
# ALLOWED_ORIGINS="http://192.168.1.50:5500,https://manager.mysalon.com"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


PUBLIC_OWNER_READS = {"/", "/salon", "/business-hours", "/services", "/availability"}
PUBLIC_TWILIO_HTTP = {"/voice/twilio/incoming", "/voice/twilio/status"}


@app.middleware("http")
async def owner_authorization_boundary(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    if request.method == "OPTIONS" or path.startswith("/auth/") or path in PUBLIC_TWILIO_HTTP or (request.method == "GET" and path in PUBLIC_OWNER_READS):
        return await call_next(request)
    db = SessionLocal()
    try:
        auth_service.authenticate_request(request, db, require_csrf=request.method not in {"GET", "HEAD"})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    finally:
        db.close()
    return await call_next(request)


@app.exception_handler(crud.BusinessRuleError)
async def business_rule_handler(request, exc: crud.BusinessRuleError):
    """Every salon-rule violation raised in crud.py becomes a clean HTTP 400."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(booking_service.BookingRuleError)
async def booking_rule_handler(request, exc: booking_service.BookingRuleError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(booking_service.IdempotencyConflictError)
async def idempotency_conflict_handler(request, exc: booking_service.IdempotencyConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(notification_service.NotificationRuleError)
async def notification_rule_handler(request, exc: notification_service.NotificationRuleError):
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


def get_customer_gateway():
    return HttpCustomerGateway()


@app.post("/voice/twilio/incoming")
async def twilio_incoming(request: Request, db: Session = Depends(get_db)):
    config = VoiceConfig.from_env()
    form = await validated_twilio_form(request, config)
    try:
        config.require_media()
    except VoiceConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    validate_called_number(form.get("To", ""), config)
    if not form.get("CallSid"):
        raise HTTPException(status_code=400, detail="Malformed incoming call")
    # A missing/anonymous/unsupported caller ID is a normal telephony condition, not an error:
    # the call proceeds as an unverified Level-0 call with no trusted caller phone.
    call, _created = voice_foundation.get_or_create_provider_call(
        db, provider_call_sid=form["CallSid"], caller_phone=form.get("From"), called_phone=form["To"]
    )
    token = voice_foundation.issue_stream_token(db, call, config.stream_token_ttl_seconds)
    return Response(content=build_stream_twiml(config, call, token), media_type="application/xml")


@app.post("/voice/twilio/status")
async def twilio_status(request: Request, db: Session = Depends(get_db)):
    config = VoiceConfig.from_env()
    form = await validated_twilio_form(request, config)
    apply_status(db, form)
    return Response(status_code=204)


@app.websocket("/voice/twilio/media")
async def twilio_media(websocket: WebSocket):
    await run_media_bridge(
        websocket, config=VoiceConfig.from_env(), db_factory=SessionLocal,
        gateway=get_customer_gateway(),
    )


@app.post("/auth/login", response_model=schemas.OwnerSessionOut)
def owner_login(payload: schemas.OwnerLoginRequest, request: Request):
    db = SessionLocal()
    try:
        client_key = request.client.host if request.client else "unknown"
        session_token, csrf_token, expires_at = auth_service.login(db, payload.password, client_key)
    finally:
        db.close()
    response = JSONResponse({"authenticated": True, "expires_at": expires_at.isoformat()})
    auth_service.set_session_cookies(response, session_token, csrf_token, expires_at)
    return response


@app.get("/auth/session", response_model=schemas.OwnerSessionOut)
def owner_session(request: Request):
    db = SessionLocal()
    try:
        try:
            session = auth_service.authenticate_request(request, db)
            return {"authenticated": True, "expires_at": session.expires_at}
        except HTTPException:
            return {"authenticated": False, "expires_at": None}
    finally:
        db.close()


@app.post("/auth/logout")
def owner_logout(request: Request):
    db = SessionLocal()
    try:
        auth_service.authenticate_request(request, db, require_csrf=True)
        auth_service.logout(db, request)
    finally:
        db.close()
    response = JSONResponse({"message": "Logged out"})
    auth_service.clear_session_cookies(response)
    return response


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
@app.get("/salon", response_model=schemas.SalonSettingsOut)
def get_salon(db: Session = Depends(get_db)):
    return booking_service.get_salon_settings(db)


@app.get("/business-hours", response_model=list[schemas.BusinessHourOut])
def get_business_hours(db: Session = Depends(get_db)):
    return db.query(models.BusinessHour).order_by(models.BusinessHour.day_of_week).all()


@app.get("/services", response_model=list[schemas.BookingServiceOut])
def get_booking_services(db: Session = Depends(get_db)):
    return booking_service.get_active_services(db)


@app.get("/availability", response_model=list[schemas.AvailabilitySlot])
def get_availability(
    day: date = Query(alias="date"),
    service_ids: list[int] = Query(),
    technician_id: Optional[int] = None,
    people_count: int = 1,
    db: Session = Depends(get_db),
):
    return booking_service.generate_available_slots(
        db, day, service_ids, technician_id=technician_id, people_count=people_count
    )


@app.post("/appointments", response_model=schemas.AppointmentOut)
def create_appointment(appointment: schemas.AppointmentCreate, db: Session = Depends(get_db)):
    return booking_service.create_booking(db, appointment)


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
    _or_404(crud.get_appointment(db, appointment_id), "Appointment")
    service_ids = appointment.service_ids
    if not service_ids:
        service_ids = booking_service.resolve_service_ids_from_legacy_names(
            db, appointment.service_category or appointment.service_name
        )
    payload = schemas.AppointmentReschedule(
        appointment_time=appointment.appointment_time,
        service_ids=service_ids,
        technician_id=appointment.technician_id,
        preferred_technician_id=appointment.preferred_technician_id,
        people_count=appointment.people_count,
        customer_name=appointment.customer_name,
        customer_phone=appointment.customer_phone,
        special_requests=appointment.special_requests,
        allergies=appointment.allergies,
        note=appointment.note,
        idempotency_key=appointment.idempotency_key,
    )
    return _or_404(booking_service.reschedule_booking(db, appointment_id, payload), "Appointment")


@app.post("/appointments/{appointment_id}/reschedule", response_model=schemas.AppointmentOut)
def reschedule_appointment(
    appointment_id: int,
    payload: schemas.AppointmentReschedule,
    db: Session = Depends(get_db),
):
    return _or_404(booking_service.reschedule_booking(db, appointment_id, payload), "Appointment")


@app.post("/appointments/{appointment_id}/cancel", response_model=schemas.AppointmentOut)
def cancel_appointment(
    appointment_id: int,
    payload: schemas.AppointmentCancel,
    db: Session = Depends(get_db),
):
    return _or_404(booking_service.cancel_booking(db, appointment_id, payload), "Appointment")


@app.post("/appointments/{appointment_id}/check-in", response_model=schemas.AppointmentOut)
def check_in_appointment(appointment_id: int, db: Session = Depends(get_db)):
    return _or_404(crud.mark_appointment_checked_in(db, appointment_id), "Appointment")


@app.post("/checkins/match", response_model=schemas.CheckinMatchOut)
def match_checkin(payload: schemas.CheckinMatchRequest, db: Session = Depends(get_db)):
    result = checkin_service.match_checkin_to_appointment(
        db,
        customer_phone=payload.customer_phone,
        customer_name=payload.customer_name,
        checked_in_at=payload.checked_in_at,
    )
    return {
        "outcome": result.outcome,
        "appointment": result.appointment,
        "candidate_ids": list(result.candidate_ids),
        "reason": result.reason,
    }


@app.get("/checkins/today", response_model=schemas.IntegratedCheckinsResponse)
def get_integrated_checkins(
    db: Session = Depends(get_db), gateway=Depends(get_customer_gateway)
):
    try:
        items = gateway.get_today_checkins()
        output = []
        for raw in items:
            required = ("visit_id", "customer_id", "position", "full_name", "phone_number", "checked_in_at")
            if not isinstance(raw, dict) or any(key not in raw for key in required):
                raise CustomerGatewayError("Check-in service returned malformed queue data")
            checked_in_at = datetime.fromisoformat(raw["checked_in_at"]) if isinstance(raw["checked_in_at"], str) else raw["checked_in_at"]
            result = checkin_service.match_checkin_to_appointment(
                db,
                customer_phone=raw.get("phone_e164") or raw["phone_number"],
                customer_name=raw["full_name"],
                checked_in_at=checked_in_at,
            )
            if result.outcome == "ambiguous":
                notification_service.create_notification(
                    db,
                    notification_type="ambiguous_appointment",
                    severity="warning",
                    title="Appointment match needs review",
                    message=f"{raw['full_name']} has multiple possible appointments for today's check-in.",
                    source_type="checkin_visit",
                    source_id=str(raw["visit_id"]),
                    event_key=f"ambiguous-checkin:{raw['visit_id']}",
                    external_customer_id=raw["customer_id"],
                    metadata={"candidate_ids": list(result.candidate_ids), "phone_e164": normalize_us_phone(raw.get("phone_e164") or raw["phone_number"]).e164},
                )
            output.append({
                **raw,
                "phone_e164": normalize_us_phone(raw.get("phone_e164") or raw["phone_number"]).e164,
                "appointment_match": {
                    "outcome": result.outcome,
                    "appointment": result.appointment,
                    "candidate_ids": list(result.candidate_ids),
                    "reason": result.reason,
                },
            })
        return {"checkins": output}
    except CustomerGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/notifications", response_model=list[schemas.NotificationOut])
def get_notifications(
    unread_only: bool = False,
    severity: Optional[str] = None,
    notification_type: Optional[str] = Query(default=None, alias="type"),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return notification_service.list_notifications(
        db, unread_only=unread_only, severity=severity, notification_type=notification_type,
        start=start, end=end, limit=limit,
    )


@app.get("/notifications/unread-count", response_model=schemas.NotificationCountOut)
def get_notification_unread_count(db: Session = Depends(get_db)):
    return {"unread_count": notification_service.unread_count(db)}


@app.post("/notifications/read-all")
def read_all_notifications(db: Session = Depends(get_db)):
    return {"marked_read": notification_service.mark_all_read(db)}


@app.post("/notifications/{notification_id}/read", response_model=schemas.NotificationOut)
def read_notification(notification_id: int, db: Session = Depends(get_db)):
    return _or_404(notification_service.mark_read(db, notification_id), "Notification")


@app.post("/callbacks", response_model=schemas.NotificationOut)
def create_callback_request(payload: schemas.CallbackRequest, db: Session = Depends(get_db)):
    return notification_service.request_owner_callback(db, **payload.model_dump())


@app.delete("/appointments/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    """Administrative cleanup only. Normal cancellation uses POST /cancel."""
    _or_404(crud.delete_appointment(db, appointment_id), "Appointment")
    return {"message": "Appointment deleted"}


@app.post(
    "/technicians/{technician_id}/blocked-times",
    response_model=schemas.TechnicianBlockedTimeOut,
)
def create_technician_blocked_time(
    technician_id: int,
    payload: schemas.TechnicianBlockedTimeCreate,
    db: Session = Depends(get_db),
):
    return booking_service.create_blocked_time(db, technician_id, payload)


@app.get(
    "/technicians/{technician_id}/blocked-times",
    response_model=list[schemas.TechnicianBlockedTimeOut],
)
def get_technician_blocked_times(technician_id: int, db: Session = Depends(get_db)):
    _or_404(crud.get_technician(db, technician_id), "Technician")
    return (
        db.query(models.TechnicianBlockedTime)
        .filter(models.TechnicianBlockedTime.technician_id == technician_id)
        .order_by(models.TechnicianBlockedTime.starts_at_utc)
        .all()
    )


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
