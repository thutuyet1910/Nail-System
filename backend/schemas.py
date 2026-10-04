from datetime import date, datetime, time
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from phone_normalization import normalize_us_phone


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
        try:
            normalize_us_phone(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a valid US number: {exc}") from exc
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
    service_ids: Optional[list[int]] = None


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
    service_ids: Optional[list[int]] = None


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
class BookingServiceOut(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: int
    price: Optional[float] = None
    buffer_before_minutes: int = 0
    buffer_after_minutes: int = 0
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AppointmentServiceOut(BaseModel):
    booking_service_id: Optional[int] = None
    service_name_snapshot: str
    duration_minutes_snapshot: int
    price_snapshot: Optional[float] = None
    buffer_before_minutes_snapshot: int
    buffer_after_minutes_snapshot: int
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


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
    service_ids: Optional[list[int]] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=200)
    external_customer_id: Optional[int] = None


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(AppointmentBase):
    pass


class AppointmentOut(AppointmentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    starts_at_utc: Optional[datetime] = None
    ends_at_utc: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    legacy_duration_fallback: bool = False
    cancelled_at_utc: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    cancellation_source: Optional[str] = None
    appointment_services: list[AppointmentServiceOut] = []
    customer_phone_e164: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AppointmentReschedule(BaseModel):
    appointment_time: datetime
    service_ids: Optional[list[int]] = None
    technician_id: Optional[int] = None
    preferred_technician_id: Optional[int] = None
    people_count: Optional[int] = Field(default=None, ge=1)
    customer_name: Optional[str] = None
    customer_phone: OptionalCustomerPhone = None
    special_requests: Optional[str] = None
    allergies: Optional[str] = None
    note: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=200)


class AppointmentCancel(BaseModel):
    reason: Optional[str] = None
    source: str = "owner"
    idempotency_key: Optional[str] = Field(default=None, max_length=200)


class AvailabilitySlot(BaseModel):
    start: datetime
    end: datetime
    timezone: str
    eligible_technician_ids: list[int]
    selected_technician_id: Optional[int] = None
    total_duration_minutes: int


class SalonSettingsOut(BaseModel):
    id: int
    salon_name: str
    timezone: str
    business_phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    slot_interval_minutes: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class BusinessHourOut(BaseModel):
    day_of_week: int
    is_closed: bool
    opens_at: Optional[time] = None
    closes_at: Optional[time] = None

    model_config = ConfigDict(from_attributes=True)


BLOCK_TYPES = ("break", "date_off", "manual", "other")


class TechnicianBlockedTimeCreate(BaseModel):
    start: datetime
    end: datetime
    block_type: str = "other"
    reason: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def validate_block(self):
        if self.block_type not in BLOCK_TYPES:
            raise ValueError(f"Block type must be one of: {', '.join(BLOCK_TYPES)}")
        if self.end <= self.start:
            raise ValueError("Blocked time end must be after start")
        return self


class TechnicianBlockedTimeOut(BaseModel):
    id: int
    technician_id: int
    starts_at_utc: datetime
    ends_at_utc: datetime
    block_type: str
    reason: Optional[str] = None
    note: Optional[str] = None
    created_at_utc: datetime

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
    appointment_id: Optional[int] = None
    checkin_customer_id: Optional[int] = None
    checkin_visit_id: Optional[int] = None


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
    appointment_id: Optional[int] = None
    checkin_customer_id: Optional[int] = None
    checkin_visit_id: Optional[int] = None


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
    customer_phone_e164: Optional[str] = None
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
    appointment_id: Optional[int] = None
    checkin_customer_id: Optional[int] = None
    checkin_visit_id: Optional[int] = None

    created_at: datetime
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CheckinMatchRequest(BaseModel):
    customer_phone: CustomerPhone
    customer_name: Optional[str] = None
    checked_in_at: datetime
    customer_id: Optional[int] = None
    visit_id: Optional[int] = None


class CheckinMatchOut(BaseModel):
    outcome: str
    appointment: Optional[AppointmentOut] = None
    candidate_ids: list[int] = []
    reason: Optional[str] = None


class IntegratedCheckinOut(BaseModel):
    visit_id: int
    customer_id: int
    position: int
    full_name: str
    phone_number: str
    phone_e164: str
    checked_in_at: datetime
    services: list[str] = []
    discount_type: Optional[str] = None
    discount_value: float = 0
    discount_label: Optional[str] = None
    appointment_match: CheckinMatchOut


class IntegratedCheckinsResponse(BaseModel):
    checkins: list[IntegratedCheckinOut]


class OwnerLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class OwnerSessionOut(BaseModel):
    authenticated: bool
    expires_at: Optional[datetime] = None


class NotificationOut(BaseModel):
    id: int
    notification_type: str
    severity: str
    title: str
    message: str
    source_type: str
    source_id: Optional[str] = None
    event_key: Optional[str] = None
    appointment_id: Optional[int] = None
    external_customer_id: Optional[int] = None
    read_at: Optional[datetime] = None
    created_at: datetime
    metadata_json: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationCountOut(BaseModel):
    unread_count: int


class CallbackRequest(BaseModel):
    caller_phone: CustomerPhone
    category: str
    urgency: str = "normal"
    summary: str = Field(min_length=1, max_length=2000)
    operation_key: str = Field(min_length=1, max_length=200)
    external_customer_id: Optional[int] = None
    appointment_id: Optional[int] = None


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
