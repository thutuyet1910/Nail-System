from typing import Optional
from pydantic import BaseModel
from datetime import date, datetime


class CustomerCreate(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str] = None
    date_of_birth: date
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
    birthday_discount_amount: int
    birthday_discount_used_month: Optional[str] = None
    visit_count_cycle: int
    used_referral_code: Optional[str] = None
    used_referral_from_customer_id: Optional[int] = None

    class Config:
        from_attributes = True


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
    discounts_applied: list = []


class ApplyReferralCodeRequest(BaseModel):
    phone_number: str
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


class TodayCheckInItem(BaseModel):
    position: int
    full_name: str
    phone_number: str
    checked_in_at: datetime

    class Config:
        from_attributes = True


class TodayCheckInResponse(BaseModel):
    checkins: list[TodayCheckInItem]    

class UpdatePhoneRequest(BaseModel):
    new_phone_number: str