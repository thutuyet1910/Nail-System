"""Voice appointment creation: the model never supplies its own availability.

Flow enforced here (not just in the prompt):
  1. get_available_slots -> the backend records the offer on the call and returns opaque slot_ids.
  2. create_booking(slot_id, customer_name)              -> PREPARE: availability is rechecked and the
     backend returns the summary (service, date, time, technician, name). Nothing is booked.
  3. the caller answers; create_booking(..., caller_confirmation="yes ...") -> COMMIT, allowed only if
       - the same slot/name was prepared earlier on this call,
       - at least one new caller utterance happened after that prepare,
       - the confirmation words are affirmative and not hedged.
  4. booking_service.create_booking does the transactional recheck + idempotent insert.
Only IDs that the backend itself offered on this call can be booked; free-text times are impossible.
"""
import hashlib
import re
import secrets
from datetime import date, datetime

import booking_service
import models
import notification_service
import schemas
import voice_foundation
from phone_normalization import PhoneNormalizationError, normalize_us_phone
from timeutils import as_salon_datetime

VoiceFoundationError = voice_foundation.VoiceFoundationError
MAX_SERVICES_PER_BOOKING = 5
_NAME = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ '.\-])*$", re.UNICODE)
_AFFIRM = re.compile(
    r"\b(yes|yeah|yep|yup|sure|ok|okay|correct|confirm|confirmed|please do|go ahead|book it|sounds good|"
    r"that works|that's right|thats right|perfect|absolutely|definitely)\b", re.I)
_HEDGE = re.compile(
    r"\b(no|nope|not|don't|dont|maybe|wait|hold on|actually|let me think|unsure|i guess|probably|but|"
    r"cancel|change|different|instead)\b", re.I)

SLOT_GONE = ("That time is no longer available. Tell the caller briefly and offer other times by calling "
             "get_available_slots again. Do not say anything was booked.")
NOT_BOOKED = ("The booking could not be completed and nothing was booked. Do not tell the caller it is booked; "
              "apologize briefly and offer another time or request_owner_callback.")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _clean_name(value) -> str:
    name = " ".join(str(value or "").split())
    if len(name) < 2 or len(name) > 60 or not _NAME.match(name):
        raise VoiceFoundationError("A valid customer name is required. Ask the caller to say their name.")
    return name


def _resolve_phone(context, supplied) -> str:
    if context.caller_phone_e164:
        return context.caller_phone_e164  # trusted provider caller ID wins over anything the model says
    if not supplied:
        raise VoiceFoundationError("Caller ID is unavailable. Ask the caller for a callback phone number and pass it as customer_phone.")
    try:
        return normalize_us_phone(str(supplied)).e164
    except (PhoneNormalizationError, ValueError):
        raise VoiceFoundationError("That phone number is not a valid US number. Ask the caller to repeat it.")


def is_explicit_confirmation(text) -> bool:
    text = str(text or "").strip()
    return bool(text) and len(text) <= 120 and bool(_AFFIRM.search(text)) and not _HEDGE.search(text)


# ---------------------------------------------------------------- offers (get_available_slots)
def _resolve_technician(db, technician_id, technician_name) -> int | None:
    if technician_id is not None:
        return int(technician_id)
    wanted = " ".join(str(technician_name or "").split()).lower()
    if not wanted:
        return None
    matches = [t for t in db.query(models.Technician).filter(models.Technician.is_active.is_(True)).all()
               if t.full_name.strip().lower() == wanted or t.full_name.strip().lower().split(" ")[0] == wanted]
    if len(matches) != 1:
        raise VoiceFoundationError("Could not match exactly one technician by that name. Ask the caller to confirm, or offer any available technician.")
    return matches[0].id


