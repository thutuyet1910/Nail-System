"""Owner-only salon settings: profile, weekly booking hours, AI receptionist status, owner security.

Booking hours stay in the one existing table (business_hours): the calendar, manual booking, the AI's
availability and get_salon_info all read it, so saving here updates every one of them at once.
Nothing in this module reads or returns a secret.
"""
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

import models
from phone_normalization import PhoneNormalizationError, normalize_us_phone
from voice_config import VoiceConfig


class SettingsError(ValueError):
    """A change the salon's rules refuse. main.py turns it into an HTTP 400."""


TIMEZONE_NOTE = ("The time zone is set when the salon is installed. Appointments are stored against it, "
                 "so changing it later would silently move real appointments.")


def normalize_optional_phone(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return normalize_us_phone(text).e164
    except PhoneNormalizationError as exc:
        raise SettingsError(str(exc)) from exc


def format_us_phone(e164: str | None) -> str | None:
    if not e164:
        return None
    digits = e164[-10:]
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}" if len(digits) == 10 and digits.isdigit() else e164


def mask_phone(e164: str | None) -> str | None:
    return f"(***) ***-{e164[-4:]}" if e164 and len(e164) >= 4 else None


# ------------------------------------------------------------------ salon profile
def _settings_row(db: Session) -> models.SalonSettings:
    row = db.get(models.SalonSettings, 1)
    if not row:
        raise SettingsError("Salon settings have not been created yet")
    return row


def get_profile(db: Session) -> dict:
    row = _settings_row(db)
    return {
        "salon_name": row.salon_name,
        "business_phone": row.business_phone,
        "business_phone_display": format_us_phone(row.business_phone),
        "timezone": row.timezone,
        "timezone_editable": False,
        "timezone_note": TIMEZONE_NOTE,
        "slot_interval_minutes": row.slot_interval_minutes,
    }


def update_profile(db: Session, *, salon_name: str, business_phone: str | None) -> dict:
    row = _settings_row(db)
    phone = normalize_optional_phone(business_phone)  # validate before touching anything
    row.salon_name = salon_name.strip()
    row.business_phone = phone
    db.commit()
    return get_profile(db)


# ------------------------------------------------------------------ weekly booking hours
def hours_payload(db: Session) -> list[dict]:
    rows = {row.day_of_week: row for row in db.query(models.BusinessHour).all()}
    return [{
        "day_of_week": day, "is_closed": rows[day].is_closed if day in rows else True,
        "opens_at": rows[day].opens_at.isoformat(timespec="minutes") if day in rows and rows[day].opens_at else None,
        "closes_at": rows[day].closes_at.isoformat(timespec="minutes") if day in rows and rows[day].closes_at else None,
    } for day in range(7)]


def replace_business_hours(db: Session, days) -> list[dict]:
    """The complete 7-day schedule, validated first and written in ONE transaction: an invalid day leaves
    the whole week untouched. Appointments are never moved or deleted by a hours change."""
    interval = _settings_row(db).slot_interval_minutes
    for day in days:
        if day.is_closed:
            continue
        for label, value in (("Opening", day.opens_at), ("Closing", day.closes_at)):
            if (value.hour * 60 + value.minute) % interval:
                raise SettingsError(f"{label} time must be on a {interval}-minute boundary")
    try:
        existing = {row.day_of_week: row for row in db.query(models.BusinessHour).all()}
        for day in days:
            row = existing.get(day.day_of_week)
            if row is None:
                row = models.BusinessHour(day_of_week=day.day_of_week)
                db.add(row)
            row.is_closed, row.opens_at, row.closes_at = day.is_closed, day.opens_at, day.closes_at
        db.commit()
    except Exception:
        db.rollback()
        raise
    return hours_payload(db)


# ------------------------------------------------------------------ AI receptionist (read-only status)
def ai_receptionist_status(db: Session) -> dict:
    """Which parts of the voice integration are configured on the SERVER. Never returns a credential: only
    yes/no flags, the (public) Twilio phone number and the names of missing items."""
    config = VoiceConfig.from_env()
    parts = {
        "Twilio account": bool(config.twilio_account_sid and config.twilio_auth_token),
        "Twilio phone number": bool(config.twilio_phone_number),
        "OpenAI": bool(config.openai_api_key and config.openai_realtime_model),
        "Public web address (https)": urlsplit(config.public_base_url).scheme == "https" and bool(urlsplit(config.public_base_url).netloc),
    }
    configured = all(parts.values())
    try:
        twilio_number = normalize_us_phone(config.twilio_phone_number).e164 if config.twilio_phone_number else None
    except PhoneNormalizationError:
        twilio_number = None
    salon_phone = _settings_row(db).business_phone
    return {
        "configured": configured,
        "missing": [name for name, ok in parts.items() if not ok],
        "voice_enabled": config.enabled,
        "real_calls_allowed": config.allow_real_calls,
        "ready_for_calls": configured and config.enabled and config.allow_real_calls,
        "twilio_number": twilio_number,
        "twilio_number_display": format_us_phone(twilio_number),
        "public_salon_phone": salon_phone,
        "public_salon_phone_display": format_us_phone(salon_phone),
        "note": ("The public salon phone is the number customers know. It is NOT the Twilio number and changing it "
                 "does not connect or reconfigure Twilio."),
    }


# ------------------------------------------------------------------ owner security
def security_status(db: Session) -> dict:
    credential = db.query(models.OwnerCredential).filter(models.OwnerCredential.is_active.is_(True)).first()
    phone = credential.recovery_phone_e164 if credential else None
    return {
        "has_recovery_phone": bool(phone),
        "recovery_phone_masked": mask_phone(phone),
        "sms_recovery_available": False,
        "sms_recovery_note": ("Text-message recovery is not available yet. If the password is forgotten, "
                              "an administrator can reset it on the salon computer with the reset tool."),
    }


def set_recovery_phone(db: Session, credential: models.OwnerCredential, phone: str | None) -> dict:
    credential.recovery_phone_e164 = normalize_optional_phone(phone)
    db.commit()
    return security_status(db)
