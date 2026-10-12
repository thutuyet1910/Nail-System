"""
Test suite for the Nail Salon backend (updated for v0.4.0).

Covers: Technicians, Appointments, Turns/Dispatch, Checkout, Inventory, Income Reports,
plus the four fixes:
  1. Fair auto-assign (fewest turns first)
  2. Server-calculated checkout math
  3. Ordered turn statuses
  4. SQLite foreign keys enforced

    pip install pytest httpx
    pytest test_main.py -v
"""

import asyncio
import base64
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

# The app must point at a THROWAWAY database before anything imports `database`.
# (reset_db below drops every table, so it must never touch nail_system.db.)
TEST_DB_FILE = "test_main.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_FILE}"
os.environ["OWNER_BOOTSTRAP_PASSWORD"] = "test-owner-password"
os.environ["CHECKIN_INTERNAL_SERVICE_TOKEN"] = "test-internal-token"
os.environ["VOICE_ENABLED"] = "true"
os.environ["VOICE_ALLOW_REAL_CALLS"] = "true"
os.environ["PUBLIC_BASE_URL"] = "https://voice.test"
os.environ["TWILIO_ACCOUNT_SID"] = "AC11111111111111111111111111111111"
os.environ["TWILIO_AUTH_TOKEN"] = "test-twilio-auth-token"
os.environ["TWILIO_PHONE_NUMBER"] = "+16025559999"
os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
os.environ["OPENAI_REALTIME_MODEL"] = "gpt-realtime-2.1"

from datetime import date, datetime, time, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

import models  # noqa: E402
from booking_migrations import seed_booking_reference_data  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
import main as main_module  # noqa: E402
import auth_service  # noqa: E402
import notification_service  # noqa: E402
import voice_foundation  # noqa: E402
import realtime_bridge  # noqa: E402
import voice_tools  # noqa: E402
from voice_config import VoiceConfig  # noqa: E402
from twilio.request_validator import RequestValidator  # noqa: E402
from customer_gateway import CustomerGatewayError  # noqa: E402
import customer_gateway  # noqa: E402
from phone_normalization import PhoneNormalizationError, normalize_us_phone  # noqa: E402
import booking_service  # noqa: E402
import timeutils  # noqa: E402
from timeutils import as_salon_datetime, utc_now_naive  # noqa: E402

# Safety net: refuse to run (and drop tables) against anything but the test database.
assert TEST_DB_FILE in str(engine.url), (
    f"Tests are pointing at {engine.url}. Another module imported `database` first; "
    "run pytest from the project folder with only this test file."
)

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite.*Decimal")

client = TestClient(app, raise_server_exceptions=True)


# A throwaway route that raises a raw database error, used to test the 409 handler.
@app.get("/__test_integrity_error")
def _raise_integrity_error():
    raise IntegrityError("INSERT ...", {}, Exception("FOREIGN KEY constraint failed"))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_booking_reference_data(db)
    auth_service.ensure_owner_credential(db)
    for hours in db.query(models.BusinessHour).all():
        hours.is_closed = False
        hours.opens_at = time(0, 0)
        hours.closes_at = time(23, 59)
    db.commit()
    db.close()
    client.cookies.clear()
    login = client.post("/auth/login", json={"password": "test-owner-password"})
    assert login.status_code == 200, login.text
    client.headers.update({"X-CSRF-Token": client.cookies.get("owner_csrf")})
    yield


@pytest.fixture(autouse=True)
def booking_clock_is_start_of_today(monkeypatch):
    """Most tests book "today" or a future day. Pin the booking clock to 00:00 of the host date so
    they stay deterministic; TestPastTimeBooking overrides this with explicit clocks."""
    start = datetime.combine(date.today(), time.min)
    monkeypatch.setattr(booking_service, "current_salon_time", lambda tz: as_salon_datetime(start, tz))


@pytest.fixture(scope="session", autouse=True)
def remove_test_db_file():
    yield
    engine.dispose()
    try:
        os.remove(TEST_DB_FILE)
    except OSError:
        pass


# ── Shared helpers ────────────────────────────────────────────────────────────

def make_tech(
    full_name="Mia",
    status="active",
    availability="available today",
    specialties="acrylic, gel",
    employee_id=None,
):
    return client.post("/technicians", json={
        "full_name": full_name,
        "status": status,
        "availability": availability,
        "specialties": specialties,
        "employee_id": employee_id,
        "work_schedule": '{"days":["monday","tuesday","wednesday","thursday","friday","saturday","sunday"],"start_time":"00:00","end_time":"23:59"}',
    })


def make_appointment(
    customer_name="Alice",
    customer_phone="5550000001",
    service_category="Gel Manicure",
    appointment_time=None,
    technician_id=None,
):
    if appointment_time is None:
        appointment_time = datetime.combine(date.today(), time(12, 0)).isoformat()
    if technician_id is None:
        technician_id = make_tech(
            f"Booking Tech {len(client.get('/technicians').json()) + 1}",
            specialties="manicure / pedicure, acrylic, gel, dip powder, builder / hard gel, nail art, nail repair / removal, waxing, facial",
        ).json()["id"]
    payload = {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service_category": service_category,
        "appointment_time": appointment_time,
    }
    payload["technician_id"] = technician_id
    return client.post("/appointments", json=payload)


def make_turn(technician_id, customer_name="Alice", service_name="Acrylic Full Set"):
    """A turn in 'waiting' status (counts as an open turn for that technician)."""
    return client.post("/turns", json={
        "customer_name": customer_name,
        "service_name": service_name,
        "technician_id": technician_id,
        "status": "waiting",
        "source": "checkin",
    })


def give_turn(technician_id, customer_name="Alice", service_name="Acrylic Full Set", complete=True):
    """Assigns a customer to a technician. By default the turn is completed, so the tech is free again."""
    r = client.post("/turns/assign-next", json={
        "customer_name": customer_name,
        "service_name": service_name,
        "technician_id": technician_id,
        "source": "manual",
    })
    assert r.status_code == 200, r.text
    turn = r.json()
    if complete:
        assert client.put(f"/turns/{turn['id']}/complete", json={}).status_code == 200
    return turn


def auto_assign(customer_name="Alice", service_name="Acrylic Full Set", **extra):
    return client.post("/turns/assign-auto", json={
        "customer_name": customer_name,
        "service_name": service_name,
        **extra,
    })


def get_turn_today(turn_id):
    return next(t for t in client.get("/turns/today").json() if t["id"] == turn_id)


def make_checkout(
    customer_name="Alice",
    customer_phone=None,
    service_name="Gel Manicure",
    subtotal=100.0,
    tip_amount=0.0,
    technician_id=None,
    turn_id=None,
    appointment_id=None,
    discount_type="none",
    discount_value=0.0,
    payment_method="cash",
    **extra,
):
    """Sends INPUTS only. Anything in **extra is sent too (used to test forged numbers)."""
    payload = {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service_name": service_name,
        "subtotal": subtotal,
        "tip_amount": tip_amount,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "payment_method": payment_method,
    }
    if technician_id:
        payload["technician_id"] = technician_id
    if turn_id:
        payload["turn_id"] = turn_id
    if appointment_id:
        payload["appointment_id"] = appointment_id
    payload.update(extra)
    return client.post("/checkouts", json=payload)


def make_inventory(
    item_name="Acrylic Powder",
    category="Supplies",
    quantity=10,
    unit_price=15.0,
    purchase_date=None,
    low_stock_level=3,
):
    return client.post("/inventory", json={
        "item_name": item_name,
        "category": category,
        "quantity": quantity,
        "unit_price": unit_price,
        "purchase_date": purchase_date or date.today().isoformat(),
        "low_stock_level": low_stock_level,
    })


class TestOwnerAuthenticationAndSecurity:

    def test_valid_and_invalid_login(self):
        separate = TestClient(app)
        assert separate.post("/auth/login", json={"password": "wrong-password"}).status_code == 401
        response = separate.post("/auth/login", json={"password": "test-owner-password"})
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        assert separate.cookies.get("owner_session")
        cookies = response.headers.get_list("set-cookie")
        assert any("HttpOnly" in value and "SameSite=strict" in value for value in cookies)

    def test_login_attempts_are_rate_limited(self):
        auth_service._attempts.clear()
        separate = TestClient(app)
        try:
            for _ in range(auth_service.LOGIN_LIMIT):
                assert separate.post("/auth/login", json={"password": "wrong-password"}).status_code == 401
            assert separate.post("/auth/login", json={"password": "wrong-password"}).status_code == 429
        finally:
            auth_service._attempts.clear()

    def test_anonymous_mutation_rejected_and_authenticated_accepted(self):
        anonymous = TestClient(app)
        payload = {"full_name": "Protected Tech", "status": "active", "availability": "available today"}
        assert anonymous.post("/technicians", json=payload).status_code == 401
        assert client.post("/technicians", json=payload).status_code == 200

    def test_logout_and_expired_session(self):
        separate = TestClient(app)
        assert separate.post("/auth/login", json={"password": "test-owner-password"}).status_code == 200
        csrf = separate.cookies.get("owner_csrf")
        assert separate.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert separate.get("/appointments").status_code == 401

        assert separate.post("/auth/login", json={"password": "test-owner-password"}).status_code == 200
        db = SessionLocal()
        session = db.query(models.OwnerSession).order_by(models.OwnerSession.id.desc()).first()
        session.expires_at = utc_now_naive() - timedelta(seconds=1)
        db.commit()
        db.close()
        assert separate.get("/appointments").status_code == 401

    def test_password_hash_and_secrets_are_not_exposed(self):
        session_payload = client.get("/auth/session").text
        assert "test-owner-password" not in session_payload
        assert "password_hash" not in session_payload
        assert "test-internal-token" not in client.get("/").text

    def test_http_customer_gateway_sends_internal_token(self, monkeypatch):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self):
                return b'{"checkins": []}'

        def fake_urlopen(request, timeout):
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            captured["timeout"] = timeout
            return FakeResponse()

        monkeypatch.setattr(customer_gateway, "urlopen", fake_urlopen)
        gateway = customer_gateway.HttpCustomerGateway("http://checkin.test", timeout_seconds=2.5)
        assert gateway.get_today_checkins() == []
        assert captured["headers"]["x-internal-service-token"] == "test-internal-token"
        assert captured["timeout"] == 2.5


class TestPersistentNotificationsAndCalls:

    def test_notification_lifecycle_and_deduplication(self):
        db = SessionLocal()
        first = notification_service.create_notification(
            db, notification_type="system_issue", severity="warning", title="Test",
            message="A persistent test", source_type="test", event_key="test:event:1",
        )
        second = notification_service.create_notification(
            db, notification_type="system_issue", severity="warning", title="Duplicate",
            message="Duplicate", source_type="test", event_key="test:event:1",
        )
        assert first.id == second.id
        db.close()

        assert client.get("/notifications/unread-count").json()["unread_count"] == 1
        listed = client.get("/notifications?unread_only=true").json()
        assert len(listed) == 1
        assert client.post(f"/notifications/{listed[0]['id']}/read").status_code == 200
        assert client.get("/notifications/unread-count").json()["unread_count"] == 0

        db = SessionLocal()
        notification_service.create_notification(
            db, notification_type="system_issue", severity="info", title="Another",
            message="Another", source_type="test", event_key="test:event:2",
        )
        db.close()
        assert client.post("/notifications/read-all").json()["marked_read"] == 1


def _twilio_post(path, form, signature_override=None):
    url = f"https://voice.test{path}"
    signature = RequestValidator("test-twilio-auth-token").compute_signature(url, form)
    if signature_override is not None:
        signature = signature_override
    return client.post(path, data=form, headers={"X-Twilio-Signature": signature})


