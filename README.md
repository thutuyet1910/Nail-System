# Nail Salon Customer Check-In System

Customer-facing check-in system for a nail salon. Customers enter their phone number, create or update their profile, select services, receive eligible rewards, and join the same-day live check-in queue.

This system is designed to work with the owner dashboard in `Nail-System-complete`.

## What This System Does

- Phone-first customer lookup
- New customer registration
- Returning customer check-in
- Customer profile update
- Service selection before check-in
- Birthday discount support
- Referral code and referral discount support
- Loyalty visit reward support
- Live same-day queue with latest customers shown last
- Promotion area with disclaimer text
- Discount data passed to the owner dashboard checkout flow

## Related System

Run this check-in backend together with the owner dashboard backend for the full salon flow:

- Check-in backend: `http://127.0.0.1:8000`
- Owner backend: `http://127.0.0.1:8001`

The owner dashboard reads this system's `/today-checkins` endpoint to auto-assign customers.

## Project Structure

```text
Nail-System-main/
  backend/
    app/
      __init__.py
      main.py
      database.py
      models.py
      schemas.py
      scheduler.py
      email_utils.py
      test_main.py
    requirements.txt
  frontend/
    index.html
    script.js
    style.css
  README.md
```

## Run The Backend

Open a terminal in:

```text
cd backend
```

Then run:

```powershell
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Backend URLs:

- API root: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

## Run The Frontend

Open:

```text
frontend\index.html
```

You can open it directly in a browser or use VS Code Live Server.

## Run Tests

Open a terminal in the check-in backend folder and run:

```powershell
venv\Scripts\Activate.ps1
python -m pytest app\test_main.py -q
```

Current expected result:

```text
84 passed
```

## Main Check-In Flow

1. Customer enters phone number.
2. System checks if the customer already exists.
3. New customers create a profile.
4. Returning customers can confirm or update profile information.
5. Customer selects one or more services.
6. System applies eligible birthday, referral, or loyalty discounts.
7. Customer joins today's live queue.
8. Owner dashboard can auto-assign the customer to a matching technician.

## Main API Endpoints

- `GET /`
- `GET /services`
- `POST /customers/new`
- `GET /customers`
- `GET /customers/{phone_number}`
- `GET /customers/check-in-status/{phone_number}`
- `POST /customers/check-in/{phone_number}`
- `GET /today-checkins`
- `POST /referrals/apply`
- `PATCH /customers/{phone_number}/update-phone`
- `PATCH /customers/{phone_number}/profile`
- `GET /customers/{phone_number}/visits`
- `GET /birthday-reminders`
- `POST /birthday-reminders/send`

## Notes

- Date inputs use `MM-DD-YYYY` in the frontend.
- Backend API dates are stored in ISO format.
- The backend stores local SQLite data in `backend\nail_system.db`.
- Test data uses `backend\test_checkin.db`.
