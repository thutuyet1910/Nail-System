from contextlib import asynccontextmanager
from datetime import date, datetime
import random
import re
import string
from zoneinfo import ZoneInfo

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .database import Base, SessionLocal, engine, get_db
from .email_utils import send_birthday_email, send_referral_discount_email
from .scheduler import scheduler

Base.metadata.create_all(bind=engine)


def ensure_visit_discount_columns() -> None:
    with engine.begin() as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(visits)")).fetchall()
        }
        if "discount_type" not in existing_columns:
            conn.execute(text("ALTER TABLE visits ADD COLUMN discount_type VARCHAR"))
        if "discount_value" not in existing_columns:
            conn.execute(text("ALTER TABLE visits ADD COLUMN discount_value FLOAT DEFAULT 0"))
        if "discount_label" not in existing_columns:
            conn.execute(text("ALTER TABLE visits ADD COLUMN discount_label VARCHAR"))


ensure_visit_discount_columns()

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


def seed_services(db: Session) -> None:
    existing_names = {
        item.name.strip().lower()
        for item in db.query(models.Service).all()
    }

    created = False
    for service_name in DEFAULT_SERVICES:
        if service_name.strip().lower() not in existing_names:
            db.add(models.Service(name=service_name.strip(), is_active=True))
            created = True

    if created:
        db.commit()


def generate_referral_code(length: int = 5) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def get_unique_referral_code(db: Session) -> str:
    while True:
        code = generate_referral_code()
        existing = db.query(models.Customer).filter(models.Customer.referral_code == code).first()
        if not existing:
            return code


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) != 10:
        raise HTTPException(status_code=422, detail="Phone number must be exactly 10 digits.")
    return digits


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


def days_until_next_birthday(dob: date) -> int:
    today = date.today()
    current_year_birthday = date(today.year, dob.month, dob.day)

    if current_year_birthday < today:
        next_birthday = date(today.year + 1, dob.month, dob.day)
    else:
        next_birthday = current_year_birthday

    return (next_birthday - today).days


def is_exact_birthday(dob: date) -> bool:
    today = date.today()
    return dob.month == today.month and dob.day == today.day


def should_reset_birthday_reminder(customer, today: date) -> bool:
    if not customer.birthday_reminder_sent_date:
        return False
    return customer.birthday_reminder_sent_date.year < today.year


def _birthday_discount_eligible(customer) -> bool:
    if not customer.date_of_birth:
        return False

    current_month_key = date.today().strftime("%Y-%m")
    already_used = customer.birthday_discount_used_month == current_month_key
    return is_exact_birthday(customer.date_of_birth) and not already_used


def _apply_birthday_discount(customer, db: Session) -> bool:
    if not _birthday_discount_eligible(customer):
        return False
    customer.birthday_discount_used_month = date.today().strftime("%Y-%m")
    db.add(customer)
    return True


def _referral_discount_eligible(customer) -> bool:
    return bool(customer.referral_discount_pending)


def _apply_referral_discount(customer, db: Session) -> bool:
    if not _referral_discount_eligible(customer):
        return False
    customer.referral_discount_pending = False
    db.add(customer)
    return True


def _visit_discount_eligible(customer) -> bool:
    return bool(customer.visit_discount_pending)


def _apply_visit_discount(customer, db: Session) -> bool:
    if not _visit_discount_eligible(customer):
        return False
    customer.visit_discount_pending = False
    db.add(customer)
    return True


def _discount_from_applied(discounts_applied: list[dict]) -> dict:
    fixed_total = 0
    percent_total = 0
    fixed_labels = []
    percent_labels = []

    for discount in discounts_applied:
        description = discount.get("description") or ""
        if "amount" in discount:
            fixed_total += float(discount.get("amount") or 0)
            if description:
                fixed_labels.append(description)
        elif "percent" in discount:
            percent_total += float(discount.get("percent") or 0)
            if description:
                percent_labels.append(description)

    if fixed_total > 0:
        return {
            "discount_type": "fixed",
            "discount_value": fixed_total,
            "discount_label": " + ".join(fixed_labels) or f"${fixed_total:g} discount",
        }

    if percent_total > 0:
        return {
            "discount_type": "percent",
            "discount_value": percent_total,
            "discount_label": " + ".join(percent_labels) or f"{percent_total:g}% discount",
        }

    return {
        "discount_type": None,
        "discount_value": 0,
        "discount_label": None,
    }


