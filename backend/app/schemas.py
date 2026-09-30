import re
from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, computed_field, field_validator

from .timeutils import today_local

MIN_BIRTH_DATE = date(1900, 1, 1)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def format_phone_display(digits: str) -> str:
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def validate_phone(v: str) -> str:
    digits_only = re.sub(r"\D", "", v)
    if len(digits_only) != 10:
        raise ValueError("Phone number must be exactly 10 digits.")
    return digits_only


def _clean_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Name cannot be empty.")
    return v


def _clean_email(v: Optional[str]) -> Optional[str]:
    """Empty -> None; otherwise it must look like an email address."""
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if not _EMAIL_RE.match(v):
        raise ValueError("Please enter a valid email address.")
    return v


def _check_birth_date(v: date) -> date:
    if v > today_local():
        raise ValueError("Date of birth cannot be in the future.")
    if v < MIN_BIRTH_DATE:
        raise ValueError("Date of birth must be 1900 or later.")
    return v


Phone = Annotated[str, AfterValidator(validate_phone)]
Name = Annotated[str, AfterValidator(_clean_name)]
OptionalEmail = Annotated[Optional[str], AfterValidator(_clean_email)]
BirthDate = Annotated[date, AfterValidator(_check_birth_date)]


# ----------------------------
# Customers
# ----------------------------
class CustomerCreate(BaseModel):
    full_name: Name
    phone_number: Phone
    email: OptionalEmail = None
    date_of_birth: BirthDate
    referral_code: Optional[str] = None  


class CustomerResponse(BaseModel):
    id: int
    full_name: str
    phone_number: str
    email: Optional[str] = None
    date_of_birth: date
    referral_code: Optional[str] = None
    referral_count: int = 0
    referral_discount_percent: int
    referral_discount_pending: bool = False
    visit_discount_pending: bool = False
    birthday_discount_amount: int
    birthday_discount_used_month: Optional[str] = None
    visit_count_cycle: int
    used_referral_code: Optional[str] = None
    used_referral_from_customer_id: Optional[int] = None

    @computed_field
    @property
    def phone_number_formatted(self) -> str:
        return format_phone_display(self.phone_number)

    model_config = ConfigDict(from_attributes=True)


class UpdatePhoneRequest(BaseModel):
    new_phone_number: Phone


class UpdateCustomerProfileRequest(BaseModel):
    full_name: Name
    phone_number: Phone
    email: OptionalEmail = None


# ----------------------------
# Services / check-in
# ----------------------------
class ServiceResponse(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class CheckInCreate(BaseModel):
    selected_service_ids: list[int]

    @field_validator("selected_service_ids")
    @classmethod
    def validate_service_ids(cls, v: list[int]) -> list[int]:
        unique_ids = list(dict.fromkeys(item for item in v if item > 0))
        if not unique_ids:
            raise ValueError("Please select at least one service.")
        return unique_ids


class CheckInResponse(BaseModel):
    message: str
    phone_number: str
    full_name: str
    visit_count: int
    visit_count_cycle: int
    referral_code: Optional[str] = None
    referral_discount_percent: int
    birthday_discount_available: bool
    birthday_discount_amount: int
    discounts_applied: list[dict] = []
    selected_services: list[str] = []


class TodayCheckInItem(BaseModel):
    position: int
    full_name: str
    phone_number: str
    checked_in_at: datetime
    services: list[str] = []
    discount_type: Optional[str] = None
    discount_value: float = 0
    discount_label: Optional[str] = None


class TodayCheckInResponse(BaseModel):
    checkins: list[TodayCheckInItem]


# ----------------------------
# Referrals / birthdays
# ----------------------------
class ApplyReferralCodeRequest(BaseModel):
    phone_number: Phone
    referral_code: str


class ApplyReferralCodeResponse(BaseModel):
    message: str
    phone_number: str
    full_name: str
    used_referral_code: str
    referral_from_customer_name: str
    discount_percent: int


class BirthdayReminderResponse(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str] = None
    date_of_birth: date
    days_until_birthday: int
    birthday_discount_amount: int