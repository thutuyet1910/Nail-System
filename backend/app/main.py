from datetime import date, datetime
import random
import string

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo
from .scheduler import scheduler

from . import models, schemas
from .database import Base, engine, get_db, SessionLocal
from .email_utils import send_birthday_email

Base.metadata.create_all(bind=engine)


def generate_referral_code(length: int = 5) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def get_unique_referral_code(db: Session) -> str:
    while True:
        code = generate_referral_code()
        existing = db.query(models.Customer).filter(models.Customer.referral_code == code).first()
        if not existing:
            return code


def days_until_next_birthday(dob: date) -> int:
    today = date.today()
    current_year_birthday = date(today.year, dob.month, dob.day)

    if current_year_birthday < today:
        next_birthday = date(today.year + 1, dob.month, dob.day)
    else:
        next_birthday = current_year_birthday

    return (next_birthday - today).days


def is_birthday_window(dob: date) -> bool:
    days_left = days_until_next_birthday(dob)
    return 0 <= days_left <= 5


def is_exact_birthday(dob: date) -> bool:
    today = date.today()
    return dob.month == today.month and dob.day == today.day


def should_reset_birthday_reminder(customer, today: date) -> bool:
    if not customer.birthday_reminder_sent_date:
        return False
    return customer.birthday_reminder_sent_date.year < today.year


def run_scheduled_birthday_reminders():
    db = SessionLocal()
    try:
        customers = db.query(models.Customer).all()
        today = date.today()

        sent_count = 0
        skipped_count = 0

        for customer in customers:
            print("Checking customer:", customer.full_name, customer.email, customer.date_of_birth)

            if should_reset_birthday_reminder(customer, today):
                customer.birthday_reminder_sent = False
                customer.birthday_reminder_sent_date = None

            if not customer.email:
                print("Skipped: no email")
                skipped_count += 1
                continue

            days_left = days_until_next_birthday(customer.date_of_birth)
            print("Days until birthday:", days_left)

            if 0 <= days_left <= 5:
                if customer.birthday_reminder_sent and customer.birthday_reminder_sent_date == today:
                    print("Skipped: already sent today")
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
                    print("Email sent to:", customer.email)
                except Exception as e:
                    print(f"Failed to send email to {customer.email}: {e}")
                    skipped_count += 1
            else:
                print("Skipped: birthday not within 5 days")

        db.commit()

        print({
            "message": "Scheduled birthday reminder process completed.",
            "sent": sent_count,
            "skipped": skipped_count,
        })
    finally:
        db.close()

# change the time and minutes back when done developing
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.add_job(
            run_scheduled_birthday_reminders,
            #
            #"cron",
            #hour=9,
            #minute=0,

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


app = FastAPI(title="Nail System API", version="0.1.0", lifespan=lifespan)

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


@app.post("/customers/new", response_model=schemas.CustomerResponse, status_code=201)
def create_new_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    existing_customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == customer.phone_number.strip())
        .first()
    )

    if existing_customer:
        raise HTTPException(status_code=400, detail="Phone number already exists.")

    new_customer = models.Customer(
        full_name=customer.full_name.strip(),
        phone_number=customer.phone_number.strip(),
        email=(customer.email or "").strip() or None,
        date_of_birth=customer.date_of_birth,
        referral_code=None,
        referral_discount_percent=10,
        birthday_discount_amount=10,
        visit_count_cycle=0,
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
        .filter(models.Customer.phone_number == phone_number.strip())
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    return customer


@app.get("/customers/check-in-status/{phone_number}")
def get_check_in_status(phone_number: str, db: Session = Depends(get_db)):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == phone_number.strip())
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    today = date.today()

    existing_visit_today = (
        db.query(models.Visit)
        .filter(
            models.Visit.customer_id == customer.id,
            models.Visit.visit_date == today
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
        db.query(models.Visit, models.Customer)
        .join(models.Customer, models.Visit.customer_id == models.Customer.id)
        .filter(models.Visit.visit_date == today)
        .order_by(models.Visit.checked_in_at.asc())
        .all()
    )

    result = []
    for index, (visit, customer) in enumerate(visits, start=1):
        result.append({
            "position": index,
            "full_name": customer.full_name,
            "phone_number": customer.phone_number,
            "checked_in_at": visit.checked_in_at,
        })

    return {"checkins": result}

@app.post("/customers/check-in/{phone_number}", response_model=schemas.CheckInResponse)
def check_in_customer(phone_number: str, db: Session = Depends(get_db)):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == phone_number.strip())
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    today = date.today()

    existing_visit_today = (
        db.query(models.Visit)
        .filter(
            models.Visit.customer_id == customer.id,
            models.Visit.visit_date == today
        )
        .first()
    )

    if existing_visit_today:
        raise HTTPException(
            status_code=400,
            detail="This phone number has already checked in today."
        )

    new_visit = models.Visit(
    customer_id=customer.id,
    visit_date=today,
    checked_in_at=datetime.now()
    )
    db.add(new_visit)

    customer.visit_count_cycle += 1

    # Change back to >= 5 later for the real rule
    if customer.visit_count_cycle >= 5 and not customer.referral_code:
        customer.referral_code = get_unique_referral_code(db)

    db.commit()
    db.refresh(customer)

    total_visits = (
        db.query(models.Visit)
        .filter(models.Visit.customer_id == customer.id)
        .count()
    )

    birthday_discount_available = is_exact_birthday(customer.date_of_birth)

    return {
        "message": "Customer checked in successfully.",
        "phone_number": customer.phone_number,
        "full_name": customer.full_name,
        "visit_count": total_visits,
        "visit_count_cycle": customer.visit_count_cycle,
        "referral_code": customer.referral_code,
        "referral_discount_percent": customer.referral_discount_percent,
        "birthday_discount_available": birthday_discount_available,
        "birthday_discount_amount": customer.birthday_discount_amount,
    }


