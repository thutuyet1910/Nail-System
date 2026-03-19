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

# Birthday helpers

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

# Birthday discount helpers (old-customer rules)

def _birthday_discount_eligible(customer) -> bool:
    if not customer.date_of_birth:
        return False

    current_month_key = date.today().strftime("%Y-%m")
    already_used = (customer.birthday_discount_used_month == current_month_key)
    return is_exact_birthday(customer.date_of_birth) and not already_used

def _apply_birthday_discount(customer, db: Session) -> bool:
    if not _birthday_discount_eligible(customer):
        return False
    customer.birthday_discount_used_month = date.today().strftime("%Y-%m")
    db.add(customer)
    return True 

# Referral discount helpers (old-customer rules)

def _referral_discount_eligible(customer) -> bool:
    return bool(customer.referral_discount_pending)

 
def _apply_referral_discount(customer, db: Session) -> bool:
    if not _referral_discount_eligible(customer):
        return False
    customer.referral_discount_pending = False
    db.add(customer)
    return True

# Visit milestone discount helpers

def _visit_discount_eligible(customer) -> bool:
    return bool(customer.visit_discount_pending)

def _apply_visit_discount(customer, db: Session) -> bool:
    if not _visit_discount_eligible(customer):
        return False
    customer.visit_discount_pending = False

    db.add(customer)
    return True

# Scheduled birthday email job

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

# Lifespan (scheduler)

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

# NEW CUSTOMER — registration

@app.post("/customers/new", response_model=schemas.CustomerResponse, status_code=201)
def create_new_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    existing_customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == customer.phone_number)
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
        referral_count=0,
        referral_discount_percent=10,
        referral_discount_pending=False,               
        birthday_discount_amount=10,
        birthday_discount_used_month=None,
        visit_count_cycle=0,
        used_referral_code=None,
        used_referral_from_customer_id=None,
    )

    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer

# CUSTOMER LIST & LOOKUP

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

# CHECK-IN STATUS

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

# TODAY'S CHECK-IN

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

# Check-in (applies discounts)

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

    # Unlock referral code after 5 visits in the cycle
    if customer.visit_count_cycle >= 5 and not customer.referral_code:
        customer.referral_code = get_unique_referral_code(db)

    discounts_applied = []

    # OLD CUSTOMER DISCOUNT LOGIC
    if _apply_birthday_discount(customer, db):
        discounts_applied.append({
            "type": "birthday",
            "description": f"🎂 ${customer.birthday_discount_amount} birthday discount",
            "amount": customer.birthday_discount_amount,
        })

    if _apply_referral_discount(customer, db):
        discounts_applied.append({
            "type": "referral",
            "description": f"🎉 {customer.referral_discount_percent}% referral discount",
            "percent": customer.referral_discount_percent,
        })

    if _apply_visit_discount(customer, db):
        discounts_applied.append({
            "type": "loyalty",
            "description": "⭐ 10% loyalty discount (every 10th visit reward)",
            "percent": 10,
        })

    if customer.visit_count_cycle % 10 == 0:
        customer.visit_discount_pending = True
        print(f"[NOTIFICATION] {customer.full_name} earned a 10% loyalty discount (visit #{customer.visit_count_cycle})!")


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
    }

# REFERRAL — apply a code (new customer enters someone's code)

@app.post("/referrals/apply", response_model=schemas.ApplyReferralCodeResponse)
def apply_referral_code(payload: schemas.ApplyReferralCodeRequest, db: Session = Depends(get_db)):
    customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == payload.phone_number)
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

    if code_owner.referral_count == 3 and not code_owner.referral_discount_pending:
        code_owner.referral_discount_pending = True
        # In production, trigger a real push/SMS/email notification here
        print(
            f"[NOTIFICATION] {code_owner.full_name} earned a 10% referral discount "
            f"(referred {code_owner.referral_count} people)!"
        )


    db.commit()
    db.refresh(customer)
    db.refresh(code_owner)

    return {
        "message": "Referral code accepted successfully.",
        "phone_number": customer.phone_number,
        "full_name": customer.full_name,
        "used_referral_code": entered_code,
        "referral_from_customer_name": code_owner.full_name,
        "discount_percent": 10,
    }

# OLD CUSTOMER — update phone number

@app.patch("/customers/{phone_number}/update-phone", response_model=schemas.CustomerResponse)
def update_phone_number(
    phone_number: str,
    payload: schemas.UpdatePhoneRequest,
    db: Session = Depends(get_db),
):
 customer = (
        db.query(models.Customer)
        .filter(models.Customer.phone_number == phone_number.strip())
        .first()
    )
 if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
 
 new_phone = payload.new_phone_number.strip()
 
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

# VISITS

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
        "referral_count": customer.referral_count,
        "referral_discount_pending": customer.referral_discount_pending,
        "used_referral_code": customer.used_referral_code,
        "used_referral_from_customer_id": customer.used_referral_from_customer_id,
    }


# BIRTHDAY REMINDERS

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