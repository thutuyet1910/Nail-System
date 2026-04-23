# Nail Check-In System

A modern nail salon **customer check-in system** designed to support both **new** and **returning** customer flows, service selection, referral rewards, birthday rewards, and live same-day queue tracking.

This project is part of a larger salon management system and is intended to connect later with:
- technician assignment
- appointments
- checkout
- discounts
- revenue reporting

---

## Overview

The Nail Check-In System helps a salon manage the front-desk check-in experience by allowing customers to:
- check in using their phone number
- create a new customer profile if they are new
- continue as a returning customer if already in the system
- select services before final confirmation
- receive birthday and referral rewards when eligible
- join the live check-in queue for the day

---

## Current Features

### Customer Identification
- Phone-first check-in flow
- Detects whether the customer is:
  - **new**
  - **returning**
- Prevents duplicate same-day check-ins

### New Customer Flow
- Collects:
  - phone number
  - full name
  - email (optional)
  - date of birth
  - referral code (optional)
- Lets customer select one or more services
- Shows a review screen before final confirmation
- Saves the new customer into the database
- Checks the customer into today’s queue

### Returning Customer Flow
- Looks up customer by phone number
- Displays customer profile
- Allows profile updates
- Lets returning customer select services
- Shows a review screen before final confirmation
- Checks the customer into today’s queue

### Rewards & Promotions
- Birthday reward support
- Referral code support
- Referral discount application
- Success modal and birthday modal for reward messages
- Referral code unlock flow

### Services
- Loads services from backend
- Searchable service list
- Multi-service selection
- Review selected services before final check-in

### Live Queue
- Displays today’s check-in order
- Shows queue position
- Shows check-in time
- Auto-refreshes the queue

---

## Tech Stack

### Backend
- FastAPI
- SQLAlchemy
- SQLite

### Frontend
- HTML
- CSS
- JavaScript

---

## Project Structure

```text
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

## How to Run
1. Open the project
2. Backend setup
    Open a terminal and run:
        cd backend
        python -m venv venv
    Activate the virtual environment:
        venv\Scripts\Activate.ps1
        venv\Scripts\activate
    Install dependencies:
        pip install -r requirements.txt
    Run the backend:
        uvicorn app.main:app --reload
Backend will run at:
      API: http://127.0.0.1:8000
      Docs: http://127.0.0.1:8000/docs
3. Frontend setup
    Open frontend/index.html directly in the browser, or use the VS Code Live Server extension.

## Future Improvements
    - Update the overall design of the check-in system
    - In the future, reminder logic should be updated to use phone numbers instead, since email is optional
    
   