class TestReadOnlyVoiceIntegration:
    def incoming_form(self, **changes):
        data = {
            "AccountSid": "AC11111111111111111111111111111111",
            "CallSid": "CA11111111111111111111111111111111",
            "From": "+16025551234", "To": "+16025559999",
        }
        data.update(changes)
        return data

    def test_valid_incoming_signature_returns_connect_stream_and_is_idempotent(self):
        first = _twilio_post("/voice/twilio/incoming", self.incoming_form())
        second = _twilio_post("/voice/twilio/incoming", self.incoming_form())
        assert first.status_code == second.status_code == 200
        assert "<Connect>" in first.text and "<Stream" in first.text
        assert "wss://voice.test/voice/twilio/media" in first.text
        assert "test-openai-api-key" not in first.text
        assert "test-twilio-auth-token" not in first.text
        db = SessionLocal()
        assert db.query(models.VoiceCall).count() == 1
        assert db.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.event_type == "call_created").count() == 1
        db.close()

    @pytest.mark.parametrize("signature", [None, "not-valid"])
    def test_missing_or_invalid_signature_is_rejected(self, signature):
        headers = {} if signature is None else {"X-Twilio-Signature": signature}
        assert client.post("/voice/twilio/incoming", data=self.incoming_form(), headers=headers).status_code == 403

    def test_unexpected_called_number_is_rejected(self):
        assert _twilio_post("/voice/twilio/incoming", self.incoming_form(To="+16025550000")).status_code == 403

    def test_public_deployment_guard_defaults_to_rejection(self, monkeypatch):
        monkeypatch.setenv("VOICE_ENABLED", "false")
        assert _twilio_post("/voice/twilio/incoming", self.incoming_form()).status_code == 503

    def test_status_callback_is_signed_and_terminal_state_is_not_reversed(self):
        _twilio_post("/voice/twilio/incoming", self.incoming_form())
        completed = {"AccountSid": self.incoming_form()["AccountSid"], "CallSid": self.incoming_form()["CallSid"], "CallStatus": "completed", "SequenceNumber": "1"}
        assert _twilio_post("/voice/twilio/status", completed).status_code == 204
        assert _twilio_post("/voice/twilio/status", completed).status_code == 204
        stale = {**completed, "CallStatus": "ringing", "SequenceNumber": "0"}
        assert _twilio_post("/voice/twilio/status", stale).status_code == 204
        db = SessionLocal()
        call = db.query(models.VoiceCall).one()
        assert call.call_state == "completed"
        assert db.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.event_type == "call_completed").count() == 1
        db.close()

    def test_status_callback_rejects_invalid_signature(self):
        form = {"AccountSid": self.incoming_form()["AccountSid"], "CallSid": self.incoming_form()["CallSid"], "CallStatus": "completed"}
        assert client.post("/voice/twilio/status", data=form, headers={"X-Twilio-Signature": "bad"}).status_code == 403

    def test_stream_token_valid_invalid_expired_and_call_bound(self):
        db = SessionLocal()
        call = voice_foundation.get_or_create_provider_call(db, provider_call_sid="CA-one", caller_phone="6025551234", called_phone="6025559999")[0]
        other = voice_foundation.get_or_create_provider_call(db, provider_call_sid="CA-two", caller_phone="6025555678", called_phone="6025559999")[0]
        token = voice_foundation.issue_stream_token(db, call, 120)
        assert voice_foundation.consume_stream_token(db, raw_token="wrong", provider_call_sid="CA-one", stream_sid="MZ-one") is None
        assert voice_foundation.consume_stream_token(db, raw_token=token, provider_call_sid="CA-two", stream_sid="MZ-one") is None
        assert voice_foundation.consume_stream_token(db, raw_token=token, provider_call_sid="CA-one", stream_sid="MZ-one").id == call.id
        assert voice_foundation.consume_stream_token(db, raw_token=token, provider_call_sid="CA-one", stream_sid="MZ-other") is None
        expired = voice_foundation.issue_stream_token(db, other, 120)
        row = db.query(models.VoiceStreamToken).filter(models.VoiceStreamToken.token_hash == __import__("hashlib").sha256(expired.encode()).hexdigest()).one()
        row.expires_at = utc_now_naive() - timedelta(seconds=1)
        db.commit()
        assert voice_foundation.consume_stream_token(db, raw_token=expired, provider_call_sid="CA-two", stream_sid="MZ-two") is None
        db.close()

    def test_realtime_session_has_current_audio_shape_and_only_allowlisted_tools(self):
        payload = realtime_bridge.build_session_update(VoiceConfig.from_env(), "Test Nails", "America/Phoenix")
        session = payload["session"]
        assert session["model"] == "gpt-realtime-2.1"
        assert session["audio"]["input"]["format"] == {"type": "audio/pcmu"}
        assert session["audio"]["output"]["format"] == {"type": "audio/pcmu"}
        assert "AI phone receptionist" in session["instructions"]
        instructions = session["instructions"]
        assert "never repeat it" in instructions and "asks whether they are talking to a human or an AI" in instructions
        assert "Do not end ordinary answers" in instructions
        for trigger in ("asks for the owner or a human", "asks for a callback", "rescheduling, cancelling or changing an existing appointment", "genuine error"):
            assert trigger in instructions
        names = {tool["name"] for tool in session["tools"]}
        assert names == {"get_salon_info", "list_services", "get_service_details", "get_available_slots", "identify_customer_candidate", "request_owner_callback", "create_booking"}
        assert not names.intersection({"reschedule_booking", "cancel_booking", "update_customer"})

    def test_read_only_tools_prices_privacy_trusted_phone_and_callback_idempotency(self):
        db = SessionLocal()
        service = db.query(models.BookingService).first()
        service.price = None
        db.commit()
        call = voice_foundation.create_call(db, caller_phone="6025551234", called_phone="6025559999", call_id="voice-tools")
        context = voice_foundation.VoiceAuthorizationContext(call.id, call.call_id, 0, call.caller_phone_e164, None)
        facade = voice_foundation.VoiceBookingFacade(db, context)

        class FakeGateway:
            def __init__(self): self.phone = None
            def find_customer_by_phone(self, phone):
                self.phone = phone
                return {"id": 42, "full_name": "Safe Name", "email": "must-not-return@example.com", "date_of_birth": "1990-01-01", "referral_code": "NOPE"}

        gateway = FakeGateway()
        assert facade.get_salon_info()["timezone"] == "America/Phoenix"
        assert any(item["price"] is None for item in facade.list_services())
        candidate = voice_tools.dispatch_voice_tool(facade, gateway, "identify_customer_candidate", {"phone": "+19999999999"})
        assert gateway.phone == "+16025551234"
        assert candidate == {"matched": True}  # caller ID is spoofable: no stored name is disclosed
        assert "email" not in candidate and "date_of_birth" not in candidate and "referral_code" not in candidate
        args = {"category": "booking", "urgency": "normal", "summary": "Please call about booking"}
        first = voice_tools.dispatch_voice_tool(facade, gateway, "request_owner_callback", args)
        second = voice_tools.dispatch_voice_tool(facade, gateway, "request_owner_callback", args)
        assert first == second == {"requested": True}
        assert db.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "callback_request").count() == 1
        assert db.query(models.Appointment).count() == 0
        db.close()

    def test_available_slots_are_authoritative_and_unknown_tool_is_blocked(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        make_tech("Voice Availability", specialties="manicure / pedicure, gel")
        db = SessionLocal()
        call = voice_foundation.create_call(db, caller_phone="6025551234", called_phone="6025559999", call_id="voice-slots")
        facade = voice_foundation.VoiceBookingFacade(db, voice_foundation.VoiceAuthorizationContext(call.id, call.call_id, 0, call.caller_phone_e164, None))
        slots = facade.get_available_slots(day.isoformat(), [service_id])
        assert slots and slots[0]["timezone"] == "America/Phoenix"
        with pytest.raises(voice_foundation.VoiceFoundationError):
            voice_tools.dispatch_voice_tool(facade, object(), "create_booking", {})
        db.close()

    def test_media_start_authentication_and_mulaw_forwarding(self):
        db = SessionLocal()
        call = voice_foundation.get_or_create_provider_call(db, provider_call_sid="CA-media", caller_phone="6025551234", called_phone="6025559999")[0]
        token = voice_foundation.issue_stream_token(db, call, 120)

        class FakeTwilio:
            def __init__(self):
                self.incoming = [
                    {"event": "connected", "protocol": "Call", "version": "1.0.0"},
                    {"event": "start", "start": {"accountSid": "AC11111111111111111111111111111111", "callSid": "CA-media", "streamSid": "MZ-media", "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}, "customParameters": {"voice_call_id": call.call_id, "stream_token": token}}},
                    {"event": "start", "start": {}},
                    {"event": "media", "streamSid": "MZ-media", "media": {"payload": base64.b64encode(b"\xff" * 160).decode()}},
                    {"event": "stop", "streamSid": "MZ-media", "stop": {"callSid": "CA-media"}},
                ]
            async def receive_json(self): return self.incoming.pop(0)

        class FakeOpenAI:
            def __init__(self): self.sent = []
            async def send_json(self, value): self.sent.append(value)

        ws, ai = FakeTwilio(), FakeOpenAI()
        state = {"db": db, "config": VoiceConfig.from_env(), "stopped": False, "started": False}
        asyncio.run(realtime_bridge._authenticate_twilio_start(ws, state))
        asyncio.run(realtime_bridge._twilio_to_openai(ws, ai, state))
        assert state["stream_sid"] == "MZ-media" and state["stopped"] is True
        assert ai.sent == [{"type": "input_audio_buffer.append", "audio": base64.b64encode(b"\xff" * 160).decode()}]
        assert db.get(models.VoiceCall, call.id).provider_stream_sid == "MZ-media"
        db.close()

    def test_media_rejects_wrong_call_token_and_malformed_audio(self):
        db = SessionLocal()
        call = voice_foundation.get_or_create_provider_call(db, provider_call_sid="CA-media", caller_phone="6025551234", called_phone="6025559999")[0]
        token = voice_foundation.issue_stream_token(db, call, 120)

        class FakeTwilio:
            def __init__(self, incoming): self.incoming = list(incoming)
            async def receive_json(self): return self.incoming.pop(0)

        wrong = FakeTwilio([{"event": "connected", "protocol": "Call", "version": "1.0.0"}, {"event": "start", "start": {"accountSid": "AC11111111111111111111111111111111", "callSid": "CA-other", "streamSid": "MZ-x", "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}, "customParameters": {"voice_call_id": call.call_id, "stream_token": token}}}])
        with pytest.raises(PermissionError):
            asyncio.run(realtime_bridge._authenticate_twilio_start(wrong, {"db": db, "config": VoiceConfig.from_env()}))

        class FakeOpenAI:
            async def send_json(self, value): pass

        malformed = FakeTwilio([{"event": "media", "streamSid": "MZ-one", "media": {"payload": "not base64!"}}])
        with pytest.raises(ValueError):
            asyncio.run(realtime_bridge._twilio_to_openai(malformed, FakeOpenAI(), {"started": True, "stream_sid": "MZ-one"}))
        db.close()

    def test_openai_audio_and_barge_in_emit_twilio_media_mark_clear_and_truncate(self):
        audio = base64.b64encode(b"\xff" * 800).decode()

        class FakeTwilio:
            def __init__(self): self.sent = []
            async def send_json(self, value): self.sent.append(value)

        class FakeOpenAI:
            def __init__(self):
                self.events = [
                    {"type": "response.output_item.added", "item": {"type": "message", "id": "item-1"}},
                    {"type": "response.output_audio.delta", "delta": audio},
                    {"type": "input_audio_buffer.speech_started"},
                ]
                self.sent = []
            async def receive_json(self):
                if self.events: return self.events.pop(0)
                raise realtime_bridge.WebSocketDisconnect()
            async def send_json(self, value): self.sent.append(value)

        ws, ai = FakeTwilio(), FakeOpenAI()
        state = {"stopped": False, "stream_sid": "MZ-one"}
        with pytest.raises(realtime_bridge.WebSocketDisconnect):
            asyncio.run(realtime_bridge._openai_to_twilio(ws, ai, state, object()))
        assert [item["event"] for item in ws.sent] == ["media", "mark", "clear"]
        assert len(ai.sent) == 1 and ai.sent[0]["type"] == "conversation.item.truncate"
        assert ai.sent[0]["item_id"] == "item-1" and ai.sent[0]["audio_end_ms"] == 0 and ai.sent[0]["content_index"] == 0

    def test_openai_connection_failure_marks_call_and_notifies_owner(self):
        db = SessionLocal()
        call = voice_foundation.get_or_create_provider_call(db, provider_call_sid="CA-fail", caller_phone="6025551234", called_phone="6025559999")[0]
        token = voice_foundation.issue_stream_token(db, call, 120)
        call_id, internal_call_id = call.id, call.call_id
        db.close()

        class FakeTwilio:
            def __init__(self): self.accepted = False; self.closed = None; self.messages = [
                {"event": "connected", "protocol": "Call", "version": "1.0.0"},
                {"event": "start", "start": {"accountSid": "AC11111111111111111111111111111111", "callSid": "CA-fail", "streamSid": "MZ-fail", "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}, "customParameters": {"voice_call_id": internal_call_id, "stream_token": token}}},
            ]
            async def accept(self): self.accepted = True
            async def receive_json(self): return self.messages.pop(0)
            async def close(self, code): self.closed = code

        async def fail_connect(_config):
            raise RuntimeError("simulated")

        ws = FakeTwilio()
        asyncio.run(realtime_bridge.run_media_bridge(
            ws, config=VoiceConfig.from_env(), db_factory=SessionLocal,
            gateway=object(), openai_factory=fail_connect,
        ))
        verify = SessionLocal()
        assert verify.get(models.VoiceCall, call_id).call_state == "failed"
        assert verify.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "failed_call").count() == 1
        assert ws.accepted and ws.closed == 1011
        verify.close()

    def test_simulated_end_to_end_stream_completes_without_external_calls(self):
        db = SessionLocal()
        call = voice_foundation.get_or_create_provider_call(db, provider_call_sid="CA-e2e", caller_phone="6025551234", called_phone="6025559999")[0]
        token = voice_foundation.issue_stream_token(db, call, 120)
        call_id, internal_call_id = call.id, call.call_id
        db.close()
        audio = base64.b64encode(b"\xff" * 160).decode()

        class FakeTwilio:
            def __init__(self):
                self.accepted = False
                self.messages = [
                    {"event": "connected", "protocol": "Call", "version": "1.0.0"},
                    {"event": "start", "start": {"accountSid": "AC11111111111111111111111111111111", "callSid": "CA-e2e", "streamSid": "MZ-e2e", "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}, "customParameters": {"voice_call_id": internal_call_id, "stream_token": token}}},
                    {"event": "media", "streamSid": "MZ-e2e", "media": {"payload": audio}},
                    {"event": "stop", "streamSid": "MZ-e2e", "stop": {"callSid": "CA-e2e"}},
                ]
            async def accept(self): self.accepted = True
            async def receive_json(self): return self.messages.pop(0)
            async def send_json(self, value): pass
            async def close(self, code): pass

        class FakeOpenAI:
            def __init__(self): self.sent = []; self.closed = False; self.handshake = [{"type": "session.created"}, {"type": "session.updated"}]
            async def send_json(self, value): self.sent.append(value)
            async def receive_json(self):
                if self.handshake: return self.handshake.pop(0)
                await asyncio.Event().wait()
            async def close(self): self.closed = True

        ws, ai = FakeTwilio(), FakeOpenAI()
        async def connect(_config): return ai
        asyncio.run(realtime_bridge.run_media_bridge(
            ws, config=VoiceConfig.from_env(), db_factory=SessionLocal,
            gateway=object(), openai_factory=connect,
        ))
        assert ws.accepted and ai.closed
        assert ai.sent[0]["type"] == "session.update"
        assert ai.sent[1]["type"] == "response.create"
        assert ai.sent[2] == {"type": "input_audio_buffer.append", "audio": audio}
        verify = SessionLocal()
        finished = verify.get(models.VoiceCall, call_id)
        assert finished.call_state == "completed" and finished.provider_stream_sid == "MZ-e2e"
        event_types = {event.event_type for event in verify.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.call_id == call_id)}
        assert {"call_created", "stream_started", "stream_stopped", "call_completed"}.issubset(event_types)
        assert verify.query(models.Appointment).count() == 0
        verify.close()

    def test_callback_without_appointment_is_idempotent(self):
        payload = {
            "caller_phone": "+16025551234", "category": "general", "urgency": "normal",
            "summary": "Please call me back", "operation_key": "callback-op-1",
        }
        first = client.post("/callbacks", json=payload)
        second = client.post("/callbacks", json=payload)
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["appointment_id"] is None

    def test_call_record_state_event_idempotency_and_secret_rejection(self):
        db = SessionLocal()
        call = voice_foundation.create_call(db, caller_phone="6025551234", called_phone="4805559999", call_id="call-test-1")
        assert call.call_state == "created"
        updated = voice_foundation.update_call_state(db, call.id, "connected", intent="booking")
        assert updated.call_state == "connected"
        first = voice_foundation.append_call_event(
            db, call=updated, event_type="booking_lookup", result_status="success",
            operation_key="op-1", metadata={"candidate_count": 1},
        )
        second = voice_foundation.append_call_event(
            db, call=updated, event_type="booking_lookup", result_status="success", operation_key="op-1",
        )
        assert first.id == second.id
        with pytest.raises(voice_foundation.VoiceFoundationError):
            voice_foundation.append_call_event(
                db, call=updated, event_type="failed", result_status="failed",
                metadata={"auth_token": "must-not-persist"},
            )
        assert "must-not-persist" not in str([row.metadata_json for row in db.query(models.VoiceCallEvent).all()])
        db.close()

    def test_ambiguous_poll_creates_one_notification_without_appointment_mutation(self):
        tech1 = make_tech("Ambiguous One", specialties="manicure / pedicure").json()["id"]
        tech2 = make_tech("Ambiguous Two", specialties="manicure / pedicure").json()["id"]
        first = make_appointment(customer_phone="6025551234", technician_id=tech1).json()
        second = make_appointment(
            customer_phone="6025551234", technician_id=tech2,
            appointment_time=datetime.combine(date.today(), time(14, 0)).isoformat(),
        ).json()

        class AmbiguousGateway:
            def get_today_checkins(self):
                return [{
                    "visit_id": 919, "customer_id": 818, "position": 1,
                    "full_name": "Ambiguous Customer", "phone_number": "6025551234",
                    "phone_e164": "+16025551234",
                    "checked_in_at": datetime.combine(date.today(), time(13, 0)).isoformat(),
                    "services": ["Gel Manicure"],
                }]

        app.dependency_overrides[main_module.get_customer_gateway] = lambda: AmbiguousGateway()
        try:
            assert client.get("/checkins/today").json()["checkins"][0]["appointment_match"]["outcome"] == "ambiguous"
            client.get("/checkins/today")
            notices = client.get("/notifications?type=ambiguous_appointment").json()
            assert len(notices) == 1
            assert set(notices[0]["metadata_json"]["candidate_ids"]) == {first["id"], second["id"]}
            assert client.get(f"/appointments/{first['id']}").json()["status"] == "scheduled"
            assert client.get(f"/appointments/{second['id']}").json()["status"] == "scheduled"
        finally:
            app.dependency_overrides.pop(main_module.get_customer_gateway, None)


class TestCheckinIdentityIntegration:

    @pytest.mark.parametrize(
        "value",
        ["6025551234", "(602) 555-1234", "602-555-1234", "+16025551234"],
    )
    def test_phone_formats_have_one_identity(self, value):
        assert normalize_us_phone(value).e164 == "+16025551234"

    @pytest.mark.parametrize("value", ["123", "+442071838750", "602-CALL-NOW"])
    def test_invalid_phone_is_rejected(self, value):
        with pytest.raises(PhoneNormalizationError):
            normalize_us_phone(value)

    def test_match_today_by_phone_across_formatting(self):
        appointment = make_appointment(customer_phone="6025551234").json()
        response = client.post("/checkins/match", json={
            "customer_phone": "+16025551234",
            "customer_name": "Different Display Name",
            "checked_in_at": datetime.combine(date.today(), time(11, 45)).isoformat(),
        })
        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "exact_match"
        assert response.json()["appointment"]["id"] == appointment["id"]

    @pytest.mark.parametrize("status", ["cancelled", "done"])
    def test_match_ignores_final_appointments(self, status):
        appointment = make_appointment(customer_phone="6025551234").json()
        db = SessionLocal()
        db.get(models.Appointment, appointment["id"]).status = status
        db.commit()
        db.close()
        response = client.post("/checkins/match", json={
            "customer_phone": "602-555-1234",
            "checked_in_at": datetime.combine(date.today(), time(12, 0)).isoformat(),
        })
        assert response.json()["outcome"] == "no_match"

    def test_name_never_overrides_wrong_phone(self):
        make_appointment(customer_name="Same Name", customer_phone="6025551234")
        response = client.post("/checkins/match", json={
            "customer_phone": "4805559999",
            "customer_name": "Same Name",
            "checked_in_at": datetime.combine(date.today(), time(12, 0)).isoformat(),
        })
        assert response.json()["outcome"] == "no_match"

    def test_two_plausible_appointments_are_ambiguous(self):
        tech1 = make_tech("One", specialties="manicure / pedicure").json()["id"]
        tech2 = make_tech("Two", specialties="manicure / pedicure").json()["id"]
        first = make_appointment(customer_phone="6025551234", technician_id=tech1).json()
        second = make_appointment(
            customer_phone="(602) 555-1234",
            technician_id=tech2,
            appointment_time=datetime.combine(date.today(), time(14, 0)).isoformat(),
        ).json()
        response = client.post("/checkins/match", json={
            "customer_phone": "+16025551234",
            "checked_in_at": datetime.combine(date.today(), time(13, 0)).isoformat(),
        })
        assert response.json()["outcome"] == "ambiguous"
        assert set(response.json()["candidate_ids"]) == {first["id"], second["id"]}

    def test_valid_and_invalid_arrival_transitions(self):
        scheduled = make_appointment(customer_phone="6025551234").json()
        checked_in = client.post(f"/appointments/{scheduled['id']}/check-in")
        assert checked_in.status_code == 200
        assert checked_in.json()["status"] == "checked_in"

        cancelled = make_appointment(customer_phone="4805551234").json()
        assert client.post(f"/appointments/{cancelled['id']}/cancel", json={}).status_code == 200
        assert client.post(f"/appointments/{cancelled['id']}/check-in").status_code == 400

        done = make_appointment(customer_phone="6235551234").json()
        db = SessionLocal()
        db.get(models.Appointment, done["id"]).status = "done"
        db.commit()
        db.close()
        assert client.post(f"/appointments/{done['id']}/check-in").status_code == 400

    def test_appointment_turn_checkout_traceability_and_duplicate_visit(self):
        appointment = make_appointment(customer_phone="6025551234").json()
        payload = {
            "customer_name": "Alice",
            "customer_phone": "+16025551234",
            "service_name": "Gel Manicure",
            "preferred_technician_id": appointment["technician_id"],
            "source": "checkin",
            "appointment_id": appointment["id"],
            "checkin_customer_id": 77,
            "checkin_visit_id": 88,
        }
        first = client.post("/turns/assign-preferred", json=payload)
        assert first.status_code == 200, first.text
        turn = first.json()
        assert turn["appointment_id"] == appointment["id"]
        assert turn["checkin_customer_id"] == 77
        assert turn["checkin_visit_id"] == 88
        assert client.get(f"/appointments/{appointment['id']}").json()["status"] == "assigned"

        duplicate = client.post("/turns/assign-preferred", json={**payload, "customer_name": "Stale Browser Copy"})
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == turn["id"]
        assert len(client.get("/turns/today").json()) == 1

        checkout = make_checkout(turn_id=turn["id"], appointment_id=None, subtotal=50)
        assert checkout.status_code == 200, checkout.text
        assert checkout.json()["appointment_id"] == appointment["id"]
        assert client.get(f"/appointments/{appointment['id']}").json()["status"] == "done"

    def test_walkin_turn_and_checkout_still_work_without_appointment(self):
        tech_id = make_tech("Walkin Tech", specialties="acrylic").json()["id"]
        turn = auto_assign(
            customer_name="Walk In",
            customer_phone="4805550101",
            service_name="Acrylic Full Set",
            checkin_customer_id=9,
            checkin_visit_id=10,
        )
        assert turn.status_code == 200, turn.text
        assert turn.json()["appointment_id"] is None
        checkout = make_checkout(turn_id=turn.json()["id"], subtotal=40)
        assert checkout.status_code == 200
        assert checkout.json()["appointment_id"] is None

    def test_integrated_queue_failure_does_not_mutate_database(self):
        class FailedGateway:
            def get_today_checkins(self):
                raise CustomerGatewayError("offline")

        app.dependency_overrides[main_module.get_customer_gateway] = lambda: FailedGateway()
        try:
            response = client.get("/checkins/today")
            assert response.status_code == 503
            assert client.get("/turns").json() == []
            assert client.get("/appointments").json() == []
        finally:
            app.dependency_overrides.pop(main_module.get_customer_gateway, None)

    def test_malformed_integrated_queue_does_not_mutate_database(self):
        class MalformedGateway:
            def get_today_checkins(self):
                return [{"full_name": "Missing stable IDs"}]

        app.dependency_overrides[main_module.get_customer_gateway] = lambda: MalformedGateway()
        try:
            response = client.get("/checkins/today")
            assert response.status_code == 503
            assert client.get("/turns").json() == []
        finally:
            app.dependency_overrides.pop(main_module.get_customer_gateway, None)

    def test_integrated_queue_returns_match_without_mutating_appointment(self):
        appointment = make_appointment(customer_phone="6025551234").json()

        class FakeGateway:
            def get_today_checkins(self):
                return [{
                    "visit_id": 42,
                    "customer_id": 24,
                    "position": 1,
                    "full_name": "Alice",
                    "phone_number": "6025551234",
                    "phone_e164": "+16025551234",
                    "checked_in_at": datetime.combine(date.today(), time(11, 55)).isoformat(),
                    "services": ["Gel Manicure"],
                }]

        app.dependency_overrides[main_module.get_customer_gateway] = lambda: FakeGateway()
        try:
            item = client.get("/checkins/today").json()["checkins"][0]
            repeated = client.get("/checkins/today").json()["checkins"][0]
            assert item["appointment_match"]["outcome"] == "exact_match"
            assert repeated["appointment_match"]["appointment"]["id"] == appointment["id"]
            assert item["appointment_match"]["appointment"]["id"] == appointment["id"]
            assert client.get(f"/appointments/{appointment['id']}").json()["status"] == "scheduled"
            assert client.get("/turns").json() == []
        finally:
            app.dependency_overrides.pop(main_module.get_customer_gateway, None)


# ══════════════════════════════════════════════════════════════════════════════
# 1. TECHNICIANS
# ══════════════════════════════════════════════════════════════════════════════

class TestTechnicians:

    def test_create_technician_success(self):
        r = make_tech("Mia")
        assert r.status_code == 200
        data = r.json()
        assert data["full_name"] == "Mia"
        assert data["status"] == "active"
        assert data["availability"] == "available today"
        assert data["id"] is not None

    def test_create_duplicate_name_fails(self):
        make_tech("Mia")
        r = make_tech("Mia")
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"].lower()

    def test_create_duplicate_name_case_insensitive(self):
        make_tech("Mia")
        r = make_tech("mia")
        assert r.status_code == 400

    def test_create_duplicate_employee_id_fails(self):
        make_tech("Mia", employee_id="EMP001")
        r = make_tech("Lisa", employee_id="EMP001")
        assert r.status_code == 400
        assert "employee id" in r.json()["detail"].lower()

    def test_create_with_invalid_status_fails(self):
        r = client.post("/technicians", json={
            "full_name": "Mia",
            "status": "unknown_status",
            "availability": "available today",
        })
        assert r.status_code == 422

    def test_create_with_invalid_availability_fails(self):
        r = client.post("/technicians", json={
            "full_name": "Mia",
            "status": "active",
            "availability": "flying",
        })
        assert r.status_code == 422

    def test_create_with_invalid_phone_fails(self):
        r = client.post("/technicians", json={
            "full_name": "Mia",
            "status": "active",
            "availability": "available today",
            "phone": "12345",
        })
        assert r.status_code == 422

    def test_get_all_technicians(self):
        make_tech("Mia")
        make_tech("Lisa")
        r = client.get("/technicians")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_technician_by_id(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.get(f"/technicians/{tech_id}")
        assert r.status_code == 200
        assert r.json()["full_name"] == "Mia"

    def test_get_nonexistent_technician_returns_404(self):
        assert client.get("/technicians/9999").status_code == 404

    def test_search_technician_by_name(self):
        make_tech("Mia")
        make_tech("Lisa")
        r = client.get("/technicians?search=mi")
        assert r.status_code == 200
        names = [t["full_name"] for t in r.json()]
        assert "Mia" in names
        assert "Lisa" not in names

    def test_filter_technician_by_status(self):
        make_tech("Mia", status="active")
        make_tech("Lisa", status="off", availability="off today")
        r = client.get("/technicians?status=active")
        assert r.status_code == 200
        assert all(t["status"] == "active" for t in r.json())

    def test_filter_technician_by_specialty(self):
        make_tech("Mia", specialties="acrylic")
        make_tech("Lisa", specialties="waxing")
        r = client.get("/technicians?specialty=acrylic")
        assert r.status_code == 200
        names = [t["full_name"] for t in r.json()]
        assert "Mia" in names
        assert "Lisa" not in names

    def test_update_technician_name(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.put(f"/technicians/{tech_id}", json={"full_name": "Mia Updated"})
        assert r.status_code == 200
        assert r.json()["full_name"] == "Mia Updated"

    def test_update_technician_name_to_existing_fails(self):
        tech_id = make_tech("Mia").json()["id"]
        make_tech("Lisa")
        r = client.put(f"/technicians/{tech_id}", json={"full_name": "Lisa"})
        assert r.status_code == 400

    def test_update_nonexistent_technician_returns_404(self):
        assert client.put("/technicians/9999", json={"full_name": "Ghost"}).status_code == 404

    def test_delete_technician_without_history_really_deletes(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.delete(f"/technicians/{tech_id}")
        assert r.status_code == 200
        assert client.get(f"/technicians/{tech_id}").status_code == 404

    def test_delete_technician_with_history_deactivates_instead(self):
        tech_id = make_tech("Mia").json()["id"]
        give_turn(tech_id)  # a finished turn = history
        r = client.delete(f"/technicians/{tech_id}")
        assert r.status_code == 200
        assert "deactivated" in r.json()["message"].lower()
        tech = client.get(f"/technicians/{tech_id}").json()
        assert tech["is_active"] is False

    def test_deactivate_with_open_turn_fails(self):
        tech_id = make_tech("Mia").json()["id"]
        make_turn(tech_id)  # waiting = open
        r = client.put(f"/technicians/{tech_id}/deactivate")
        assert r.status_code == 400
        assert "open turn" in r.json()["detail"].lower()

    def test_reactivate_technician(self):
        tech_id = make_tech("Mia").json()["id"]
        client.put(f"/technicians/{tech_id}/deactivate")
        r = client.put(f"/technicians/{tech_id}/reactivate")
        assert r.status_code == 200
        assert r.json()["is_active"] is True

    def test_delete_nonexistent_technician_returns_404(self):
        assert client.delete("/technicians/9999").status_code == 404

    def test_technician_cards_include_today_counts(self):
        tech_id = make_tech("Mia").json()["id"]
        make_appointment(technician_id=tech_id)
        make_turn(tech_id)
        r = client.get("/technicians/cards")
        assert r.status_code == 200
        card = r.json()[0]
        assert card["today_appointments_count"] == 1
        assert card["today_turns_count"] == 1

    def test_technician_cards_count_preferred_appointments(self):
        tech_id = make_tech("Mia").json()["id"]
        client.post("/appointments", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel Manicure",
            "appointment_time": datetime.combine(date.today(), time(12, 0)).isoformat(),
            "preferred_technician_id": tech_id,
        })
        card = client.get("/technicians/cards").json()[0]
        assert card["today_appointments_count"] == 1

    def test_technician_cards_zero_counts_when_no_activity(self):
        make_tech("Mia")
        r = client.get("/technicians/cards")
        assert r.status_code == 200
        card = r.json()[0]
        assert card["today_appointments_count"] == 0
        assert card["today_turns_count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. APPOINTMENTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAppointments:

    def test_create_appointment_success(self):
        r = make_appointment()
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Alice"
        assert data["customer_phone"] == "5550000001"
        assert data["appointment_code"].startswith("APT-")
        assert data["id"] is not None

    def test_appointment_codes_are_unique(self):
        code1 = make_appointment(customer_name="Alice", customer_phone="5550000001").json()["appointment_code"]
        code2 = make_appointment(customer_name="Bob", customer_phone="5550000002").json()["appointment_code"]
        assert code1 != code2
        assert code1.startswith("APT-") and code2.startswith("APT-")

    def test_create_appointment_invalid_phone_fails(self):
        assert make_appointment(customer_phone="123").status_code == 422

    def test_create_appointment_invalid_status_fails(self):
        r = client.post("/appointments", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel Manicure",
            "appointment_time": datetime.combine(date.today(), time(12, 0)).isoformat(),
            "status": "not_a_status",
        })
        assert r.status_code == 422

    def test_create_appointment_with_nonexistent_tech_fails(self):
        r = make_appointment(technician_id=9999)
        assert r.status_code == 400
        assert "technician" in r.json()["detail"].lower()

    def test_create_appointment_with_valid_tech(self):
        tech_id = make_tech("Mia").json()["id"]
        r = make_appointment(technician_id=tech_id)
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id

    def test_service_name_is_set_from_service_category(self):
        assert make_appointment(service_category="Dip Powder").json()["service_name"] == "Dip Powder"

    def test_get_all_appointments(self):
        make_appointment(customer_name="Alice", customer_phone="5550000001")
        make_appointment(customer_name="Bob", customer_phone="5550000002")
        r = client.get("/appointments")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_filter_appointments_by_date(self):
        make_appointment()
        r = client.get(f"/appointments?date={date.today().isoformat()}")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_filter_appointments_by_technician_id(self):
        tech_id = make_tech("Mia").json()["id"]
        make_appointment(technician_id=tech_id)
        make_appointment(customer_name="Bob", customer_phone="5550000002")
        r = client.get(f"/appointments?technician_id={tech_id}")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert all(a["technician_id"] == tech_id for a in r.json())

    def test_filter_appointments_by_preferred_technician_when_unassigned(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.post("/appointments", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel Manicure",
            "appointment_time": datetime.combine(date.today(), time(12, 15)).isoformat(),
            "preferred_technician_id": tech_id,
        })
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id
        assert r.json()["preferred_technician_id"] == tech_id

        filtered = client.get(f"/appointments?technician_id={tech_id}")
        assert filtered.status_code == 200
        assert len(filtered.json()) == 1

    def test_get_appointment_by_id(self):
        apt_id = make_appointment().json()["id"]
        r = client.get(f"/appointments/{apt_id}")
        assert r.status_code == 200
        assert r.json()["id"] == apt_id

    def test_get_nonexistent_appointment_returns_404(self):
        assert client.get("/appointments/9999").status_code == 404

    def test_update_appointment_customer_name(self):
        apt_id = make_appointment().json()["id"]
        r = client.put(f"/appointments/{apt_id}", json={
            "customer_name": "Alice Updated",
            "customer_phone": "5550000001",
            "service_category": "Gel Manicure",
            "appointment_time": datetime.combine(date.today(), time(12, 15)).isoformat(),
        })
        assert r.status_code == 200
        assert r.json()["customer_name"] == "Alice Updated"

    def test_update_appointment_preserves_code(self):
        apt = make_appointment().json()
        r = client.put(f"/appointments/{apt['id']}", json={
            "customer_name": "Alice",
            "customer_phone": "5550000001",
            "service_category": "Gel Manicure",
            "appointment_time": datetime.combine(date.today(), time(12, 0)).isoformat(),
        })
        assert r.json()["appointment_code"] == apt["appointment_code"]

    def test_update_nonexistent_appointment_returns_404(self):
        r = client.put("/appointments/9999", json={
            "customer_name": "Ghost",
            "customer_phone": "5550000001",
            "service_category": "Gel",
            "appointment_time": datetime.now().isoformat(),
        })
        assert r.status_code == 404

    def test_delete_appointment_success(self):
        apt_id = make_appointment().json()["id"]
        assert client.delete(f"/appointments/{apt_id}").status_code == 200
        assert client.get(f"/appointments/{apt_id}").status_code == 404

    def test_delete_nonexistent_appointment_returns_404(self):
        assert client.delete("/appointments/9999").status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 3. TURNS / DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

class TestTurns:

    def test_create_turn_success(self):
        tech_id = make_tech("Mia").json()["id"]
        r = make_turn(tech_id)
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Alice"
        assert data["status"] == "waiting"
        assert data["turn_number"] == 1

    def test_turn_numbers_increment_per_day(self):
        tech_id = make_tech("Mia").json()["id"]
        t1 = make_turn(tech_id, customer_name="Alice").json()["turn_number"]
        t2 = make_turn(tech_id, customer_name="Bob").json()["turn_number"]
        assert t2 == t1 + 1

    def test_create_turn_with_nonexistent_tech_returns_404(self):
        r = client.post("/turns", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "technician_id": 9999,
            "status": "waiting",
            "source": "checkin",
        })
        assert r.status_code == 404

    def test_get_turns(self):
        make_turn(make_tech("Mia").json()["id"])
        r = client.get("/turns")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_get_today_turns(self):
        make_turn(make_tech("Mia").json()["id"])
        r = client.get("/turns/today")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_start_turn_sets_in_service(self):
        turn_id = make_turn(make_tech("Mia").json()["id"]).json()["id"]
        r = client.put(f"/turns/{turn_id}/start", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "in_service"
        assert r.json()["started_at"] is not None

    def test_complete_turn_sets_done(self):
        turn_id = make_turn(make_tech("Mia").json()["id"]).json()["id"]
        r = client.put(f"/turns/{turn_id}/complete", json={})
        assert r.status_code == 200
        assert r.json()["status"] == "done"
        assert r.json()["completed_at"] is not None

    def test_start_and_complete_save_notes(self):
        turn_id = make_turn(make_tech("Mia").json()["id"]).json()["id"]
        r = client.put(f"/turns/{turn_id}/start", json={"notes": "allergic to latex"})
        assert r.json()["notes"] == "allergic to latex"

    def test_assign_next_turn_manually(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.post("/turns/assign-next", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "technician_id": tech_id,
            "source": "manual",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "assigned"
        assert r.json()["assigned_at"] is not None

    def test_assign_next_turn_with_nonexistent_tech_returns_404(self):
        r = client.post("/turns/assign-next", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "technician_id": 9999,
        })
        assert r.status_code == 404

    def test_auto_assign_picks_available_tech(self):
        make_tech("Mia", specialties="acrylic")
        r = auto_assign()
        assert r.status_code == 200
        assert r.json()["status"] == "assigned"

    def test_auto_assign_fails_when_no_available_tech(self):
        r = auto_assign()
        assert r.status_code == 400
        assert "no available technician" in r.json()["detail"].lower()

    def test_auto_assign_fails_when_tech_has_active_turn(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        make_turn(tech_id, customer_name="Bob")
        assert auto_assign().status_code == 400

    def test_auto_assign_returns_existing_active_turn(self):
        make_tech("Mia", specialties="acrylic")
        r1 = auto_assign(customer_phone="5550000001")
        assert r1.status_code == 200
        r2 = auto_assign(customer_phone="5550000001")
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]

    def test_assign_preferred_turn_success(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        r = client.post("/turns/assign-preferred", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "preferred_technician_id": tech_id,
        })
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id
        assert r.json()["status"] == "assigned"

    def test_assign_preferred_fails_when_tech_unavailable(self):
        tech_id = make_tech("Mia", status="off", availability="off today", specialties="acrylic").json()["id"]
        r = client.post("/turns/assign-preferred", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "preferred_technician_id": tech_id,
        })
        assert r.status_code == 400
        assert "not available" in r.json()["detail"].lower()

    def test_assign_preferred_fails_when_service_does_not_match(self):
        tech_id = make_tech("Mia", specialties="waxing").json()["id"]
        r = client.post("/turns/assign-preferred", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "preferred_technician_id": tech_id,
        })
        assert r.status_code == 400
        assert "does not match" in r.json()["detail"].lower()

    def test_reassign_turn_success(self):
        tech1_id = make_tech("Mia", specialties="acrylic").json()["id"]
        tech2_id = make_tech("Lisa", specialties="acrylic").json()["id"]
        turn_id = make_turn(tech1_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech2_id

    def test_reassign_to_busy_tech_fails(self):
        tech1_id = make_tech("Mia", specialties="acrylic").json()["id"]
        tech2_id = make_tech("Lisa", specialties="acrylic").json()["id"]
        make_turn(tech2_id, customer_name="Carol")  # Lisa is busy
        turn_id = make_turn(tech1_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 400
        assert "already assigned" in r.json()["detail"].lower()

    def test_reassign_to_wrong_specialty_fails(self):
        tech1_id = make_tech("Mia", specialties="acrylic").json()["id"]
        tech2_id = make_tech("Lisa", specialties="waxing").json()["id"]
        turn_id = make_turn(tech1_id).json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": tech2_id})
        assert r.status_code == 400
        assert "does not match" in r.json()["detail"].lower()

    def test_reassign_nonexistent_turn_returns_404(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        assert client.put("/turns/9999/reassign", json={"technician_id": tech_id}).status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 3a. FIX 1: FAIR AUTO-ASSIGN
# ══════════════════════════════════════════════════════════════════════════════

class TestFairAutoAssign:
    """Active -> available today -> specialty -> free -> fewest turns -> stable tie-breaker."""

    def test_picks_tech_with_fewest_turns_not_first_alphabetically(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(amy, "Customer 1")  # Amy now has 1 turn, Bea has 0

        r = auto_assign("Customer 2")
        assert r.status_code == 200
        assert r.json()["technician_id"] == bea  # old code would have picked Amy

    def test_work_is_shared_evenly(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]

        order = []
        for i in range(1, 5):
            turn = auto_assign(f"Customer {i}").json()
            order.append(turn["technician_id"])
            client.put(f"/turns/{turn['id']}/complete", json={})  # free the tech again

        assert order == [amy, bea, amy, bea]

    def test_tie_goes_to_whoever_waited_longest(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(bea, "Customer 1")  # Bea was assigned first
        give_turn(amy, "Customer 2")  # Amy later; both now have 1 turn

        r = auto_assign("Customer 3")
        assert r.json()["technician_id"] == bea  # idle longest, even though Amy is first by name

    def test_final_tie_break_is_name_and_is_stable(self):
        zoe = make_tech("Zoe", specialties="acrylic").json()["id"]  # created first, so lowest id
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        r = auto_assign("Customer 1")
        assert r.json()["technician_id"] == amy
        assert amy != zoe

    def test_cancelled_turns_do_not_count(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(bea, "Customer 1")  # Bea: 1 done turn (older)
        cancelled = give_turn(amy, "Customer 2", complete=False)  # Amy: 1 turn, later...
        assert client.put(f"/turns/{cancelled['id']}/status", json={"status": "cancelled"}).status_code == 200

        # ...but it was cancelled, so Amy has 0 real turns vs Bea's 1.
        # If cancelled turns were counted this would be a tie and Bea (idle longer) would win.
        r = auto_assign("Customer 3")
        assert r.json()["technician_id"] == amy

    def test_skips_busy_off_and_deactivated_techs(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        make_tech("Bea", status="off", availability="off today", specialties="acrylic")
        dan = make_tech("Dan", specialties="acrylic").json()["id"]
        cat = make_tech("Cat", specialties="acrylic").json()["id"]

        make_turn(amy, "Busy customer")  # Amy is busy
        client.put(f"/technicians/{dan}/deactivate")  # Dan is deactivated
        give_turn(cat, "Customer 1")  # Cat is free, with 1 turn: the only eligible tech

        r = auto_assign("Customer 2")
        assert r.status_code == 200
        assert r.json()["technician_id"] == cat

    def test_only_considers_techs_with_matching_specialty(self):
        make_tech("Amy", specialties="waxing")  # 0 turns, wrong specialty
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(bea, "Customer 1")

        r = auto_assign("Customer 2", service_name="Acrylic Full Set")
        assert r.json()["technician_id"] == bea

    def test_waiting_turn_is_not_counted_against_its_own_candidates(self):
        amy = make_tech("Amy", specialties="acrylic").json()["id"]
        bea = make_tech("Bea", specialties="acrylic").json()["id"]
        give_turn(bea, "Customer 1")  # Bea: 1 turn
        waiting = make_turn(amy, customer_name="Alice").json()  # Alice waiting, parked on Amy

        r = auto_assign("Alice")
        assert r.status_code == 200
        assert r.json()["id"] == waiting["id"]  # re-uses her waiting turn
        assert r.json()["status"] == "assigned"
        assert r.json()["technician_id"] == amy  # Amy: 0 other turns vs Bea's 1


# ══════════════════════════════════════════════════════════════════════════════
# 3b. FIX 3: ORDERED TURN STATUSES
# ══════════════════════════════════════════════════════════════════════════════

class TestTurnStatusFlow:

    def _new_turn(self):
        tech_id = make_tech("Mia", specialties="acrylic").json()["id"]
        return tech_id, make_turn(tech_id).json()["id"]

    def _set(self, turn_id, status):
        return client.put(f"/turns/{turn_id}/status", json={"status": status})

    def test_normal_forward_flow(self):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "assigned").json()["status"] == "assigned"
        assert self._set(turn_id, "in_service").json()["status"] == "in_service"
        done = self._set(turn_id, "done").json()
        assert done["status"] == "done"
        assert done["assigned_at"] and done["started_at"] and done["completed_at"]

    def test_waiting_can_jump_straight_to_in_service(self):
        _, turn_id = self._new_turn()
        r = self._set(turn_id, "in_service")
        assert r.status_code == 200
        assert r.json()["started_at"] is not None

    def test_waiting_can_jump_straight_to_done_and_fills_timestamps(self):
        _, turn_id = self._new_turn()
        data = self._set(turn_id, "done").json()
        assert data["status"] == "done"
        assert data["assigned_at"] and data["started_at"] and data["completed_at"]

    def test_invalid_status_value_is_422(self):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "flying").status_code == 422

    def test_nonexistent_turn_is_404(self):
        assert self._set(9999, "done").status_code == 404

    def test_done_cannot_go_back_to_waiting(self):
        _, turn_id = self._new_turn()
        completed_at = self._set(turn_id, "done").json()["completed_at"]

        r = self._set(turn_id, "waiting")
        assert r.status_code == 400
        assert "done" in r.json()["detail"] and "waiting" in r.json()["detail"]

        turn = get_turn_today(turn_id)
        assert turn["status"] == "done"
        assert turn["completed_at"] == completed_at  # untouched

    @pytest.mark.parametrize("target", ["waiting", "assigned", "in_service", "cancelled"])
    def test_done_is_final(self, target):
        _, turn_id = self._new_turn()
        self._set(turn_id, "done")
        assert self._set(turn_id, target).status_code == 400

    @pytest.mark.parametrize("target", ["waiting", "assigned", "in_service", "done"])
    def test_cancelled_is_final(self, target):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "cancelled").status_code == 200
        assert self._set(turn_id, target).status_code == 400

    def test_in_service_cannot_go_backwards(self):
        _, turn_id = self._new_turn()
        self._set(turn_id, "in_service")
        assert self._set(turn_id, "assigned").status_code == 400
        assert self._set(turn_id, "waiting").status_code == 400

    def test_open_turn_can_be_cancelled(self):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "cancelled").json()["status"] == "cancelled"

    def test_same_status_twice_is_not_an_error(self):
        _, turn_id = self._new_turn()
        assert self._set(turn_id, "in_service").status_code == 200
        assert self._set(turn_id, "in_service").status_code == 200

    def test_completing_twice_keeps_original_completed_at(self):
        _, turn_id = self._new_turn()
        first = client.put(f"/turns/{turn_id}/complete", json={}).json()
        second = client.put(f"/turns/{turn_id}/complete", json={})
        assert second.status_code == 200
        assert second.json()["completed_at"] == first["completed_at"]

    def test_cannot_start_a_done_turn(self):
        _, turn_id = self._new_turn()
        client.put(f"/turns/{turn_id}/complete", json={})
        assert client.put(f"/turns/{turn_id}/start", json={}).status_code == 400

    def test_cannot_complete_a_cancelled_turn(self):
        _, turn_id = self._new_turn()
        self._set(turn_id, "cancelled")
        assert client.put(f"/turns/{turn_id}/complete", json={}).status_code == 400

    def test_reassign_keeps_in_service_status(self):
        mia = make_tech("Mia", specialties="acrylic").json()["id"]
        lisa = make_tech("Lisa", specialties="acrylic").json()["id"]
        turn_id = make_turn(mia).json()["id"]
        started = client.put(f"/turns/{turn_id}/start", json={}).json()

        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": lisa})
        assert r.status_code == 200
        assert r.json()["technician_id"] == lisa
        assert r.json()["status"] == "in_service"  # must not drop back to "assigned"
        assert r.json()["started_at"] == started["started_at"]

    def test_reassign_moves_waiting_turn_to_assigned(self):
        mia = make_tech("Mia", specialties="acrylic").json()["id"]
        lisa = make_tech("Lisa", specialties="acrylic").json()["id"]
        turn_id = make_turn(mia).json()["id"]
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": lisa})
        assert r.json()["status"] == "assigned"
        assert r.json()["assigned_at"] is not None

    @pytest.mark.parametrize("final_status", ["done", "cancelled"])
    def test_finished_turn_cannot_be_reassigned(self, final_status):
        mia = make_tech("Mia", specialties="acrylic").json()["id"]
        lisa = make_tech("Lisa", specialties="acrylic").json()["id"]
        turn_id = make_turn(mia).json()["id"]
        self._set(turn_id, final_status)
        r = client.put(f"/turns/{turn_id}/reassign", json={"technician_id": lisa})
        assert r.status_code == 400
        assert "cannot be reassigned" in r.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# 4. CHECKOUT
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckout:

    def test_create_checkout_success(self):
        r = make_checkout()
        assert r.status_code == 200
        data = r.json()
        assert data["customer_name"] == "Alice"
        assert data["subtotal"] == 100.0
        assert data["id"] is not None

    def test_create_checkout_links_to_technician(self):
        tech_id = make_tech("Mia").json()["id"]
        r = make_checkout(technician_id=tech_id)
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id

    def test_create_checkout_with_turn_marks_turn_done(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        assert make_checkout(technician_id=tech_id, turn_id=turn_id).status_code == 200
        turn = get_turn_today(turn_id)
        assert turn["status"] == "done"
        assert turn["completed_at"] is not None

    def test_checkout_of_already_completed_turn_works(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        client.put(f"/turns/{turn_id}/complete", json={})  # tech taps "done" first
        assert make_checkout(technician_id=tech_id, turn_id=turn_id).status_code == 200

    def test_auto_assign_checkout_flow_moves_customer_to_history(self):
        make_tech("Mia", specialties="acrylic")

        assigned = auto_assign(
            "Alice",
            customer_phone="5550000001",
            discount_type="fixed",
            discount_value=10.0,
            discount_label="$10 birthday discount",
        )
        assert assigned.status_code == 200
        turn = assigned.json()
        assert turn["status"] == "assigned"
        assert turn["discount_type"] == "fixed"

        ready = [t for t in client.get("/turns/today").json() if t["status"] in {"assigned", "in_service"}]
        assert [t["id"] for t in ready] == [turn["id"]]

        checkout = make_checkout(
            customer_name="Alice",
            customer_phone="5550000001",
            service_name="Acrylic Full Set",
            subtotal=100.0,
            tip_amount=15.0,
            technician_id=turn["technician_id"],
            turn_id=turn["id"],
            discount_type="fixed",
            discount_value=10.0,
        )
        assert checkout.status_code == 200

        today_turns = client.get("/turns/today").json()
        completed = next(t for t in today_turns if t["id"] == turn["id"])
        assert completed["status"] == "done"
        assert completed["completed_at"] is not None
        assert not [t for t in today_turns if t["status"] in {"assigned", "in_service"}]

        history = client.get("/checkouts").json()
        assert len(history) == 1
        assert history[0]["customer_name"] == "Alice"
        assert history[0]["customer_phone"] == "5550000001"
        assert history[0]["discount_amount"] == 10.0
        assert history[0]["tip_amount"] == 15.0

    def test_create_checkout_invalid_payment_method_fails(self):
        assert make_checkout(payment_method="bitcoin").status_code == 422

    def test_create_checkout_invalid_discount_type_fails(self):
        assert make_checkout(discount_type="unknown").status_code == 422

    def test_get_all_checkouts(self):
        make_checkout(customer_name="Alice")
        make_checkout(customer_name="Bob")
        r = client.get("/checkouts")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_checkout_by_id(self):
        checkout_id = make_checkout().json()["id"]
        r = client.get(f"/checkouts/{checkout_id}")
        assert r.status_code == 200
        assert r.json()["id"] == checkout_id

    def test_get_nonexistent_checkout_returns_404(self):
        assert client.get("/checkouts/9999").status_code == 404

    def test_delete_checkout_success(self):
        checkout_id = make_checkout().json()["id"]
        assert client.delete(f"/checkouts/{checkout_id}").status_code == 200
        assert client.get(f"/checkouts/{checkout_id}").status_code == 404

    def test_delete_nonexistent_checkout_returns_404(self):
        assert client.delete("/checkouts/9999").status_code == 404

    # ── Fix 2: the server does the math ──────────────────────────────────────

    def test_server_calculates_split_without_discount(self):
        data = make_checkout(subtotal=100.0, tip_amount=20.0).json()
        assert data["discount_amount"] == 0.0
        assert data["net_service"] == 100.0
        assert data["technician_share"] == 60.0
        assert data["salon_share"] == 40.0
        assert data["salon_actual_revenue"] == 40.0
        assert data["technician_total"] == 80.0  # 60 + 20 tip
        assert data["customer_pays"] == 120.0  # 100 + 20 tip
        assert data["discount_paid_by"] == "owner"

    def test_fixed_discount_is_calculated_by_server(self):
        data = make_checkout(subtotal=100.0, discount_type="fixed", discount_value=15.0).json()
        assert data["discount_amount"] == 15.0
        assert data["net_service"] == 85.0
        assert data["technician_share"] == 60.0  # 60% of the $100 price: the discount doesn't touch it
        assert data["salon_share"] == 40.0
        assert data["salon_actual_revenue"] == 25.0  # the owner absorbs the whole $15 discount
        assert data["technician_total"] == 60.0
        assert data["customer_pays"] == 85.0

    def test_discount_never_reduces_technician_pay(self):
        no_discount = make_checkout(subtotal=100.0, tip_amount=10.0).json()
        with_discount = make_checkout(
            subtotal=100.0, tip_amount=10.0, discount_type="percent", discount_value=50.0
        ).json()
        assert with_discount["technician_share"] == no_discount["technician_share"] == 60.0
        assert with_discount["technician_total"] == no_discount["technician_total"] == 70.0

    def test_discount_bigger_than_salon_share_makes_salon_revenue_negative(self):
        # Owner pays the discount, so a 50% discount on $100 costs the salon $10 on this customer.
        data = make_checkout(subtotal=100.0, discount_type="percent", discount_value=50.0).json()
        assert data["salon_actual_revenue"] == -10.0

    def test_percent_discount_is_calculated_by_server(self):
        data = make_checkout(
            subtotal=100.0, tip_amount=15.0, discount_type="percent", discount_value=10.0
        ).json()
        assert data["discount_amount"] == 10.0
        assert data["net_service"] == 90.0
        assert data["technician_share"] == 60.0  # 60% of the $100 price
        assert data["salon_share"] == 40.0
        assert data["salon_actual_revenue"] == 30.0  # 40 - 10 discount
        assert data["technician_total"] == 75.0  # 60 + 15 tip
        assert data["customer_pays"] == 105.0  # 90 + 15 tip

    def test_forged_client_numbers_are_ignored(self):
        r = make_checkout(
            subtotal=100.0,
            tip_amount=10.0,
            # An old or tampered client tries to rewrite the books:
            discount_amount=100.0,
            net_service=0.0,
            technician_share=100.0,
            salon_share=0.0,
            salon_actual_revenue=999.0,
            technician_total=500.0,
            customer_pays=1.0,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["discount_amount"] == 0.0
        assert data["net_service"] == 100.0
        assert data["technician_share"] == 60.0
        assert data["salon_share"] == 40.0
        assert data["salon_actual_revenue"] == 40.0
        assert data["technician_total"] == 70.0
        assert data["customer_pays"] == 110.0

    def test_forged_numbers_do_not_reach_income_report(self):
        make_checkout(subtotal=100.0, tip_amount=0.0, salon_actual_revenue=999.0, technician_share=1.0)
        day = client.get(f"/income/salon?date={date.today().isoformat()}").json()["day"]
        assert day["tech_60_percent_total"] == 60.0
        assert day["salon_income_after_techs"] == 40.0

    def test_money_is_rounded_to_cents_and_shares_add_up(self):
        data = make_checkout(subtotal=33.33).json()
        assert data["technician_share"] == 20.0  # 19.998 rounds to 20.00
        assert data["salon_share"] == 13.33
        assert data["technician_share"] + data["salon_share"] == pytest.approx(data["subtotal"])

    def test_percent_discount_rounds_half_up(self):
        data = make_checkout(subtotal=0.05, discount_type="percent", discount_value=10.0).json()
        assert data["discount_amount"] == 0.01  # 0.005 -> 0.01 (not banker's rounding to 0.00)

    def test_percent_discount_over_100_rejected(self):
        assert make_checkout(discount_type="percent", discount_value=101.0).status_code == 422

    def test_fixed_discount_above_subtotal_rejected(self):
        assert make_checkout(subtotal=50.0, discount_type="fixed", discount_value=60.0).status_code == 422

    def test_negative_tip_rejected(self):
        assert make_checkout(tip_amount=-5.0).status_code == 422

    def test_negative_subtotal_rejected(self):
        assert make_checkout(subtotal=-1.0).status_code == 422

    # ── Links to turns, technicians, appointments ────────────────────────────

    def test_technician_is_filled_in_from_turn_when_missing(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        r = make_checkout(turn_id=turn_id)  # no technician_id sent
        assert r.status_code == 200
        assert r.json()["technician_id"] == tech_id

    def test_technician_must_match_turn(self):
        mia = make_tech("Mia").json()["id"]
        lisa = make_tech("Lisa").json()["id"]
        turn_id = make_turn(mia).json()["id"]
        r = make_checkout(technician_id=lisa, turn_id=turn_id)
        assert r.status_code == 400
        assert "does not match" in r.json()["detail"].lower()

    def test_turn_cannot_be_checked_out_twice(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        assert make_checkout(technician_id=tech_id, turn_id=turn_id).status_code == 200
        r = make_checkout(technician_id=tech_id, turn_id=turn_id)
        assert r.status_code == 400
        assert "already" in r.json()["detail"].lower()
        assert len(client.get("/checkouts").json()) == 1

    def test_cancelled_turn_cannot_be_checked_out(self):
        tech_id = make_tech("Mia").json()["id"]
        turn_id = make_turn(tech_id).json()["id"]
        client.put(f"/turns/{turn_id}/status", json={"status": "cancelled"})
        r = make_checkout(technician_id=tech_id, turn_id=turn_id)
        assert r.status_code == 400
        assert "cancelled" in r.json()["detail"].lower()
        assert client.get("/checkouts").json() == []  # nothing was saved
        assert get_turn_today(turn_id)["status"] == "cancelled"  # and the turn is untouched

    def test_checkout_with_unknown_turn_fails(self):
        r = make_checkout(turn_id=9999)
        assert r.status_code == 400
        assert "turn not found" in r.json()["detail"].lower()

    def test_checkout_with_unknown_technician_fails(self):
        r = make_checkout(technician_id=9999)
        assert r.status_code == 400
        assert "technician not found" in r.json()["detail"].lower()

    def test_checkout_with_unknown_appointment_fails(self):
        r = make_checkout(appointment_id=9999)
        assert r.status_code == 400
        assert "appointment not found" in r.json()["detail"].lower()

    def test_checkout_with_valid_appointment(self):
        apt_id = make_appointment().json()["id"]
        r = make_checkout(appointment_id=apt_id)
        assert r.status_code == 200
        assert r.json()["appointment_id"] == apt_id


# ══════════════════════════════════════════════════════════════════════════════
# 4b. FIX 4: FOREIGN KEYS
# ══════════════════════════════════════════════════════════════════════════════

class TestForeignKeys:

    def test_foreign_keys_pragma_is_on(self):
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

    def test_database_rejects_a_turn_for_a_missing_technician(self):
        db = SessionLocal()
        try:
            db.add(models.Turn(turn_number=1, customer_name="X", service_name="Y", technician_id=9999))
            with pytest.raises(IntegrityError):
                db.commit()
        finally:
            db.rollback()
            db.close()

    def test_database_rejects_a_checkout_for_a_missing_turn(self):
        db = SessionLocal()
        try:
            db.add(models.Checkout(customer_name="X", service_name="Y", turn_id=9999))
            with pytest.raises(IntegrityError):
                db.commit()
        finally:
            db.rollback()
            db.close()

    def test_unknown_preferred_technician_on_new_turn_is_400_not_500(self):
        tech_id = make_tech("Mia").json()["id"]
        r = client.post("/turns", json={
            "customer_name": "Alice",
            "service_name": "Acrylic Full Set",
            "technician_id": tech_id,
            "preferred_technician_id": 9999,
        })
        assert r.status_code == 400
        assert "preferred technician not found" in r.json()["detail"].lower()

    def test_unknown_preferred_technician_on_auto_assign_is_400_not_500(self):
        make_tech("Mia", specialties="acrylic")
        r = auto_assign("Alice", preferred_technician_id=9999)
        assert r.status_code == 400
        assert "preferred technician not found" in r.json()["detail"].lower()

    def test_cannot_delete_appointment_that_has_a_checkout(self):
        apt_id = make_appointment().json()["id"]
        assert make_checkout(appointment_id=apt_id).status_code == 200

        r = client.delete(f"/appointments/{apt_id}")
        assert r.status_code == 400
        assert "checkout" in r.json()["detail"].lower()
        assert client.get(f"/appointments/{apt_id}").status_code == 200  # still there

    def test_integrity_error_becomes_409_not_a_crash(self):
        r = client.get("/__test_integrity_error")
        assert r.status_code == 409
        assert "conflicts" in r.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# 5. INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

class TestInventory:

    def test_create_inventory_item_success(self):
        r = make_inventory()
        assert r.status_code == 200
        data = r.json()
        assert data["item_name"] == "Acrylic Powder"
        assert data["quantity"] == 10
        assert data["unit_price"] == 15.0
        assert data["id"] is not None

    def test_negative_quantity_rejected(self):
        assert make_inventory(quantity=-1).status_code == 422

    def test_get_all_inventory_items(self):
        make_inventory("Acrylic Powder")
        make_inventory("Acetone", category="Liquids", quantity=5, unit_price=8.0)
        r = client.get("/inventory")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_inventory_item_by_id(self):
        item_id = make_inventory().json()["id"]
        r = client.get(f"/inventory/{item_id}")
        assert r.status_code == 200
        assert r.json()["id"] == item_id

    def test_get_nonexistent_inventory_item_returns_404(self):
        assert client.get("/inventory/9999").status_code == 404

    def test_update_inventory_item_quantity(self):
        item_id = make_inventory(quantity=10).json()["id"]
        r = client.put(f"/inventory/{item_id}", json={"quantity": 25})
        assert r.status_code == 200
        assert r.json()["quantity"] == 25

    def test_update_inventory_item_price(self):
        item_id = make_inventory(unit_price=10.0).json()["id"]
        r = client.put(f"/inventory/{item_id}", json={"unit_price": 20.0})
        assert r.status_code == 200
        assert r.json()["unit_price"] == 20.0

    def test_update_nonexistent_inventory_item_returns_404(self):
        assert client.put("/inventory/9999", json={"quantity": 5}).status_code == 404

    def test_delete_inventory_item_success(self):
        item_id = make_inventory().json()["id"]
        assert client.delete(f"/inventory/{item_id}").status_code == 200
        assert client.get(f"/inventory/{item_id}").status_code == 404

    def test_delete_nonexistent_inventory_item_returns_404(self):
        assert client.delete("/inventory/9999").status_code == 404

    def test_inventory_summary_total_value(self):
        make_inventory(quantity=10, unit_price=15.0)  # $150
        make_inventory("Acetone", category="Liquids", quantity=5, unit_price=8.0)  # $40
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["total_inventory_value"] == 190.0

    def test_inventory_summary_low_stock_flag(self):
        make_inventory(quantity=2, unit_price=15.0, low_stock_level=3)  # 2 <= 3 -> low stock
        make_inventory("Acetone", category="Liquids", quantity=10, unit_price=8.0, low_stock_level=3)
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["low_stock_items"] == 1

    def test_inventory_summary_weekly_expense(self):
        make_inventory(quantity=4, unit_price=25.0, purchase_date=date.today().isoformat())
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["weekly_expense"] == 100.0

    def test_inventory_summary_excludes_old_purchase_from_weekly(self):
        old_date = (date.today() - timedelta(days=14)).isoformat()
        make_inventory(quantity=4, unit_price=25.0, purchase_date=old_date)
        r = client.get("/inventory/summary")
        assert r.status_code == 200
        assert r.json()["weekly_expense"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 6. INCOME REPORTS
# ══════════════════════════════════════════════════════════════════════════════

class TestIncomeReports:

    def _seed_checkout(self, tech_id, subtotal=100.0, tip=20.0, discount=0.0):
        """discount is a fixed amount in dollars; the server works out everything else."""
        return make_checkout(
            technician_id=tech_id,
            subtotal=subtotal,
            tip_amount=tip,
            discount_type="fixed" if discount else "none",
            discount_value=discount,
        )

    def test_tech_income_report_returns_correct_date(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id)
        today = date.today().isoformat()
        r = client.get(f"/income/tech?date={today}")
        assert r.status_code == 200
        assert r.json()["date"] == today

    def test_tech_income_report_groups_by_technician(self):
        tech1_id = make_tech("Mia").json()["id"]
        tech2_id = make_tech("Lisa").json()["id"]
        self._seed_checkout(tech1_id)
        self._seed_checkout(tech2_id)
        r = client.get(f"/income/tech?date={date.today().isoformat()}")
        assert r.status_code == 200
        assert len(r.json()["technicians"]) == 2

    def test_tech_income_report_sums_correctly(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=10.0)
        self._seed_checkout(tech_id, subtotal=80.0, tip=5.0)
        r = client.get(f"/income/tech?date={date.today().isoformat()}")
        summary = r.json()["technicians"][0]
        assert summary["gross_before_60"] == 180.0
        assert summary["tech_after_60"] == 108.0
        assert summary["tip_total"] == 15.0
        assert summary["tech_total"] == 123.0
        assert summary["turns"] == 2

    def test_tech_income_report_filters_by_technician_id(self):
        tech1_id = make_tech("Mia").json()["id"]
        tech2_id = make_tech("Lisa").json()["id"]
        self._seed_checkout(tech1_id)
        self._seed_checkout(tech2_id)
        r = client.get(f"/income/tech?date={date.today().isoformat()}&technician_id={tech1_id}")
        assert r.status_code == 200
        techs = r.json()["technicians"]
        assert len(techs) == 1
        assert techs[0]["technician_id"] == tech1_id

    def test_tech_income_report_empty_when_no_checkouts(self):
        r = client.get(f"/income/tech?date={date.today().isoformat()}")
        assert r.status_code == 200
        assert r.json()["technicians"] == []

    def test_tech_income_report_technicians_sorted_alphabetically(self):
        zoe_id = make_tech("Zoe").json()["id"]
        amy_id = make_tech("Amy").json()["id"]
        self._seed_checkout(zoe_id)
        self._seed_checkout(amy_id)
        r = client.get(f"/income/tech?date={date.today().isoformat()}")
        names = [t["technician_name"] for t in r.json()["technicians"]]
        assert names == ["Amy", "Zoe"]

    def test_salon_income_report_day_totals(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=20.0)
        r = client.get(f"/income/salon?date={date.today().isoformat()}")
        assert r.status_code == 200
        day = r.json()["day"]
        assert day["income_before_discount"] == 100.0
        assert day["income_after_discount"] == 100.0
        assert day["tech_60_percent_total"] == 60.0
        assert day["salon_income_after_techs"] == 40.0
        assert day["tech_tip_total"] == 20.0
        assert day["total_paid_to_techs"] == 80.0
        assert day["turns"] == 1

    def test_salon_income_report_with_discount(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=0.0, discount=10.0)
        day = client.get(f"/income/salon?date={date.today().isoformat()}").json()["day"]
        assert day["income_before_discount"] == 100.0
        assert day["total_discount"] == 10.0
        assert day["income_after_discount"] == 90.0
        assert day["tech_60_percent_total"] == 60.0  # 60% of the $100 price
        assert day["salon_income_after_techs"] == 30.0  # 40 salon share - 10 discount (owner pays it)

    def test_salon_income_report_includes_day_week_year_periods(self):
        r = client.get(f"/income/salon?date={date.today().isoformat()}")
        assert r.status_code == 200
        data = r.json()
        assert "day" in data and "week" in data and "year" in data

    def test_salon_income_report_week_and_year_include_today(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id, subtotal=100.0, tip=0.0)
        data = client.get(f"/income/salon?date={date.today().isoformat()}").json()
        assert data["week"]["income_before_discount"] == 100.0
        assert data["year"]["income_before_discount"] == 100.0

    def test_salon_income_report_includes_details(self):
        tech_id = make_tech("Mia").json()["id"]
        self._seed_checkout(tech_id)
        details = client.get(f"/income/salon?date={date.today().isoformat()}").json()["details"]
        assert len(details) == 1
        assert details[0]["technician_id"] == tech_id

    def test_salon_income_report_empty_day_when_no_checkouts(self):
        r = client.get(f"/income/salon?date={date.today().isoformat()}")
        assert r.status_code == 200
        day = r.json()["day"]
        assert day["income_before_discount"] == 0.0
        assert day["turns"] == 0
        assert r.json()["details"] == []


# ---------------------------------------------------------------------------
# Booking-domain foundation
# ---------------------------------------------------------------------------

def _booking_day(weekday=0):
    today = date.today()
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _service(name="Gel Manicure"):
    db = SessionLocal()
    try:
        return db.query(models.BookingService).filter(models.BookingService.name == name).first()
    finally:
        db.close()


def _configure_service(name="Gel Manicure", duration=60, before=0, after=0):
    db = SessionLocal()
    service = db.query(models.BookingService).filter(models.BookingService.name == name).first()
    service.duration_minutes = duration
    service.buffer_before_minutes = before
    service.buffer_after_minutes = after
    db.commit()
    service_id = service.id
    db.close()
    return service_id


def _set_business_hours(day, opens=time(9, 0), closes=time(18, 0), closed=False):
    db = SessionLocal()
    hours = db.query(models.BusinessHour).filter(models.BusinessHour.day_of_week == day.weekday()).first()
    hours.is_closed = closed
    hours.opens_at = None if closed else opens
    hours.closes_at = None if closed else closes
    db.commit()
    db.close()


def _set_tech_schedule(technician_id, day, starts=time(9, 0), ends=time(18, 0), working=True):
    db = SessionLocal()
    schedule = db.query(models.TechnicianWorkSchedule).filter(
        models.TechnicianWorkSchedule.technician_id == technician_id,
        models.TechnicianWorkSchedule.day_of_week == day.weekday(),
    ).first()
    schedule.is_working = working
    schedule.starts_at = starts if working else None
    schedule.ends_at = ends if working else None
    db.commit()
    db.close()


def _booking_payload(technician_id, start, service_ids, **extra):
    return {
        "customer_name": extra.pop("customer_name", "Booking Customer"),
        "customer_phone": extra.pop("customer_phone", "5551112222"),
        "service_category": "ignored when IDs are supplied",
        "service_ids": service_ids,
        "appointment_time": start.isoformat(),
        "technician_id": technician_id,
        **extra,
    }


class TestBookingServiceDuration:
    def test_one_service_duration(self):
        service_id = _configure_service(duration=40)
        tech_id = make_tech("Duration Tech", specialties="manicure / pedicure, gel").json()["id"]
        start = datetime.combine(_booking_day(), time(10, 0))
        data = client.post("/appointments", json=_booking_payload(tech_id, start, [service_id])).json()
        assert data["duration_minutes"] == 40

    def test_multiple_services_and_buffers_are_aggregated(self):
        first = _configure_service("Gel Manicure", duration=30, before=5, after=10)
        second = _configure_service("Classic Pedicure", duration=45, before=0, after=5)
        tech_id = make_tech("Multi Tech", specialties="manicure / pedicure, gel").json()["id"]
        start = datetime.combine(_booking_day(), time(10, 0))
        data = client.post("/appointments", json=_booking_payload(tech_id, start, [first, second])).json()
        assert data["duration_minutes"] == 95
        assert len(data["appointment_services"]) == 2


class TestBookingBusinessHoursAndSchedule:
    def test_before_opening_and_after_closing_are_rejected(self):
        day = _booking_day()
        _set_business_hours(day)
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Hours Tech", specialties="manicure / pedicure, gel").json()["id"]
        assert client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(8, 45)), [service_id])).status_code == 400
        assert client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(17, 15)), [service_id])).status_code == 400

    def test_exact_open_and_close_boundaries_are_valid(self):
        day = _booking_day()
        _set_business_hours(day)
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Boundary Tech", specialties="manicure / pedicure, gel").json()["id"]
        first = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(9, 0)), [service_id]))
        second = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(17, 0)), [service_id], customer_phone="5551112223"))
        assert first.status_code == 200
        assert second.status_code == 200

    def test_closed_day_is_rejected(self):
        day = _booking_day()
        _set_business_hours(day, closed=True)
        service_id = _configure_service()
        tech_id = make_tech("Closed Tech", specialties="manicure / pedicure, gel").json()["id"]
        response = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id]))
        assert response.status_code == 400

    def test_during_shift_accepted_and_outside_shift_rejected(self):
        day = _booking_day()
        _set_business_hours(day)
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Shift Tech", specialties="manicure / pedicure, gel").json()["id"]
        _set_tech_schedule(tech_id, day, time(10, 0), time(16, 0))
        assert client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id])).status_code == 200
        assert client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(9, 0)), [service_id], customer_phone="5551112223")).status_code == 400


