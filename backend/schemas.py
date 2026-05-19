from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


# ----------------------------
# Technician Schemas
# ----------------------------
class TechnicianBase(BaseModel):
    employee_id: Optional[str] = None
    full_name: str
    phone: Optional[str] = None
    skills: Optional[str] = None
    specialties: Optional[str] = None
    start_date: Optional[date] = None
    status: str = "off"
    availability: str = "off today"
    work_schedule: Optional[str] = None
    notes: Optional[str] = None
    profile_photo: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if not v:
            return v
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Phone number must contain 10 digits")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        allowed = {"active", "off", "unavailable"}
        if v not in allowed:
            raise ValueError("Status must be one of: active, off, unavailable")
        return v

    @field_validator("availability")
    @classmethod
    def validate_availability(cls, v):
        if v and v.lower().startswith("date off:"):
            return v
        allowed = {"available today", "on break", "busy", "off today"}
        if v not in allowed:
            raise ValueError("Availability must be one of: available today, on break, busy, off today, or date off range")
        return v


class TechnicianCreate(TechnicianBase):
    pass


class TechnicianUpdate(BaseModel):
    employee_id: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    skills: Optional[str] = None
    specialties: Optional[str] = None
    start_date: Optional[date] = None
    status: Optional[str] = None
    availability: Optional[str] = None
    work_schedule: Optional[str] = None
    notes: Optional[str] = None
    profile_photo: Optional[str] = None