@app.post("/referrals/apply", response_model=schemas.ApplyReferralCodeResponse)
def apply_referral_code(payload: schemas.ApplyReferralCodeRequest, db: Session = Depends(get_db)):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == payload.phone_number.strip())
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    entered_code = payload.referral_code.strip().upper()

    code_owner = (
        db.query(models.Customer)
        .filter(models.Customer.referral_code == entered_code)
        .first()
    )

    if not code_owner:
        raise HTTPException(
            status_code=404,
            detail="Referral code is invalid or already used."
        )

    usage = models.ReferralUsage(
        code=entered_code,
        code_owner_customer_id=code_owner.id,
        used_by_customer_id=customer.id,
        used_on=date.today(),
    )
    db.add(usage)

    customer.used_referral_code = entered_code
    customer.used_referral_from_customer_id = code_owner.id

    code_owner.referral_code = None
    code_owner.visit_count_cycle = 0

    db.commit()
    db.refresh(customer)
    db.refresh(code_owner)

    return {
        "message": "Referral code has been activated. 10% discount on all services.",
        "phone_number": customer.phone_number,
        "full_name": customer.full_name,
        "used_referral_code": entered_code,
        "referral_from_customer_name": code_owner.full_name,
        "discount_percent": 10,
    }


@app.get("/customers/{phone_number}/visits")
def get_customer_visits(phone_number: str, db: Session = Depends(get_db)):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == phone_number.strip())
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    visits = (
        db.query(models.Visit)
        .filter(models.Visit.customer_id == customer.id)
        .all()
    )

    return {
        "full_name": customer.full_name,
        "phone_number": customer.phone_number,
        "visit_count": len(visits),
        "visit_count_cycle": customer.visit_count_cycle,
        "visits": [{"id": v.id, "visit_date": v.visit_date} for v in visits],
        "referral_code": customer.referral_code,
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
            reminder_list.append({
                "full_name": customer.full_name,
                "phone_number": customer.phone_number,
                "email": customer.email,
                "date_of_birth": customer.date_of_birth,
                "days_until_birthday": days_left,
                "birthday_discount_amount": customer.birthday_discount_amount,
            })

    return reminder_list


@app.post("/birthday-reminders/send")
def send_birthday_reminders(db: Session = Depends(get_db)):
    customers = db.query(models.Customer).all()
    today = date.today()

    sent_count = 0
    skipped_count = 0

    for customer in customers:
        print("Checking customer:", customer.full_name, customer.email, customer.date_of_birth)

        if should_reset_birthday_reminder(customer, today):
            customer.birthday_reminder_sent = False
            customer.birthday_reminder_sent_date = None

        if not customer.email:
            print("Skipped: no email")
            skipped_count += 1
            continue

        days_left = days_until_next_birthday(customer.date_of_birth)
        print("Days until birthday:", days_left)

        if 0 <= days_left <= 5:
            if customer.birthday_reminder_sent and customer.birthday_reminder_sent_date == today:
                print("Skipped: already sent today")
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
                print("Email sent to:", customer.email)
            except Exception as e:
                print(f"Failed to send email to {customer.email}: {e}")
                skipped_count += 1
        else:
            print("Skipped: birthday not within 5 days")

    db.commit()

    return {
        "message": "Birthday reminder process completed.",
        "sent": sent_count,
        "skipped": skipped_count,
    }