class TestBookingEligibilityAndBlocks:
    def test_eligible_and_ineligible_technicians(self):
        day = _booking_day()
        service_id = _configure_service()
        eligible = make_tech("Eligible", specialties="manicure / pedicure, gel").json()["id"]
        ineligible = make_tech("Ineligible", specialties="waxing").json()["id"]
        start = datetime.combine(day, time(10, 0))
        assert client.post("/appointments", json=_booking_payload(eligible, start, [service_id])).status_code == 200
        assert client.post("/appointments", json=_booking_payload(ineligible, start, [service_id], customer_phone="5551112223")).status_code == 400

    @pytest.mark.parametrize("block_type", ["break", "date_off"])
    def test_overlapping_block_is_rejected(self, block_type):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech(f"Blocked {block_type}", specialties="manicure / pedicure, gel").json()["id"]
        client.post(f"/technicians/{tech_id}/blocked-times", json={
            "start": datetime.combine(day, time(10, 30)).isoformat(),
            "end": datetime.combine(day, time(11, 30)).isoformat(),
            "block_type": block_type,
        })
        response = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id]))
        assert response.status_code == 400

    def test_adjacent_block_is_allowed(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Adjacent Block", specialties="manicure / pedicure, gel").json()["id"]
        client.post(f"/technicians/{tech_id}/blocked-times", json={
            "start": datetime.combine(day, time(11, 0)).isoformat(),
            "end": datetime.combine(day, time(12, 0)).isoformat(),
            "block_type": "manual",
        })
        response = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id]))
        assert response.status_code == 200


