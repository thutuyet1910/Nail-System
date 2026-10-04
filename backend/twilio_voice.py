from fastapi import HTTPException, Request
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

import voice_foundation
from phone_normalization import normalize_us_phone
from voice_config import VoiceConfig, VoiceConfigurationError


def external_request_url(request: Request, config: VoiceConfig) -> str:
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{config.public_base_url}{request.url.path}{query}"


async def validated_twilio_form(request: Request, config: VoiceConfig) -> dict:
    try:
        config.require_http()
    except VoiceConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    signature = request.headers.get("X-Twilio-Signature", "")
    form = await request.form()
    if not signature or not RequestValidator(config.twilio_auth_token).validate(
        external_request_url(request, config), form, signature
    ):
        raise HTTPException(status_code=403, detail="Invalid provider signature")
    values = dict(form.multi_items())
    if config.twilio_account_sid and values.get("AccountSid") != config.twilio_account_sid:
        raise HTTPException(status_code=403, detail="Unexpected provider account")
    return values


def validate_called_number(value: str, config: VoiceConfig) -> None:
    try:
        matches = normalize_us_phone(value).e164 == normalize_us_phone(config.twilio_phone_number).e164
    except ValueError:
        matches = False
    if not matches:
        raise HTTPException(status_code=403, detail="Unexpected called number")


def build_stream_twiml(config: VoiceConfig, call, stream_token: str) -> str:
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(
        url=config.websocket_url("/voice/twilio/media"),
        status_callback=config.public_url("/voice/twilio/status"),
        status_callback_method="POST",
    )
    stream.parameter(name="voice_call_id", value=call.call_id)
    stream.parameter(name="stream_token", value=stream_token)
    connect.append(stream)
    response.append(connect)
    return str(response)


TWILIO_STATUS_TO_STATE = {
    "queued": "created", "ringing": "ringing", "in-progress": "in_progress",
    "completed": "completed", "busy": "failed", "no-answer": "failed",
    "failed": "failed", "canceled": "failed",
}
TERMINAL_STATES = {"completed", "failed"}
STATE_RANK = {"created": 0, "ringing": 1, "connected": 2, "in_progress": 3, "completed": 4, "failed": 4}


def apply_status(db, form: dict):
    call = db.query(__import__("models").VoiceCall).filter(
        __import__("models").VoiceCall.provider_call_sid == form.get("CallSid")
    ).first()
    if not call:
        return None
    stream_event = form.get("StreamEvent")
    if stream_event:
        stream_sid = form.get("StreamSid")
        if stream_sid and not call.provider_stream_sid:
            call.provider_stream_sid = stream_sid
            db.commit()
        event_type = {"stream-started": "stream_started", "stream-stopped": "stream_stopped", "stream-error": "failed"}.get(stream_event)
        if not event_type:
            return call
        if stream_event == "stream-error" and call.call_state not in TERMINAL_STATES:
            voice_foundation.update_call_state(db, call.id, "failed", error_code="twilio_stream_error")
        return voice_foundation.append_call_event(
            db, call=call, event_type=event_type,
            result_status="failed" if stream_event == "stream-error" else "success",
            operation_key=f"twilio-stream:{stream_event}:{stream_sid}",
            metadata={"provider_event": stream_event},
        )
    provider_status = form.get("CallStatus")
    target = TWILIO_STATUS_TO_STATE.get(provider_status)
    if not target or call.call_state in TERMINAL_STATES or STATE_RANK[target] < STATE_RANK.get(call.call_state, 0):
        return call
    voice_foundation.update_call_state(db, call.id, target, outcome=provider_status)
    event_type = "call_completed" if target == "completed" else ("failed" if target == "failed" else "provider_connected")
    return voice_foundation.append_call_event(
        db, call=call, event_type=event_type,
        result_status="failed" if target == "failed" else "success",
        operation_key=f"twilio-status:{provider_status}:{form.get('SequenceNumber', '')}",
        metadata={"provider_status": provider_status},
    )
