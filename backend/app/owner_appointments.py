"""Read-only client for "is there an appointment today for this phone number?" (Owner internal API).

    Browser -> Check-In backend (this module) -> Owner GET /internal/appointments/lookup

Same rules as owner_catalog: the internal token is read from the environment on every call, sent only to the configured Owner URL as
X-Internal-Service-Token, redirects are never followed, and the browser never sees any of it. Nothing is cached: an appointment can be
cancelled or booked at any moment, and an answer that is a few minutes old would send a customer to the wrong screen.

Any failure raises AppointmentLookupUnavailable (with no detail that could leak): the kiosk then asks the customer to see a staff member
instead of silently treating the customer as a walk-in.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

from .owner_catalog import _opener
from .security import INTERNAL_TOKEN_HEADER

logger = logging.getLogger("nail_system.owner_appointments")

LOOKUP_PATH = "/internal/appointments/lookup"
REQUEST_TIMEOUT_SECONDS = 5.0
OUTCOMES = ("none", "one", "multiple", "incomplete")


class AppointmentLookupUnavailable(Exception):
    """The Owner could not be asked, or answered something unusable."""


@dataclass(frozen=True)
class AppointmentService:
    id: Optional[int]
    name: str


@dataclass(frozen=True)
class FoundAppointment:
    code: str
    appointment_time: str          # salon-local, "YYYY-MM-DDTHH:MM"
    status: str
    customer_name: str
    services: tuple = field(default_factory=tuple)
    technician_name: Optional[str] = None


@dataclass(frozen=True)
class Lookup:
    outcome: str
    appointment: Optional[FoundAppointment] = None


def parse_lookup(payload) -> Lookup:
    """Validates the Owner's answer; anything unexpected rejects the whole answer."""
    if not isinstance(payload, dict) or payload.get("outcome") not in OUTCOMES:
        raise ValueError("unexpected lookup answer")
    outcome, raw = payload["outcome"], payload.get("appointment")
    if outcome in ("none", "multiple"):
        return Lookup(outcome)
    if not isinstance(raw, dict):
        raise ValueError("missing appointment")
    for key in ("code", "appointment_time", "status", "customer_name"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError(f"bad {key}")
    services = []
    for item in raw.get("services") or []:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError("bad service")
        service_id = item.get("id")
        if service_id is not None and (isinstance(service_id, bool) or not isinstance(service_id, int) or service_id <= 0):
            raise ValueError("bad service id")
        services.append(AppointmentService(service_id, item["name"].strip()))
    technician = raw.get("technician_name")
    if technician is not None and not isinstance(technician, str):
        raise ValueError("bad technician")
    return Lookup(outcome, FoundAppointment(raw["code"].strip(), raw["appointment_time"].strip(), raw["status"].strip(), raw["customer_name"].strip(),
                                            tuple(services), technician.strip() if technician and technician.strip() else None))


def _http_lookup(base_url: str, token: str, phone_e164: str) -> object:
    if urllib.parse.urlparse(base_url).scheme not in ("http", "https"):
        raise ValueError("OWNER_API_BASE must be an http(s) URL")
    request = urllib.request.Request(
        base_url.rstrip("/") + LOOKUP_PATH + "?" + urllib.parse.urlencode({"phone": phone_e164}),
        headers={INTERNAL_TOKEN_HEADER: token, "Accept": "application/json"},
        method="GET",
    )
    with _opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # nosec - configured Owner URL
        return json.loads(response.read().decode("utf-8"))


class OwnerAppointmentClient:
    def __init__(self, fetcher: Callable[[str, str, str], object] = _http_lookup):
        self.fetcher = fetcher

    def lookup(self, phone_e164: str) -> Lookup:
        base_url = os.getenv("OWNER_API_BASE", "").strip()
        token = os.getenv("CHECKIN_INTERNAL_SERVICE_TOKEN", "")
        if not base_url or not token:
            raise AppointmentLookupUnavailable("not configured")
        try:
            return parse_lookup(self.fetcher(base_url, token, phone_e164))
        except urllib.error.HTTPError as exc:
            logger.error("Owner appointment lookup failed with HTTP %s.", exc.code)  # never the phone number or the body
        except (OSError, ValueError) as exc:
            logger.error("Owner appointment lookup failed: %s", type(exc).__name__)
        raise AppointmentLookupUnavailable("unavailable")


appointments_client = OwnerAppointmentClient()
