import logging
import os
import secrets
import string
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .database import Base, SessionLocal, engine, get_db
from .email_utils import send_birthday_email, send_referral_discount_email
from .scheduler import scheduler
from .timeutils import SALON_TZ, now_local, today_local

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nail_system")

Base.metadata.create_all(bind=engine)

# ----------------------------
# Reward settings
# ----------------------------
REFERRAL_MILESTONES = {3: 10, 8: 15, 18: 20}  
REFERRED_DISCOUNT_PERCENT = 10                
REFERRAL_CODE_UNLOCK_VISITS = 5
LOYALTY_EVERY_N_VISITS = 10
LOYALTY_DISCOUNT_PERCENT = 10
REMINDER_WINDOW_DAYS = 5

DEFAULT_SERVICES = [
    "Acrylic Full Set",
    "Acrylic Fill",
    "Gel Full Set",
    "Gel Fill",
    "Dip Powder",
    "Pink and White",
    "Ombre Nails",
    "Builder Gel",
    "Classic Manicure",
    "Gel Manicure",
    "Deluxe Manicure",
    "Classic Pedicure",
    "Deluxe Pedicure",
    "Spa Pedicure",
    "Jelly Pedicure",
    "Polish Change - Hands",
    "Polish Change - Feet",
    "Nail Repair",
    "Nail Removal",
    "French Tip",
    "Nail Art",
    "Chrome / Cat Eye",
    "Paraffin Treatment",
    "Waxing - Eyebrows",
    "Waxing - Lip",
    "Waxing - Chin",
]


# ----------------------------
# Startup migrations (SQLite)
# ----------------------------
NEW_COLUMNS = {
    "visits": {
        "discount_type": "VARCHAR",
        "discount_value": "FLOAT DEFAULT 0",
        "discount_label": "VARCHAR",
    },
    "customers": {
        "referred_discount_pending": "BOOLEAN NOT NULL DEFAULT 0",
    },
}

UNIQUE_INDEXES = [
    # (index name, table, columns)
    ("uq_visit_customer_date", "visits", "customer_id, visit_date"),
    ("uq_referral_used_by", "referral_usages", "used_by_customer_id"),
]


def ensure_columns() -> None:
    """Adds columns that older databases don't have yet."""
    with engine.begin() as conn:
        for table, columns in NEW_COLUMNS.items():
            existing = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def ensure_unique_indexes() -> None:
    """Adds the database-level rules: one visit per day, one referral code per customer."""
    for name, table, columns in UNIQUE_INDEXES:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table} ({columns})")
                )
        except Exception as exc:
            logger.warning("Could not create unique index %s (duplicate rows already exist?): %s", name, exc)


ensure_columns()
ensure_unique_indexes()


def seed_services(db: Session) -> None:
    existing_names = {item.name.strip().lower() for item in db.query(models.Service).all()}

    created = False
    for service_name in DEFAULT_SERVICES:
        if service_name.strip().lower() not in existing_names:
            db.add(models.Service(name=service_name.strip(), is_active=True))
            created = True

    if created:
        db.commit()


# ----------------------------
# General helpers
# ----------------------------
def generate_referral_code(length: int = 5) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_unique_referral_code(db: Session) -> str:
    while True:
        code = generate_referral_code()
        exists = db.query(models.Customer).filter(models.Customer.referral_code == code).first()
        if not exists:
            return code


def _normalize_phone(phone: str) -> str:
    try:
        return schemas.validate_phone(phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _get_customer_or_404(db: Session, phone_number: str) -> models.Customer:
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == _normalize_phone(phone_number))
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return customer


def _phone_in_use(db: Session, phone_digits: str) -> bool:
    return (
        db.query(models.Customer).filter(models.Customer.phone_number == phone_digits).first()
        is not None
    )


def _get_visit_today(db: Session, customer_id: int):
    return (
        db.query(models.Visit)
        .filter(
            models.Visit.customer_id == customer_id,
            models.Visit.visit_date == today_local(),
        )
        .first()
    )


