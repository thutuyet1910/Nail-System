# Nail Salon Owner Dashboard

Owner dashboard for managing the nail salon operation after customers check in. It works with the separate check-in system and focuses on technician scheduling, appointments, assignment, checkout, inventory, and income reporting.

## What This System Does

- Shows the live customer check-in queue from the check-in app
- Auto-assigns waiting customers to available technicians by service specialty
- Shows assigned and in-service customers in the Checkout view
- Moves checked-out customers into salon checkout history
- Manages technicians, specialties, date off, temporary unavailable status, and weekly schedule
- Books appointments with preferred technician support
- Shows a technician calendar with matching technician colors
- Manages inventory and purchase dates
- Calculates checkout totals, discounts, tips, 60 percent technician pay, and salon revenue
- Reviews Technician Income and Nail Salon Income by date, week, year, and custom ranges

## Required Running Apps

This dashboard expects two local backends:

- Owner dashboard backend: `http://127.0.0.1:8001`
- Customer check-in backend: `http://127.0.0.1:8000`

The owner frontend reads live check-ins from the check-in backend, so run the check-in system too when testing the full customer flow.

## Project Structure

```text
Nail-System-complete/
  backend/
    main.py
    crud.py
    database.py
    models.py
    schemas.py
    Test-main.py
    requirements.txt
  frontend/
    index.html
    app.js
    styles.css
  README.md
```

## Run The Owner Backend

Open a terminal in:

```text
C:\Users\Flying Phoenix PCs\source\repos\Nail-System-complete\Nail-System-complete\backend
```

Then run:

```powershell
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8001
```

Backend URLs:

- API root: `http://127.0.0.1:8001`
- Docs: `http://127.0.0.1:8001/docs`

## Run The Frontend

Open:

```text
frontend\index.html
```

You can open it directly in a browser or use VS Code Live Server.

## Run Tests

Open a terminal in the owner backend folder and run:

```powershell
venv\Scripts\Activate.ps1
python -m pytest Test-main.py -q
```

Current expected result:

```text
101 passed
```

## Main Owner Features

### Customer List

- Shows live waiting check-ins from the check-in system
- Auto Assign moves customers out of the waiting queue and into Checkout
- Salon History - Checked-Out Today shows completed checkout records
- Check-Out History button loads all completed checkout history

### Technician Directory

- Add, edit, delete technicians
- Track status, date off, temporary unavailable, specialties, and weekly schedule
- Specialty chips are collapsed into a button on cards for cleaner layout
- Specialty delete removes checked service groups

### Appointments And Calendar

- Create appointments with service, date/time, people count, and preferred technician
- Preferred technician appointments show under that technician's calendar column
- Booked, assigned, and in-service blocks use the same color as the technician
- Ten technician colors are available before colors repeat

### Checkout

- Shows assigned and in-service customers ready for checkout
- Applies and displays discount data carried from check-in
- Owner pays discounts
- Calculates gross service, discount, net service, tip, 60 percent technician share, and customer total
- Completing checkout marks the customer turn as done

### Income

- Technician Income groups Date Review and Range Review together by technician
- Nail Salon Income shows income before discount, discounts, after discount, tech pay, tips, and salon income
- Date, week, and year review modes are supported

## Notes

- Date inputs use `MM-DD-YYYY`.
- Year inputs are limited to 4 digits.
- The owner backend stores local SQLite data in `backend\nail_system.db`.
- Test data uses `backend\test_owner.db`.