def offer_slots(facade, day: str, service_ids, technician_id=None, technician_name=None) -> list[dict]:
    db, context = facade.db, facade.context
    ids = list(service_ids or [])
    if not ids or len(ids) > MAX_SERVICES_PER_BOOKING or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
        raise VoiceFoundationError("service_ids must be 1 to 5 service ids from list_services.")
    tech_id = _resolve_technician(db, technician_id, technician_name)
    try:
        slots = booking_service.generate_available_slots(db, date.fromisoformat(day), ids, technician_id=tech_id)
    except booking_service.BookingRuleError:
        raise VoiceFoundationError("Those services cannot be scheduled. Check list_services and try again.")
    result = [{
        "start": slot["start"].isoformat(), "end": slot["end"].isoformat(), "timezone": slot["timezone"],
        "total_duration_minutes": slot["total_duration_minutes"],
    } for slot in slots]
    if slots:
        offer_id = secrets.token_hex(4)
        call = db.get(models.VoiceCall, context.call_database_id)
        voice_foundation.append_call_event(
            db, call=call, event_type="booking_lookup", result_status="success", operation_key=f"offer:{offer_id}",
            metadata={"offer_id": offer_id, "service_ids": ids, "technician_id": tech_id,
                      "slots": [item["start"] for item in result]},
        )
        for index, item in enumerate(result):
            item["slot_id"] = f"{offer_id}-{index}"
    return result


def _load_offer(db, call, slot_id: str) -> tuple[dict, str]:
    match = re.fullmatch(r"([0-9a-f]{8})-(\d{1,3})", str(slot_id or ""))
    event = None
    if match:
        event = db.query(models.VoiceCallEvent).filter(
            models.VoiceCallEvent.call_id == call.id,
            models.VoiceCallEvent.operation_key == f"offer:{match.group(1)}",
        ).first()
    index = int(match.group(2)) if match else -1
    meta = event.metadata_json if event else None
    if not meta or not (0 <= index < len(meta["slots"])):
        raise VoiceFoundationError("Unknown slot_id. Use a slot_id exactly as returned by get_available_slots in this call.")
    return meta, meta["slots"][index]


# ---------------------------------------------------------------- create_booking
def _describe(db, service_ids, start_iso, technician_id, name) -> dict:
    settings = booking_service.get_salon_settings(db)
    plan = booking_service.calculate_service_plan(db, service_ids)
    start = as_salon_datetime(datetime.fromisoformat(start_iso), settings.timezone)
    technician = db.get(models.Technician, technician_id) if technician_id else None
    return {
        "service": ", ".join(service.name for service in plan.services),
        "date": start.strftime("%A, %B %d").replace(" 0", " "),
        "time": start.strftime("%I:%M %p").lstrip("0"),
        "technician": technician.full_name if technician else "first available technician",
        "customer_name": name,
        "duration_minutes": plan.total_duration_minutes,
    }


def _booked_result(db, appointment) -> dict:
    settings = booking_service.get_salon_settings(db)
    start = as_salon_datetime(appointment.appointment_time, settings.timezone)
    technician = db.get(models.Technician, appointment.technician_id) if appointment.technician_id else None
    return {
        "status": "booked", "reference": appointment.appointment_code, "service": appointment.service_name,
        "date": start.strftime("%A, %B %d").replace(" 0", " "), "time": start.strftime("%I:%M %p").lstrip("0"),
        "technician": technician.full_name if technician else None, "customer_name": appointment.customer_name,
    }