def _today_queue_discount(visit, customer) -> dict:
    if visit.discount_type:
        return {
            "discount_type": visit.discount_type,
            "discount_value": float(visit.discount_value or 0),
            "discount_label": visit.discount_label,
        }

    current_month_key = date.today().strftime("%Y-%m")
    if (
        customer.date_of_birth
        and is_exact_birthday(customer.date_of_birth)
        and customer.birthday_discount_used_month == current_month_key
    ):
        amount = customer.birthday_discount_amount or 10
        return {
            "discount_type": "fixed",
            "discount_value": amount,
            "discount_label": f"${amount} birthday discount",
        }

    return {
        "discount_type": None,
        "discount_value": 0,
        "discount_label": None,
    }


def run_scheduled_birthday_reminders():
    db = SessionLocal()
    try:
        customers = db.query(models.Customer).all()
        today = date.today()

        sent_count = 0
        skipped_count = 0

        for customer in customers:
            if should_reset_birthday_reminder(customer, today):
                customer.birthday_reminder_sent = False
                customer.birthday_reminder_sent_date = None

            if not customer.email:
                skipped_count += 1
                continue

            days_left = days_until_next_birthday(customer.date_of_birth)

            if 0 <= days_left <= 5:
                if customer.birthday_reminder_sent and customer.birthday_reminder_sent_date == today:
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
                except Exception as exc:
                    print(f"Failed to send email to {customer.email}: {exc}")
                    skipped_count += 1
            else:
                skipped_count += 1

        db.commit()

        print(
            {
                "message": "Scheduled birthday reminder process completed.",
                "sent": sent_count,
                "skipped": skipped_count,
            }
        )
    finally:
        db.close()


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
            "interval",
            minutes=1,
            timezone=ZoneInfo("America/Phoenix"),
            id="daily_birthday_reminders",
            replace_existing=True,
        )
        scheduler.start()
        print("Birthday reminder scheduler started.")

    yield

    if scheduler.running:
        scheduler.shutdown()
        print("Birthday reminder scheduler stopped.")


app = FastAPI(title="Nail System API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Nail System API is running"}


@app.get("/services", response_model=list[schemas.ServiceResponse])
def get_services(db: Session = Depends(get_db)):
    seed_services(db)
    return (
        db.query(models.Service)
        .filter(models.Service.is_active.is_(True))
        .order_by(models.Service.name.asc())
        .all()
    )


@app.post("/customers/new", response_model=schemas.CustomerResponse, status_code=201)
def create_new_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    normalized_phone = _normalize_phone(customer.phone_number)

    existing_customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == normalized_phone)
        .first()
    )

    if existing_customer:
        raise HTTPException(status_code=400, detail="Phone number already exists.")

    new_customer = models.Customer(
        full_name=customer.full_name.strip(),
        phone_number=normalized_phone,
        email=(customer.email or "").strip() or None,
        date_of_birth=customer.date_of_birth,
        referral_code=None,
        referral_count=0,
        referral_discount_percent=10,
        referral_discount_pending=False,
        birthday_discount_amount=10,
        birthday_discount_used_month=None,
        visit_count_cycle=0,
        visit_discount_pending=False,
        used_referral_code=None,
        used_referral_from_customer_id=None,
    )

    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer


@app.get("/customers", response_model=list[schemas.CustomerResponse])
def get_all_customers(db: Session = Depends(get_db)):
    return db.query(models.Customer).all()


@app.get("/customers/by-phone/{phone_number}", response_model=schemas.CustomerResponse)
def get_customer_by_phone(phone_number: str, db: Session = Depends(get_db)):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == _normalize_phone(phone_number))
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    return customer


@app.get("/customers/check-in-status/{phone_number}")
def get_check_in_status(phone_number: str, db: Session = Depends(get_db)):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == _normalize_phone(phone_number))
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    today = date.today()

    existing_visit_today = (
        db.query(models.Visit)
        .filter(
            models.Visit.customer_id == customer.id,
            models.Visit.visit_date == today,
        )
        .first()
    )

    return {
        "phone_number": customer.phone_number,
        "full_name": customer.full_name,
        "already_checked_in_today": existing_visit_today is not None,
    }