class TestBookingOverlap:
    @pytest.mark.parametrize("second_start,second_duration", [
        (time(10, 0), 60),
        (time(10, 30), 60),
        (time(10, 15), 30),
        (time(9, 30), 120),
    ])
    def test_overlapping_intervals_are_rejected(self, second_start, second_duration):
        day = _booking_day()
        first_service = _configure_service("Gel Manicure", duration=60)
        second_service = _configure_service("Classic Pedicure", duration=second_duration)
        tech_id = make_tech("Overlap Tech", specialties="manicure / pedicure, gel").json()["id"]
        assert client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [first_service])).status_code == 200
        response = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, second_start), [second_service], customer_phone="5551112223"))
        assert response.status_code == 400

    def test_back_to_back_allowed_without_buffer(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Back To Back", specialties="manicure / pedicure, gel").json()["id"]
        first = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id]))
        second = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(11, 0)), [service_id], customer_phone="5551112223"))
        assert first.status_code == second.status_code == 200

    def test_cancelled_appointment_does_not_block(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Cancelled Slot", specialties="manicure / pedicure, gel").json()["id"]
        first = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id])).json()
        client.post(f"/appointments/{first['id']}/cancel", json={"reason": "Changed plans"})
        second = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id], customer_phone="5551112223"))
        assert second.status_code == 200


class TestAvailabilityAndMutations:
    def test_slot_generation_only_returns_valid_slots_and_filters_technician(self):
        day = _booking_day()
        _set_business_hours(day, time(9, 0), time(11, 0))
        service_id = _configure_service(duration=60)
        first = make_tech("Slots One", specialties="manicure / pedicure, gel").json()["id"]
        second = make_tech("Slots Two", specialties="manicure / pedicure, gel").json()["id"]
        response = client.get(f"/availability?date={day.isoformat()}&service_ids={service_id}&technician_id={second}")
        assert response.status_code == 200
        slots = response.json()
        assert slots and all(slot["selected_technician_id"] == second for slot in slots)
        assert all(slot["eligible_technician_ids"] == [second] for slot in slots)
        assert all(slot["start"][11:16] >= "09:00" and slot["end"][11:16] <= "11:00" for slot in slots)

    def test_no_eligible_technician_produces_no_slots(self):
        day = _booking_day()
        service_id = _configure_service()
        make_tech("Wax Only", specialties="waxing")
        response = client.get(f"/availability?date={day.isoformat()}&service_ids={service_id}")
        assert response.status_code == 200
        assert response.json() == []

    def test_reschedule_ignores_self_but_rejects_another_appointment(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Reschedule Tech", specialties="manicure / pedicure, gel").json()["id"]
        first = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id])).json()
        self_move = client.post(f"/appointments/{first['id']}/reschedule", json={
            "appointment_time": datetime.combine(day, time(10, 0)).isoformat(),
            "service_ids": [service_id],
            "technician_id": tech_id,
        })
        assert self_move.status_code == 200
        client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(12, 0)), [service_id], customer_phone="5551112223"))
        conflict = client.post(f"/appointments/{first['id']}/reschedule", json={
            "appointment_time": datetime.combine(day, time(12, 0)).isoformat(),
            "service_ids": [service_id],
            "technician_id": tech_id,
        })
        assert conflict.status_code == 400

    def test_cancellation_preserves_history_and_reopens_slot(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Cancel History", specialties="manicure / pedicure, gel").json()["id"]
        appointment = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id])).json()
        cancelled = client.post(f"/appointments/{appointment['id']}/cancel", json={"reason": "Customer request"})
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["cancellation_reason"] == "Customer request"
        assert client.get(f"/appointments/{appointment['id']}").status_code == 200
        slots = client.get(f"/availability?date={day.isoformat()}&service_ids={service_id}&technician_id={tech_id}").json()
        assert any(slot["start"][11:16] == "10:00" for slot in slots)


class TestBookingTimezoneConcurrencyAndLegacy:
    def test_create_idempotency_key_replays_same_booking(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Idempotent Tech", specialties="manicure / pedicure, gel").json()["id"]
        payload = _booking_payload(
            tech_id,
            datetime.combine(day, time(10, 0)),
            [service_id],
            idempotency_key="booking-request-123",
        )
        first = client.post("/appointments", json=payload)
        second = client.post("/appointments", json=payload)
        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert len(client.get("/appointments").json()) == 1

    def test_phoenix_local_time_is_stored_as_utc(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Timezone Tech", specialties="manicure / pedicure, gel").json()["id"]
        data = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(9, 0)), [service_id])).json()
        assert data["appointment_time"][11:16] == "09:00"
        assert data["starts_at_utc"][11:16] == "16:00"

    def test_competing_requests_cannot_both_book_same_interval(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = make_tech("Concurrent Tech", specialties="manicure / pedicure, gel").json()["id"]
        start = datetime.combine(day, time(10, 0))
        barrier = Barrier(2)

        def attempt(index):
            barrier.wait()
            payload = _booking_payload(
                tech_id,
                start,
                [service_id],
                customer_name=f"Concurrent {index}",
                customer_phone=f"55511122{index:02d}",
            )
            return client.post("/appointments", json=payload).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(attempt, (1, 2)))
        assert statuses == [200, 400]

    def test_legacy_appointment_is_backfilled_and_readable(self):
        from booking_migrations import backfill_legacy_booking_data

        db = SessionLocal()
        legacy = models.Appointment(
            appointment_code="APT-LEGACY-001",
            customer_name="Legacy Customer",
            customer_phone="5551119999",
            service_name="Unknown Legacy Service",
            service_category="Unknown Legacy Service",
            appointment_time=datetime.combine(_booking_day(), time(10, 0)),
            status="scheduled",
            customer_type="returning",
            people_count=1,
        )
        db.add(legacy)
        db.commit()
        legacy_id = legacy.id
        backfill_legacy_booking_data(db)
        db.refresh(legacy)
        assert legacy.legacy_duration_fallback is True
        assert legacy.duration_minutes == 60
        assert legacy.ends_at_utc - legacy.starts_at_utc == timedelta(minutes=60)
        db.close()
        response = client.get(f"/appointments/{legacy_id}")
        assert response.status_code == 200
        assert response.json()["service_category"] == "Unknown Legacy Service"

    def test_legacy_date_off_string_becomes_interval_block(self):
        from booking_migrations import backfill_legacy_booking_data

        day = _booking_day()
        tech_id = make_tech(
            "Legacy Date Off",
            availability=f"date off: {day.isoformat()} to {day.isoformat()}",
            specialties="manicure / pedicure, gel",
        ).json()["id"]
        db = SessionLocal()
        backfill_legacy_booking_data(db)
        block = db.query(models.TechnicianBlockedTime).filter(
            models.TechnicianBlockedTime.technician_id == tech_id,
            models.TechnicianBlockedTime.block_type == "date_off",
        ).one()
        assert block.ends_at_utc - block.starts_at_utc == timedelta(days=1)
        db.close()


# ===========================================================================
# Focused repair pass: tests
# ===========================================================================
_REAL_CURRENT_SALON_TIME = booking_service.current_salon_time
_UTC = __import__("datetime").timezone.utc


def _salon_now_is(monkeypatch, local_naive):
    """Pin the booking clock to a salon-local wall-clock time."""
    monkeypatch.setattr(booking_service, "current_salon_time", lambda tz: as_salon_datetime(local_naive, tz))


def _bookable_tech(name):
    return make_tech(name, specialties="manicure / pedicure, gel").json()["id"]


class TestPastTimeBooking:
    def setup_day(self):
        day = _booking_day()
        _set_business_hours(day, time(9, 0), time(18, 0))
        return day, _configure_service(duration=60), _bookable_tech("Clock Tech")

    def test_past_date_availability_returns_no_slots(self, monkeypatch):
        day, service_id, _ = self.setup_day()
        _salon_now_is(monkeypatch, datetime.combine(day, time(12, 0)))
        earlier = day - timedelta(days=7)
        assert client.get(f"/availability?date={earlier.isoformat()}&service_ids={service_id}").json() == []

    def test_availability_today_hides_slots_before_now_but_keeps_later_ones(self, monkeypatch):
        day, service_id, _ = self.setup_day()
        _salon_now_is(monkeypatch, datetime.combine(day, time(12, 0)))
        starts = [slot["start"][11:16] for slot in client.get(f"/availability?date={day.isoformat()}&service_ids={service_id}").json()]
        assert starts and min(starts) >= "12:00" and "12:00" in starts and "17:00" in starts

    def test_earlier_today_is_rejected_and_later_today_is_accepted(self, monkeypatch):
        day, service_id, tech_id = self.setup_day()
        _salon_now_is(monkeypatch, datetime.combine(day, time(12, 0)))
        early = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id]))
        assert early.status_code == 400 and "past" in early.json()["detail"]
        later = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(13, 0)), [service_id]))
        assert later.status_code == 200

    def test_direct_reschedule_into_the_past_is_rejected(self, monkeypatch):
        day, service_id, tech_id = self.setup_day()
        _salon_now_is(monkeypatch, datetime.combine(day, time(8, 0)))
        created = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(14, 0)), [service_id])).json()
        _salon_now_is(monkeypatch, datetime.combine(day, time(12, 0)))
        moved = client.post(f"/appointments/{created['id']}/reschedule", json={"appointment_time": datetime.combine(day, time(10, 0)).isoformat()})
        assert moved.status_code == 400 and "past" in moved.json()["detail"]
        assert client.get(f"/appointments/{created['id']}").json()["appointment_time"][11:16] == "14:00"

    def test_real_clock_uses_phoenix_not_host_or_utc(self, monkeypatch):
        # 03:30 UTC on Oct 5 is 20:30 on Oct 4 in Phoenix (UTC-7, no DST).
        monkeypatch.setattr(timeutils, "_utc_now_aware", lambda: datetime(2026, 10, 5, 3, 30, tzinfo=_UTC))
        now = _REAL_CURRENT_SALON_TIME("America/Phoenix")
        assert (now.year, now.month, now.day, now.hour, now.minute) == (2026, 10, 4, 20, 30)
        assert now.utcoffset() == timedelta(hours=-7)


class TestPhoenixBusinessDay:
    def test_turn_checkout_and_income_follow_phoenix_not_utc(self, monkeypatch):
        monkeypatch.setattr(timeutils, "_utc_now_aware", lambda: datetime(2026, 10, 5, 3, 30, tzinfo=_UTC))
        import crud
        assert crud._today_bounds()[0].date() == date(2026, 10, 4)
        assert crud._now() == datetime(2026, 10, 4, 20, 30)
        tech_id = make_tech("Phoenix Day Tech", specialties="acrylic").json()["id"]
        turn = make_turn(tech_id).json()
        assert turn["created_at"].startswith("2026-10-04T20:30")
        assert [t["id"] for t in client.get("/turns/today").json()] == [turn["id"]]
        checkout = make_checkout(turn_id=turn["id"], technician_id=tech_id, service_name="Acrylic Full Set")
        assert checkout.status_code == 200 and checkout.json()["created_at"].startswith("2026-10-04")
        assert client.get("/income/salon?date=2026-10-04").json()["day"]["turns"] == 1
        assert client.get("/income/salon?date=2026-10-05").json()["day"]["turns"] == 0

    def test_fair_assignment_counts_the_phoenix_day(self, monkeypatch):
        monkeypatch.setattr(timeutils, "_utc_now_aware", lambda: datetime(2026, 10, 5, 3, 30, tzinfo=_UTC))
        first = make_tech("Fair A", specialties="acrylic").json()["id"]
        make_tech("Fair B", specialties="acrylic")
        give_turn(first, "Customer One")
        assigned = auto_assign("Customer Two")
        assert assigned.status_code == 200
        assert assigned.json()["technician_id"] != first  # one turn already counted "today" for A


class TestBookingIdempotencyBinding:
    def booked(self, key=None, hour=10, name="Key Customer", phone="5551112222"):
        day = _booking_day()
        service_id = _configure_service(duration=30)
        techs = client.get("/technicians").json()
        tech_id = techs[0]["id"] if techs else _bookable_tech("Key Tech")
        extra = {"idempotency_key": key} if key else {}
        return client.post("/appointments", json=_booking_payload(
            tech_id, datetime.combine(day, time(hour, 0)), [service_id], customer_name=name, customer_phone=phone, **extra))

    @staticmethod
    def make_legacy(key):
        db = SessionLocal()
        record = db.query(models.BookingIdempotencyRecord).filter(
            models.BookingIdempotencyRecord.idempotency_key == key
        ).one()
        record.request_hash = None
        db.commit()
        db.close()

    @staticmethod
    def stored_hash(key):
        db = SessionLocal()
        value = db.query(models.BookingIdempotencyRecord.request_hash).filter(
            models.BookingIdempotencyRecord.idempotency_key == key
        ).scalar()
        db.close()
        return value

    def test_exact_replay_returns_the_same_appointment_for_create_reschedule_and_cancel(self):
        first, again = self.booked("k-create"), self.booked("k-create")
        assert first.status_code == again.status_code == 200 and first.json()["id"] == again.json()["id"]
        appt = first.json()["id"]
        move = {"appointment_time": datetime.combine(_booking_day(), time(12, 0)).isoformat(), "idempotency_key": "k-move"}
        assert client.post(f"/appointments/{appt}/reschedule", json=move).status_code == 200
        assert client.post(f"/appointments/{appt}/reschedule", json=move).status_code == 200
        cancel = {"reason": "changed mind", "idempotency_key": "k-cancel"}
        assert client.post(f"/appointments/{appt}/cancel", json=cancel).status_code == 200
        assert client.post(f"/appointments/{appt}/cancel", json=cancel).status_code == 200  # replay, not an error
        assert len(client.get("/appointments").json()) == 1

    def test_same_key_with_different_customer_or_time_is_rejected(self):
        assert self.booked("k-1").status_code == 200
        other_customer = self.booked("k-1", name="Someone Else", phone="5553334444")
        assert other_customer.status_code == 409 and "different request" in other_customer.json()["detail"]
        assert self.booked("k-1", hour=14).status_code == 409
        assert len(client.get("/appointments").json()) == 1

    def test_reschedule_and_cancel_keys_cannot_replay_a_different_appointment(self):
        a = self.booked(hour=9).json()["id"]
        b = self.booked(hour=11).json()["id"]
        when = datetime.combine(_booking_day(), time(15, 0)).isoformat()
        assert client.post(f"/appointments/{a}/reschedule", json={"appointment_time": when, "idempotency_key": "shared-move"}).status_code == 200
        assert client.post(f"/appointments/{b}/reschedule", json={"appointment_time": when, "idempotency_key": "shared-move"}).status_code == 409
        assert client.post(f"/appointments/{a}/cancel", json={"idempotency_key": "shared-cancel"}).status_code == 200
        assert client.post(f"/appointments/{b}/cancel", json={"idempotency_key": "shared-cancel"}).status_code == 409
        assert client.get(f"/appointments/{b}").json()["status"] == "scheduled"

    def test_key_reused_for_a_different_operation_is_rejected(self):
        appt = self.booked("k-op").json()["id"]
        assert client.post(f"/appointments/{appt}/cancel", json={"idempotency_key": "k-op"}).status_code == 409

    def test_legacy_create_exact_request_replays_and_lazily_backfills_hash(self):
        appt = self.booked("legacy-create-same").json()["id"]
        self.make_legacy("legacy-create-same")
        replay = self.booked("legacy-create-same")
        assert replay.status_code == 200 and replay.json()["id"] == appt
        assert self.stored_hash("legacy-create-same") is not None

    def test_legacy_create_different_customer_is_409_and_stays_unhashed(self):
        assert self.booked("legacy-create-customer").status_code == 200
        self.make_legacy("legacy-create-customer")
        changed = self.booked("legacy-create-customer", name="Different Customer", phone="5553334444")
        assert changed.status_code == 409
        assert self.stored_hash("legacy-create-customer") is None

    def test_legacy_create_different_time_is_409_and_stays_unhashed(self):
        assert self.booked("legacy-create-time", hour=10).status_code == 200
        self.make_legacy("legacy-create-time")
        assert self.booked("legacy-create-time", hour=14).status_code == 409
        assert self.stored_hash("legacy-create-time") is None

    def test_legacy_create_different_services_is_409_and_stays_unhashed(self):
        original = self.booked("legacy-create-services").json()
        self.make_legacy("legacy-create-services")
        other_service = _configure_service("Classic Pedicure", duration=30)
        payload = _booking_payload(
            original["technician_id"], datetime.combine(_booking_day(), time(10, 0)),
            [other_service], idempotency_key="legacy-create-services",
        )
        assert client.post("/appointments", json=payload).status_code == 409
        assert self.stored_hash("legacy-create-services") is None

    def test_legacy_reschedule_exact_target_replays_and_lazily_backfills_hash(self):
        appt = self.booked(hour=10).json()["id"]
        move = {"appointment_time": datetime.combine(_booking_day(), time(14, 0)).isoformat(),
                "idempotency_key": "legacy-move-same"}
        assert client.post(f"/appointments/{appt}/reschedule", json=move).status_code == 200
        self.make_legacy("legacy-move-same")
        replay = client.post(f"/appointments/{appt}/reschedule", json=move)
        assert replay.status_code == 200 and replay.json()["id"] == appt
        assert self.stored_hash("legacy-move-same") is not None

    def test_legacy_reschedule_cannot_replay_a_different_appointment(self):
        first = self.booked(hour=9).json()["id"]
        second = self.booked(hour=11, phone="5551112233").json()["id"]
        move = {"appointment_time": datetime.combine(_booking_day(), time(15, 0)).isoformat(),
                "idempotency_key": "legacy-move-appointment"}
        assert client.post(f"/appointments/{first}/reschedule", json=move).status_code == 200
        self.make_legacy("legacy-move-appointment")
        assert client.post(f"/appointments/{second}/reschedule", json=move).status_code == 409
        assert self.stored_hash("legacy-move-appointment") is None

    def test_legacy_reschedule_different_target_is_409_and_stays_unhashed(self):
        appt = self.booked(hour=10).json()["id"]
        first = {"appointment_time": datetime.combine(_booking_day(), time(14, 0)).isoformat(),
                 "idempotency_key": "legacy-move-target"}
        assert client.post(f"/appointments/{appt}/reschedule", json=first).status_code == 200
        self.make_legacy("legacy-move-target")
        changed = {**first, "appointment_time": datetime.combine(_booking_day(), time(15, 0)).isoformat()}
        assert client.post(f"/appointments/{appt}/reschedule", json=changed).status_code == 409
        assert self.stored_hash("legacy-move-target") is None

    def test_legacy_reschedule_with_ambiguous_event_history_is_409(self):
        appt = self.booked(hour=10).json()["id"]
        original = {"appointment_time": datetime.combine(_booking_day(), time(12, 0)).isoformat(),
                    "idempotency_key": "legacy-move-history"}
        assert client.post(f"/appointments/{appt}/reschedule", json=original).status_code == 200
        assert client.post(f"/appointments/{appt}/reschedule", json={
            "appointment_time": datetime.combine(_booking_day(), time(14, 0)).isoformat()
        }).status_code == 200
        assert client.post(f"/appointments/{appt}/reschedule", json={
            "appointment_time": original["appointment_time"]
        }).status_code == 200
        self.make_legacy("legacy-move-history")
        assert client.post(f"/appointments/{appt}/reschedule", json=original).status_code == 409
        assert self.stored_hash("legacy-move-history") is None

    def test_legacy_cancel_exact_request_replays_and_lazily_backfills_hash(self):
        appt = self.booked().json()["id"]
        cancel = {"reason": "Customer request", "source": "owner", "idempotency_key": "legacy-cancel-same"}
        assert client.post(f"/appointments/{appt}/cancel", json=cancel).status_code == 200
        self.make_legacy("legacy-cancel-same")
        replay = client.post(f"/appointments/{appt}/cancel", json=cancel)
        assert replay.status_code == 200 and replay.json()["id"] == appt
        assert self.stored_hash("legacy-cancel-same") is not None

    def test_legacy_cancel_cannot_replay_a_different_appointment(self):
        first = self.booked(hour=9).json()["id"]
        second = self.booked(hour=11, phone="5551112233").json()["id"]
        cancel = {"reason": "Customer request", "idempotency_key": "legacy-cancel-appointment"}
        assert client.post(f"/appointments/{first}/cancel", json=cancel).status_code == 200
        self.make_legacy("legacy-cancel-appointment")
        assert client.post(f"/appointments/{second}/cancel", json=cancel).status_code == 409
        assert self.stored_hash("legacy-cancel-appointment") is None

    @pytest.mark.parametrize("change", [
        {"reason": "Different reason", "source": "owner"},
        {"reason": "Customer request", "source": "phone"},
    ])
    def test_legacy_cancel_different_reason_or_source_is_409_and_stays_unhashed(self, change):
        appt = self.booked().json()["id"]
        original = {"reason": "Customer request", "source": "owner", "idempotency_key": "legacy-cancel-fields"}
        assert client.post(f"/appointments/{appt}/cancel", json=original).status_code == 200
        self.make_legacy("legacy-cancel-fields")
        assert client.post(f"/appointments/{appt}/cancel", json={**change, "idempotency_key": "legacy-cancel-fields"}).status_code == 409
        assert self.stored_hash("legacy-cancel-fields") is None

    def test_request_hash_column_migration_remains_idempotent(self):
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE booking_idempotency_records DROP COLUMN request_hash"))
        from booking_migrations import ensure_booking_columns
        ensure_booking_columns()
        ensure_booking_columns()
        with engine.begin() as connection:
            assert "request_hash" in {row[1] for row in connection.execute(text("PRAGMA table_info(booking_idempotency_records)"))}


