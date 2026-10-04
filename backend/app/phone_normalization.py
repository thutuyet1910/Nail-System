import re
from dataclasses import dataclass


_ALLOWED_PHONE_CHARACTERS = re.compile(r"^[0-9+().\-\s]+$")


class PhoneNormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class USPhone:
    national_digits: str
    e164: str


def normalize_us_phone(value: str) -> USPhone:
    """Normalize a US phone without accepting arbitrary international numbers."""
    raw = (value or "").strip()
    if not raw or not _ALLOWED_PHONE_CHARACTERS.fullmatch(raw):
        raise PhoneNormalizationError("Phone number must be a valid 10-digit US number.")

    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        if len(digits) != 11 or not digits.startswith("1"):
            raise PhoneNormalizationError("Only +1 US phone numbers are supported.")
        digits = digits[1:]
    elif len(digits) != 10:
        raise PhoneNormalizationError("Phone number must be exactly 10 US digits.")

    if len(digits) != 10:
        raise PhoneNormalizationError("Phone number must be exactly 10 US digits.")
    return USPhone(national_digits=digits, e164=f"+1{digits}")
