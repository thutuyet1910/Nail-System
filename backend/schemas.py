from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


TECHNICIAN_STATUSES = ("active", "off", "unavailable")
TECHNICIAN_AVAILABILITY = ("available today", "on break", "busy", "off today")
CUSTOMER_TYPES = ("new", "returning")
APPOINTMENT_STATUSES = ("scheduled", "checked_in", "assigned", "in_service", "done", "cancelled")
TURN_STATUSES = ("waiting", "assigned", "in_service", "done", "cancelled")
TURN_SOURCES = ("checkin", "appointment", "manual")
PAYMENT_METHODS = ("cash", "card", "zelle", "gift card")
DISCOUNT_TYPES = ("none", "fixed", "percent")


def _phone_check(label: str, allow_empty: bool):
    def check(value):
        if allow_empty and not value:
            return value
        if len("".join(ch for ch in (value or "") if ch.isdigit())) != 10:
            raise ValueError(f"{label} must contain 10 digits")
        return value

    return check


def _one_of(label: str, allowed: tuple):
    def check(value):
        if value not in allowed:
            raise ValueError(f"{label} must be one of: {', '.join(allowed)}")
        return value

    return check


def _check_availability(value):
    if value and value.lower().startswith("date off:"):
        return value
    if value not in TECHNICIAN_AVAILABILITY:
        raise ValueError(
            f"Availability must be one of: {', '.join(TECHNICIAN_AVAILABILITY)}, or date off range"
        )
    return value


TechnicianPhone = Annotated[Optional[str], AfterValidator(_phone_check("Phone number", True))]
CustomerPhone = Annotated[str, AfterValidator(_phone_check("Customer phone number", False))]
OptionalCustomerPhone = Annotated[Optional[str], AfterValidator(_phone_check("Customer phone number", True))]

TechnicianStatus = Annotated[str, AfterValidator(_one_of("Status", TECHNICIAN_STATUSES))]
Availability = Annotated[str, AfterValidator(_check_availability)]
CustomerType = Annotated[str, AfterValidator(_one_of("Customer type", CUSTOMER_TYPES))]
AppointmentStatus = Annotated[str, AfterValidator(_one_of("Appointment status", APPOINTMENT_STATUSES))]
TurnStatus = Annotated[str, AfterValidator(_one_of("Turn status", TURN_STATUSES))]
TurnSource = Annotated[str, AfterValidator(_one_of("Source", TURN_SOURCES))]
PaymentMethod = Annotated[str, AfterValidator(_one_of("Payment method", PAYMENT_METHODS))]
DiscountType = Annotated[str, AfterValidator(_one_of("Discount type", DISCOUNT_TYPES))]

Money = Annotated[float, Field(ge=0)]  # money amounts can't be negative


# ----------------------------
# Technicians
# ----------------------------
class TechnicianBase(BaseModel):
    employee_id: Optional[str] = None
    full_name: str
    phone: TechnicianPhone = None
    skills: Optional[str] = None
    specialties: Optional[str] = None
    start_date: Optional[date] = None
    status: TechnicianStatus = "off"
    availability: Availability = "off today"
    work_schedule: Optional[str] = None
    notes: Optional[str] = None
    profile_photo: Optional[str] = None


class TechnicianCreate(TechnicianBase):
    pass


class TechnicianUpdate(BaseModel):
    """Same rules as TechnicianBase, but every field is optional."""

    employee_id: Optional[str] = None
    full_name: Optional[str] = None
    phone: TechnicianPhone = None
    skills: Optional[str] = None
    specialties: Optional[str] = None
    start_date: Optional[date] = None
    status: Optional[TechnicianStatus] = None
    availability: Optional[Availability] = None
    work_schedule: Optional[str] = None
    notes: Optional[str] = None
    profile_photo: Optional[str] = None


class TechnicianOut(TechnicianBase):
    id: int
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class TechnicianCardOut(TechnicianOut):
    today_appointments_count: int
    today_turns_count: int