class TestAppointmentLifecycleRestrictions:
    def make(self, hour=10):
        day = _booking_day()
        service_id = _configure_service(duration=30)
        tech_id = _bookable_tech(f"Life Tech {hour}")
        data = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(hour, 0)), [service_id])).json()
        return data["id"], tech_id, day

    def set_status(self, appointment_id, status):
        db = SessionLocal()
        db.get(models.Appointment, appointment_id).status = status
        db.commit()
        db.close()

    @pytest.mark.parametrize("status", ["checked_in", "assigned", "in_service", "done", "cancelled"])
    def test_only_scheduled_appointments_can_be_rescheduled(self, status):
        appt, _tech, day = self.make()
        self.set_status(appt, status)
        r = client.post(f"/appointments/{appt}/reschedule", json={"appointment_time": datetime.combine(day, time(15, 0)).isoformat()})
        assert r.status_code == 400 and "cannot be rescheduled" in r.json()["detail"]

    @pytest.mark.parametrize("status", ["scheduled", "checked_in"])
    def test_scheduled_and_checked_in_without_a_turn_can_be_cancelled(self, status):
        appt, _tech, _day = self.make()
        self.set_status(appt, status)
        assert client.post(f"/appointments/{appt}/cancel", json={}).status_code == 200

    @pytest.mark.parametrize("status", ["in_service", "done"])
    def test_started_or_finished_appointments_cannot_be_cancelled(self, status):
        appt, _tech, _day = self.make()
        self.set_status(appt, status)
        r = client.post(f"/appointments/{appt}/cancel", json={})
        assert r.status_code == 400 and client.get(f"/appointments/{appt}").json()["status"] == status

    def test_cancelling_twice_is_an_error_but_replay_with_the_same_key_is_not(self):
        appt, _tech, _day = self.make()
        assert client.post(f"/appointments/{appt}/cancel", json={"idempotency_key": "c-1"}).status_code == 200
        assert client.post(f"/appointments/{appt}/cancel", json={"idempotency_key": "c-1"}).status_code == 200
        again = client.post(f"/appointments/{appt}/cancel", json={})
        assert again.status_code == 400 and "already cancelled" in again.json()["detail"]

    def test_appointment_with_an_open_turn_must_be_handled_through_the_turn(self):
        appt, tech_id, _day = self.make()
        turn = client.post("/turns", json={"customer_name": "Booking Customer", "customer_phone": "5551112222", "service_name": "Gel Manicure",
                                           "technician_id": tech_id, "status": "assigned", "appointment_id": appt}).json()
        assert client.get(f"/appointments/{appt}").json()["status"] == "assigned"
        blocked = client.post(f"/appointments/{appt}/cancel", json={})
        assert blocked.status_code == 400 and "open turn" in blocked.json()["detail"]
        assert client.get("/turns/today").json()[0]["status"] == "assigned"  # nothing deleted or changed
        # The owner's normal path: cancel the Turn and the appointment follows atomically.
        assert client.put(f"/turns/{turn['id']}/status", json={"status": "cancelled"}).status_code == 200
        assert client.get(f"/appointments/{appt}").json()["status"] == "cancelled"


class TestBookingEdgeCases:
    def test_inactive_service_malformed_and_unknown_service_ids_are_rejected(self):
        day = _booking_day()
        service_id = _configure_service(duration=30)
        tech_id = _bookable_tech("Edge Tech")
        start = datetime.combine(day, time(10, 0))
        db = SessionLocal()
        db.get(models.BookingService, service_id).is_active = False
        db.commit()
        db.close()
        assert client.post("/appointments", json=_booking_payload(tech_id, start, [service_id])).status_code == 400
        assert client.post("/appointments", json=_booking_payload(tech_id, start, [999999])).status_code == 400
        assert client.post("/appointments", json=_booking_payload(tech_id, start, ["abc"])).status_code == 422

    def test_closing_boundary_includes_service_buffers(self):
        day = _booking_day()
        _set_business_hours(day, time(9, 0), time(18, 0))
        service_id = _configure_service(duration=45, before=5, after=10)  # 60 minutes of occupied time
        tech_id = _bookable_tech("Closing Tech")
        ok = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(17, 0)), [service_id]))
        assert ok.status_code == 200 and ok.json()["duration_minutes"] == 60
        late = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(17, 15)), [service_id], customer_phone="5559998888"))
        assert late.status_code == 400  # 17:15 + 60 minutes would run past 18:00

    def test_technician_blocked_after_availability_query_is_caught_at_create(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = _bookable_tech("Race Tech")
        slots = client.get(f"/availability?date={day.isoformat()}&service_ids={service_id}&technician_id={tech_id}").json()
        assert any(slot["start"][11:16] == "10:00" for slot in slots)
        block = client.post(f"/technicians/{tech_id}/blocked-times", json={
            "start": datetime.combine(day, time(9, 30)).isoformat(), "end": datetime.combine(day, time(10, 30)).isoformat(), "block_type": "manual"})
        assert block.status_code == 200
        assert client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(10, 0)), [service_id])).status_code == 400

    def test_concurrent_reschedules_cannot_take_the_same_slot(self):
        day = _booking_day()
        service_id = _configure_service(duration=60)
        tech_id = _bookable_tech("Concurrent Move")
        ids = [client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(hour, 0)), [service_id], customer_phone=f"55511133{hour:02d}")).json()["id"] for hour in (9, 11)]
        target = datetime.combine(day, time(15, 0)).isoformat()
        barrier = Barrier(2)

        def move(appointment_id):
            barrier.wait()
            return client.post(f"/appointments/{appointment_id}/reschedule", json={"appointment_time": target, "technician_id": tech_id}).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(move, ids)) == [200, 400]


# ---------------------------------------------------------------------------
# Voice repairs
# ---------------------------------------------------------------------------
def _voice_call(sid="CA-repair", phone="6025551234", state=None):
    db = SessionLocal()
    call = voice_foundation.get_or_create_provider_call(db, provider_call_sid=sid, caller_phone=phone, called_phone="6025559999")[0]
    if state:
        voice_foundation.update_call_state(db, call.id, state)
    token = voice_foundation.issue_stream_token(db, call, 120)
    info = (call.id, call.call_id, token)
    db.close()
    return info


def _facade(db, call_id, phone):
    call = db.get(models.VoiceCall, call_id)
    return voice_foundation.VoiceBookingFacade(db, voice_foundation.VoiceAuthorizationContext(call.id, call.call_id, 0, phone, None))


class TestAnonymousAndUnsupportedCallers:
    def form(self, **changes):
        data = {"AccountSid": "AC11111111111111111111111111111111", "CallSid": "CA-anon", "From": "anonymous", "To": "+16025559999"}
        data.update(changes)
        return data

    @pytest.mark.parametrize("caller", ["anonymous", "+266696687", "+442071234567", "", None])
    def test_unusable_caller_id_still_gets_valid_twiml_and_no_trusted_phone(self, caller):
        form = self.form()
        if caller is None:
            form.pop("From")
        else:
            form["From"] = caller
        response = _twilio_post("/voice/twilio/incoming", form)
        assert response.status_code == 200 and "<Stream" in response.text
        db = SessionLocal()
        assert db.query(models.VoiceCall).one().caller_phone_e164 is None
        db.close()

    def test_bad_signature_still_rejected_for_anonymous_callers(self):
        assert client.post("/voice/twilio/incoming", data=self.form(), headers={"X-Twilio-Signature": "bad"}).status_code == 403

    def test_no_customer_match_and_callback_needs_a_number_that_is_never_trusted(self):
        call_id, _internal, _token = _voice_call("CA-anon-tools", phone="anonymous")
        db = SessionLocal()
        facade = _facade(db, call_id, None)

        class ExplodingGateway:
            def find_customer_by_phone(self, phone):
                raise AssertionError("must not look anything up without a trusted phone")

        assert voice_tools.dispatch_voice_tool(facade, ExplodingGateway(), "identify_customer_candidate", {}) == {"matched": False}
        base = {"category": "general", "urgency": "normal", "summary": "Call me"}
        with pytest.raises(voice_foundation.VoiceFoundationError):
            voice_tools.dispatch_voice_tool(facade, None, "request_owner_callback", base)
        with pytest.raises(voice_foundation.VoiceFoundationError):
            voice_tools.dispatch_voice_tool(facade, None, "request_owner_callback", {**base, "callback_phone": "not a number"})
        result = voice_tools.dispatch_voice_tool(facade, None, "request_owner_callback", {**base, "callback_phone": "(480) 555-0100"})
        assert result == {"requested": True}
        note = db.query(models.OwnerNotification).one()
        assert note.metadata_json["caller_phone"] == "+14805550100" and note.metadata_json["phone_source"] == "spoken_by_caller"
        call = db.get(models.VoiceCall, call_id)
        assert call.caller_phone_e164 is None and call.external_customer_id is None  # a spoken number is never identity
        db.close()


class TestCallbackAntiSpamAndPrivacy:
    def test_trusted_phone_wins_and_repeated_calls_create_one_notification(self):
        call_id, _internal, _token = _voice_call("CA-cb", phone="6025551234")
        db = SessionLocal()
        facade = _facade(db, call_id, "+16025551234")
        first = voice_tools.dispatch_voice_tool(facade, None, "request_owner_callback", {
            "category": "booking", "urgency": "normal", "summary": "first", "operation_key": "model-key-1",
            "callback_phone": "+19998887777", "caller_phone": "+19998887777"})
        second = voice_tools.dispatch_voice_tool(facade, None, "request_owner_callback", {
            "category": "complaint", "urgency": "urgent", "summary": "second", "operation_key": "model-key-2"})
        third = voice_tools.dispatch_voice_tool(facade, None, "request_owner_callback", {"category": "other", "urgency": "normal", "summary": "third"})
        assert first == second == third == {"requested": True}
        notes = db.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "callback_request").all()
        assert len(notes) == 1 and notes[0].message == "first"
        assert notes[0].metadata_json["caller_phone"] == "+16025551234" and notes[0].metadata_json["phone_source"] == "caller_id"
        assert db.get(models.VoiceCall, call_id).needs_owner_attention is True
        db.close()

    def test_each_call_gets_its_own_callback_and_bad_urgency_is_rejected(self):
        db = SessionLocal()
        for index, sid in enumerate(("CA-cb-a", "CA-cb-b")):
            call_id, *_ = _voice_call(sid, phone="6025551234")
            voice_tools.dispatch_voice_tool(_facade(db, call_id, "+16025551234"), None, "request_owner_callback", {"category": "general", "urgency": "normal", "summary": f"call {index}"})
        assert db.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "callback_request").count() == 2
        call_id, *_ = _voice_call("CA-cb-c", phone="6025551234")
        with pytest.raises(voice_foundation.VoiceFoundationError):
            voice_tools.dispatch_voice_tool(_facade(db, call_id, "+16025551234"), None, "request_owner_callback", {"category": "general", "urgency": "whenever", "summary": "x"})
        db.close()

    def test_callback_tool_schema_no_longer_lets_the_model_pick_an_idempotency_key(self):
        schema = next(t for t in voice_tools.READ_ONLY_TOOL_DEFINITIONS if t["name"] == "request_owner_callback")
        assert "operation_key" not in schema["parameters"]["properties"] and "callback_phone" in schema["parameters"]["properties"]

    def test_level_one_match_never_discloses_the_stored_name_or_other_fields(self):
        call_id, *_ = _voice_call("CA-priv", phone="6025551234")
        db = SessionLocal()

        class Gateway:
            def find_customer_by_phone(self, phone):
                return {"id": 7, "full_name": "Secret Person", "email": "x@example.com", "date_of_birth": "1990-01-01"}

        result = voice_tools.dispatch_voice_tool(_facade(db, call_id, "+16025551234"), Gateway(), "identify_customer_candidate", {})
        assert result == {"matched": True}
        assert db.get(models.VoiceCall, call_id).external_customer_id == 7  # recorded server-side only
        db.close()

    @pytest.mark.parametrize("name", ["reschedule_booking", "cancel_booking", "update_customer", "get_salon_info; create_booking", "", "GET_SALON_INFO", "__import__('os')"])
    def test_tool_name_injection_and_unknown_tools_are_blocked(self, name):
        call_id, *_ = _voice_call("CA-inject", phone="6025551234")
        db = SessionLocal()
        with pytest.raises(voice_foundation.VoiceFoundationError):
            voice_tools.dispatch_voice_tool(_facade(db, call_id, "+16025551234"), None, name, {"name": "create_booking"})
        assert db.query(models.Appointment).count() == 0
        db.close()


