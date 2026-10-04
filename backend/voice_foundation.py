import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from phone_normalization import normalize_us_phone
from timeutils import utc_now_naive


CALL_STATES = {"created", "ringing", "connected", "in_progress", "completed", "failed"}
CALL_EVENT_TYPES = {
    "call_created", "provider_connected", "customer_identified", "booking_lookup",
    "appointment_created", "appointment_rescheduled", "appointment_cancelled",
    "owner_callback_requested", "transferred", "failed", "call_completed",
    "stream_started", "stream_stopped", "tool_called", "provider_error",
}
TERMINAL_CALL_STATES = {"completed", "failed"}
RESULT_STATUSES = {"success", "rejected", "failed", "pending"}
_SECRET_FRAGMENTS = ("secret", "token", "password", "authorization", "api_key")


class VoiceFoundationError(ValueError):
    pass


def _safe_metadata(metadata: dict | None) -> dict | None:
    if not metadata:
        return None
    for key in metadata:
        if any(fragment in str(key).lower() for fragment in _SECRET_FRAGMENTS):
            raise VoiceFoundationError("Secret-bearing metadata keys are not allowed")
    return metadata


def trusted_caller_phone(value: str | None) -> str | None:
    """Provider caller ID -> E.164, or None when absent, anonymous, or not a supported US number.

    None is stored as-is: we never invent a phone number, and an unusable caller ID is simply
    "caller ID unavailable" (no customer match, no trusted callback number).
    """
    if not value:
        return None
    try:
        return normalize_us_phone(value).e164
    except ValueError:
        return None


def create_call(db: Session, *, caller_phone: str | None, called_phone: str, call_id: str | None = None) -> models.VoiceCall:
    item = models.VoiceCall(
        call_id=call_id or f"call_{secrets.token_urlsafe(12)}",
        caller_phone_e164=trusted_caller_phone(caller_phone),
        called_phone_e164=normalize_us_phone(called_phone).e164,
        call_state="created", started_at=utc_now_naive(), created_at=utc_now_naive(), updated_at=utc_now_naive(),
    )
    db.add(item)
    db.flush()
    append_call_event(db, call=item, event_type="call_created", result_status="success", commit=False)
    db.commit()
    db.refresh(item)
    return item


def get_or_create_provider_call(
    db: Session, *, provider_call_sid: str, caller_phone: str | None, called_phone: str
) -> tuple[models.VoiceCall, bool]:
    existing = db.query(models.VoiceCall).filter(models.VoiceCall.provider_call_sid == provider_call_sid).first()
    if existing:
        return existing, False
    now = utc_now_naive()
    item = models.VoiceCall(
        call_id=f"call_{secrets.token_urlsafe(12)}", provider_call_sid=provider_call_sid,
        caller_phone_e164=trusted_caller_phone(caller_phone),
        called_phone_e164=normalize_us_phone(called_phone).e164,
        call_state="ringing", started_at=now, created_at=now, updated_at=now,
    )
    db.add(item)
    try:
        db.flush()
        append_call_event(db, call=item, event_type="call_created", result_status="success", commit=False)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(models.VoiceCall).filter(models.VoiceCall.provider_call_sid == provider_call_sid).one()
        return existing, False
    db.refresh(item)
    return item, True


def update_call_state(db: Session, call_id: int, state: str, **fields):
    if state not in CALL_STATES:
        raise VoiceFoundationError("Unsupported call state")
    item = db.get(models.VoiceCall, call_id)
    if not item:
        return None
    if item.call_state in TERMINAL_CALL_STATES and state != item.call_state:
        # A finished call never moves again (late status callbacks, late streams, cleanup races).
        return item
    item.call_state = state
    for name in ("intent", "outcome", "external_customer_id", "appointment_id", "needs_owner_attention", "summary", "error_code"):
        if name in fields:
            setattr(item, name, fields[name])
    if state in {"completed", "failed"} and not item.ended_at:
        item.ended_at = utc_now_naive()
    item.updated_at = utc_now_naive()
    db.commit()
    db.refresh(item)
    return item


def issue_stream_token(db: Session, call: models.VoiceCall, ttl_seconds: int) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(models.VoiceStreamToken(
        call_id=call.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=utc_now_naive() + timedelta(seconds=ttl_seconds),
        created_at=utc_now_naive(),
    ))
    db.commit()
    return raw