@app.get("/today-checkins")
def get_today_checkins(db: Session = Depends(get_db)):
    today = date.today()

    visits = (
        db.query(models.Visit)
        .options(
            joinedload(models.Visit.customer),
            joinedload(models.Visit.visit_services).joinedload(models.VisitService.service),
        )
        .filter(models.Visit.visit_date == today)
        .order_by(models.Visit.checked_in_at.asc())
        .all()
    )

    result = []
    for index, visit in enumerate(visits, start=1):
        discount = _today_queue_discount(visit, visit.customer)
        result.append(
            {
                "position": index,
                "full_name": visit.customer.full_name,
                "phone_number": visit.customer.phone_number,
                "checked_in_at": visit.checked_in_at,
                "services": [item.service.name for item in visit.visit_services],
                **discount,
            }
        )

    return {"checkins": result}

@app.post("/customers/check-in/{phone_number}", response_model=schemas.CheckInResponse)
def check_in_customer(
    phone_number: str,
    payload: schemas.CheckInCreate = Body(...),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == _normalize_phone(phone_number))
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    today = date.today()

    existing_visit_today = (
        db.query(models.Visit)
        .filter(
            models.Visit.customer_id == customer.id,
            models.Visit.visit_date == today,
        )
        .first()
    )

    if existing_visit_today:
        raise HTTPException(
            status_code=400,
            detail="This phone number has already checked in today.",
        )

    selected_services = _get_selected_services_or_404(db, payload.selected_service_ids)

    new_visit = models.Visit(
        customer_id=customer.id,
        visit_date=today,
        checked_in_at=datetime.now(),
    )
    db.add(new_visit)
    db.flush()

    for service in selected_services:
        db.add(models.VisitService(visit_id=new_visit.id, service_id=service.id))

    customer.visit_count_cycle += 1

    if customer.visit_count_cycle >= 5 and not customer.referral_code:
        customer.referral_code = get_unique_referral_code(db)

    discounts_applied = []

    if _apply_birthday_discount(customer, db):
        discounts_applied.append(
            {
                "type": "birthday",
                "description": f"🎂 ${customer.birthday_discount_amount} birthday discount",
                "amount": customer.birthday_discount_amount,
            }
        )

    if _apply_referral_discount(customer, db):
        discounts_applied.append(
            {
                "type": "referral",
                "description": f"🎉 {customer.referral_discount_percent}% referral discount",
                "percent": customer.referral_discount_percent,
            }
        )

    if _apply_visit_discount(customer, db):
        discounts_applied.append(
            {
                "type": "loyalty",
                "description": "⭐ 10% loyalty discount (every 10th visit reward)",
                "percent": 10,
            }
        )

    visit_discount = _discount_from_applied(discounts_applied)
    new_visit.discount_type = visit_discount["discount_type"]
    new_visit.discount_value = visit_discount["discount_value"]
    new_visit.discount_label = visit_discount["discount_label"]

    if customer.visit_count_cycle % 10 == 0:
        customer.visit_discount_pending = True
        print(
            f"[NOTIFICATION] {customer.full_name} earned a 10% loyalty discount "
            f"(visit #{customer.visit_count_cycle})!"
        )

    db.commit()
    db.refresh(customer)

    total_visits = (
        db.query(models.Visit)
        .filter(models.Visit.customer_id == customer.id)
        .count()
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


@app.post("/referrals/apply", response_model=schemas.ApplyReferralCodeResponse)
def apply_referral_code(payload: schemas.ApplyReferralCodeRequest, db: Session = Depends(get_db)):
    normalized_phone = _normalize_phone(payload.phone_number)

    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == normalized_phone)
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    if customer.used_referral_code:
        raise HTTPException(
            status_code=400,
            detail="You have already used a referral code.",
        )

    entered_code = payload.referral_code.strip().upper()

    code_owner = (
        db.query(models.Customer)
        .filter(models.Customer.referral_code == entered_code)
        .first()
    )

    if not code_owner:
        raise HTTPException(status_code=404, detail="Referral code not found.")

    if code_owner.id == customer.id:
        raise HTTPException(status_code=400, detail="You cannot use your own referral code.")

    customer.used_referral_code = entered_code
    customer.used_referral_from_customer_id = code_owner.id
    code_owner.referral_count = (code_owner.referral_count or 0) + 1

    if not code_owner.referral_discount_pending:
        if code_owner.referral_count == 3:
            code_owner.referral_discount_pending = True
            code_owner.referral_discount_percent = 10
        elif code_owner.referral_count == 8:
            code_owner.referral_discount_pending = True
            code_owner.referral_discount_percent = 15
        elif code_owner.referral_count == 18:
            code_owner.referral_discount_pending = True
            code_owner.referral_discount_percent = 20

    db.add(
        models.ReferralUsage(
            code=entered_code,
            code_owner_customer_id=code_owner.id,
            used_by_customer_id=customer.id,
            used_on=date.today(),
        )
    )

    db.commit()
    db.refresh(customer)
    db.refresh(code_owner)

    if customer.email:
        try:
            send_referral_discount_email(
                to_email=customer.email,
                customer_name=customer.full_name,
                referrer_name=code_owner.full_name,
                discount_percent=10,
            )
        except Exception as exc:
            print(f"Failed to send referral discount email to {customer.email}: {exc}")

    return {
        "message": "Referral code accepted successfully. You received 10% off today.",
        "phone_number": customer.phone_number,
        "full_name": customer.full_name,
        "used_referral_code": entered_code,
        "referral_from_customer_name": code_owner.full_name,
        "discount_percent": 10,
    }