class TestTerminalCallAndLateStream:
    @pytest.mark.parametrize("terminal", ["completed", "failed"])
    def test_late_stream_cannot_reopen_a_finished_call(self, terminal):
        call_id, internal, token = _voice_call(f"CA-late-{terminal}")
        db = SessionLocal()
        voice_foundation.update_call_state(db, call_id, terminal)
        assert voice_foundation.consume_stream_token(db, raw_token=token, provider_call_sid=f"CA-late-{terminal}", stream_sid="MZ-late") is None
        assert db.get(models.VoiceCall, call_id).call_state == terminal
        assert voice_foundation.update_call_state(db, call_id, "connected").call_state == terminal
        assert voice_foundation.update_call_state(db, call_id, "failed" if terminal == "completed" else "completed").call_state == terminal
        db.close()

    def test_late_stream_never_connects_to_openai(self):
        call_id, internal, token = _voice_call("CA-late-bridge", state="completed")

        class FakeTwilio:
            def __init__(self):
                self.messages = [{"event": "connected", "protocol": "Call", "version": "1.0.0"},
                                 {"event": "start", "start": {"accountSid": "AC11111111111111111111111111111111", "callSid": "CA-late-bridge", "streamSid": "MZ-late", "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}, "customParameters": {"voice_call_id": internal, "stream_token": token}}}]
            async def accept(self): pass
            async def receive_json(self): return self.messages.pop(0)
            async def close(self, code): self.closed = code

        opened = []

        async def connect(_config):
            opened.append(1)

        ws = FakeTwilio()
        asyncio.run(realtime_bridge.run_media_bridge(ws, config=VoiceConfig.from_env(), db_factory=SessionLocal, gateway=object(), openai_factory=connect))
        assert opened == [] and ws.closed == 1008
        verify = SessionLocal()
        assert verify.get(models.VoiceCall, call_id).call_state == "completed"
        verify.close()

    def test_same_stream_duplicate_is_still_accepted_while_live_but_other_streams_are_not(self):
        call_id, _internal, token = _voice_call("CA-dup")
        db = SessionLocal()
        assert voice_foundation.consume_stream_token(db, raw_token=token, provider_call_sid="CA-dup", stream_sid="MZ-1").id == call_id
        assert voice_foundation.consume_stream_token(db, raw_token=token, provider_call_sid="CA-dup", stream_sid="MZ-1").id == call_id
        assert voice_foundation.consume_stream_token(db, raw_token=token, provider_call_sid="CA-dup", stream_sid="MZ-2") is None
        assert db.get(models.VoiceCall, call_id).provider_stream_sid == "MZ-1"
        db.close()

    def test_token_cannot_be_claimed_twice_by_racing_starts(self):
        call_id, _internal, token = _voice_call("CA-race")
        results = []

        def claim(stream_sid):
            local = SessionLocal()
            try:
                results.append(voice_foundation.consume_stream_token(local, raw_token=token, provider_call_sid="CA-race", stream_sid=stream_sid))
            finally:
                local.close()

        threads = [__import__("threading").Thread(target=claim, args=(f"MZ-{i}",)) for i in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert sum(1 for r in results if r is not None) == 1

    def test_status_after_terminal_cannot_revive_the_call(self):
        form = {"AccountSid": "AC11111111111111111111111111111111", "CallSid": "CA-status", "From": "+16025551234", "To": "+16025559999"}
        _twilio_post("/voice/twilio/incoming", form)
        status = {"AccountSid": form["AccountSid"], "CallSid": "CA-status", "CallStatus": "completed", "SequenceNumber": "5"}
        _twilio_post("/voice/twilio/status", status)
        _twilio_post("/voice/twilio/status", {**status, "CallStatus": "in-progress", "SequenceNumber": "6"})
        _twilio_post("/voice/twilio/status", {**status, "CallStatus": "failed", "SequenceNumber": "7"})
        db = SessionLocal()
        assert db.query(models.VoiceCall).one().call_state == "completed"
        db.close()


class TestMediaStartValidation:
    class Twilio:
        def __init__(self, incoming):
            self.incoming = list(incoming)
        async def receive_json(self):
            return self.incoming.pop(0)

    def messages(self, internal, token, **start_changes):
        start = {"accountSid": "AC11111111111111111111111111111111", "callSid": "CA-start", "streamSid": "MZ-start",
                 "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                 "customParameters": {"voice_call_id": internal, "stream_token": token}}
        start.update(start_changes)
        return [{"event": "connected", "protocol": "Call", "version": "1.0.0"}, {"event": "start", "start": start}]

    def test_unexpected_account_sid_is_rejected_without_consuming_the_token(self):
        call_id, internal, token = _voice_call("CA-start")
        db = SessionLocal()
        with pytest.raises(ValueError):
            asyncio.run(realtime_bridge._authenticate_twilio_start(self.Twilio(self.messages(internal, token, accountSid="ACother")), {"db": db, "config": VoiceConfig.from_env()}))
        assert db.query(models.VoiceStreamToken).one().consumed_at is None
        db.close()

    def test_duplicate_start_cannot_change_the_authenticated_stream(self):
        call_id, internal, token = _voice_call("CA-start")
        db = SessionLocal()
        state = {"db": db, "config": VoiceConfig.from_env(), "stopped": False, "started": False}
        asyncio.run(realtime_bridge._authenticate_twilio_start(self.Twilio(self.messages(internal, token)), state))
        second = self.Twilio([{"event": "start", "start": {"streamSid": "MZ-evil", "callSid": "CA-start"}},
                              {"event": "media", "streamSid": "MZ-evil", "media": {"payload": "AAAA"}}])

        class Sink:
            async def send_json(self, value):
                raise AssertionError("audio for another stream must never be forwarded")

        with pytest.raises(ValueError):
            asyncio.run(realtime_bridge._twilio_to_openai(second, Sink(), state))
        assert state["stream_sid"] == "MZ-start" and db.get(models.VoiceCall, call_id).provider_stream_sid == "MZ-start"
        db.close()


class FakeOpenAIEvents:
    """Plays scripted events, then ends the loop with a disconnect."""
    def __init__(self, events, fail_on=None):
        self.events, self.sent, self.fail_on = list(events), [], fail_on
    async def receive_json(self):
        if self.events:
            return self.events.pop(0)
        raise realtime_bridge.WebSocketDisconnect()
    async def send_json(self, value):
        if self.fail_on and value.get("type") == self.fail_on:
            raise ConnectionError("simulated provider disconnect")
        self.sent.append(value)
    async def close(self):
        pass


class FakeTwilioSink:
    def __init__(self):
        self.sent = []
    async def send_json(self, value):
        self.sent.append(value)


class FakeTwilioMarks:
    def __init__(self, names):
        self.messages = [{"event": "mark", "streamSid": "MZ", "mark": {"name": n}} for n in names]
    async def receive_json(self):
        if self.messages:
            return self.messages.pop(0)
        raise realtime_bridge.WebSocketDisconnect()


def _run_openai(state, events, gateway=None):
    ai, ws = FakeOpenAIEvents(events), FakeTwilioSink()
    with pytest.raises(realtime_bridge.WebSocketDisconnect):
        asyncio.run(realtime_bridge._openai_to_twilio(ws, ai, state, gateway or object()))
    return ws, ai


def _marks(state, *names):
    with pytest.raises(realtime_bridge.WebSocketDisconnect):
        asyncio.run(realtime_bridge._twilio_to_openai(FakeTwilioMarks(names), None, state))


AUDIO_100MS = base64.b64encode(b"\xff" * 800).decode()
SPEECH = {"type": "input_audio_buffer.speech_started"}


def _item(item_id):
    return {"type": "response.output_item.added", "item": {"type": "message", "id": item_id}}


def _delta(item_id=None):
    event = {"type": "response.output_audio.delta", "delta": AUDIO_100MS}
    if item_id:
        event["item_id"] = item_id
    return event


def _truncates(ai):
    return [m for m in ai.sent if m.get("type") == "conversation.item.truncate"]


class TestBargeInStateMachine:
    def state(self):
        return {"stopped": False, "stream_sid": "MZ"}

    def test_truncates_at_the_heard_position_and_never_beyond_what_was_generated(self):
        state = self.state()
        _run_openai(state, [_item("a"), _delta("a"), _delta("a"), _delta("a")])
        _marks(state, "audio-1-100", "audio-1-200")
        assert state["played_ms"] == 200
        _marks(state, "audio-1-99999")
        assert state["played_ms"] == 300  # clamped to the 300 ms actually generated
        _marks(state, "audio-1-100")
        assert state["played_ms"] == 300  # never moves backwards
        state["played_ms"] = 200
        ws, ai = _run_openai(state, [SPEECH])
        (truncate,) = _truncates(ai)
        assert truncate["item_id"] == "a" and truncate["audio_end_ms"] == 200
        assert truncate["event_id"].startswith(realtime_bridge.RECOVERABLE_TAG)
        assert [m["event"] for m in ws.sent] == ["clear"]

    def test_stale_marks_after_clear_do_not_advance_the_next_response(self):
        state = self.state()
        _run_openai(state, [_item("a"), _delta("a"), _delta("a"), _delta("a"), SPEECH])
        _marks(state, "audio-1-100", "audio-1-200", "audio-1-300")  # Twilio echoes pending marks after clear
        assert state["played_ms"] == 0
        _run_openai(state, [_item("b"), _delta("b")])
        _marks(state, "audio-1-300")  # still stale: old generation
        assert state["played_ms"] == 0
        ws, ai = _run_openai(state, [SPEECH])
        (truncate,) = _truncates(ai)
        assert truncate["item_id"] == "b" and truncate["audio_end_ms"] == 0

    def test_speech_with_no_active_assistant_audio_clears_but_never_truncates(self):
        state = self.state()
        ws, ai = _run_openai(state, [SPEECH, SPEECH])
        assert _truncates(ai) == [] and [m["event"] for m in ws.sent] == ["clear", "clear"]
        _run_openai(state, [_item("a"), _delta("a")])
        _marks(state, "audio-%d-100" % state["generation"])  # fully played
        ws, ai = _run_openai(state, [SPEECH])
        assert _truncates(ai) == []

    def test_repeated_barge_in_truncates_once_and_late_audio_is_dropped(self):
        state = self.state()
        ws, ai = _run_openai(state, [_item("a"), _delta("a"), SPEECH, SPEECH, SPEECH])
        assert len(_truncates(ai)) == 1
        assert [m["event"] for m in ws.sent] == ["media", "mark", "clear", "clear", "clear"]
        late, _ = _run_openai(state, [_delta("a")])  # provider still streaming the interrupted item
        assert late.sent == []
        fresh, _ = _run_openai(state, [_item("b"), _delta("b")])
        assert [m["event"] for m in fresh.sent] == ["media", "mark"]


class TestRealtimeErrorClassification:
    def call_state(self):
        call_id, *_ = _voice_call("CA-err")
        db = SessionLocal()
        return db, {"stopped": False, "stream_sid": "MZ", "db": db, "call": db.get(models.VoiceCall, call_id), "config": VoiceConfig.from_env()}

    def provider_events(self, db):
        return db.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.event_type == "provider_error").all()

    def test_classification_rules(self):
        c = realtime_bridge.classify_realtime_error
        assert c({"error": {"type": "invalid_request_error", "code": None, "event_id": "ai-recoverable-truncate-1"}}) == "recoverable"
        assert c({"error": {"type": "invalid_request_error", "code": "response_cancel_not_active"}}) == "recoverable"
        assert c({"error": {"type": "authentication_error"}}) == "fatal"
        assert c({"error": {"type": "invalid_request_error", "code": "invalid_api_key"}}) == "fatal"
        assert c({"error": {"type": "server_error"}}) == "fatal"
        assert c({"error": {"type": "something_new", "code": "mystery"}}) == "unknown"
        assert c({"type": "error"}) == "unknown" and c({"error": "garbage"}) == "unknown"

    def test_recoverable_error_is_audited_and_the_call_keeps_going(self):
        db, state = self.call_state()
        error = {"type": "error", "error": {"type": "invalid_request_error", "code": "x", "message": "SECRET provider text", "event_id": "ai-recoverable-truncate-3"}}
        ws, ai = _run_openai(state, [error, _item("a"), _delta("a")])
        assert [m["event"] for m in ws.sent] == ["media", "mark"]  # processing continued after the error
        (event,) = self.provider_events(db)
        assert event.metadata_json["classification"] == "recoverable" and "SECRET" not in str(event.metadata_json)
        assert db.get(models.VoiceCall, state["call"].id).call_state != "failed"
        db.close()

    @pytest.mark.parametrize("error", [{"type": "authentication_error", "code": "invalid_api_key", "message": "bad key sk-secret"}, {"type": "server_error"}, {"type": "brand_new_kind", "code": "???"}])
    def test_fatal_and_unknown_errors_fail_closed(self, error):
        db, state = self.call_state()
        with pytest.raises(realtime_bridge.RealtimeFatalError) as raised:
            asyncio.run(realtime_bridge._openai_to_twilio(FakeTwilioSink(), FakeOpenAIEvents([{"type": "error", "error": error}]), state, object()))
        assert "sk-secret" not in str(raised.value)
        (event,) = self.provider_events(db)
        assert event.result_status == "failed" and "sk-secret" not in str(event.metadata_json)
        db.close()

    def test_a_flood_of_recoverable_errors_eventually_ends_the_call(self):
        db, state = self.call_state()
        flood = [{"type": "error", "error": {"code": "response_cancel_not_active"}}] * (realtime_bridge.MAX_RECOVERABLE_ERRORS_PER_CALL + 1)
        with pytest.raises(realtime_bridge.RealtimeFatalError):
            asyncio.run(realtime_bridge._openai_to_twilio(FakeTwilioSink(), FakeOpenAIEvents(flood), state, object()))
        db.close()

    def test_unknown_event_types_are_ignored_safely(self):
        ws, ai = _run_openai({"stopped": False, "stream_sid": "MZ"}, [{"type": "brand.new.event", "x": 1}, {"type": "rate_limits.updated"}, {}])
        assert ws.sent == [] and ai.sent == []


class TestToolFailuresMidCall:
    def start_messages(self, internal, token, sid):
        return [{"event": "connected", "protocol": "Call", "version": "1.0.0"},
                {"event": "start", "start": {"accountSid": "AC11111111111111111111111111111111", "callSid": sid, "streamSid": "MZ-" + sid, "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}, "customParameters": {"voice_call_id": internal, "stream_token": token}}}]

    def function_call(self, name="get_salon_info", arguments="{}"):
        return {"type": "response.done", "response": {"output": [{"type": "function_call", "name": name, "arguments": arguments, "call_id": "fc-1"}]}}

    def test_openai_disconnect_while_answering_a_tool_fails_the_call_cleanly(self):
        call_id, internal, token = _voice_call("CA-mid1")
        messages = self.start_messages(internal, token, "CA-mid1")

        class Twilio:
            async def accept(self): pass
            async def receive_json(self):
                if messages:
                    return messages.pop(0)
                await asyncio.Event().wait()
            async def send_json(self, value): pass
            async def close(self, code): pass

        ai = FakeOpenAIEvents([{"type": "session.created"}, {"type": "session.updated"}, self.function_call()], fail_on="conversation.item.create")

        async def connect(_config):
            return ai

        asyncio.run(realtime_bridge.run_media_bridge(Twilio(), config=VoiceConfig.from_env(), db_factory=SessionLocal, gateway=object(), openai_factory=connect))
        verify = SessionLocal()
        assert verify.get(models.VoiceCall, call_id).call_state == "failed"
        assert verify.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "failed_call").count() == 1
        verify.close()

    def test_caller_hangup_while_a_tool_is_running_completes_the_call(self, monkeypatch):
        import threading
        call_id, internal, token = _voice_call("CA-mid2")
        messages = self.start_messages(internal, token, "CA-mid2")
        release = threading.Event()
        monkeypatch.setattr(realtime_bridge, "_execute_tool_with_own_session", lambda state, gateway, item: release.wait(1.5) or {"late": True})

        class Twilio:
            async def accept(self): pass
            async def receive_json(self):
                if messages:
                    return messages.pop(0)
                await asyncio.sleep(0.3)
                return {"event": "stop", "streamSid": "MZ-CA-mid2", "stop": {"callSid": "CA-mid2"}}
            async def send_json(self, value): pass
            async def close(self, code): pass

        class OpenAI(FakeOpenAIEvents):
            async def receive_json(self):
                if self.events:
                    return self.events.pop(0)
                await asyncio.Event().wait()

        ai = OpenAI([{"type": "session.created"}, {"type": "session.updated"}, self.function_call()])

        async def connect(_config):
            return ai

        asyncio.run(realtime_bridge.run_media_bridge(Twilio(), config=VoiceConfig.from_env(), db_factory=SessionLocal, gateway=object(), openai_factory=connect))
        release.set()
        verify = SessionLocal()
        assert verify.get(models.VoiceCall, call_id).call_state == "completed"
        assert verify.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "failed_call").count() == 0
        verify.close()

    def test_model_requesting_a_prohibited_tool_gets_a_refusal_and_nothing_changes(self):
        import json
        call_id, *_ = _voice_call("CA-mid3")
        db = SessionLocal()
        state = {"stopped": False, "stream_sid": "MZ", "db": db, "db_factory": SessionLocal, "call": db.get(models.VoiceCall, call_id), "config": VoiceConfig.from_env()}
        ws, ai = _run_openai(state, [self.function_call("reschedule_booking", '{"customer_name": "x"}')])
        output = json.loads(ai.sent[0]["item"]["output"])
        assert output["ok"] is False and ai.sent[1] == {"type": "response.create"}
        assert db.query(models.Appointment).count() == 0
        db.close()


class TestToolOutputBatching:
    """One model response with N tool calls -> N outputs, then exactly one response.create."""

    def calls(self, n):
        return {"type": "response.done", "response": {"output": [
            {"type": "function_call", "name": "get_service_details", "arguments": "{}", "call_id": f"fc-{i}"} for i in range(1, n + 1)]}}

    def run(self, monkeypatch, events):
        monkeypatch.setattr(realtime_bridge, "_execute_tool_with_own_session", lambda state, gateway, item: {"call": item["call_id"]})
        _, ai = _run_openai({"stopped": False, "config": VoiceConfig.from_env()}, events)
        return [m["item"]["call_id"] if m["type"] == "conversation.item.create" else m["type"] for m in ai.sent]

    def test_one_tool_call_sends_one_output_then_one_response_create(self, monkeypatch):
        assert self.run(monkeypatch, [self.calls(1)]) == ["fc-1", "response.create"]

    def test_two_tool_calls_send_both_outputs_before_a_single_response_create(self, monkeypatch):
        assert self.run(monkeypatch, [self.calls(2)]) == ["fc-1", "fc-2", "response.create"]

    def test_three_tool_calls_send_all_outputs_before_a_single_response_create(self, monkeypatch):
        assert self.run(monkeypatch, [self.calls(3)]) == ["fc-1", "fc-2", "fc-3", "response.create"]

    def test_separate_responses_each_get_their_own_response_create(self, monkeypatch):
        assert self.run(monkeypatch, [self.calls(2), self.calls(1)]) == ["fc-1", "fc-2", "response.create", "fc-1", "response.create"]

    def test_responses_without_tool_calls_never_send_response_create(self, monkeypatch):
        text = {"type": "response.done", "response": {"output": [{"type": "message"}]}}
        assert self.run(monkeypatch, [text, {"type": "response.done", "response": {"output": []}}]) == []

    def test_a_failing_tool_still_gets_an_output_and_the_batch_one_response_create(self, monkeypatch):
        def flaky(state, gateway, item):
            if item["call_id"] == "fc-1":
                raise RuntimeError("boom")
            return {"ok": True}
        monkeypatch.setattr(realtime_bridge, "_execute_tool_with_own_session", flaky)
        state = {"stopped": False, "config": VoiceConfig.from_env(), "db": type("D", (), {"rollback": lambda self: None})(), "call": None}
        _, ai = _run_openai(state, [self.calls(2)])
        assert [m["type"] for m in ai.sent] == ["conversation.item.create", "conversation.item.create", "response.create"]
        assert "temporarily unavailable" in ai.sent[0]["item"]["output"]


# ── Owner service catalog ─────────────────────────────────────────────────────

def _catalog():
    return {item["name"]: item for item in client.get("/booking-services").json()}


def _new_service(**overrides):
    payload = {"name": "Test Service", "category": "Test", "duration_minutes": 45, **overrides}
    return client.post("/booking-services", json=payload)


class TestOwnerServiceCatalog:
    def test_seeded_services_are_listed_including_inactive(self):
        assert "Gel Manicure" in _catalog()
        service_id = _catalog()["Gel Manicure"]["id"]
        client.patch(f"/booking-services/{service_id}", json={"is_active": False})
        assert _catalog()["Gel Manicure"]["is_active"] is False
        assert "Gel Manicure" not in {s["name"] for s in client.get("/services").json()}

    def test_create_service_and_duplicate_name_rejected_case_insensitively(self):
        created = _new_service(price=25, buffer_before_minutes=5, buffer_after_minutes=10)
        assert created.status_code == 201
        body = created.json()
        assert body["name"] == "Test Service" and body["price"] == 25.0 and body["is_active"] is True
        assert (body["buffer_before_minutes"], body["buffer_after_minutes"]) == (5, 10)
        assert _new_service(name="  test SERVICE ").status_code == 409
        service_id = _catalog()["Gel Manicure"]["id"]
        assert client.patch(f"/booking-services/{service_id}", json={"name": "test service"}).status_code == 409
        assert client.patch(f"/booking-services/{service_id}", json={"name": "Gel Manicure"}).status_code == 200

    def test_update_duration_price_buffers_and_null_price(self):
        service_id = _catalog()["Gel Manicure"]["id"]
        updated = client.patch(f"/booking-services/{service_id}", json={"duration_minutes": 75, "price": 38.5, "buffer_before_minutes": 5, "buffer_after_minutes": 10}).json()
        assert (updated["duration_minutes"], updated["price"], updated["buffer_before_minutes"], updated["buffer_after_minutes"]) == (75, 38.5, 5, 10)
        assert _catalog()["Gel Manicure"]["duration_minutes"] == 75
        # a patch that does not mention price leaves it alone; explicit null clears it
        assert client.patch(f"/booking-services/{service_id}", json={"duration_minutes": 80}).json()["price"] == 38.5
        assert client.patch(f"/booking-services/{service_id}", json={"price": None}).json()["price"] is None

    def test_invalid_values_are_rejected_and_nothing_changes(self):
        service_id = _catalog()["Gel Manicure"]["id"]
        before = _catalog()["Gel Manicure"]
        for bad in ({"duration_minutes": 0}, {"duration_minutes": -5}, {"duration_minutes": 100000}, {"buffer_before_minutes": -1},
                    {"buffer_after_minutes": -1}, {"price": -1}, {"price": 1000000}, {"name": "   "}, {"name": None},
                    {"is_active": None}, {"duration_minutes": None}, {"unknown_field": 1}):
            assert client.patch(f"/booking-services/{service_id}", json=bad).status_code in (400, 422), bad
        assert _new_service(duration_minutes=-10).status_code == 422
        assert _new_service(name="").status_code == 422
        assert _new_service(buffer_after_minutes=-1).status_code == 422
        assert _catalog()["Gel Manicure"] == before
        assert client.patch("/booking-services/999999", json={"duration_minutes": 30}).status_code == 404

    def test_technician_eligibility_update_affects_availability(self):
        day = _booking_day()
        _set_business_hours(day, time(9, 0), time(11, 0))
        service = _new_service(name="Eligibility Service", duration_minutes=60).json()
        tech = make_tech("Elig Tech", specialties="waxing").json()["id"]
        assert client.get(f"/availability?date={day.isoformat()}&service_ids={service['id']}").json() == []
        updated = client.put(f"/booking-services/{service['id']}/technicians", json={"technician_ids": [tech]})
        assert updated.status_code == 200 and updated.json()["eligible_technician_ids"] == [tech]
        slots = client.get(f"/availability?date={day.isoformat()}&service_ids={service['id']}").json()
        assert slots and all(slot["eligible_technician_ids"] == [tech] for slot in slots)
        assert client.put(f"/booking-services/{service['id']}/technicians", json={"technician_ids": []}).json()["eligible_technician_ids"] == []
        assert client.get(f"/availability?date={day.isoformat()}&service_ids={service['id']}").json() == []
        assert client.put(f"/booking-services/{service['id']}/technicians", json={"technician_ids": [tech, 999999]}).status_code == 400
        assert client.put("/booking-services/999999/technicians", json={"technician_ids": []}).status_code == 404

    def test_duration_and_buffer_changes_drive_availability_but_not_existing_appointments(self):
        day = _booking_day()
        _set_business_hours(day, time(9, 0), time(11, 0))
        service_id = _catalog()["Gel Manicure"]["id"]
        tech = make_tech("Dur Tech", specialties="manicure / pedicure, gel").json()["id"]
        client.patch(f"/booking-services/{service_id}", json={"duration_minutes": 30})
        booked = client.post("/appointments", json=_booking_payload(tech, datetime.combine(day, time(9, 0)), [service_id])).json()
        assert booked["duration_minutes"] == 30
        client.patch(f"/booking-services/{service_id}", json={"duration_minutes": 90, "price": 50})
        slots = client.get(f"/availability?date={day.isoformat()}&service_ids={service_id}").json()
        assert all(slot["total_duration_minutes"] == 90 for slot in slots)
        stored = [a for a in client.get("/appointments").json() if a["id"] == booked["id"]][0]
        assert stored["duration_minutes"] == 30
        assert stored["appointment_services"][0]["duration_minutes_snapshot"] == 30

    def test_catalog_requires_owner_session_and_csrf(self):
        anonymous = TestClient(app)
        assert anonymous.get("/booking-services").status_code == 401
        assert anonymous.post("/booking-services", json={"name": "X Service", "duration_minutes": 30}).status_code == 401
        assert anonymous.patch("/booking-services/1", json={"is_active": False}).status_code == 401
        assert anonymous.put("/booking-services/1/technicians", json={"technician_ids": []}).status_code == 401
        no_csrf = TestClient(app)
        assert no_csrf.post("/auth/login", json={"password": "test-owner-password"}).status_code == 200
        assert no_csrf.get("/booking-services").status_code == 200
        service_id = _catalog()["Gel Manicure"]["id"]
        assert no_csrf.post("/booking-services", json={"name": "No Csrf", "duration_minutes": 30}).status_code == 403
        assert no_csrf.patch(f"/booking-services/{service_id}", json={"is_active": False}).status_code == 403
        assert no_csrf.put(f"/booking-services/{service_id}/technicians", json={"technician_ids": []}).status_code == 403
        assert "No Csrf" not in _catalog() and _catalog()["Gel Manicure"]["is_active"] is True
        forged = no_csrf.patch(f"/booking-services/{service_id}", json={"is_active": False}, headers={"X-CSRF-Token": "forged"})
        assert forged.status_code == 403

    def test_no_delete_endpoint_exists(self):
        service_id = _catalog()["Gel Manicure"]["id"]
        assert client.delete(f"/booking-services/{service_id}").status_code == 405
        assert "Gel Manicure" in _catalog()

    def test_voice_tools_reflect_catalog_edits(self):
        service_id = _catalog()["Gel Manicure"]["id"]
        db = SessionLocal()
        call = voice_foundation.create_call(db, caller_phone="6025551234", called_phone="6025559999", call_id="voice-catalog")
        facade = voice_foundation.VoiceBookingFacade(db, voice_foundation.VoiceAuthorizationContext(call.id, call.call_id, 0, call.caller_phone_e164, None))

        def details():
            db.expire_all()
            return voice_tools.dispatch_voice_tool(facade, object(), "get_service_details", {"service_id": service_id})

        def listed():
            db.expire_all()
            return {item["name"]: item for item in voice_tools.dispatch_voice_tool(facade, object(), "list_services", {})}

        assert details()["price"] is None  # NULL price stays NULL: nothing to invent
        client.patch(f"/booking-services/{service_id}", json={"price": 42.5, "duration_minutes": 55})
        assert details()["price"] == 42.5 and details()["duration_minutes"] == 55
        assert listed()["Gel Manicure"]["price"] == 42.5
        client.patch(f"/booking-services/{service_id}", json={"price": None})
        assert details()["price"] is None
        client.patch(f"/booking-services/{service_id}", json={"is_active": False})
        assert "Gel Manicure" not in listed() and details() is None
        client.patch(f"/booking-services/{service_id}", json={"is_active": True})
        assert "Gel Manicure" in listed() and details() is not None
        _new_service(name="Voice New Service", price=19)
        assert listed()["Voice New Service"]["price"] == 19.0
        db.close()

    def test_voice_availability_uses_updated_duration_and_eligibility(self):
        day = _booking_day()
        _set_business_hours(day, time(9, 0), time(11, 0))
        service_id = _catalog()["Gel Manicure"]["id"]
        make_tech("Voice Slot Tech", specialties="manicure / pedicure, gel")
        client.patch(f"/booking-services/{service_id}", json={"duration_minutes": 45, "buffer_after_minutes": 15})
        db = SessionLocal()
        call = voice_foundation.create_call(db, caller_phone="6025551234", called_phone="6025559999", call_id="voice-slots")
        facade = voice_foundation.VoiceBookingFacade(db, voice_foundation.VoiceAuthorizationContext(call.id, call.call_id, 0, call.caller_phone_e164, None))
        slots = voice_tools.dispatch_voice_tool(facade, object(), "get_available_slots", {"date": day.isoformat(), "service_ids": [service_id]})
        assert slots and all(slot["total_duration_minutes"] == 60 for slot in slots)
        client.put(f"/booking-services/{service_id}/technicians", json={"technician_ids": []})
        assert voice_tools.dispatch_voice_tool(facade, object(), "get_available_slots", {"date": day.isoformat(), "service_ids": [service_id]}) == []
        db.close()

    def test_voice_allowlist_still_has_no_catalog_or_write_tools(self):
        names = {tool["name"] for tool in voice_tools.READ_ONLY_TOOL_DEFINITIONS}
        assert names == {"get_salon_info", "list_services", "get_service_details", "get_available_slots", "identify_customer_candidate", "request_owner_callback", "create_booking"}


# ── Internal service catalog contract for Check-In ────────────────────────────

INTERNAL_HEADERS = {"X-Internal-Service-Token": "test-internal-token"}


def _internal_client():
    return TestClient(app)  # no owner session: only the service token


class TestInternalServiceCatalog:
    def test_internal_endpoint_requires_the_service_token(self):
        anonymous = _internal_client()
        assert anonymous.get("/internal/services").status_code == 401
        assert anonymous.get("/internal/services", headers={"X-Internal-Service-Token": "wrong"}).status_code == 401
        assert anonymous.get("/internal/services", headers={"X-Internal-Service-Token": ""}).status_code == 401
        # an owner session alone is not the service credential
        assert client.get("/internal/services").status_code == 401
        assert anonymous.get("/internal/services", headers=INTERNAL_HEADERS).status_code == 200

    def test_internal_endpoint_fails_closed_when_no_token_is_configured(self, monkeypatch):
        monkeypatch.delenv("CHECKIN_INTERNAL_SERVICE_TOKEN", raising=False)
        assert _internal_client().get("/internal/services", headers=INTERNAL_HEADERS).status_code == 503
        assert _internal_client().get("/internal/services", headers={"X-Internal-Service-Token": ""}).status_code == 503

    def test_active_services_with_stable_ids_and_only_safe_fields(self):
        rows = _internal_client().get("/internal/services", headers=INTERNAL_HEADERS).json()
        assert rows and all(set(row) == {"id", "name", "category", "duration_minutes", "is_active"} for row in rows)
        assert all(row["is_active"] for row in rows)
        assert {row["name"]: row["id"] for row in rows} == {name: item["id"] for name, item in _catalog().items()}
        assert [row["id"] for row in rows] == sorted(row["id"] for row in rows)

    def test_inactive_services_are_omitted_unless_requested_and_ids_survive_rename(self):
        service_id = _catalog()["Gel Manicure"]["id"]
        client.patch(f"/booking-services/{service_id}", json={"is_active": False})
        internal = _internal_client()
        assert service_id not in {r["id"] for r in internal.get("/internal/services", headers=INTERNAL_HEADERS).json()}
        everything = internal.get("/internal/services?include_inactive=true", headers=INTERNAL_HEADERS).json()
        assert next(r for r in everything if r["id"] == service_id)["is_active"] is False
        client.patch(f"/booking-services/{service_id}", json={"is_active": True, "name": "Gel Mani Renamed"})
        renamed = {r["id"]: r["name"] for r in internal.get("/internal/services", headers=INTERNAL_HEADERS).json()}
        assert renamed[service_id] == "Gel Mani Renamed"

    def test_internal_endpoint_is_read_only(self):
        before = _catalog()
        internal = _internal_client()
        for method in ("post", "put", "patch", "delete"):
            response = getattr(internal, method)("/internal/services", headers=INTERNAL_HEADERS)
            assert response.status_code in (401, 403, 405), method  # token never substitutes for owner auth
        service_id = before["Gel Manicure"]["id"]
        assert internal.patch(f"/booking-services/{service_id}", json={"is_active": False}, headers=INTERNAL_HEADERS).status_code == 401
        assert internal.post("/booking-services", json={"name": "Sneaky", "duration_minutes": 30}, headers=INTERNAL_HEADERS).status_code == 401
        assert _catalog() == before

    def test_voice_allowlist_and_public_services_unchanged(self):
        names = {tool["name"] for tool in voice_tools.READ_ONLY_TOOL_DEFINITIONS}
        assert names == {"get_salon_info", "list_services", "get_service_details", "get_available_slots", "identify_customer_candidate", "request_owner_callback", "create_booking"}
        public = client.get("/services").json()
        assert {"id", "name", "price", "duration_minutes", "is_active"} <= set(public[0])


class TestIdFirstCheckinServiceResolution:
    def _eligible_tech(self, name, service_id):
        tech_id = make_tech(name, specialties="waxing").json()["id"]
        assert client.put(f"/booking-services/{service_id}/technicians", json={"technician_ids": [tech_id]}).status_code == 200
        return tech_id

    def test_service_ids_are_preferred_over_unrelated_service_name_text(self):
        service_id = _catalog()["Gel Manicure"]["id"]
        wanted = self._eligible_tech("Id First Tech", service_id)
        make_tech("Name Only Tech", specialties="manicure / pedicure, gel")
        response = auto_assign("Ida", "totally unrelated text", service_ids=[service_id])
        assert response.status_code == 200, response.text
        turn = response.json()
        assert turn["technician_id"] == wanted
        assert turn["service_name"] == "Gel Manicure"  # canonical Owner name, not the caller's text

    def test_unknown_or_inactive_id_fails_safely_without_name_fallback(self):
        make_tech("Fallback Tech", specialties="acrylic, gel, manicure / pedicure")
        before = len(client.get("/turns").json())
        unknown = auto_assign("Ulla", "Acrylic Full Set", service_ids=[999999])
        assert unknown.status_code == 400 and "Unknown or inactive service id" in unknown.json()["detail"]
        mixed = auto_assign("Ulla", "Acrylic Full Set", service_ids=[_catalog()["Acrylic Full Set"]["id"], 999999])
        assert mixed.status_code == 400
        inactive_id = _catalog()["Gel Manicure"]["id"]
        client.patch(f"/booking-services/{inactive_id}", json={"is_active": False})
        assert auto_assign("Ulla", "Gel Manicure", service_ids=[inactive_id]).status_code == 400
        preferred = client.post("/turns/assign-preferred", json={"customer_name": "Ulla", "service_name": "Acrylic Full Set", "service_ids": [999999], "preferred_technician_id": 1})
        assert preferred.status_code == 400
        assert len(client.get("/turns").json()) == before

    def test_renaming_a_service_does_not_break_id_resolution(self):
        service_id = _catalog()["Gel Manicure"]["id"]
        tech_id = self._eligible_tech("Rename Tech", service_id)
        client.patch(f"/booking-services/{service_id}", json={"name": "Renamed Gel"})
        turn = auto_assign("Rena", "Gel Manicure", service_ids=[service_id]).json()
        assert turn["technician_id"] == tech_id and turn["service_name"] == "Renamed Gel"

    def test_preferred_assignment_checks_id_eligibility(self):
        service_id = _catalog()["Gel Manicure"]["id"]
        other = make_tech("Pref Other", specialties="manicure / pedicure, gel").json()["id"]
        eligible = self._eligible_tech("Pref Eligible", service_id)  # the PUT then makes only this technician eligible
        ok = client.post("/turns/assign-preferred", json={"customer_name": "Pia", "service_name": "x", "service_ids": [service_id], "preferred_technician_id": eligible})
        assert ok.status_code == 200 and ok.json()["technician_id"] == eligible
        refused = client.post("/turns/assign-preferred", json={"customer_name": "Pam", "service_name": "x", "service_ids": [service_id], "preferred_technician_id": other})
        assert refused.status_code == 400  # not eligible for that id, whatever the name text says

    def test_legacy_service_name_payloads_still_work(self):
        tech_id = make_tech("Legacy Tech", specialties="acrylic").json()["id"]
        response = auto_assign("Lea", "Acrylic Full Set")
        assert response.status_code == 200 and response.json()["technician_id"] == tech_id
        assert response.json()["service_name"] == "Acrylic Full Set"
        assert auto_assign("Lou", "Acrylic Full Set", service_ids=[]).status_code in (200, 400)  # empty ids = legacy path

    def test_appointments_prefer_ids_and_never_name_map_an_unknown_id(self):
        day = _booking_day()
        _set_business_hours(day, time(9, 0), time(18, 0))
        service_id = _catalog()["Gel Manicure"]["id"]
        tech_id = make_tech("Appt Tech", specialties="manicure / pedicure, gel").json()["id"]
        start = datetime.combine(day, time(10, 0))
        ok = client.post("/appointments", json=_booking_payload(tech_id, start, [service_id], service_name="Acrylic Full Set"))
        assert ok.status_code == 200, ok.text
        assert [s["service_name_snapshot"] for s in ok.json()["appointment_services"]] == ["Gel Manicure"]
        bad = client.post("/appointments", json=_booking_payload(tech_id, datetime.combine(day, time(13, 0)), [999999], service_name="Gel Manicure"))
        assert bad.status_code == 400


# ── Check-In service_ids -> Owner assignment ──────────────────────────────────

def _checkin_item(visit_id=501, services=("Gel Manicure",), phone="6025551234", **extra):
    item = {
        "visit_id": visit_id, "customer_id": 24, "position": 1, "full_name": "Ida Checkin",
        "phone_number": phone, "phone_e164": "+1" + phone,
        "checked_in_at": datetime.combine(date.today(), time(11, 55)).isoformat(),
        "services": list(services),
    }
    item.update(extra)
    return item


class _checkins_from:
    """Context manager: Check-In's /today-checkins returns these items."""
    def __init__(self, *items):
        self.items = list(items)

    def __enter__(self):
        items = self.items

        class Gateway:
            def get_today_checkins(self):
                return items

        app.dependency_overrides[main_module.get_customer_gateway] = lambda: Gateway()
        return self

    def __exit__(self, *exc):
        app.dependency_overrides.pop(main_module.get_customer_gateway, None)


def _queue():
    return client.get("/checkins/today")


def _turn_body_from(item, **extra):
    """What the dashboard posts for a queue item (see queue.js autoAssignCheckin)."""
    body = {
        "customer_name": item["full_name"], "customer_phone": item["phone_number"],
        "service_name": ", ".join(item["services"]), "source": "checkin",
        "checkin_visit_id": item["visit_id"], "checkin_customer_id": item["customer_id"],
    }
    if item.get("service_ids"):
        body["service_ids"] = item["service_ids"]
    body.update(extra)
    return body


def _only_eligible(name, service_id):
    """A technician whose ONLY route to the service is the Owner catalog, not specialty text."""
    tech_id = make_tech(name, specialties="waxing").json()["id"]
    assert client.put(f"/booking-services/{service_id}/technicians", json={"technician_ids": [tech_id]}).status_code == 200
    return tech_id


class TestCheckinServiceIdsFlow:
    def test_service_ids_are_parsed_and_exposed_with_names_untouched(self):
        gel = _catalog()["Gel Manicure"]["id"]
        tech = _only_eligible("Flow Tech", gel)
        with _checkins_from(_checkin_item(service_ids=[gel])):
            response = _queue()
        assert response.status_code == 200
        item = response.json()["checkins"][0]
        assert item["service_ids"] == [gel] and item["services"] == ["Gel Manicure"]
        assert item["unavailable_service_ids"] == [] and item["eligible_technician_ids"] == [tech]

    def test_service_ids_propagate_into_auto_assignment_and_canonical_name_wins(self):
        gel = _catalog()["Gel Manicure"]["id"]
        tech = _only_eligible("Auto Flow Tech", gel)
        make_tech("Name Match Tech", specialties="manicure / pedicure, gel")  # would win on the name path
        with _checkins_from(_checkin_item(services=["whatever text Check-In stored"], service_ids=[gel])):
            item = _queue().json()["checkins"][0]
        turn = client.post("/turns/assign-auto", json=_turn_body_from(item))
        assert turn.status_code == 200, turn.text
        assert turn.json()["technician_id"] == tech
        assert turn.json()["service_name"] == "Gel Manicure"

    def test_service_ids_propagate_into_preferred_and_assign_next(self):
        gel = _catalog()["Gel Manicure"]["id"]
        tech = _only_eligible("Pref Flow Tech", gel)
        with _checkins_from(_checkin_item(visit_id=601, service_ids=[gel]), _checkin_item(visit_id=602, phone="6025550002", service_ids=[gel])):
            items = _queue().json()["checkins"]
        preferred = client.post("/turns/assign-preferred", json=_turn_body_from(items[0], preferred_technician_id=tech))
        assert preferred.status_code == 200 and preferred.json()["technician_id"] == tech
        manual = client.post("/turns/assign-next", json=_turn_body_from(items[1], technician_id=tech))
        assert manual.status_code == 200 and manual.json()["service_name"] == "Gel Manicure"
        bad = client.post("/turns/assign-next", json=_turn_body_from(items[1], technician_id=tech, service_ids=[999999], checkin_visit_id=603))
        assert bad.status_code == 400

    def test_renamed_service_still_assigns_by_id_with_the_new_name(self):
        gel = _catalog()["Gel Manicure"]["id"]
        tech = _only_eligible("Rename Flow Tech", gel)
        with _checkins_from(_checkin_item(service_ids=[gel])):
            item = _queue().json()["checkins"][0]  # Check-In still shows the old name snapshot
        client.patch(f"/booking-services/{gel}", json={"name": "Gel Mani Deluxe"})
        turn = client.post("/turns/assign-auto", json=_turn_body_from(item))
        assert turn.status_code == 200 and turn.json()["technician_id"] == tech
        assert turn.json()["service_name"] == "Gel Mani Deluxe"

    def test_malformed_service_ids_fail_safely(self):
        for bad in ("10", 10, [1.5], ["a"], [True], [-3], [0], [1] * 21, {"id": 1}, [[1]]):
            with _checkins_from(_checkin_item(service_ids=bad)):
                response = _queue()
            assert response.status_code == 503, bad
            assert "malformed service ids" in response.json()["detail"]
        assert client.get("/turns").json() == []

    def test_unknown_and_inactive_ids_are_flagged_and_never_fall_back_to_the_name(self):
        make_tech("Fallback Tech", specialties="manicure / pedicure, gel")
        gel = _catalog()["Gel Manicure"]["id"]
        client.patch(f"/booking-services/{gel}", json={"is_active": False})
        with _checkins_from(_checkin_item(visit_id=701, service_ids=[gel]), _checkin_item(visit_id=702, phone="6025550003", service_ids=[999999])):
            items = _queue().json()["checkins"]
        assert [i["visit_id"] for i in items] == [701, 702]  # the visits are preserved
        assert items[0]["unavailable_service_ids"] == [gel] and items[0]["eligible_technician_ids"] == []
        assert items[1]["unavailable_service_ids"] == [999999] and items[1]["eligible_technician_ids"] == []
        for item in items:
            assert client.post("/turns/assign-auto", json=_turn_body_from(item)).status_code == 400
            assert client.post("/turns/assign-preferred", json=_turn_body_from(item, preferred_technician_id=1)).status_code == 400
        assert client.get("/turns").json() == []

    def test_deactivation_after_check_in_is_flagged_then_clears_on_reactivation(self):
        gel = _catalog()["Gel Manicure"]["id"]
        _only_eligible("Toggle Tech", gel)
        with _checkins_from(_checkin_item(service_ids=[gel])):
            assert _queue().json()["checkins"][0]["unavailable_service_ids"] == []
            client.patch(f"/booking-services/{gel}", json={"is_active": False})
            assert _queue().json()["checkins"][0]["unavailable_service_ids"] == [gel]
            client.patch(f"/booking-services/{gel}", json={"is_active": True})
            item = _queue().json()["checkins"][0]
        assert item["unavailable_service_ids"] == [] and client.post("/turns/assign-auto", json=_turn_body_from(item)).status_code == 200

    def test_legacy_visits_without_or_with_empty_service_ids_use_the_name_path(self):
        tech = make_tech("Legacy Flow Tech", specialties="acrylic").json()["id"]
        with _checkins_from(_checkin_item(visit_id=801, services=["Acrylic Full Set"]),
                            _checkin_item(visit_id=802, phone="6025550004", services=["Acrylic Full Set"], service_ids=[])):
            items = _queue().json()["checkins"]
        for item in items:
            assert item["service_ids"] == [] and item["eligible_technician_ids"] is None and item["unavailable_service_ids"] == []
        first = client.post("/turns/assign-auto", json=_turn_body_from(items[0]))
        assert first.status_code == 200 and first.json()["technician_id"] == tech
        assert first.json()["service_name"] == "Acrylic Full Set"
        assert client.post("/turns/assign-auto", json=_turn_body_from(items[1])).status_code in (200, 400)  # tech is busy: legacy rules apply

    def test_same_visit_never_creates_a_duplicate_turn(self):
        gel = _catalog()["Gel Manicure"]["id"]
        _only_eligible("Dedupe Tech", gel)
        with _checkins_from(_checkin_item(visit_id=901, service_ids=[gel])):
            item = _queue().json()["checkins"][0]
        first = client.post("/turns/assign-auto", json=_turn_body_from(item)).json()
        second = client.post("/turns/assign-auto", json=_turn_body_from(item)).json()
        assert first["id"] == second["id"] and len(client.get("/turns").json()) == 1

    def test_appointment_match_and_link_still_work_with_service_ids(self):
        gel = _catalog()["Gel Manicure"]["id"]
        make_tech("Link Tech", specialties="manicure / pedicure, gel")
        appointment = make_appointment(customer_phone="6025551234").json()
        with _checkins_from(_checkin_item(visit_id=951, service_ids=[gel])):
            item = _queue().json()["checkins"][0]
        assert item["appointment_match"]["outcome"] == "exact_match"
        turn = client.post("/turns/assign-auto", json=_turn_body_from(item, appointment_id=item["appointment_match"]["appointment"]["id"]))
        assert turn.status_code == 200 and turn.json()["appointment_id"] == appointment["id"]

    def test_voice_allowlist_unchanged(self):
        assert {tool["name"] for tool in voice_tools.READ_ONLY_TOOL_DEFINITIONS} == {
            "get_salon_info", "list_services", "get_service_details", "get_available_slots", "identify_customer_candidate", "request_owner_callback", "create_booking"}


# ── Realtime session gate and failure observability ──────────────────────────

import json as _json  # noqa: E402
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK  # noqa: E402
from websockets.frames import Close  # noqa: E402


def _bridge_start(internal, token, sid):
    return [{"event": "connected", "protocol": "Call", "version": "1.0.0"},
            {"event": "start", "start": {"accountSid": "AC11111111111111111111111111111111", "callSid": sid, "streamSid": "MZ-" + sid,
                                         "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                                         "customParameters": {"voice_call_id": internal, "stream_token": token}}}]


class BridgeTwilio:
    """Scripted Twilio side. `after_start` messages are returned one per read; then it idles."""
    def __init__(self, internal, token, sid, after_start=(), on_stop_read=None):
        self.messages = _bridge_start(internal, token, sid)
        self.after_start = list(after_start)
        self.reads_after_start = 0
        self.closed_with = []
        self.on_stop_read = on_stop_read

    async def accept(self): pass

    async def receive_json(self):
        if self.messages:
            return self.messages.pop(0)
        self.reads_after_start += 1
        if self.after_start:
            message = self.after_start.pop(0)
            if message.get("event") == "stop" and self.on_stop_read:
                self.on_stop_read()
            return message
        await asyncio.Event().wait()

    async def send_json(self, value): pass

    async def close(self, code): self.closed_with.append(code)


class BridgeOpenAI:
    """Scripted OpenAI side: plays `script` (events, or exceptions to raise), then idles."""
    def __init__(self, script):
        self.script, self.sent, self.closed = list(script), [], False
        self.on_receive = None

    async def receive_json(self):
        if self.on_receive:
            self.on_receive()
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            if callable(item):
                return await item()
            return item
        await asyncio.Event().wait()

    async def send_json(self, value): self.sent.append(value)

    async def close(self): self.closed = True


READY = [{"type": "session.created"}, {"type": "session.updated"}]


def _run_bridge(twilio, ai):
    async def main():
        async def connect(_config): return ai
        await realtime_bridge.run_media_bridge(twilio, config=VoiceConfig.from_env(), db_factory=SessionLocal, gateway=object(), openai_factory=connect)
        await asyncio.sleep(0)
        return [t.get_name() for t in asyncio.all_tasks() if t.get_name() in ("twilio_to_openai", "openai_to_twilio") and not t.done()]
    return asyncio.run(main())


def _call_events(call_id, event_type=None):
    db = SessionLocal()
    try:
        query = db.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.call_id == call_id)
        if event_type:
            query = query.filter(models.VoiceCallEvent.event_type == event_type)
        return query.all()
    finally:
        db.close()


def _call_state(call_id):
    db = SessionLocal()
    try:
        return db.get(models.VoiceCall, call_id).call_state
    finally:
        db.close()


MEDIA = {"event": "media", "streamSid": "MZ-CA-h", "media": {"payload": base64.b64encode(b"\xff" * 160).decode()}}


class TestRealtimeSessionGate:
    def test_ready_handshake_then_greeting_then_media_in_order_and_normal_hangup_completes(self):
        call_id, internal, token = _voice_call("CA-h1")
        media = {**MEDIA, "streamSid": "MZ-CA-h1"}
        twilio = BridgeTwilio(internal, token, "CA-h1", [media, {"event": "stop", "streamSid": "MZ-CA-h1", "stop": {"callSid": "CA-h1"}}])
        ai = BridgeOpenAI(READY)
        assert _run_bridge(twilio, ai) == []
        assert [m["type"] for m in ai.sent] == ["session.update", "response.create", "input_audio_buffer.append"]
        assert _call_state(call_id) == "completed" and ai.closed
        assert _call_events(call_id, "failed") == [] and _call_events(call_id, "provider_error") == []

    def test_caller_audio_is_not_read_or_forwarded_before_session_updated(self):
        call_id, internal, token = _voice_call("CA-h2")
        media = {**MEDIA, "streamSid": "MZ-CA-h2"}
        twilio = BridgeTwilio(internal, token, "CA-h2", [media, {"event": "stop", "streamSid": "MZ-CA-h2", "stop": {"callSid": "CA-h2"}}])
        seen = {}

        async def updated():
            seen["twilio_reads_when_updated"] = twilio.reads_after_start
            seen["sent_when_updated"] = [m["type"] for m in ai.sent]
            return {"type": "session.updated"}

        ai = BridgeOpenAI([{"type": "session.created"}, updated])
        _run_bridge(twilio, ai)
        assert seen == {"twilio_reads_when_updated": 0, "sent_when_updated": ["session.update"]}
        assert "response.create" not in seen["sent_when_updated"]

    def test_openai_error_before_session_updated_fails_cleanly_with_safe_metadata(self):
        call_id, internal, token = _voice_call("CA-h3")
        error = {"type": "error", "error": {"type": "insufficient_quota", "code": "insufficient_quota",
                                            "message": "You exceeded your quota. key sk-test1234567890 Bearer abc"}}
        twilio = BridgeTwilio(internal, token, "CA-h3", [{**MEDIA, "streamSid": "MZ-CA-h3"}])
        ai = BridgeOpenAI([{"type": "session.created"}, error])
        assert _run_bridge(twilio, ai) == []
        assert _call_state(call_id) == "failed"
        assert [m["type"] for m in ai.sent] == ["session.update"]  # no greeting, no caller audio
        assert twilio.closed_with == [1011] and ai.closed
        (failed,) = _call_events(call_id, "failed")
        assert failed.metadata_json["failure_stage"] == "openai_session_init" and failed.metadata_json["provider"] == "openai"
        assert failed.metadata_json["provider_error_code"] == "insufficient_quota" and failed.metadata_json["session_ready"] is False
        (provider,) = _call_events(call_id, "provider_error")
        assert provider.metadata_json["stage"] == "openai_session_init" and provider.metadata_json["error_type"] == "insufficient_quota"
        dumped = _json.dumps([failed.metadata_json, provider.metadata_json])
        assert "sk-" not in dumped and "Bearer" not in dumped and "exceeded" not in dumped  # no provider free text

    def test_session_updated_timeout_fails_cleanly(self, monkeypatch):
        monkeypatch.setattr(realtime_bridge, "SESSION_INIT_TIMEOUT_SECONDS", 0.2)
        call_id, internal, token = _voice_call("CA-h4")
        twilio = BridgeTwilio(internal, token, "CA-h4", [{**MEDIA, "streamSid": "MZ-CA-h4"}])
        ai = BridgeOpenAI([{"type": "session.created"}])  # never confirms
        assert _run_bridge(twilio, ai) == []
        assert _call_state(call_id) == "failed" and twilio.closed_with == [1011] and ai.closed
        assert [m["type"] for m in ai.sent] == ["session.update"]
        (failed,) = _call_events(call_id, "failed")
        assert failed.metadata_json["failure_stage"] == "openai_session_init_timeout" and failed.metadata_json["error_code"] == "RealtimeInitError"

    def test_openai_connect_failure_is_distinguished(self):
        call_id, internal, token = _voice_call("CA-h5")
        twilio = BridgeTwilio(internal, token, "CA-h5")

        class Rejected(Exception):
            response = type("R", (), {"status_code": 401})()

        async def main():
            async def connect(_config): raise Rejected("handshake rejected sk-secret123456")
            await realtime_bridge.run_media_bridge(twilio, config=VoiceConfig.from_env(), db_factory=SessionLocal, gateway=object(), openai_factory=connect)
        asyncio.run(main())
        (failed,) = _call_events(call_id, "failed")
        assert failed.metadata_json["failure_stage"] == "openai_connect" and failed.metadata_json["http_status"] == 401
        assert "sk-" not in _json.dumps(failed.metadata_json)

    def test_openai_connection_closed_keeps_close_code_reason_and_observer(self):
        call_id, internal, token = _voice_call("CA-h6")
        twilio = BridgeTwilio(internal, token, "CA-h6")
        closed = ConnectionClosedError(Close(1011, "internal error sk-abcdef123456 at https://api.example/x"), None)
        ai = BridgeOpenAI(READY + [closed])
        assert _run_bridge(twilio, ai) == []
        assert _call_state(call_id) == "failed"
        (failed,) = _call_events(call_id, "failed")
        meta = failed.metadata_json
        assert meta["error_code"] == "ConnectionClosedError" and meta["failure_stage"] == "openai_connection_closed"
        assert meta["close_code"] == 1011 and meta["close_initiated_by"] == "provider"
        assert meta["observed_by"] == "openai_to_twilio" and meta["session_ready"] is True
        assert "sk-" not in meta["close_reason"] and "https" not in meta["close_reason"] and "internal error" in meta["close_reason"]

    def test_no_duplicate_failure_events_or_notifications_for_one_failure(self):
        call_id, internal, token = _voice_call("CA-h7")
        twilio = BridgeTwilio(internal, token, "CA-h7")
        ai = BridgeOpenAI(READY + [{"type": "error", "error": {"type": "server_error", "code": "server_error"}}])
        _run_bridge(twilio, ai)
        assert len(_call_events(call_id, "failed")) == 1 and len(_call_events(call_id, "provider_error")) == 1
        assert _call_events(call_id, "call_completed") == []
        verify = SessionLocal()
        assert verify.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "failed_call").count() == 1
        verify.close()
        (failed,) = _call_events(call_id, "failed")
        assert failed.metadata_json["failure_stage"] == "openai_provider_error" and failed.metadata_json["provider_error_code"] == "server_error"

    def test_provider_closing_after_the_caller_hung_up_is_not_a_failure(self):
        call_id, internal, token = _voice_call("CA-h8")
        hungup = {}
        twilio = BridgeTwilio(internal, token, "CA-h8", [{"event": "stop", "streamSid": "MZ-CA-h8", "stop": {"callSid": "CA-h8"}}],
                              on_stop_read=lambda: hungup.setdefault("event", True))

        async def closes_after_hangup():
            while not hungup:
                await asyncio.sleep(0)
            raise ConnectionClosedOK(Close(1000, ""), None)

        ai = BridgeOpenAI(READY + [closes_after_hangup])
        _run_bridge(twilio, ai)
        assert _call_state(call_id) == "completed"
        assert _call_events(call_id, "failed") == [] and twilio.closed_with == []

    def test_sibling_task_is_cancelled_and_awaited_when_one_side_ends(self):
        call_id, internal, token = _voice_call("CA-h9")
        twilio = BridgeTwilio(internal, token, "CA-h9", [{"event": "stop", "streamSid": "MZ-CA-h9", "stop": {"callSid": "CA-h9"}}])
        ai = BridgeOpenAI(READY)  # the OpenAI pump idles forever until it is cancelled
        assert _run_bridge(twilio, ai) == []  # no pump left dangling
        assert _call_state(call_id) == "completed"

    def test_no_secret_header_or_payload_is_persisted_on_failure(self):
        call_id, internal, token = _voice_call("CA-h10")
        twilio = BridgeTwilio(internal, token, "CA-h10")
        error = {"type": "error", "error": {"type": "authentication_error", "code": "invalid_api_key", "message": "Incorrect API key sk-live-ABCDEFGH12345 Authorization: Bearer xyz"}}
        _run_bridge(twilio, BridgeOpenAI([{"type": "session.created"}, error]))
        db = SessionLocal()
        blob = _json.dumps([e.metadata_json for e in db.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.call_id == call_id)], default=str)
        blob += str([(c.error_code, c.summary) for c in db.query(models.VoiceCall).all()])
        blob += str([n.message + str(n.metadata_json) for n in db.query(models.OwnerNotification).all()])
        db.close()
        for forbidden in ("sk-", "Bearer", "Authorization", "test-openai-api-key", "test-twilio-auth-token", token, "ABCDEFGH"):
            assert forbidden not in blob

    def test_working_call_with_batched_tools_is_unchanged_after_the_gate(self):
        call_id, internal, token = _voice_call("CA-h11")
        calls = {"type": "response.done", "response": {"output": [
            {"type": "function_call", "name": "get_salon_info", "arguments": "{}", "call_id": "a"},
            {"type": "function_call", "name": "list_services", "arguments": "{}", "call_id": "b"}]}}
        twilio = BridgeTwilio(internal, token, "CA-h11", [{"event": "stop", "streamSid": "MZ-CA-h11", "stop": {"callSid": "CA-h11"}}])

        class SlowStop(BridgeTwilio):
            async def receive_json(self):
                if not self.messages:
                    await asyncio.sleep(0.3)  # let the tool round-trip finish before the caller hangs up
                return await super().receive_json()

        twilio = SlowStop(internal, token, "CA-h11", [{"event": "stop", "streamSid": "MZ-CA-h11", "stop": {"callSid": "CA-h11"}}])
        ai = BridgeOpenAI(READY + [calls])
        _run_bridge(twilio, ai)
        types = [m["type"] for m in ai.sent]
        assert types[:2] == ["session.update", "response.create"]
        assert types[2:] == ["conversation.item.create", "conversation.item.create", "response.create"]
        assert _call_state(call_id) == "completed"

    def test_voice_allowlist_and_service_lookup_unchanged(self):
        assert {t["name"] for t in voice_tools.READ_ONLY_TOOL_DEFINITIONS} == {
            "get_salon_info", "list_services", "get_service_details", "get_available_slots", "identify_customer_candidate", "request_owner_callback", "create_booking"}
        db = SessionLocal()
        call = voice_foundation.create_call(db, caller_phone="6025551234", called_phone="6025559999", call_id="voice-gate")
        facade = voice_foundation.VoiceBookingFacade(db, voice_foundation.VoiceAuthorizationContext(call.id, call.call_id, 0, call.caller_phone_e164, None))
        assert {s["name"] for s in facade.list_services()} == {s["name"] for s in client.get("/services").json()}
        db.close()


class TestTwilioStreamErrorAndFallback:
    FORM = {"AccountSid": "AC11111111111111111111111111111111", "From": "+16025551234", "To": "+16025559999", "CallSid": "CA-se1"}

    def test_stream_error_text_is_captured_sanitized_and_tied_to_the_call(self):
        _twilio_post("/voice/twilio/incoming", self.FORM)
        form = {"AccountSid": self.FORM["AccountSid"], "CallSid": "CA-se1", "StreamEvent": "stream-error", "StreamSid": "MZse1",
                "StreamError": "Failed to connect to wss://voice.test/voice/twilio/media with sk-leak123456 token", "SequenceNumber": "3"}
        assert _twilio_post("/voice/twilio/status", form).status_code == 204
        assert _twilio_post("/voice/twilio/status", form).status_code == 204  # replay: still one event
        db = SessionLocal()
        call = db.query(models.VoiceCall).filter(models.VoiceCall.provider_call_sid == "CA-se1").one()
        events = db.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.call_id == call.id, models.VoiceCallEvent.event_type == "failed").all()
        assert call.call_state == "failed" and call.error_code == "twilio_stream_error" and len(events) == 1
        meta = events[0].metadata_json
        assert meta["provider_event"] == "stream-error" and "Failed to connect" in meta["stream_error"]
        assert "wss://" not in meta["stream_error"] and "sk-" not in meta["stream_error"] and "Signature" not in str(meta)
        db.close()

    def test_stream_error_without_text_still_recorded_and_other_stream_events_unchanged(self):
        _twilio_post("/voice/twilio/incoming", {**self.FORM, "CallSid": "CA-se2"})
        base = {"AccountSid": self.FORM["AccountSid"], "CallSid": "CA-se2", "StreamSid": "MZse2"}
        assert _twilio_post("/voice/twilio/status", {**base, "StreamEvent": "stream-started"}).status_code == 204
        assert _twilio_post("/voice/twilio/status", {**base, "StreamEvent": "stream-error"}).status_code == 204
        db = SessionLocal()
        call = db.query(models.VoiceCall).filter(models.VoiceCall.provider_call_sid == "CA-se2").one()
        by_type = {e.event_type: e.metadata_json for e in db.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.call_id == call.id)}
        assert by_type["stream_started"] == {"provider_event": "stream-started"}
        assert by_type["failed"]["provider_event"] == "stream-error" and by_type["failed"].get("stream_error") is None
        db.close()

    def test_twiml_adds_a_generic_spoken_fallback_that_never_names_the_provider(self):
        response = _twilio_post("/voice/twilio/incoming", {**self.FORM, "CallSid": "CA-se3"})
        text = response.text
        assert text.index("</Connect>") < text.index("<Say>") and "<Stream" in text
        lowered = text.lower()
        for word in ("openai", "quota", "error", "provider"):
            assert word not in lowered


# ── Voice appointment creation ────────────────────────────────────────────────

class VoiceBookingEnv:
    """A live call + facade + one eligible technician; tools are called exactly as the bridge does."""

    def __init__(self, sid, phone="6025551234", techs=("Zed Tech",)):
        self.db = SessionLocal()
        self.call = voice_foundation.create_call(self.db, caller_phone=phone, called_phone="6025559999", call_id=sid)
        self.facade = voice_foundation.VoiceBookingFacade(self.db, voice_foundation.VoiceAuthorizationContext(
            self.call.id, self.call.call_id, 0, self.call.caller_phone_e164, None))
        self.facade.caller_turns = 1
        self.service_id = _catalog()["Gel Manicure"]["id"]
        self.tech_ids = []
        for name in techs:
            tech_id = make_tech(name, specialties="manicure / pedicure, gel").json()["id"]
            self.tech_ids.append(tech_id)
        self.day = _booking_day(2)
        _set_business_hours(self.day, time(9, 0), time(18, 0))
        for tech_id in self.tech_ids:
            _set_tech_schedule(tech_id, self.day, time(9, 0), time(18, 0))

    def tool(self, name, **args):
        self.db.expire_all()
        return voice_tools.dispatch_voice_tool(self.facade, object(), name, args)

    def offer(self, **extra):
        slots = self.tool("get_available_slots", date=self.day.isoformat(), service_ids=[self.service_id], **extra)
        return next(s for s in slots if "T10:00" in s["start"])

    def hear_caller(self):
        self.facade.caller_turns += 1

    def appointments(self):
        verify = SessionLocal()
        try:
            return verify.query(models.Appointment).count()
        finally:
            verify.close()

    def close(self):
        self.db.close()


FAIL = voice_foundation.VoiceFoundationError


class TestVoiceAppointmentCreation:
    def test_full_flow_books_only_after_prepare_new_caller_turn_and_explicit_yes(self):
        env = VoiceBookingEnv("CA-vb1")
        slot = env.offer()
        prepared = env.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez")
        assert prepared["status"] == "confirmation_required" and env.appointments() == 0
        assert prepared["summary"]["service"] == "Gel Manicure" and prepared["summary"]["customer_name"] == "Maria Lopez"
        assert prepared["summary"]["time"] == "10:00 AM" and prepared["summary"]["technician"] == "first available technician"
        env.hear_caller()
        booked = env.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez", caller_confirmation="Yes, please book it")
        assert booked["status"] == "booked" and booked["service"] == "Gel Manicure" and booked["technician"] == "Zed Tech"
        assert booked["reference"] and booked["time"] == "10:00 AM" and env.appointments() == 1
        verify = SessionLocal()
        appointment = verify.query(models.Appointment).one()
        assert appointment.customer_phone_e164 == "+16025551234" and appointment.status == "scheduled"
        assert [s.service_name_snapshot for s in appointment.appointment_services] == ["Gel Manicure"]
        call = verify.get(models.VoiceCall, env.call.id)
        assert call.appointment_id == appointment.id and call.outcome == "booked"
        assert verify.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.event_type == "appointment_created").count() == 1
        assert verify.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "phone_booking").count() == 1
        verify.close(); env.close()

    def test_nothing_is_booked_before_a_real_confirmation(self):
        env = VoiceBookingEnv("CA-vb2")
        slot = env.offer()
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        with pytest.raises(FAIL, match="Read the booking summary"):
            env.tool("create_booking", **args, caller_confirmation="yes")  # no prepare yet
        env.tool("create_booking", **args)
        with pytest.raises(FAIL, match="Wait for the caller"):
            env.tool("create_booking", **args, caller_confirmation="yes")  # caller has not spoken since the summary
        env.hear_caller()
        for phrase in ("maybe", "yes but wait", "no", "sure, actually no", "uh", "hmm let me think", "I guess", "what time is it", "", "x" * 300):
            if phrase:
                with pytest.raises(FAIL):
                    env.tool("create_booking", **args, caller_confirmation=phrase)
        assert env.appointments() == 0
        env.facade.caller_turns = None  # cannot verify the caller's answer -> refuse
        with pytest.raises(FAIL, match="cannot be verified"):
            env.tool("create_booking", **args, caller_confirmation="yes")
        assert env.appointments() == 0
        env.close()

    def test_only_backend_offered_slot_ids_are_accepted(self):
        env = VoiceBookingEnv("CA-vb3")
        other = VoiceBookingEnv("CA-vb3b", techs=())
        slot = env.offer()
        for bad in ("deadbeef-0", "nonsense", "", slot["slot_id"].split("-")[0] + "-999", "../" + slot["slot_id"]):
            with pytest.raises(FAIL, match="Unknown slot_id"):
                env.tool("create_booking", slot_id=bad, customer_name="Maria Lopez")
        # a slot offered on a DIFFERENT call is not valid here
        other.service_id, other.day = env.service_id, env.day
        foreign = other.offer()
        with pytest.raises(FAIL, match="Unknown slot_id"):
            env.tool("create_booking", slot_id=foreign["slot_id"], customer_name="Maria Lopez")
        # model-invented times/services are simply not part of the tool
        prepared = env.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez", appointment_time="2030-01-01T03:00", service_ids=[1])
        assert prepared["summary"]["time"] == "10:00 AM" and prepared["summary"]["service"] == "Gel Manicure"
        assert env.appointments() == 0
        env.close(); other.close()

    def test_unknown_or_inactive_service_cannot_be_offered(self):
        env = VoiceBookingEnv("CA-vb4")
        with pytest.raises(FAIL):
            env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[999999])
        client.patch(f"/booking-services/{env.service_id}", json={"is_active": False})
        with pytest.raises(FAIL):
            env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[env.service_id])
        with pytest.raises(FAIL):
            env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[])
        env.close()

    def test_service_deactivated_between_summary_and_confirmation_fails_safely(self):
        env = VoiceBookingEnv("CA-vb5")
        slot = env.offer()
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        env.tool("create_booking", **args)
        client.patch(f"/booking-services/{env.service_id}", json={"is_active": False})
        env.hear_caller()
        with pytest.raises(FAIL, match="no longer available"):
            env.tool("create_booking", **args, caller_confirmation="yes")
        assert env.appointments() == 0
        env.close()

    def test_slot_taken_between_summary_and_confirmation_fails_safely_and_other_booking_survives(self):
        env = VoiceBookingEnv("CA-vb6")
        slot = env.offer()
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        env.tool("create_booking", **args)
        taken = client.post("/appointments", json=_booking_payload(env.tech_ids[0], datetime.fromisoformat(slot["start"]).replace(tzinfo=None), [env.service_id], customer_name="Walk In"))
        assert taken.status_code == 200
        env.hear_caller()
        with pytest.raises(FAIL, match="no longer available"):
            env.tool("create_booking", **args, caller_confirmation="yes")
        assert env.appointments() == 1
        # and a fresh prepare for the taken slot is refused up front
        with pytest.raises(FAIL, match="no longer available"):
            env.tool("create_booking", slot_id=slot["slot_id"], customer_name="Other Person")
        env.close()

    def test_specific_technician_by_name_and_that_technician_becoming_unavailable(self):
        env = VoiceBookingEnv("CA-vb7", techs=("Zed Tech", "Amy Tech"))
        slot = env.offer(technician_name="Amy")
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        assert env.tool("create_booking", **args)["summary"]["technician"] == "Amy Tech"
        client.post("/appointments", json=_booking_payload(env.tech_ids[1], datetime.fromisoformat(slot["start"]).replace(tzinfo=None), [env.service_id], customer_name="Walk In"))
        env.hear_caller()
        with pytest.raises(FAIL, match="no longer available"):
            env.tool("create_booking", **args, caller_confirmation="yes")  # Zed is free but the caller asked for Amy
        assert env.appointments() == 1
        with pytest.raises(FAIL, match="No active technician matches"):
            env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[env.service_id], technician_name="Nobody")
        env.close()

    def test_any_technician_uses_authoritative_availability(self):
        env = VoiceBookingEnv("CA-vb8", techs=("Zed Tech", "Amy Tech"))
        slot = env.offer()
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        env.tool("create_booking", **args)
        env.hear_caller()
        booked = env.tool("create_booking", **args, caller_confirmation="yes")
        verify = SessionLocal()
        appointment = verify.query(models.Appointment).one()
        assert appointment.technician_id in env.tech_ids and appointment.preferred_technician_id is None
        assert booked["technician"] in ("Zed Tech", "Amy Tech")
        verify.close(); env.close()

    def test_duplicate_or_retried_confirmation_creates_exactly_one_appointment(self):
        env = VoiceBookingEnv("CA-vb9")
        slot = env.offer()
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        env.tool("create_booking", **args)
        env.hear_caller()
        first = env.tool("create_booking", **args, caller_confirmation="yes")
        second = env.tool("create_booking", **args, caller_confirmation="yes")
        third = env.tool("create_booking", **args)  # even a repeated prepare returns the same booking
        assert first == second == third and env.appointments() == 1
        verify = SessionLocal()
        assert verify.query(models.OwnerNotification).filter(models.OwnerNotification.notification_type == "phone_booking").count() == 1
        verify.close()
        with pytest.raises(FAIL, match="different details"):
            env.tool("create_booking", slot_id=slot["slot_id"], customer_name="Someone Else", caller_confirmation="yes")
        other = [s for s in env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[env.service_id]) if "T11:00" in s["start"]][0]
        with pytest.raises(FAIL, match="already booked on this call"):
            env.tool("create_booking", slot_id=other["slot_id"], customer_name="Maria Lopez")
        assert env.appointments() == 1
        env.close()

    def test_same_idempotency_key_with_a_different_payload_fails_safely(self):
        env = VoiceBookingEnv("CA-vb10")
        slot = env.offer()
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        env.tool("create_booking", **args)
        # someone already used this call's booking key for a DIFFERENT request
        import schemas
        booking_service.create_booking(env.db, schemas.AppointmentCreate(
            customer_name="Squatter", customer_phone="6025550999", service_category="x", service_ids=[env.service_id],
            appointment_time=datetime.fromisoformat(slot["start"]) + timedelta(hours=3), technician_id=env.tech_ids[0],
            idempotency_key=f"voice:{env.call.call_id}:{slot['slot_id']}"))
        env.hear_caller()
        with pytest.raises(FAIL, match="conflicts with an earlier request"):
            env.tool("create_booking", **args, caller_confirmation="yes")
        assert env.appointments() == 1
        env.close()

    def test_ambiguous_customer_details_are_not_guessed(self):
        env = VoiceBookingEnv("CA-vb11")
        slot = env.offer()
        for name in ("", "X", "1234", "<script>", "a" * 61, None):
            with pytest.raises(FAIL, match="valid customer name"):
                env.tool("create_booking", slot_id=slot["slot_id"], customer_name=name)
        env.close()
        anon = VoiceBookingEnv("CA-vb11b", phone="", techs=("Una Tech",))
        slot = anon.offer()
        with pytest.raises(FAIL, match="Caller ID is unavailable"):
            anon.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez")
        with pytest.raises(FAIL, match="not a valid US number"):
            anon.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez", customer_phone="12")
        assert anon.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez", customer_phone="(480) 555-0100")["status"] == "confirmation_required"
        anon.hear_caller()
        anon.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez", customer_phone="(480) 555-0100", caller_confirmation="yes")
        verify = SessionLocal()
        assert verify.query(models.Appointment).one().customer_phone_e164 == "+14805550100"
        verify.close(); anon.close()

    def test_trusted_caller_id_wins_over_a_phone_the_model_supplies(self):
        env = VoiceBookingEnv("CA-vb12")
        slot = env.offer()
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez", "customer_phone": "4805550100"}
        env.tool("create_booking", **args)
        env.hear_caller()
        env.tool("create_booking", **args, caller_confirmation="yes")
        verify = SessionLocal()
        assert verify.query(models.Appointment).one().customer_phone_e164 == "+16025551234"
        verify.close(); env.close()

    def test_backend_failure_never_produces_a_false_success(self, monkeypatch):
        env = VoiceBookingEnv("CA-vb13")
        slot = env.offer()
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        env.tool("create_booking", **args)
        env.hear_caller()

        def explode(*_a, **_k):
            raise RuntimeError("database is locked sk-secret")
        monkeypatch.setattr(booking_service, "create_booking", explode)
        with pytest.raises(FAIL, match="nothing was booked") as raised:
            env.tool("create_booking", **args, caller_confirmation="yes")
        assert "sk-secret" not in str(raised.value) and "RuntimeError" not in str(raised.value)
        monkeypatch.setattr(booking_service, "create_booking", lambda *_a, **_k: (_ for _ in ()).throw(booking_service.BookingRuleError("outside hours")))
        with pytest.raises(FAIL, match="no longer available"):
            env.tool("create_booking", **args, caller_confirmation="yes")
        env.db.expire_all()
        assert env.appointments() == 0 and env.db.get(models.VoiceCall, env.call.id).appointment_id is None
        env.close()

    def test_bridge_counts_caller_utterances_and_hands_the_count_to_the_tools(self, monkeypatch):
        state = {"stopped": False, "stream_sid": "MZ"}
        _run_openai(state, [SPEECH, SPEECH, SPEECH])
        assert state["caller_turns"] == 3
        call_id, *_ = _voice_call("CA-vb14")
        seen = {}
        monkeypatch.setattr(realtime_bridge, "dispatch_voice_tool", lambda facade, gateway, name, arguments: seen.setdefault("turns", facade.caller_turns))
        call_state = {"db_factory": SessionLocal, "call": SessionLocal().get(models.VoiceCall, call_id), "caller_turns": 4}
        realtime_bridge._execute_tool_with_own_session(call_state, object(), {"name": "get_salon_info", "arguments": "{}"})
        assert seen["turns"] == 4

    def test_prompt_requires_confirmation_and_names_no_unsupported_actions_as_available(self):
        text = realtime_bridge.receptionist_instructions("Test Nails", "America/Phoenix")
        assert "only after create_booking returns status booked" in text
        assert "Silence" in text and "NOT a yes" in text and "ONLY times it returns" in text
        assert "Rescheduling, cancelling or changing an existing appointment is not supported" in text

    def test_allowlist_is_exactly_seven_with_no_reschedule_cancel_or_private_lookup(self):
        names = {tool["name"] for tool in voice_tools.READ_ONLY_TOOL_DEFINITIONS}
        assert names == {"get_salon_info", "list_services", "get_service_details", "get_available_slots",
                         "identify_customer_candidate", "request_owner_callback", "create_booking"}
        env = VoiceBookingEnv("CA-vb15")
        for forbidden in ("reschedule_booking", "cancel_booking", "get_appointment", "lookup_appointment", "update_customer",
                          "assign_technician", "checkout", "update_service", "delete_booking"):
            with pytest.raises(FAIL):
                env.tool(forbidden, appointment_id=1)
        result = env.tool("request_owner_callback", category="reschedule", urgency="normal", summary="Wants to move an appointment")
        assert result == {"requested": True}  # unsupported requests still go to the owner
        env.close()