def consume_stream_token(
    db: Session, *, raw_token: str, provider_call_sid: str, stream_sid: str
) -> models.VoiceCall | None:
    digest = hashlib.sha256((raw_token or "").encode()).hexdigest()
    token = db.query(models.VoiceStreamToken).filter(models.VoiceStreamToken.token_hash == digest).first()
    now = utc_now_naive()
    if not token or token.expires_at < now:
        return None
    call = db.get(models.VoiceCall, token.call_id)
    if not call or call.provider_call_sid != provider_call_sid:
        return None
    if call.call_state in TERMINAL_CALL_STATES:
        return None  # a late stream must never reopen or reconnect a finished call
    if token.consumed_at:
        return call if token.stream_sid == stream_sid else None
    # Compare-and-set so two simultaneous starts cannot both consume the token.
    try:
        claimed = db.execute(
            update(models.VoiceStreamToken)
            .where(models.VoiceStreamToken.id == token.id, models.VoiceStreamToken.consumed_at.is_(None))
            .values(consumed_at=now, stream_sid=stream_sid)
        ).rowcount
    except IntegrityError:
        db.rollback()
        return None
    if claimed != 1:
        db.rollback()
        db.expire_all()
        winner = db.get(models.VoiceStreamToken, token.id)
        return db.get(models.VoiceCall, winner.call_id) if winner and winner.stream_sid == stream_sid else None
    call.provider_stream_sid = stream_sid
    call.call_state = "connected"
    call.updated_at = now
    db.commit()
    db.refresh(call)
    return call


def append_call_event(
    db: Session, *, call: models.VoiceCall, event_type: str, result_status: str,
    operation_key: str | None = None, related_entity_type: str | None = None,
    related_entity_id: str | None = None, metadata: dict | None = None, commit: bool = True,
) -> models.VoiceCallEvent:
    if event_type not in CALL_EVENT_TYPES or result_status not in RESULT_STATUSES:
        raise VoiceFoundationError("Unsupported call event")
    if operation_key:
        existing = db.query(models.VoiceCallEvent).filter(
            models.VoiceCallEvent.call_id == call.id,
            models.VoiceCallEvent.operation_key == operation_key,
        ).first()
        if existing:
            return existing
    event = models.VoiceCallEvent(
        call_id=call.id, event_type=event_type, occurred_at=utc_now_naive(),
        operation_key=operation_key, related_entity_type=related_entity_type,
        related_entity_id=related_entity_id, result_status=result_status,
        metadata_json=_safe_metadata(metadata),
    )
    db.add(event)
    if commit:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if operation_key:
                return db.query(models.VoiceCallEvent).filter(
                    models.VoiceCallEvent.call_id == call.id,
                    models.VoiceCallEvent.operation_key == operation_key,
                ).one()
            raise
        db.refresh(event)
    else:
        db.flush()
    return event


@dataclass(frozen=True)
class VoiceAuthorizationContext:
    call_database_id: int
    internal_call_id: str
    verification_level: int
    caller_phone_e164: str | None  # trusted provider caller ID only; None when unavailable
    external_customer_id: int | None


