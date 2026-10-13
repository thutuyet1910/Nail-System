"""Kiosk device authentication, rate limiting, client-address trust and the short-lived profile-edit token.

Trust model (Phase 2 of the LAN deployment)
-------------------------------------------
* Every route a tablet may call (see deploy/lan-poc/README.md) requires a **device token** in the
  `X-Kiosk-Device-Token` header. The token is opaque, random, issued once when a pairing code is redeemed,
  stored only as a SHA-256 hash, and revocable. It is NOT the internal service token and grants nothing
  except these kiosk routes.
* The backend listens on 127.0.0.1 only. The reverse proxy (Caddy) is the one process that talks to the
  LAN, and it writes the real client address into `X-Kiosk-Client-Ip`, replacing whatever the client sent.
  That header is believed ONLY when the TCP peer is a trusted proxy (loopback by default,
  `TRUSTED_PROXY_IPS`). A request from any other peer is rate limited by its own address.
* Rate limits are in-process (one backend process per salon). A multi-process or cloud deployment needs a
  shared store.
"""

import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .database import get_db

DEVICE_TOKEN_HEADER = "X-Kiosk-Device-Token"
PROFILE_TOKEN_HEADER = "X-Profile-Edit-Token"
CLIENT_IP_HEADER = "X-Kiosk-Client-Ip"

PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: easy to read off a screen
PAIRING_CODE_LENGTH = 8

# bucket -> (allowed events, window in seconds). Tests may adjust these.
LIMITS = {
    "device_requests": (120, 60),      # every kiosk call, per device
    "lookup": (20, 60),                # phone lookup + today's status, per device
    "lookup_miss": (15, 600),          # lookups that found nobody (enumeration), per device
    "referral": (10, 60),              # referral validate/apply, per device
    "referral_fail": (10, 600),        # referral calls that failed (code guessing), per device
    "pair_fail_ip": (5, 600),          # wrong/expired pairing codes, per client address
    "pair_fail_global": (20, 600),     # wrong/expired pairing codes, whole salon
    "profile_fail_customer": (5, 900),  # wrong birth dates, per customer
    "profile_fail_device": (10, 900),   # wrong birth dates / missing edit token, per device
    "bad_token_ip": (30, 600),         # unknown or revoked device tokens, per client address
}

PROFILE_EDIT_SECONDS = int(os.getenv("KIOSK_PROFILE_EDIT_SECONDS", "300"))
PAIRING_CODE_MINUTES = max(1, min(30, int(os.getenv("KIOSK_PAIRING_CODE_MINUTES", "10"))))
MAX_ACTIVE_DEVICES = 10
LAST_SEEN_RESOLUTION_SECONDS = 60


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_secret(value: str) -> str:
    """Tokens and pairing codes are 40+ bits of CSPRNG output, so a plain SHA-256 is enough: there is nothing
    to brute-force offline that the pairing expiry and rate limits do not already stop."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_pairing_code() -> str:
    return "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def display_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def normalize_code(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def first_name_of(full_name: str | None) -> str:
    parts = str(full_name or "").split()
    return parts[0] if parts else "there"


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


# --------------------------------------------------------------------------------------------------
# Client address (trust boundary)
# --------------------------------------------------------------------------------------------------
def _trusted_proxies() -> set[str]:
    raw = os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1")
    return {item.strip() for item in raw.split(",") if item.strip()}


def client_ip(request: Request) -> str:
    """The caller's address for rate limiting. `X-Kiosk-Client-Ip` is honoured only from a trusted proxy."""
    peer = request.client.host if request.client else ""
    if peer in _trusted_proxies():
        forwarded = request.headers.get(CLIENT_IP_HEADER, "").strip()
        if forwarded:
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass  # malformed: fall back to the peer
    return peer or "unknown"


# --------------------------------------------------------------------------------------------------
# Rate limiting (sliding window, in process)
# --------------------------------------------------------------------------------------------------
_events: dict[tuple[str, str], deque] = {}
_lock = threading.Lock()


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Too many attempts. Please wait a few minutes, or ask the front desk for help.",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _window(bucket: str) -> tuple[int, int]:
    return LIMITS[bucket]


def _prune(events: deque, window: int, now: float) -> None:
    while events and events[0] <= now - window:
        events.popleft()