# ── Preferred-technician booking ──────────────────────────────────────────────

def _at(slots, hhmm):
    return next(s for s in slots if f"T{hhmm}" in s["start"])


def _slots(env, **extra):
    return env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[env.service_id], **extra)


class TestPreferredTechnicianBooking:
    def env(self, sid, techs=("Holy Nguyen", "Andy Tran")):
        return VoiceBookingEnv(sid, techs=techs)

    def test_the_named_technician_is_resolved_and_every_slot_is_theirs(self):
        env = self.env("CA-pt1")
        slots = _slots(env, technician_name="Holy")
        assert slots and all(s["technician"] == "Holy Nguyen" for s in slots)
        verify = SessionLocal()
        offer = verify.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.operation_key == f"offer:{slots[0]['slot_id'].split('-')[0]}").one()
        assert offer.metadata_json["technician_id"] == env.tech_ids[0] and offer.metadata_json["technician_requested"] is True
        verify.close(); env.close()

    @pytest.mark.parametrize("spoken", ["holy", "HOLY", "  Holy  ", "Holy Nguyen", "holy nguyen.", "Holy, ", "hOlY  nGuYeN"])
    def test_case_whitespace_and_punctuation_are_normalised(self, spoken):
        env = self.env("CA-pt2")
        assert {s["technician"] for s in _slots(env, technician_name=spoken)} == {"Holy Nguyen"}
        env.close()

    def test_a_clearly_unique_close_spelling_resolves_and_the_summary_shows_the_real_name(self):
        env = self.env("CA-pt3")
        slots = _slots(env, technician_name="Holly")  # speech-to-text variant
        assert {s["technician"] for s in slots} == {"Holy Nguyen"}
        prepared = env.tool("create_booking", slot_id=_at(slots, "10:00")["slot_id"], customer_name="Maria Lopez")
        assert prepared["summary"]["technician"] == "Holy Nguyen"  # the caller hears the canonical name before confirming
        env.close()

    def test_unknown_ambiguous_inactive_and_ineligible_technicians_fail_with_no_fallback(self):
        env = self.env("CA-pt4", techs=("Holy Nguyen", "Sam Lee", "Sam Ray"))
        for bad in ("Zzzzz", "Qwerty Uiop", "Bob"):
            with pytest.raises(FAIL, match="No active technician matches"):
                _slots(env, technician_name=bad)
        with pytest.raises(FAIL, match="More than one technician"):
            _slots(env, technician_name="Sam")
        assert {s["technician"] for s in _slots(env, technician_name="Sam Lee")} == {"Sam Lee"}
        db = SessionLocal()
        db.get(models.Technician, env.tech_ids[0]).is_active = False
        db.commit(); db.close()
        with pytest.raises(FAIL, match="No active technician matches"):
            _slots(env, technician_name="Holy")
        wax = make_tech("Wanda Wax", specialties="waxing").json()["id"]
        with pytest.raises(FAIL, match="does not perform all of those services"):
            _slots(env, technician_name="Wanda")
        env.close()

    def test_requested_technician_busy_at_the_time_never_falls_back_to_someone_else(self):
        env = self.env("CA-pt5")
        any_slots = _slots(env)
        assert _at(any_slots, "10:00")  # generic availability exists at 10:00
        client.post("/appointments", json=_booking_payload(env.tech_ids[0], datetime.combine(env.day, time(10, 0)), [env.service_id], customer_name="Walk In"))
        holy = _slots(env, technician_name="Holy")
        assert not any("T10:00" in s["start"] for s in holy), "Holy is busy at 10:00; Andy being free must not leak in"
        assert all(s["technician"] == "Holy Nguyen" for s in holy)
        assert any("T10:00" in s["start"] for s in _slots(env)), "caller agreed to anyone: Andy is offered"
        env.close()

    def test_no_openings_for_the_named_technician_is_an_explicit_instruction_not_an_empty_list(self):
        env = self.env("CA-pt6")
        _set_tech_schedule(env.tech_ids[0], env.day, working=False)
        with pytest.raises(FAIL, match="Holy Nguyen has no openings.*Do NOT switch") as raised:
            _slots(env, technician_name="holy")
        assert "agree" in str(raised.value)
        assert _slots(env)  # 'anyone' still works once the caller agrees
        env.close()

    def test_the_slot_id_is_bound_to_the_technician_and_cannot_be_redirected(self):
        env = self.env("CA-pt7")
        holy_slot = _at(_slots(env, technician_name="Holy"), "10:00")
        any_slot = _at(_slots(env), "10:00")
        args = {"slot_id": holy_slot["slot_id"], "customer_name": "Maria Lopez"}
        # model-supplied technician fields are ignored by create_booking and get_available_slots
        env.tool("create_booking", **args, technician_id=env.tech_ids[1], technician_name="Andy")
        env.hear_caller()
        booked = env.tool("create_booking", **args, caller_confirmation="yes", technician_id=env.tech_ids[1], technician_name="Andy")
        assert booked["technician"] == "Holy Nguyen"
        verify = SessionLocal()
        appointment = verify.query(models.Appointment).one()
        assert appointment.technician_id == env.tech_ids[0] and appointment.preferred_technician_id == env.tech_ids[0]
        verify.close()
        # a generic slot cannot be turned into Holy either: it books whoever the picker chooses, unchanged semantics
        assert any_slot["slot_id"] != holy_slot["slot_id"] and "technician" not in any_slot
        env.close()

    def test_the_model_cannot_fabricate_a_technician_id(self):
        env = self.env("CA-pt8")
        slots = env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[env.service_id], technician_id=env.tech_ids[1])
        assert slots and all("technician" not in s for s in slots)  # ignored: this is an 'anyone' offer
        verify = SessionLocal()
        offer = verify.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.operation_key == f"offer:{slots[0]['slot_id'].split('-')[0]}").one()
        assert offer.metadata_json["technician_id"] is None and offer.metadata_json["technician_requested"] is False
        verify.close()
        assert "technician_id" not in str(voice_tools.READ_ONLY_TOOL_DEFINITIONS[3]["parameters"])
        env.close()

    def test_holy_becoming_unavailable_between_offer_and_confirmation_fails_without_substituting(self):
        env = self.env("CA-pt9")
        slot = _at(_slots(env, technician_name="Holy"), "10:00")
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        assert env.tool("create_booking", **args)["summary"]["technician"] == "Holy Nguyen"
        client.post("/appointments", json=_booking_payload(env.tech_ids[0], datetime.combine(env.day, time(10, 0)), [env.service_id], customer_name="Walk In"))
        env.hear_caller()
        with pytest.raises(FAIL, match="no longer available"):
            env.tool("create_booking", **args, caller_confirmation="yes")
        verify = SessionLocal()
        assert [(a.customer_name, a.technician_id) for a in verify.query(models.Appointment)] == [("Walk In", env.tech_ids[0])]
        verify.close(); env.close()

    def test_duplicate_preferred_technician_confirmation_is_idempotent(self):
        env = self.env("CA-pt10")
        slot = _at(_slots(env, technician_name="Holy"), "11:00")
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        env.tool("create_booking", **args)
        env.hear_caller()
        first = env.tool("create_booking", **args, caller_confirmation="yes")
        second = env.tool("create_booking", **args, caller_confirmation="yes")
        assert first == second and first["technician"] == "Holy Nguyen" and env.appointments() == 1
        env.close()

    def test_anyone_still_books_with_an_eligible_technician(self):
        env = self.env("CA-pt11")
        slot = _at(_slots(env), "10:00")
        args = {"slot_id": slot["slot_id"], "customer_name": "Maria Lopez"}
        env.tool("create_booking", **args)
        env.hear_caller()
        booked = env.tool("create_booking", **args, caller_confirmation="sure, go ahead")
        assert booked["status"] == "booked" and booked["technician"] in ("Holy Nguyen", "Andy Tran")
        env.close()

    def test_canonical_technician_names_are_available_to_the_model_without_private_data(self):
        env = self.env("CA-pt12")
        details = env.tool("get_service_details", service_id=env.service_id)
        assert details["technicians"] == ["Andy Tran", "Holy Nguyen"]
        listed = {s["name"]: s for s in env.tool("list_services")}
        assert all("technicians" not in s for s in listed.values()), "a service list never carries staff names"
        assert "Reference only" in details["technicians_note"]
        blob = str(details)
        for private in ("phone", "schedule", "income", "notes", "employee", "specialties", "email"):
            assert private not in blob.lower()
        assert all(isinstance(name, str) for name in details["technicians"])
        env.close()

    def test_prompt_makes_a_named_technician_a_hard_requirement(self):
        text = realtime_bridge.receptionist_instructions("Test Nails", "America/Phoenix")
        assert "ALWAYS pass technician_name" in text and "hard requirement, never a preference" in text
        assert "ONLY after the caller agrees" in text and "the technician's name" in text
        assert "name only the technician it returns" in text
        definitions = {t["name"]: t for t in voice_tools.READ_ONLY_TOOL_DEFINITIONS}
        assert "ALWAYS pass technician_name" in definitions["get_available_slots"]["description"]
        assert {t["name"] for t in definitions.values()} == {"get_salon_info", "list_services", "get_service_details", "get_available_slots",
                                                              "identify_customer_candidate", "request_owner_callback", "create_booking"}

    def test_full_call_sequence_gel_manicure_with_holy_survives_to_the_appointment_row(self):
        """The tool calls the model makes for: 'I want a Gel Manicure with Holy tomorrow at 2 PM.'"""
        env = self.env("CA-pt13")
        services = env.tool("list_services")
        gel = next(s for s in services if s["name"] == "Gel Manicure")
        assert "Holy Nguyen" in env.tool("get_service_details", service_id=gel["id"])["technicians"]
        slots = env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[gel["id"]], technician_name="Holy")
        two_pm = _at(slots, "14:00")
        assert two_pm["technician"] == "Holy Nguyen"
        summary = env.tool("create_booking", slot_id=two_pm["slot_id"], customer_name="Maria Lopez")
        assert summary["status"] == "confirmation_required"
        assert (summary["summary"]["service"], summary["summary"]["time"], summary["summary"]["technician"]) == ("Gel Manicure", "2:00 PM", "Holy Nguyen")
        env.hear_caller()  # the caller says "yes, book it"
        booked = env.tool("create_booking", slot_id=two_pm["slot_id"], customer_name="Maria Lopez", caller_confirmation="Yes, book it")
        assert booked["status"] == "booked" and booked["technician"] == "Holy Nguyen"
        verify = SessionLocal()
        row = verify.query(models.Appointment).one()
        assert row.technician_id == env.tech_ids[0] and row.preferred_technician_id == env.tech_ids[0]
        assert row.appointment_time.hour == 14 and row.customer_name == "Maria Lopez"
        assert [s.service_name_snapshot for s in row.appointment_services] == ["Gel Manicure"]
        call = verify.get(models.VoiceCall, env.call.id)
        assert call.appointment_id == row.id
        verify.close(); env.close()


