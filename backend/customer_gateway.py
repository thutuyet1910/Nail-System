import json
import os
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from phone_normalization import normalize_us_phone


class CustomerGatewayError(RuntimeError):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


class CustomerGateway(Protocol):
    def find_customer_by_phone(self, phone: str) -> dict | None: ...
    def get_customer(self, customer_id: int) -> dict | None: ...
    def get_today_checkins(self) -> list[dict]: ...


class HttpCustomerGateway:
    """The owner app's narrow boundary to the check-in customer authority."""

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 3.0):
        self.base_url = (base_url or os.getenv("CHECKIN_API_BASE", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.internal_token = os.getenv("CHECKIN_INTERNAL_SERVICE_TOKEN", "")

    def _get(self, path: str):
        try:
            headers = {"Accept": "application/json"}
            if self.internal_token:
                headers["X-Internal-Service-Token"] = self.internal_token
            with urlopen(Request(f"{self.base_url}{path}", headers=headers), timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            status = 502 if exc.code in (401, 403, 500, 503) else 503
            raise CustomerGatewayError(f"Check-in service returned HTTP {exc.code}", status) from exc
        except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CustomerGatewayError("Check-in service is unavailable or returned malformed data") from exc
        return payload

    def find_customer_by_phone(self, phone: str) -> dict | None:
        national = normalize_us_phone(phone).national_digits
        payload = self._get(f"/internal/customers/by-phone/{quote(national)}")
        if payload is not None and not isinstance(payload, dict):
            raise CustomerGatewayError("Check-in service returned malformed customer data")
        return payload

    def get_customer(self, customer_id: int) -> dict | None:
        payload = self._get(f"/customers/id/{int(customer_id)}")
        if payload is not None and not isinstance(payload, dict):
            raise CustomerGatewayError("Check-in service returned malformed customer data")
        return payload

    def get_today_checkins(self) -> list[dict]:
        payload = self._get("/today-checkins")
        if not isinstance(payload, dict) or not isinstance(payload.get("checkins"), list):
            raise CustomerGatewayError("Check-in service returned malformed queue data")
        return payload["checkins"]