class VoiceBookingFacade:
    """Narrow, server-authorized read-only voice boundary (callback is the only write)."""

    def __init__(self, db: Session, context: VoiceAuthorizationContext):
        if context.verification_level not in (0, 1, 2):
            raise VoiceFoundationError("Invalid verification level")
        call = db.get(models.VoiceCall, context.call_database_id)
        if not call or call.call_id != context.internal_call_id or call.caller_phone_e164 != context.caller_phone_e164:
            raise VoiceFoundationError("Voice authorization context is not backed by a call record")
        self.db = db
        self.context = context

    def require_level(self, minimum: int) -> None:
        if self.context.verification_level < minimum:
            raise VoiceFoundationError("Caller verification level is insufficient")

    def validate_operation_key(self, operation_key: str) -> str:
        value = (operation_key or "").strip()
        if not value or len(value) > 200:
            raise VoiceFoundationError("A valid idempotency key is required")
        return value

    def get_salon_info(self) -> dict:
        import booking_service
        settings = booking_service.get_salon_settings(self.db)
        hours = self.db.query(models.BusinessHour).order_by(models.BusinessHour.day_of_week).all()
        day_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        return {
            "salon_name": settings.salon_name, "business_phone": settings.business_phone,
            "address": ", ".join(filter(None, [settings.address_line1, settings.address_line2, settings.city, settings.state, settings.postal_code])) or None,
            "timezone": settings.timezone,
            "business_hours": [{"day": day_names[h.day_of_week], "closed": h.is_closed,
                                "opens_at": h.opens_at.isoformat(timespec="minutes") if h.opens_at else None,
                                "closes_at": h.closes_at.isoformat(timespec="minutes") if h.closes_at else None} for h in hours],
        }

    def list_services(self) -> list[dict]:
        import booking_service
        return [self._public_service(s) for s in booking_service.get_active_services(self.db)]

    def get_service_details(self, service_id: int) -> dict | None:
        service = self.db.query(models.BookingService).filter(
            models.BookingService.id == int(service_id), models.BookingService.is_active.is_(True)
        ).first()
        return self._public_service(service) if service else None

    @staticmethod
    def _public_service(service: models.BookingService) -> dict:
        return {"id": service.id, "name": service.name, "category": service.category,
                "description": service.description, "duration_minutes": service.duration_minutes,
                "price": float(service.price) if service.price is not None else None}

    def get_available_slots(self, day: str, service_ids: list[int], technician_id: int | None = None) -> list[dict]:
        import booking_service
        parsed_day = date.fromisoformat(day)
        slots = booking_service.generate_available_slots(self.db, parsed_day, service_ids, technician_id=technician_id)
        return [{
            "start": slot["start"].isoformat(), "end": slot["end"].isoformat(),
            "timezone": slot["timezone"], "total_duration_minutes": slot["total_duration_minutes"],
        } for slot in slots]

    def identify_customer_candidate(self, gateway) -> dict:
        """Level-1 candidate match. Deliberately returns only whether caller ID matched a customer:
        caller ID is spoofable, so no stored name or any other customer detail is disclosed."""
        phone = self.context.caller_phone_e164
        if not phone:
            return {"matched": False}
        customer = gateway.find_customer_by_phone(phone)
        if not customer:
            return {"matched": False}
        call = self.db.get(models.VoiceCall, self.context.call_database_id)
        call.external_customer_id = int(customer["id"])
        self.db.commit()
        return {"matched": True}

    def request_owner_callback(
        self, *, category: str, urgency: str, summary: str, callback_phone: str | None = None
    ) -> dict:
        """The only voice mutation. At most one owner callback per call: the server, not the model,
        owns the deduplication, so repeated tool calls (any arguments) return the same result."""
        import notification_service
        if urgency not in ("normal", "urgent"):
            raise VoiceFoundationError("Urgency must be 'normal' or 'urgent'")
        text = (summary or "").strip()[:500]
        if not text:
            raise VoiceFoundationError("A short callback summary is required")
        trusted = self.context.caller_phone_e164
        if trusted:
            phone, phone_trusted = trusted, True
        else:
            if not callback_phone:
                raise VoiceFoundationError(
                    "Caller ID is unavailable. Ask the caller for a callback number and call this tool again with callback_phone."
                )
            try:
                phone, phone_trusted = normalize_us_phone(callback_phone).e164, False
            except ValueError:
                raise VoiceFoundationError("The callback number is not a valid US phone number. Ask the caller to repeat it.")
        call = self.db.get(models.VoiceCall, self.context.call_database_id)
        already = self.db.query(models.VoiceCallEvent.id).filter(
            models.VoiceCallEvent.call_id == call.id,
            models.VoiceCallEvent.operation_key == "owner-callback",
        ).first()
        if already:
            return {"requested": True}
        item = notification_service.request_owner_callback(
            self.db, caller_phone=phone, category=category, urgency=urgency, summary=text,
            operation_key=f"voice-call:{self.context.internal_call_id}",
            external_customer_id=call.external_customer_id, phone_trusted=phone_trusted,
        )
        call.needs_owner_attention = True
        append_call_event(self.db, call=call, event_type="owner_callback_requested", result_status="success",
                          operation_key="owner-callback", related_entity_type="owner_notification",
                          related_entity_id=str(item.id), metadata={"category": category, "urgency": urgency})
        return {"requested": True}