def throttle(bucket: str, key: str) -> None:
    """Counts this event and refuses it when the window is already full."""
    limit, window = _window(bucket)
    now = time.monotonic()
    with _lock:
        events = _events.setdefault((bucket, key), deque())
        _prune(events, window, now)
        if len(events) >= limit:
            raise _too_many(int(events[0] + window - now) + 1)
        events.append(now)


def ensure_not_blocked(bucket: str, key: str) -> None:
    """Refuses when `bucket` already holds its limit of recorded failures (nothing is counted here)."""
    limit, window = _window(bucket)
    now = time.monotonic()
    with _lock:
        events = _events.get((bucket, key))
        if not events:
            return
        _prune(events, window, now)
        if len(events) >= limit:
            raise _too_many(int(events[0] + window - now) + 1)


def record_failure(bucket: str, key: str) -> None:
    _limit, window = _window(bucket)
    now = time.monotonic()
    with _lock:
        events = _events.setdefault((bucket, key), deque())
        _prune(events, window, now)
        events.append(now)


def clear_failures(bucket: str, key: str) -> None:
    with _lock:
        _events.pop((bucket, key), None)


# --------------------------------------------------------------------------------------------------
# Device authentication
# --------------------------------------------------------------------------------------------------
def _not_authorized() -> HTTPException:
    # One answer for missing, malformed, unknown, unpaired and revoked tokens: nothing about validity leaks.
    return HTTPException(
        status_code=401,
        detail="This tablet is not paired. Please pair it from the Owner Dashboard.",
        headers={"WWW-Authenticate": "KioskDevice"},
    )


def issue_device_token(device_id: int) -> tuple[str, str]:
    """(token to give the tablet once, hash to store). The id prefix makes the lookup a primary-key read."""
    secret = secrets.token_urlsafe(32)
    return f"{device_id}.{secret}", hash_secret(secret)


def _device_for_token(db: Session, token: str | None) -> models.KioskDevice | None:
    if not token or "." not in token or len(token) > 200:
        return None
    raw_id, _, secret = token.partition(".")
    if not raw_id.isdigit() or len(raw_id) > 9 or len(secret) < 20:
        return None
    device = db.get(models.KioskDevice, int(raw_id))
    stored = device.token_hash if device and device.token_hash else "0" * 64
    matches = hmac.compare_digest(hash_secret(secret), stored)  # constant time, also when the device is unknown
    if device is None or not matches or device.revoked_at is not None:
        return None
    return device


def require_kiosk_device(
    request: Request,
    token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER),
    db: Session = Depends(get_db),
) -> models.KioskDevice:
    ip = client_ip(request)
    ensure_not_blocked("bad_token_ip", ip)
    device = _device_for_token(db, token)
    if device is None:
        record_failure("bad_token_ip", ip)
        raise _not_authorized()
    throttle("device_requests", str(device.id))
    now = utc_now()
    if device.last_seen_at is None or now - device.last_seen_at > timedelta(seconds=LAST_SEEN_RESOLUTION_SECONDS):
        device.last_seen_at = now
        db.commit()
    request.state.kiosk_device_id = device.id
    return device


# --------------------------------------------------------------------------------------------------
# Profile-edit token: proves "this person just gave the birth date on file" for a few minutes
# --------------------------------------------------------------------------------------------------
_profile_tokens: dict[str, tuple[int, int, float]] = {}  # hash -> (device id, customer id, expires monotonic)
_MAX_PROFILE_TOKENS = 200


def issue_profile_token(device_id: int, customer_id: int) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        for key in [k for k, v in _profile_tokens.items() if v[2] <= now]:
            del _profile_tokens[key]
        while len(_profile_tokens) >= _MAX_PROFILE_TOKENS:
            del _profile_tokens[min(_profile_tokens, key=lambda k: _profile_tokens[k][2])]
        _profile_tokens[hash_secret(token)] = (device_id, customer_id, now + PROFILE_EDIT_SECONDS)
    return token, PROFILE_EDIT_SECONDS


def profile_token_is_valid(token: str | None, device_id: int, customer_id: int) -> bool:
    if not token:
        return False
    with _lock:
        entry = _profile_tokens.get(hash_secret(token))
    if entry is None or entry[2] <= time.monotonic():
        return False
    return entry[0] == device_id and entry[1] == customer_id


def consume_profile_token(token: str) -> None:
    with _lock:
        _profile_tokens.pop(hash_secret(token), None)


def reset_state() -> None:
    """For tests: forget every counter and every profile-edit token."""
    with _lock:
        _events.clear()
        _profile_tokens.clear()