# ----------------------------
# Appointments
# ----------------------------
class AppointmentBase(BaseModel):
    customer_name: str
    customer_phone: CustomerPhone
    service_category: str
    appointment_time: datetime

    service_name: Optional[str] = None
    appointment_code: Optional[str] = None
    customer_type: CustomerType = "new"
    note: Optional[str] = None
    special_requests: Optional[str] = None
    allergies: Optional[str] = None
    technician_id: Optional[int] = None
    preferred_technician_id: Optional[int] = None
    people_count: int = Field(default=1, ge=1)
    status: AppointmentStatus = "scheduled"


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
# Turns / dispatch
# ----------------------------
class TurnBase(BaseModel):
    customer_name: str
    service_name: str
    technician_id: int
    customer_phone: OptionalCustomerPhone = None
    preferred_technician_id: Optional[int] = None
    source: TurnSource = "checkin"
    assigned_by: Optional[str] = None
    notes: Optional[str] = None
    status: TurnStatus = "waiting"
    discount_type: Optional[str] = None
    discount_value: Optional[Money] = 0
    discount_label: Optional[str] = None


class TurnCreate(TurnBase):
    pass


class _TurnRequestBase(BaseModel):
    """Fields shared by the three assign requests."""

    customer_name: str
    customer_phone: OptionalCustomerPhone = None
    service_name: str
    preferred_technician_id: Optional[int] = None
    notes: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[Money] = 0
    discount_label: Optional[str] = None


class AssignTurnRequest(_TurnRequestBase):
    technician_id: int
    source: str = "manual"
    assigned_by: Optional[str] = "manual"


class AutoAssignTurnRequest(_TurnRequestBase):
    source: str = "checkin"


class AssignPreferredTurnRequest(_TurnRequestBase):
    preferred_technician_id: int
    source: str = "checkin"


class ReassignTurnRequest(BaseModel):
    technician_id: int
    assigned_by: Optional[str] = "manager"
    notes: Optional[str] = None


class TurnStatusUpdate(BaseModel):
    status: TurnStatus


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
# Checkout
# ----------------------------
class CheckoutCreate(BaseModel):
    """What the client is allowed to send: INPUTS only.
    """

    customer_name: str
    customer_phone: OptionalCustomerPhone = None

    technician_id: Optional[int] = None
    turn_id: Optional[int] = None
    appointment_id: Optional[int] = None

    payment_method: PaymentMethod = "cash"
    service_name: str

    subtotal: Money
    discount_type: DiscountType = "none"
    discount_value: Money = 0
    tip_amount: Money = 0

    note: Optional[str] = None

    @model_validator(mode="after")
    def check_discount_makes_sense(self):
        if self.discount_type == "percent" and self.discount_value > 100:
            raise ValueError("A percent discount cannot be more than 100")
        if self.discount_type == "fixed" and self.discount_value > self.subtotal:
            raise ValueError("Discount cannot be more than the subtotal")
        return self


class CheckoutOut(BaseModel):
    """Everything stored for a checkout, including the server-calculated numbers."""

    id: int
    customer_name: str
    customer_phone: Optional[str] = None

    technician_id: Optional[int] = None
    turn_id: Optional[int] = None
    appointment_id: Optional[int] = None

    payment_method: str
    service_name: str

    subtotal: float
    discount_type: str
    discount_value: float
    discount_amount: float
    discount_paid_by: str

    tip_amount: float
    net_service: float
    technician_share: float
    salon_share: float
    salon_actual_revenue: float
    technician_total: float
    customer_pays: float

    note: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----------------------------
# Income reports
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
# Inventory
# ----------------------------
class InventoryItemBase(BaseModel):
    item_name: str
    category: str
    supplier: Optional[str] = None
    quantity: int = Field(ge=0)
    unit_price: Money
    purchase_date: Optional[date] = None
    low_stock_level: int = Field(default=3, ge=0)


class InventoryItemCreate(InventoryItemBase):
    pass


class InventoryItemUpdate(BaseModel):
    item_name: Optional[str] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    unit_price: Optional[Money] = None
    purchase_date: Optional[date] = None
    low_stock_level: Optional[int] = Field(default=None, ge=0)


class InventoryItemOut(InventoryItemBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)