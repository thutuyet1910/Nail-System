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


def send_birthday_email(to_email: str, customer_name: str, discount_amount: int) -> None:
    if not to_email:
        raise ValueError("Recipient email is missing.")

    if not SMTP_SERVER or not EMAIL_SENDER or not EMAIL_PASSWORD:
        raise ValueError("Email settings are missing in the .env file.")

    subject = "Happy Birthday! Enjoy $10 off at Nail Salon"
    body = f"""
Hi {customer_name},

Happy Birthday from Nail Salon! 🎉

You have ${discount_amount} off your services.
We look forward to seeing you soon.

Best,
Nail Salon
""".strip()

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)