def _get_selected_services_or_404(db: Session, service_ids: list[int]) -> list[models.Service]:
    unique_ids = list(dict.fromkeys(service_ids))
    services = (
        db.query(models.Service)
        .filter(models.Service.id.in_(unique_ids), models.Service.is_active.is_(True))
        .order_by(models.Service.name.asc())
        .all()
    )

    if len(services) != len(unique_ids):
        raise HTTPException(status_code=404, detail="One or more selected services were not found.")

    service_by_id = {service.id: service for service in services}
    return [service_by_id[service_id] for service_id in unique_ids]


def _commit_or_400(db: Session, conflict_detail: str) -> None:
    """Commits; if a database uniqueness rule is hit (e.g. a double click), returns a clean 400."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=conflict_detail)


def _already_checked_in_error() -> HTTPException:
    return HTTPException(status_code=400, detail="This phone number has already checked in today.")


# ----------------------------
# Birthday logic
# ----------------------------
def _birthday_in_year(dob: date, year: int) -> date:
    """The birthday in a given year. Feb 29 falls back to Feb 28 in non-leap years."""
    try:
        return date(year, dob.month, dob.day)
    except ValueError:
        return date(year, 2, 28)


def days_until_next_birthday(dob: date) -> int:
    today = today_local()
    next_birthday = _birthday_in_year(dob, today.year)
    if next_birthday < today:
        next_birthday = _birthday_in_year(dob, today.year + 1)
    return (next_birthday - today).days


def is_exact_birthday(dob: date) -> bool:
    today = today_local()
    return _birthday_in_year(dob, today.year) == today


def _month_key() -> str:
    return today_local().strftime("%Y-%m")


def _birthday_discount_eligible(customer) -> bool:
    if not customer.date_of_birth:
        return False
    already_used = customer.birthday_discount_used_month == _month_key()
    return is_exact_birthday(customer.date_of_birth) and not already_used


def _apply_birthday_discount(customer, db: Session) -> bool:
    if not _birthday_discount_eligible(customer):
        return False
    customer.birthday_discount_used_month = _month_key()
    db.add(customer)
    return True


# ----------------------------
# Referral / loyalty logic
# ----------------------------
def _consume_pending(customer, field: str, db: Session) -> bool:
    """If `field` (a pending-reward flag) is set, clears it and returns True."""
    if not getattr(customer, field):
        return False
    setattr(customer, field, False)
    db.add(customer)
    return True


def _award_referral_milestone(owner: models.Customer) -> None:
    """Gives the code owner a reward at 3 / 8 / 18 referrals.

    If an earlier reward is still unused, it is upgraded to the bigger one
    instead of the new milestone being skipped.
    """
    percent = REFERRAL_MILESTONES.get(owner.referral_count)
    if percent is None:
        return
    if not owner.referral_discount_pending or percent > (owner.referral_discount_percent or 0):
        owner.referral_discount_pending = True
        owner.referral_discount_percent = percent


# ----------------------------
# Discount bookkeeping
# ----------------------------
def _discount_from_applied(discounts_applied: list[dict]) -> dict:
    fixed_total = sum(float(d.get("amount") or 0) for d in discounts_applied if "amount" in d)
    percent_total = sum(float(d.get("percent") or 0) for d in discounts_applied if "percent" in d)
    label = " + ".join(d["description"] for d in discounts_applied if d.get("description")) or None

    if fixed_total > 0:
        return {
            "discount_type": "fixed",
            "discount_value": fixed_total,
            "discount_label": label or f"${fixed_total:g} discount",
        }
    if percent_total > 0:
        return {
            "discount_type": "percent",
            "discount_value": percent_total,
            "discount_label": label or f"{percent_total:g}% discount",
        }
    return {"discount_type": None, "discount_value": 0, "discount_label": None}


def _today_queue_discount(visit, customer) -> dict:
    if visit.discount_type:
        return {
            "discount_type": visit.discount_type,
            "discount_value": float(visit.discount_value or 0),
            "discount_label": visit.discount_label,
        }

    if (
        customer.date_of_birth
        and is_exact_birthday(customer.date_of_birth)
        and customer.birthday_discount_used_month == _month_key()
    ):
        amount = customer.birthday_discount_amount or 10
        return {
            "discount_type": "fixed",
            "discount_value": amount,
            "discount_label": f"${amount} birthday discount",
        }

    return {"discount_type": None, "discount_value": 0, "discount_label": None}


# ----------------------------
# Birthday reminders
# ----------------------------
def _reminder_recently_sent(customer, today: date) -> bool:
    """True if a reminder already went out for this birthday (once per birthday, not daily)."""
    sent = customer.birthday_reminder_sent_date
    return bool(sent) and 0 <= (today - sent).days <= REMINDER_WINDOW_DAYS


def process_birthday_reminders(db: Session) -> dict:
    today = today_local()
    sent_count = 0
    skipped_count = 0

    for customer in db.query(models.Customer).all():
        if not customer.email:
            skipped_count += 1
            continue

        days_left = days_until_next_birthday(customer.date_of_birth)
        if not 0 <= days_left <= REMINDER_WINDOW_DAYS:
            skipped_count += 1
            continue

        if _reminder_recently_sent(customer, today):
            skipped_count += 1
            continue

        try:
            send_birthday_email(
                to_email=customer.email,
                customer_name=customer.full_name,
                discount_amount=customer.birthday_discount_amount,
            )
            customer.birthday_reminder_sent = True
            customer.birthday_reminder_sent_date = today
            sent_count += 1
        except Exception:
            logger.exception("Failed to send birthday email to %s", customer.email)
            skipped_count += 1

    db.commit()
    return {"sent": sent_count, "skipped": skipped_count}


def run_scheduled_birthday_reminders() -> None:
    db = SessionLocal()
    try:
        result = process_birthday_reminders(db)
        logger.info("Scheduled birthday reminders finished: %s", result)
    finally:
        db.close()


# ----------------------------
# App setup
# ----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_services(db)
    finally:
        db.close()

    if not scheduler.running:
        scheduler.add_job(
            run_scheduled_birthday_reminders,
            "cron",
            hour=9,
            minute=0,
            timezone=SALON_TZ,
            id="daily_birthday_reminders",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Birthday reminder scheduler started (daily at 9:00 salon time).")

    yield

    if scheduler.running:
        scheduler.shutdown()
        logger.info("Birthday reminder scheduler stopped.")


app = FastAPI(title="Nail System API", version="0.3.0", lifespan=lifespan)

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Nail System API is running"}


# ----------------------------
# Services
# ----------------------------
@app.get("/services", response_model=list[schemas.ServiceResponse])
def get_services(db: Session = Depends(get_db)):
    return (
        db.query(models.Service)
        .filter(models.Service.is_active.is_(True))
        .order_by(models.Service.name.asc())
        .all()
    )


# ----------------------------
# Customers
# ----------------------------
@app.post("/customers/new", response_model=schemas.CustomerResponse, status_code=201)
def create_new_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    # Name, phone, email and birth date are already cleaned by the schema.
    if _phone_in_use(db, customer.phone_number):
        raise HTTPException(status_code=400, detail="Phone number already exists.")

    new_customer = models.Customer(
        full_name=customer.full_name,
        phone_number=customer.phone_number,
        email=customer.email,
        date_of_birth=customer.date_of_birth,
        referral_code=None,
        referral_count=0,
        referral_discount_percent=10,
        referral_discount_pending=False,
        referred_discount_pending=False,
        birthday_discount_amount=10,
        birthday_discount_used_month=None,
        visit_count_cycle=0,
        visit_discount_pending=False,
        used_referral_code=None,
        used_referral_from_customer_id=None,
    )

    db.add(new_customer)
    _commit_or_400(db, "Phone number already exists.")
    db.refresh(new_customer)
    return new_customer


@app.get("/customers", response_model=list[schemas.CustomerResponse])
def get_all_customers(db: Session = Depends(get_db)):
    return db.query(models.Customer).all()


@app.get("/customers/by-phone/{phone_number}", response_model=schemas.CustomerResponse)
def get_customer_by_phone(phone_number: str, db: Session = Depends(get_db)):
    return _get_customer_or_404(db, phone_number)


@app.patch("/customers/{phone_number}/update-phone", response_model=schemas.CustomerResponse)
def update_phone_number(
    phone_number: str,
    payload: schemas.UpdatePhoneRequest,
    db: Session = Depends(get_db),
):
    customer = _get_customer_or_404(db, phone_number)
    new_phone = payload.new_phone_number

    if customer.phone_number == new_phone:
        raise HTTPException(
            status_code=400,
            detail="New phone number is the same as the current one.",
        )

    if _phone_in_use(db, new_phone):
        raise HTTPException(
            status_code=400,
            detail="That phone number is already in use by another account.",
        )

    customer.phone_number = new_phone
    _commit_or_400(db, "That phone number is already in use by another account.")
    db.refresh(customer)
    return customer


@app.patch("/customers/{phone_number}/profile", response_model=schemas.CustomerResponse)
def update_customer_profile(
    phone_number: str,
    payload: schemas.UpdateCustomerProfileRequest,
    db: Session = Depends(get_db),
):
    customer = _get_customer_or_404(db, phone_number)
    new_phone = payload.phone_number

    if new_phone != customer.phone_number and _phone_in_use(db, new_phone):
        raise HTTPException(
            status_code=400,
            detail="That phone number is already in use by another account.",
        )

    customer.full_name = payload.full_name
    customer.phone_number = new_phone
    customer.email = payload.email

    _commit_or_400(db, "That phone number is already in use by another account.")
    db.refresh(customer)
    return customer


@app.get("/customers/{phone_number}/visits")
def get_customer_visits(phone_number: str, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(db, phone_number)

    visits = (
        db.query(models.Visit)
        .options(joinedload(models.Visit.visit_services).joinedload(models.VisitService.service))
        .filter(models.Visit.customer_id == customer.id)
        .order_by(models.Visit.checked_in_at.desc())
        .all()
    )

    return {
        "full_name": customer.full_name,
        "phone_number": customer.phone_number,
        "visit_count": len(visits),
        "visit_count_cycle": customer.visit_count_cycle,
        "visits": [
            {
                "id": visit.id,
                "visit_date": visit.visit_date,
                "checked_in_at": visit.checked_in_at,
                "services": [item.service.name for item in visit.visit_services],
            }
            for visit in visits
        ],
        "referral_code": customer.referral_code,
        "referral_count": customer.referral_count,
        "referral_discount_pending": customer.referral_discount_pending,
        "used_referral_code": customer.used_referral_code,
        "used_referral_from_customer_id": customer.used_referral_from_customer_id,
    }


# ----------------------------
# Check-in
# ----------------------------
@app.get("/customers/check-in-status/{phone_number}")
def get_check_in_status(phone_number: str, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(db, phone_number)

    return {
        "phone_number": customer.phone_number,
        "full_name": customer.full_name,
        "already_checked_in_today": _get_visit_today(db, customer.id) is not None,
    }


@app.get("/today-checkins", response_model=schemas.TodayCheckInResponse)
def get_today_checkins(db: Session = Depends(get_db)):
    visits = (
        db.query(models.Visit)
        .options(
            joinedload(models.Visit.customer),
            joinedload(models.Visit.visit_services).joinedload(models.VisitService.service),
        )
        .filter(models.Visit.visit_date == today_local())
        .order_by(models.Visit.checked_in_at.asc())
        .all()
    )

    checkins = [
        {
            "position": index,
            "full_name": visit.customer.full_name,
            "phone_number": visit.customer.phone_number,
            "checked_in_at": visit.checked_in_at,
            "services": [item.service.name for item in visit.visit_services],
            **_today_queue_discount(visit, visit.customer),
        }
        for index, visit in enumerate(visits, start=1)
    ]

    return {"checkins": checkins}


@app.post("/customers/check-in/{phone_number}", response_model=schemas.CheckInResponse)
def check_in_customer(
    phone_number: str,
    payload: schemas.CheckInCreate,
    db: Session = Depends(get_db),
):
    customer = _get_customer_or_404(db, phone_number)

    if _get_visit_today(db, customer.id):
        raise _already_checked_in_error()

    selected_services = _get_selected_services_or_404(db, payload.selected_service_ids)

    new_visit = models.Visit(
        customer_id=customer.id,
        visit_date=today_local(),
        checked_in_at=now_local(),
    )
    db.add(new_visit)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise _already_checked_in_error()

    for service in selected_services:
        db.add(models.VisitService(visit_id=new_visit.id, service_id=service.id))

    customer.visit_count_cycle += 1

    if customer.visit_count_cycle >= REFERRAL_CODE_UNLOCK_VISITS and not customer.referral_code:
        customer.referral_code = get_unique_referral_code(db)

    # Rewards that apply to THIS visit
    discounts_applied = []

    if _apply_birthday_discount(customer, db):
        discounts_applied.append(
            {
                "type": "birthday",
                "description": f"🎂 ${customer.birthday_discount_amount} birthday discount",
                "amount": customer.birthday_discount_amount,
            }
        )

    if _consume_pending(customer, "referral_discount_pending", db):
        discounts_applied.append(
            {
                "type": "referral",
                "description": f"🎉 {customer.referral_discount_percent}% referral discount",
                "percent": customer.referral_discount_percent,
            }
        )

    if _consume_pending(customer, "referred_discount_pending", db):
        discounts_applied.append(
            {
                "type": "referral_used",
                "description": f"🎁 {REFERRED_DISCOUNT_PERCENT}% referral code discount",
                "percent": REFERRED_DISCOUNT_PERCENT,
            }
        )

    if _consume_pending(customer, "visit_discount_pending", db):
        discounts_applied.append(
            {
                "type": "loyalty",
                "description": f"⭐ {LOYALTY_DISCOUNT_PERCENT}% loyalty discount (every {LOYALTY_EVERY_N_VISITS}th visit reward)",
                "percent": LOYALTY_DISCOUNT_PERCENT,
            }
        )

    visit_discount = _discount_from_applied(discounts_applied)
    new_visit.discount_type = visit_discount["discount_type"]
    new_visit.discount_value = visit_discount["discount_value"]
    new_visit.discount_label = visit_discount["discount_label"]

    # Rewards EARNED by this visit (applied on the next one)
    if customer.visit_count_cycle % LOYALTY_EVERY_N_VISITS == 0:
        customer.visit_discount_pending = True
        logger.info(
            "%s earned a %s%% loyalty discount (visit #%s)",
            customer.full_name,
            LOYALTY_DISCOUNT_PERCENT,
            customer.visit_count_cycle,
        )

    _commit_or_400(db, "This phone number has already checked in today.")
    db.refresh(customer)

    total_visits = (
        db.query(models.Visit).filter(models.Visit.customer_id == customer.id).count()
    )

    return {
        "message": "Customer checked in successfully.",
        "phone_number": customer.phone_number,
        "full_name": customer.full_name,
        "visit_count": total_visits,
        "visit_count_cycle": customer.visit_count_cycle,
        "referral_code": customer.referral_code,
        "referral_discount_percent": customer.referral_discount_percent,
        "birthday_discount_available": _birthday_discount_eligible(customer),
        "birthday_discount_amount": customer.birthday_discount_amount,
        "discounts_applied": discounts_applied,
        "selected_services": [service.name for service in selected_services],
    }


# ----------------------------
# Referrals
# ----------------------------
def _get_code_owner_or_404(db: Session, code: str) -> models.Customer:
    owner = db.query(models.Customer).filter(models.Customer.referral_code == code).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Referral code not found.")
    return owner


@app.post("/referrals/validate")
def validate_referral_code(payload: schemas.ApplyReferralCodeRequest, db: Session = Depends(get_db)):
    """Checks a code WITHOUT using it. The customer may not exist yet (new-customer flow)."""
    code = payload.referral_code.strip().upper()
    owner = _get_code_owner_or_404(db, code)

    if owner.phone_number == payload.phone_number:
        raise HTTPException(status_code=400, detail="You cannot use your own referral code.")

    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == payload.phone_number)
        .first()
    )
    if customer and customer.used_referral_code:
        raise HTTPException(status_code=400, detail="You have already used a referral code.")

    return {"valid": True}


@app.post("/referrals/apply", response_model=schemas.ApplyReferralCodeResponse)
def apply_referral_code(payload: schemas.ApplyReferralCodeRequest, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(db, payload.phone_number)

    if customer.used_referral_code:
        raise HTTPException(status_code=400, detail="You have already used a referral code.")

    entered_code = payload.referral_code.strip().upper()
    code_owner = _get_code_owner_or_404(db, entered_code)

    if code_owner.id == customer.id:
        raise HTTPException(status_code=400, detail="You cannot use your own referral code.")

    customer.used_referral_code = entered_code
    customer.used_referral_from_customer_id = code_owner.id
    customer.referred_discount_pending = True  # consumed by their check-in

    code_owner.referral_count = (code_owner.referral_count or 0) + 1
    _award_referral_milestone(code_owner)

    db.add(
        models.ReferralUsage(
            code=entered_code,
            code_owner_customer_id=code_owner.id,
            used_by_customer_id=customer.id,
            used_on=today_local(),
        )
    )

    _commit_or_400(db, "You have already used a referral code.")
    db.refresh(customer)
    db.refresh(code_owner)

    if customer.email:
        try:
            send_referral_discount_email(
                to_email=customer.email,
                customer_name=customer.full_name,
                referrer_name=code_owner.full_name,
                discount_percent=REFERRED_DISCOUNT_PERCENT,
            )
        except Exception:
            logger.exception("Failed to send referral discount email to %s", customer.email)

    return {
        "message": f"Referral code accepted successfully. You received {REFERRED_DISCOUNT_PERCENT}% off today.",
        "phone_number": customer.phone_number,
        "full_name": customer.full_name,
        "used_referral_code": entered_code,
        "referral_from_customer_name": code_owner.full_name,
        "discount_percent": REFERRED_DISCOUNT_PERCENT,
    }


# ----------------------------
# Birthday reminders
# ----------------------------
@app.get("/birthday-reminders", response_model=list[schemas.BirthdayReminderResponse])
def get_upcoming_birthday_reminders(db: Session = Depends(get_db)):
    reminders = []
    for customer in db.query(models.Customer).all():
        days_left = days_until_next_birthday(customer.date_of_birth)
        if 0 <= days_left <= REMINDER_WINDOW_DAYS:
            reminders.append(
                {
                    "full_name": customer.full_name,
                    "phone_number": customer.phone_number,
                    "email": customer.email,
                    "date_of_birth": customer.date_of_birth,
                    "days_until_birthday": days_left,
                    "birthday_discount_amount": customer.birthday_discount_amount,
                }
            )
    return reminders


@app.post("/birthday-reminders/send")
def send_birthday_reminders(db: Session = Depends(get_db)):
    result = process_birthday_reminders(db)
    return {"message": "Birthday reminder process completed.", **result}