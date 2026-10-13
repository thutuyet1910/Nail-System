"""Kiosk device pairing.

    Owner Dashboard -> Owner backend -> (loopback, internal service token) POST /internal/kiosk/pairing-codes
    Tablet          -> Caddy -> POST /kiosk/pair {code}  ->  one device token, shown to the tablet once

The internal routes are never forwarded by the reverse proxy; the tablet can reach only `/kiosk/pair`.
Neither the pairing code nor the device token is stored in clear text, and the Owner side can never read a
device token back (it only ever sees the one-time pairing code it asked for).
"""

import hmac
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session
from typing import Annotated

from . import models
from .database import get_db
from .kiosk_security import (
    MAX_ACTIVE_DEVICES,
    PAIRING_CODE_LENGTH,
    PAIRING_CODE_MINUTES,
    clear_failures,
    client_ip,
    display_code,
    ensure_not_blocked,
    hash_secret,
    issue_device_token,
    new_pairing_code,
    normalize_code,
    record_failure,
    utc_now,
)
from .security import require_internal_service

router = APIRouter()

DEFAULT_DEVICE_NAME = "Check-In tablet"
_STALE_PENDING = timedelta(hours=1)


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40)


class PairResponse(BaseModel):
    device_id: int
    display_name: str
    device_token: str


class PairingCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] = DEFAULT_DEVICE_NAME


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None  # stored as naive UTC


def _status(device: models.KioskDevice, now: datetime) -> str:
    if device.revoked_at is not None:
        return "revoked"
    if device.token_hash:
        return "paired"
    if device.pairing_expires_at and device.pairing_expires_at > now:
        return "pending"
    return "expired"


def _public_device(device: models.KioskDevice, now: datetime) -> dict:
    """Everything the Owner may see. Never a token, a code or a hash."""
    return {
        "id": device.id,
        "display_name": device.display_name,
        "status": _status(device, now),
        "created_at": _iso(device.created_at),
        "paired_at": _iso(device.paired_at),
        "last_seen_at": _iso(device.last_seen_at),
        "revoked_at": _iso(device.revoked_at),
        "pairing_expires_at": _iso(device.pairing_expires_at) if _status(device, now) == "pending" else None,
    }


def _prune_stale_pending(db: Session, now: datetime) -> None:
    db.query(models.KioskDevice).filter(
        models.KioskDevice.token_hash.is_(None),
        models.KioskDevice.revoked_at.is_(None),
        models.KioskDevice.pairing_expires_at < now - _STALE_PENDING,
    ).delete(synchronize_session=False)
    db.commit()


# ------------------------------------------------------------------------------------------------
# Tablet: redeem a pairing code (the only kiosk route that needs no device token)
# ------------------------------------------------------------------------------------------------
@router.post("/kiosk/pair", response_model=PairResponse)
def redeem_pairing_code(payload: PairRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    ip = client_ip(request)
    ensure_not_blocked("pair_fail_ip", ip)
    ensure_not_blocked("pair_fail_global", "salon")

    code = normalize_code(payload.code)
    code_hash = hash_secret(code)
    device = None
    if len(code) == PAIRING_CODE_LENGTH:
        device = db.query(models.KioskDevice).filter(models.KioskDevice.pairing_code_hash == code_hash).first()
    now = utc_now()
    valid = (
        device is not None
        and hmac.compare_digest(code_hash, device.pairing_code_hash or "")
        and device.revoked_at is None
        and device.token_hash is None
        and device.pairing_expires_at is not None
        and device.pairing_expires_at > now
    )
    if not valid:
        record_failure("pair_fail_ip", ip)
        record_failure("pair_fail_global", "salon")
        # one message for wrong, expired, already-used and revoked codes
        raise HTTPException(status_code=400, detail="That pairing code is not valid or has expired.")

    token, token_hash = issue_device_token(device.id)
    user_agent = (request.headers.get("user-agent") or "")[:200] or None
    # One-time use even under a race: only the first redemption can flip the row.
    changed = (
        db.query(models.KioskDevice)
        .filter(
            models.KioskDevice.id == device.id,
            models.KioskDevice.pairing_code_hash == code_hash,
            models.KioskDevice.token_hash.is_(None),
            models.KioskDevice.revoked_at.is_(None),
        )
        .update(
            {
                "token_hash": token_hash,
                "pairing_code_hash": None,
                "pairing_expires_at": None,
                "paired_at": now,
                "last_seen_at": now,
                "user_agent": user_agent,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if changed != 1:
        record_failure("pair_fail_ip", ip)
        record_failure("pair_fail_global", "salon")
        raise HTTPException(status_code=400, detail="That pairing code is not valid or has expired.")
    clear_failures("pair_fail_ip", ip)
    return {"device_id": device.id, "display_name": device.display_name, "device_token": token}


# ------------------------------------------------------------------------------------------------
# Owner (via the Owner backend, loopback + internal service token): manage devices
# ------------------------------------------------------------------------------------------------
@router.post("/internal/kiosk/pairing-codes", status_code=201)
def create_pairing_code(payload: PairingCodeRequest, response: Response, db: Session = Depends(get_db), _=Depends(require_internal_service)):
    response.headers["Cache-Control"] = "no-store"
    now = utc_now()
    _prune_stale_pending(db, now)
    active = [d for d in db.query(models.KioskDevice).all() if _status(d, now) in ("pending", "paired")]
    if len(active) >= MAX_ACTIVE_DEVICES:
        raise HTTPException(status_code=409, detail=f"At most {MAX_ACTIVE_DEVICES} check-in devices can be active. Revoke one first.")

    while True:  # the code space is large; a collision just draws again
        code = new_pairing_code()
        code_hash = hash_secret(code)
        if not db.query(models.KioskDevice).filter(models.KioskDevice.pairing_code_hash == code_hash).first():
            break
    expires = now + timedelta(minutes=PAIRING_CODE_MINUTES)
    device = models.KioskDevice(
        display_name=payload.display_name,
        created_at=now,
        pairing_code_hash=code_hash,
        pairing_expires_at=expires,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return {
        "device_id": device.id,
        "display_name": device.display_name,
        "pairing_code": display_code(code),
        "expires_at": _iso(expires),
        "expires_in_seconds": PAIRING_CODE_MINUTES * 60,
    }


@router.get("/internal/kiosk/devices")
def list_devices(response: Response, db: Session = Depends(get_db), _=Depends(require_internal_service)):
    response.headers["Cache-Control"] = "no-store"
    now = utc_now()
    _prune_stale_pending(db, now)
    rows = db.query(models.KioskDevice).order_by(models.KioskDevice.id.desc()).all()
    visible = [d for d in rows if _status(d, now) != "expired"]
    revoked = [d for d in visible if d.revoked_at is not None][:10]  # a short tail of history, not an ever-growing list
    shown = [d for d in visible if d.revoked_at is None] + revoked
    return {"devices": [_public_device(d, now) for d in sorted(shown, key=lambda d: d.id, reverse=True)]}


@router.post("/internal/kiosk/devices/{device_id}/revoke")
def revoke_device(device_id: int, response: Response, db: Session = Depends(get_db), _=Depends(require_internal_service)):
    response.headers["Cache-Control"] = "no-store"
    device = db.get(models.KioskDevice, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Check-in device not found.")
    now = utc_now()
    if device.revoked_at is None:
        device.revoked_at = now
    device.token_hash = None          # the credential stops working immediately
    device.pairing_code_hash = None   # and an unredeemed code can no longer be used
    device.pairing_expires_at = None
    db.commit()
    return _public_device(device, now)