class TechnicianOut(TechnicianBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class TechnicianCardOut(TechnicianOut):
    today_appointments_count: int
    today_turns_count: int

    model_config = ConfigDict(from_attributes=True)


# ----------------------------
# Appointment Schemas
# ----------------------------
class AppointmentBase(BaseModel):
    customer_name: str
    customer_phone: str
    service_category: str
    appointment_time: datetime

    service_name: Optional[str] = None
    appointment_code: Optional[str] = None
    customer_type: str = "new"
    note: Optional[str] = None
    special_requests: Optional[str] = None
    allergies: Optional[str] = None
    technician_id: Optional[int] = None
    preferred_technician_id: Optional[int] = None
    people_count: int = 1
    status: str = "scheduled"

    @field_validator("customer_phone")
    @classmethod
    def validate_customer_phone(cls, v):
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Customer phone number must contain 10 digits")
        return v

    @field_validator("customer_type")
    @classmethod
    def validate_customer_type(cls, v):
        allowed = {"new", "returning"}
        if v not in allowed:
            raise ValueError("Customer type must be one of: new, returning")
        return v

    @field_validator("status")
    @classmethod
    def validate_appointment_status(cls, v):
        allowed = {"scheduled", "checked_in", "assigned", "in_service", "done", "cancelled"}
        if v not in allowed:
            raise ValueError("Appointment status must be one of: scheduled, checked_in, assigned, in_service, done, cancelled")
        return v


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(AppointmentBase):
    pass


class AppointmentOut(AppointmentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----------------------------
# Turn Schemas
# ----------------------------
class TurnBase(BaseModel):
    customer_name: str
    service_name: str
    technician_id: int
    customer_phone: Optional[str] = None
    preferred_technician_id: Optional[int] = None
    source: str = "checkin"
    assigned_by: Optional[str] = None
    notes: Optional[str] = None
    status: str = "waiting"
    discount_type: Optional[str] = None
    discount_value: Optional[float] = 0
    discount_label: Optional[str] = None

    @field_validator("customer_phone")
    @classmethod
    def validate_turn_phone(cls, v):
        if not v:
            return v
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Customer phone number must contain 10 digits")
        return v

    @field_validator("source")
    @classmethod
    def validate_source(cls, v):
        allowed = {"checkin", "appointment", "manual"}
        if v not in allowed:
            raise ValueError("Source must be one of: checkin, appointment, manual")
        return v

    @field_validator("status")
    @classmethod
    def validate_turn_status(cls, v):
        allowed = {"waiting", "assigned", "in_service", "done", "cancelled"}
        if v not in allowed:
            raise ValueError("Turn status must be one of: waiting, assigned, in_service, done, cancelled")
        return v


class TurnCreate(TurnBase):
    pass


class AssignTurnRequest(BaseModel):
    customer_name: str
    service_name: str
    technician_id: int
    customer_phone: Optional[str] = None
    preferred_technician_id: Optional[int] = None
    source: str = "manual"
    assigned_by: Optional[str] = "manual"
    notes: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = 0
    discount_label: Optional[str] = None

    @field_validator("customer_phone")
    @classmethod
    def validate_customer_phone(cls, v):
        if not v:
            return v
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Customer phone number must contain 10 digits")
        return v


class AutoAssignTurnRequest(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    service_name: str
    preferred_technician_id: Optional[int] = None
    source: str = "checkin"
    notes: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = 0
    discount_label: Optional[str] = None

    @field_validator("customer_phone")
    @classmethod
    def validate_customer_phone(cls, v):
        if not v:
            return v
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Customer phone number must contain 10 digits")
        return v


class AssignPreferredTurnRequest(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    service_name: str
    preferred_technician_id: int
    source: str = "checkin"
    notes: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = 0
    discount_label: Optional[str] = None

    @field_validator("customer_phone")
    @classmethod
    def validate_customer_phone(cls, v):
        if not v:
            return v
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Customer phone number must contain 10 digits")
        return v


class ReassignTurnRequest(BaseModel):
    technician_id: int
    assigned_by: Optional[str] = "manager"
    notes: Optional[str] = None


class TurnStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        allowed = {"waiting", "assigned", "in_service", "done", "cancelled"}
        if v not in allowed:
            raise ValueError("Turn status must be one of: waiting, assigned, in_service, done, cancelled")
        return v


class TurnStartRequest(BaseModel):
    notes: Optional[str] = None


class TurnCompleteRequest(BaseModel):
    notes: Optional[str] = None


class TurnOut(BaseModel):
    id: int
    turn_number: int
    customer_name: str
    customer_phone: Optional[str] = None
    service_name: str
    status: str
    source: str
    assigned_by: Optional[str] = None
    notes: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = 0
    discount_label: Optional[str] = None

    technician_id: int
    preferred_technician_id: Optional[int] = None

    created_at: datetime
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------
# Checkout Schemas
# ----------------------------
class CheckoutBase(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None

    technician_id: Optional[int] = None
    turn_id: Optional[int] = None
    appointment_id: Optional[int] = None

    payment_method: str = "cash"
    service_name: str

    subtotal: float
    discount_type: str = "none"
    discount_value: float = 0
    discount_amount: float = 0
    discount_paid_by: str = "owner"

    tip_amount: float = 0
    net_service: float = 0
    technician_share: float = 0
    salon_share: float = 0
    salon_actual_revenue: float = 0
    technician_total: float = 0
    customer_pays: float = 0

    note: Optional[str] = None

    @field_validator("customer_phone")
    @classmethod
    def validate_checkout_phone(cls, v):
        if not v:
            return v
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Customer phone number must contain 10 digits")
        return v

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v):
        allowed = {"cash", "card", "zelle", "gift card"}
        if v not in allowed:
            raise ValueError("Payment method must be one of: cash, card, zelle, gift card")
        return v

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, v):
        allowed = {"none", "fixed", "percent"}
        if v not in allowed:
            raise ValueError("Discount type must be one of: none, fixed, percent")
        return v

    @field_validator("discount_paid_by")
    @classmethod
    def validate_discount_paid_by(cls, v):
        if v != "owner":
            raise ValueError("Discount paid by must be owner")
        return v


class CheckoutCreate(CheckoutBase):
    pass


class CheckoutOut(CheckoutBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----------------------------
# Income Report Schemas
# ----------------------------
class IncomeTurnDetail(BaseModel):
    checkout_id: int
    turn_id: Optional[int] = None
    turn_number: Optional[int] = None
    customer_name: str
    customer_phone: Optional[str] = None
    technician_id: Optional[int] = None
    technician_name: Optional[str] = None
    service_name: str
    payment_method: str
    gross_before_discount: float
    discount_amount: float
    net_after_discount: float
    tech_60_percent: float
    tip_amount: float
    tech_total: float
    salon_income_after_tech: float
    customer_pays: float
    created_at: datetime
    note: Optional[str] = None


class TechIncomeSummary(BaseModel):
    technician_id: Optional[int] = None
    technician_name: str
    date: date
    gross_before_60: float
    tech_after_60: float
    tip_total: float
    tech_total: float
    turns: int
    details: list[IncomeTurnDetail]


class SalonIncomePeriodSummary(BaseModel):
    period: str
    start_date: date
    end_date: date
    income_before_discount: float
    total_discount: float
    income_after_discount: float
    tech_60_percent_total: float
    tech_tip_total: float
    total_paid_to_techs: float
    salon_income_after_techs: float
    turns: int


class TechIncomeReport(BaseModel):
    date: date
    technicians: list[TechIncomeSummary]


class SalonIncomeReport(BaseModel):
    date: date
    day: SalonIncomePeriodSummary
    week: SalonIncomePeriodSummary
    year: SalonIncomePeriodSummary
    details: list[IncomeTurnDetail]


# ----------------------------
# Inventory Schemas
# ----------------------------
class InventoryItemBase(BaseModel):
    item_name: str
    category: str
    supplier: Optional[str] = None
    quantity: int
    unit_price: float
    purchase_date: Optional[date] = None
    low_stock_level: int = 3


class InventoryItemCreate(InventoryItemBase):
    pass


class InventoryItemUpdate(BaseModel):
    item_name: Optional[str] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[float] = None
    purchase_date: Optional[date] = None
    low_stock_level: Optional[int] = None


class InventoryItemOut(InventoryItemBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
