import hmac
import os

from fastapi import Header, HTTPException


INTERNAL_TOKEN_HEADER = "X-Internal-Service-Token"


def require_internal_service(x_internal_service_token: str | None = Header(default=None)) -> None:
    expected = os.getenv("CHECKIN_INTERNAL_SERVICE_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Internal service authentication is not configured")
    if not x_internal_service_token or not hmac.compare_digest(x_internal_service_token, expected):
        raise HTTPException(status_code=401, detail="Valid internal service credentials required")
