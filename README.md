# Nail System Starter

This is a starter project for the **Nail System** app focused on the **New Customer Check-In** flow.

## What this version does
- Lets a front desk user enter a new customer's:
  - phone number
  - full name
  - email (optional)
  - date of birth
  - referral code (optional)
- Saves the customer to a SQLite database
- Prevents duplicate phone numbers
- Shows a simple success/error message in the frontend

## Tech stack
- **Backend:** FastAPI + SQLAlchemy + SQLite
- **Frontend:** HTML + CSS + JavaScript

## Project structure

```
nail-system/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models.py
│   │   └── schemas.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── .gitignore
└── README.md
```

## How to run

### 1. Open the project in VS Code
Open the `nail-system` folder.

### 2. Backend setup
In a terminal:

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

**Windows PowerShell**
```bash
venv\Scripts\Activate.ps1
```

**Windows CMD**
```bash
venv\Scripts\activate
```

Install packages:

```bash
pip install -r requirements.txt
```

Run the backend:

```bash
uvicorn app.main:app --reload
```

Backend will run at:
- API: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

### 3. Frontend setup
Open `frontend/index.html` directly in the browser, or use the VS Code Live Server extension.

If your backend is running locally, the form will submit to the API.

## Next steps you can build later
- old customer lookup by phone number
- update phone number flow
- visit count tracking
- referral code generation after 5 visits
- birthday discount logic
- staff dashboard
- authentication for employees