def create_booking(facade, args: dict) -> dict:
    db, context = facade.db, facade.context
    call = db.get(models.VoiceCall, context.call_database_id)
    slot_id = str(args.get("slot_id") or "")
    name = _clean_name(args.get("customer_name"))
    phone = _resolve_phone(context, args.get("customer_phone"))
    offer, start_iso = _load_offer(db, call, slot_id)
    service_ids, technician_id = offer["service_ids"], offer.get("technician_id")
    name_hash = _hash(name.lower())

    already = db.query(models.VoiceCallEvent).filter(
        models.VoiceCallEvent.call_id == call.id, models.VoiceCallEvent.operation_key == f"voice-booking:{slot_id}"
    ).first()
    if already:  # duplicate / retried tool call: same logical booking, same result, never a second row
        appointment = db.get(models.Appointment, int(already.related_entity_id))
        if appointment is None or _hash(appointment.customer_name.lower()) != name_hash:
            raise VoiceFoundationError("This slot was already booked on this call under different details. Do not change it; request_owner_callback.")
        return _booked_result(db, appointment)
    if call.appointment_id:
        raise VoiceFoundationError("An appointment was already booked on this call. Use request_owner_callback for anything else.")

    confirmation = args.get("caller_confirmation")
    turns = getattr(facade, "caller_turns", None)
    if not confirmation:
        # PREPARE: recheck availability now so the caller is never read a summary for a dead slot.
        try:
            _, _, available = booking_service.available_technicians_for_interval(
                db, service_ids, datetime.fromisoformat(start_iso), technician_id)
            summary = _describe(db, service_ids, start_iso, technician_id, name)
        except booking_service.BookingRuleError:
            db.rollback()
            raise VoiceFoundationError(SLOT_GONE)
        if not available:
            raise VoiceFoundationError(SLOT_GONE)
        voice_foundation.append_call_event(
            db, call=call, event_type="booking_lookup", result_status="pending",
            operation_key=f"prepare:{slot_id}:{name_hash}:{turns}",
            metadata={"stage": "prepare", "slot_id": slot_id, "name_hash": name_hash, "caller_turns": turns},
        )
        return {
            "status": "confirmation_required", "summary": summary,
            "instruction": ("Nothing is booked yet. Read this summary to the caller and ask them to confirm. Only after "
                            "they clearly say yes, call create_booking again with the same slot_id and customer_name, "
                            "and caller_confirmation set to their words."),
        }

    # COMMIT guardrails
    if not isinstance(turns, int):
        raise VoiceFoundationError("Booking confirmation cannot be verified right now. Use request_owner_callback.")
    prepared = [
        event.metadata_json["caller_turns"] for event in db.query(models.VoiceCallEvent).filter(
            models.VoiceCallEvent.call_id == call.id, models.VoiceCallEvent.event_type == "booking_lookup",
            models.VoiceCallEvent.result_status == "pending")
        if event.metadata_json and event.metadata_json.get("slot_id") == slot_id
        and event.metadata_json.get("name_hash") == name_hash and isinstance(event.metadata_json.get("caller_turns"), int)
    ]
    if not prepared:
        raise VoiceFoundationError("Read the booking summary to the caller first: call create_booking without caller_confirmation, then ask the caller to confirm.")
    if turns <= max(prepared):
        raise VoiceFoundationError("Wait for the caller to answer the summary before confirming. Do not confirm on their behalf.")
    if not is_explicit_confirmation(confirmation):
        raise VoiceFoundationError("That is not a clear yes. Ask the caller directly whether to book it. Do not book on silence, maybe, or a change of topic.")

    try:
        appointment = booking_service.create_booking(db, schemas.AppointmentCreate(
            customer_name=name, customer_phone=phone, service_category="Phone booking",
            appointment_time=datetime.fromisoformat(start_iso), service_ids=service_ids,
            technician_id=technician_id, customer_type="new", note="Booked by the AI phone receptionist",
            idempotency_key=f"voice:{call.call_id}:{slot_id}"[:200],
        ))
    except booking_service.IdempotencyConflictError:
        db.rollback()
        raise VoiceFoundationError("This booking conflicts with an earlier request on this call. Do not retry; use request_owner_callback.")
    except booking_service.BookingRuleError:
        db.rollback()
        raise VoiceFoundationError(SLOT_GONE)
    except Exception:
        db.rollback()
        raise VoiceFoundationError(NOT_BOOKED)

    call = db.get(models.VoiceCall, context.call_database_id)
    voice_foundation.update_call_state(db, call.id, call.call_state, appointment_id=appointment.id, intent="booking", outcome="booked")
    voice_foundation.append_call_event(
        db, call=call, event_type="appointment_created", result_status="success", operation_key=f"voice-booking:{slot_id}",
        related_entity_type="appointment", related_entity_id=str(appointment.id),
    )
    notification_service.create_notification(
        db, notification_type="phone_booking", severity="info", title="Appointment booked by phone",
        message=f"{appointment.customer_name}: {appointment.service_name} on {appointment.appointment_time:%b} {appointment.appointment_time.day} at {appointment.appointment_time:%I:%M %p}.".replace(" 0", " "),
        source_type="appointment", source_id=str(appointment.id), event_key=f"phone-booking:{appointment.id}",
        appointment_id=appointment.id,
    )
    return _booked_result(db, appointment)