class TestRejectedToolCallsAreTraceable:
    def test_a_refused_tool_call_records_tool_and_argument_names_but_never_values(self):
        import json
        call_id, *_ = _voice_call("CA-rej1")
        db = SessionLocal()
        state = {"stopped": False, "stream_sid": "MZ", "db": db, "db_factory": SessionLocal, "call": db.get(models.VoiceCall, call_id), "config": VoiceConfig.from_env()}
        args = json.dumps({"date": "2030-01-01", "service_ids": [999999], "technician_name": "Holly SECRETNAME"})
        _run_openai(state, [{"type": "response.done", "response": {"output": [{"type": "function_call", "name": "get_available_slots", "arguments": args, "call_id": "x"}]}}])
        event = db.query(models.VoiceCallEvent).filter(models.VoiceCallEvent.call_id == call_id, models.VoiceCallEvent.result_status == "rejected").one()
        assert event.metadata_json == {"tool": "get_available_slots", "argument_names": ["date", "service_ids", "technician_name"]}
        assert "SECRETNAME" not in str(event.metadata_json) and "999999" not in str(event.metadata_json)
        db.close()


class TestTechnicianNamesAreNotVolunteered:
    def test_prompt_and_tool_text_say_technician_names_are_reference_data_only(self):
        text = realtime_bridge.receptionist_instructions("Test Nails", "America/Phoenix")
        assert "do NOT mention or ask about technicians at all" in text
        assert "Never read out a list of technicians unprompted" in text
        assert "reference data only" in text and "book with any available technician" in text
        for trigger in ("asks for or names a technician", "asks who can do a service", "ambiguous", "unavailable and the caller wants alternatives", "actually do the appointment"):
            assert trigger in text
        definitions = {t["name"]: t["description"] for t in voice_tools.READ_ONLY_TOOL_DEFINITIONS}
        assert "never recite it unprompted" in definitions["get_service_details"]
        assert "technician" not in definitions["list_services"].lower()
        # the earlier hard-constraint wording is unchanged
        assert "hard requirement, never a preference" in text and "ONLY after the caller agrees" in text

    def test_service_only_flow_needs_no_technician_choice_and_the_confirmation_names_the_real_one(self):
        env = VoiceBookingEnv("CA-nv1", techs=("Holy Nguyen", "Andy Tran", "Ashly Bui"))
        services = env.tool("list_services")
        assert all("technicians" not in s for s in services)
        gel = next(s for s in services if s["name"] == "Gel Manicure")
        slots = env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[gel["id"]])  # no technician_name at all
        assert slots and all("technician" not in s for s in slots)
        slot = _at(slots, "10:00")
        prepared = env.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez")
        assert prepared["summary"]["technician"] == "first available technician"
        env.hear_caller()
        booked = env.tool("create_booking", slot_id=slot["slot_id"], customer_name="Maria Lopez", caller_confirmation="yes please")
        assert booked["technician"] in ("Holy Nguyen", "Andy Tran", "Ashly Bui")  # the final confirmation states who it really is
        verify = SessionLocal()
        row = verify.query(models.Appointment).one()
        assert db_name(verify, row.technician_id) == booked["technician"]
        verify.close(); env.close()

    def test_who_can_do_it_is_still_answerable_and_a_named_technician_still_binds(self):
        env = VoiceBookingEnv("CA-nv2", techs=("Holy Nguyen", "Andy Tran"))
        details = env.tool("get_service_details", service_id=env.service_id)
        assert details["technicians"] == ["Andy Tran", "Holy Nguyen"]
        holy = env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[env.service_id], technician_name="Holy")
        assert holy and {s["technician"] for s in holy} == {"Holy Nguyen"}
        anyone = env.tool("get_available_slots", date=env.day.isoformat(), service_ids=[env.service_id])
        assert anyone and all("technician" not in s for s in anyone)
        env.close()


def db_name(db, technician_id):
    return db.get(models.Technician, technician_id).full_name


class TestTechnicianEditKeepsServiceEligibility:
    def test_an_unrelated_technician_edit_does_not_rebuild_eligibility_from_specialties(self):
        tech = make_tech("Elig Keep", specialties="manicure / pedicure, gel").json()["id"]
        gel = _catalog()["Gel Manicure"]["id"]
        assert tech in _catalog()["Gel Manicure"]["eligible_technician_ids"]
        assert client.put(f"/booking-services/{gel}/technicians", json={"technician_ids": []}).status_code == 200  # owner removes it on the Services page
        for change in ({"phone": "6025550100"}, {"notes": "keep"}, {"specialties": "manicure / pedicure, gel"}, {"availability": "available today"}):
            assert client.put(f"/technicians/{tech}", json=change).status_code == 200, change
            assert _catalog()["Gel Manicure"]["eligible_technician_ids"] == [], change  # the Services-page choice survives
        # a REAL change of the specialties still recomputes eligibility from them
        assert client.put(f"/technicians/{tech}", json={"specialties": "waxing"}).status_code == 200
        assert tech not in _catalog()["Gel Manicure"]["eligible_technician_ids"]
        assert client.put(f"/technicians/{tech}", json={"specialties": "manicure / pedicure, gel"}).status_code == 200
        assert tech in _catalog()["Gel Manicure"]["eligible_technician_ids"]

    def test_explicit_service_ids_on_a_technician_edit_still_win(self):
        tech = make_tech("Elig Explicit", specialties="waxing").json()["id"]
        gel = _catalog()["Gel Manicure"]["id"]
        assert client.put(f"/technicians/{tech}", json={"service_ids": [gel]}).status_code == 200
        assert tech in _catalog()["Gel Manicure"]["eligible_technician_ids"]