@app.patch("/customers/{phone_number}/update-phone", response_model=schemas.CustomerResponse)
def update_phone_number(
    phone_number: str,
    payload: schemas.UpdatePhoneRequest,
    db: Session = Depends(get_db),
):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == _normalize_phone(phone_number))
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    new_phone = _normalize_phone(payload.new_phone_number)

    if customer.phone_number == new_phone:
        raise HTTPException(
            status_code=400,
            detail="New phone number is the same as the current one.",
        )

    conflict = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == new_phone)
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=400,
            detail="That phone number is already in use by another account.",
        )

    customer.phone_number = new_phone
    db.commit()
    db.refresh(customer)
    return customer


@app.patch("/customers/{phone_number}/profile", response_model=schemas.CustomerResponse)
def update_customer_profile(
    phone_number: str,
    payload: schemas.UpdateCustomerProfileRequest,
    db: Session = Depends(get_db),
):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == _normalize_phone(phone_number))
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    new_phone = _normalize_phone(payload.phone_number)

    if new_phone != customer.phone_number:
        conflict = (
            db.query(models.Customer)
            .filter(models.Customer.phone_number == new_phone)
            .first()
        )
        if conflict:
            raise HTTPException(
                status_code=400,
                detail="That phone number is already in use by another account.",
            )

    customer.full_name = payload.full_name.strip()
    customer.phone_number = new_phone
    customer.email = (payload.email or "").strip() or None

    db.commit()
    db.refresh(customer)
    return customer


@app.get("/customers/{phone_number}/visits")
def get_customer_visits(phone_number: str, db: Session = Depends(get_db)):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == _normalize_phone(phone_number))
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

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


@app.get("/birthday-reminders", response_model=list[schemas.BirthdayReminderResponse])
def get_upcoming_birthday_reminders(db: Session = Depends(get_db)):
    customers = db.query(models.Customer).all()

    reminder_list = []
    for customer in customers:
        days_left = days_until_next_birthday(customer.date_of_birth)
        if 0 <= days_left <= 5:
            reminder_list.append(
                {
                    "full_name": customer.full_name,
                    "phone_number": customer.phone_number,
                    "email": customer.email,
                    "date_of_birth": customer.date_of_birth,
                    "days_until_birthday": days_left,
                    "birthday_discount_amount": customer.birthday_discount_amount,
                }
            )

    return reminder_list


@app.post("/birthday-reminders/send")
def send_birthday_reminders(db: Session = Depends(get_db)):
    customers = db.query(models.Customer).all()
    today = date.today()

    sent_count = 0
    skipped_count = 0

    for customer in customers:
        if should_reset_birthday_reminder(customer, today):
            customer.birthday_reminder_sent = False
            customer.birthday_reminder_sent_date = None

        if not customer.email:
            skipped_count += 1
            continue

        days_left = days_until_next_birthday(customer.date_of_birth)

        if 0 <= days_left <= 5:
            if customer.birthday_reminder_sent and customer.birthday_reminder_sent_date == today:
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
            except Exception as exc:
                print(f"Failed to send email to {customer.email}: {exc}")
                skipped_count += 1
        else:
            skipped_count += 1

    db.commit()

    return {
        "message": "Birthday reminder process completed.",
        "sent": sent_count,
        "skipped": skipped_count,
    }
