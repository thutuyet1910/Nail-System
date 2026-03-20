import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


def _send_email(to_email: str, subject: str, body: str) -> None:
    if not to_email:
        raise ValueError("Recipient email is missing.")

    if not SMTP_SERVER or not EMAIL_SENDER or not EMAIL_PASSWORD:
        raise ValueError("Email settings are missing in the .env file.")

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)


def send_birthday_email(to_email: str, customer_name: str, discount_amount: int) -> None:
    subject = "Happy Birthday! Enjoy $10 off at Nail Salon"
    body = f"""
Hi {customer_name},

Happy Birthday from Nail Salon! 🎉

You have ${discount_amount} off your services.
We look forward to seeing you soon.

Best,
Nail Salon
""".strip()

    _send_email(to_email, subject, body)


def send_referral_discount_email(
    to_email: str,
    customer_name: str,
    referrer_name: str,
    discount_percent: int,
) -> None:
    subject = "Your Referral Discount Has Been Applied"
    body = f"""
Hi {customer_name},

Good news — your referral code was accepted successfully.

You received {discount_percent}% off your visit today.
Referral from: {referrer_name}

Thank you for visiting Nail Salon. We look forward to seeing you again.

Best,
Nail Salon
""".strip()

    _send_email(to_email, subject, body)