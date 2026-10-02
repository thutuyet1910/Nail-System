# Nail Salon Owner Dashboard

A full-stack nail salon management dashboard for handling salon operations after customers check in.

The Owner Dashboard works together with a separate **Customer Check-In System**. Customers check in through the customer-facing application, and the Owner Dashboard receives the live queue so salon staff can assign technicians, manage appointments, process checkout, track inventory, and review technician and salon income.

---

## System Workflow

The main salon workflow is:

Customer Check-In
→ Live Customer Queue
→ Technician Assignment
→ Service
→ Checkout
→ Income & History

The Owner Dashboard is responsible for the salon-management side of this workflow.

---

# What This System Does

The Owner Dashboard provides tools for:

- Viewing the live customer check-in queue
- Automatically assigning customers to technicians
- Matching technicians by service specialty
- Managing technician availability and schedules
- Creating and managing appointments
- Supporting preferred technicians
- Viewing technician schedules on a calendar
- Processing customer checkout
- Applying discounts received from the Check-In System
- Calculating technician pay and salon revenue
- Tracking completed checkout history
- Managing salon inventory
- Reviewing technician income
- Reviewing overall salon income

---

# Required Applications

The complete system uses two separate backend applications.

### Customer Check-In Backend

```text
http://127.0.0.1:8000
```

This system handles the customer-facing check-in process, including customer information, selected services, discounts, rewards, and the live waiting queue.

### Owner Dashboard Backend

```text
http://127.0.0.1:8001
```

This system handles technician assignment, appointments, turns, checkout, inventory, and reporting.

The Owner Dashboard reads the live customer queue from the Check-In backend. Therefore, both systems should be running when testing the complete customer workflow.

---

# Project Structure

```text
Nail-System-complete/
│
├── backend/
│   ├── main.py
│   ├── crud.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── Test-main.py
│   ├── requirements.txt
│   └── nail_system.db
│
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
└── README.md
```

## Backend Files

### `main.py`

Contains the FastAPI application and API routes.

Responsibilities include:

- Starting the Owner Dashboard API
- Configuring CORS
- Creating/upgrading required database structures
- Technician API routes
- Technician deactivate/reactivate routes
- Appointment API routes
- Turn and assignment routes
- Checkout routes
- Inventory routes
- Income/reporting routes
- Request validation and business-rule error handling

### `crud.py`

Contains the main salon business logic and database operations.

Responsibilities include:

- Creating and updating technicians
- Deactivating technicians while preserving history
- Creating and updating appointments
- Creating salon turns
- Auto-assigning technicians
- Preferred technician assignment
- Reassigning technicians
- Managing turn status
- Processing checkout
- Calculating checkout values
- Preventing duplicate checkout
- Managing inventory
- Calculating technician income
- Calculating salon income

### `database.py`

Configures the SQLAlchemy database connection and database sessions.

The local development database is:

```text
backend/nail_system.db
```

### `models.py`

Defines the SQLAlchemy database tables.

Main models include:

- Technician
- Appointment
- Turn
- Checkout
- InventoryItem

### `schemas.py`

Defines Pydantic request and response models.

It validates data before it reaches the database, including:

- Technician information
- Phone numbers
- Technician status
- Appointment information
- People count
- Turn assignment requests
- Checkout amounts
- Discounts
- Inventory quantities
- Inventory prices

### `Test-main.py`

Contains automated backend tests for the Owner Dashboard.

Tests cover the main salon workflow and important business rules.

---

# Main Dashboard Sections

## 1. Customer List

The Customer List connects to the separate Check-In System and displays customers currently waiting for service.

### Live Customer Queue

Shows customers who have completed the customer check-in process and are waiting for a technician.

Customer information may include:

- Customer name
- Phone number
- Selected services
- Preferred technician
- Discount/reward information
- Check-in information

### Auto Assign

The **Auto Assign** function finds an appropriate technician for a waiting customer.

The assignment process considers:

1. The technician must still be an active salon employee.
2. The technician must currently have an active working status.
3. The technician must be available today.
4. The technician's specialty must match the customer's selected service.
5. The technician cannot already have another active customer.
6. Among eligible technicians, the system can use today's turn history to distribute assignments.

Once assigned, the customer moves from the waiting queue into the salon service/checkout workflow.

### Salon History - Checked-Out Today

Shows customers who completed checkout during the current day.

This allows the owner to quickly review today's completed salon services.

### Check-Out History

Loads completed checkout records so previous transactions can be reviewed.

---

# 2. Technician Directory

The Technician Directory manages salon employees.

Each technician can contain information such as:

- Full name
- Employee ID
- Phone
- Skills
- Specialties
- Start date
- Status
- Availability
- Weekly work schedule
- Notes
- Profile photo

### Technician Status

Technician status represents the technician's current working state.

For example:

```text
Active
Off
Unavailable
```

### Availability

Availability indicates whether the technician can accept customers today.

For example:

```text
Available today
Off today
```

### Active / Inactive Technician

The system also distinguishes between a technician's daily status and whether the technician still works for the salon.

```text
is_active = true
```

means the technician is still an active salon employee.

```text
is_active = false
```

means the technician has been deactivated.

Deactivation is used to preserve historical salon records when a technician leaves.

Historical appointments, turns, checkouts, and income information can therefore remain available.

### Delete Technician

If a technician has no salon history, the technician can be permanently deleted.

If the technician already has appointment, turn, or checkout history, the system preserves that history by deactivating the technician instead of deleting historical records.

### Reactivate Technician

A previously deactivated technician can be reactivated if they return to work at the salon.

### Specialties

Technician specialties are used by the assignment system to determine which services the technician can perform.

Examples include:

```text
Manicure / Pedicure
Acrylic
Dip Powder
Gel
Builder / Hard Gel
Nail Art
Waxing
Facial
```

Specialties are also displayed in a compact format on technician cards to keep the directory easier to read.

---

# 3. Appointments

The Appointment section allows salon staff to create and manage future appointments.

An appointment can contain:

- Customer name
- Customer phone
- Service
- Appointment date
- Appointment time
- Number of people
- Customer type
- Preferred technician
- Assigned technician
- Notes
- Special requests
- Allergies
- Appointment status

### Appointment Status

Appointments can maintain their current status instead of always appearing as scheduled.

Examples include:

```text
scheduled
checked_in
done
cancelled
```

This also allows appointment lists to be filtered by status.

### Preferred Technician

Customers can request a preferred technician.

The appointment stores the preferred technician separately from the technician who is eventually assigned to perform the service.

---

# 4. Technician Calendar

The calendar provides a visual schedule of technician appointments.

It is designed to help the salon owner quickly see:

- Technician schedules
- Appointment times
- Preferred technician appointments
- Assigned appointments
- In-service appointments

Appointments appear under the appropriate technician's calendar column.

Technician colors are used consistently so appointments and technicians can be recognized quickly.

The interface provides ten technician colors before colors repeat.

---

# 5. Customer Assignment and Turns

A **Turn** represents a customer's salon service workflow after assignment.

A turn stores information such as:

- Turn number
- Customer
- Service
- Assigned technician
- Preferred technician
- Discount information
- Assignment source
- Status
- Created time
- Assigned time
- Service start time
- Completion time

Turn numbers restart each day.

### Turn Status Flow

The normal workflow is:

```text
waiting
   ↓
assigned
   ↓
in_service
   ↓
done
```

A turn may also become:

```text
cancelled
```

Completed and cancelled turns are final.

The system prevents completed turns from being reassigned and prevents completed workflow states from accidentally moving backward.

---

# 6. Auto Assignment

Auto Assignment attempts to select a technician automatically instead of requiring the manager to choose one manually.

The system first filters technicians based on:

```text
Active employee
      ↓
Working/active status
      ↓
Available today
      ↓
Correct specialty
      ↓
No other active customer
```

Eligible technicians can then be compared using their turn activity for the current day.

Cancelled turns are not treated as completed service turns.

The goal is to distribute customers while still respecting technician availability and service specialty.

---

# 7. Manual / Preferred Assignment

Salon staff can also assign customers manually.

Preferred Technician assignment checks that:

- The technician exists
- The technician is active
- The technician is available today
- The technician can perform the selected service
- The technician is not already servicing another active customer

A customer can also be reassigned when necessary.

Completed or cancelled turns cannot be reassigned.

---

# 8. Checkout

The Checkout section shows customers who have been assigned and are ready to complete payment.

Checkout uses information from the customer's turn, including:

- Customer
- Technician
- Service
- Discount information

### Checkout Inputs

The checkout request provides the information needed to calculate payment, such as:

```text
Service subtotal
Discount type
Discount value
Tip
Payment method
```

### Server-Side Checkout Calculation

Important financial values are calculated by the backend rather than trusted from the frontend.

The backend calculates values such as:

- Discount amount
- Net service amount
- Technician share
- Salon share
- Technician total
- Salon actual revenue
- Customer total

This keeps income calculations consistent even if the frontend changes.

### Technician Pay

The system supports the salon's technician percentage calculation.

The current workflow uses a:

```text
60% technician share
```

along with tip and salon revenue calculations.

### Discount Handling

Discount information can be carried from the customer Check-In System into the Owner Dashboard.

Checkout validates discount values so invalid amounts cannot produce negative service totals.

### Preventing Duplicate Checkout

A turn can only be checked out once.

If a second checkout request is submitted for the same turn, the backend rejects it instead of creating duplicate revenue.

### Completing Checkout

Successful checkout also completes the associated customer turn.

The checkout and turn completion are handled together so the system does not save a payment while accidentally leaving the customer active.

---

# 9. Inventory

The Inventory section manages salon products and supplies.

Inventory items can contain:

- Item name
- Category
- Supplier
- Quantity
- Unit price
- Purchase date
- Low-stock level

### Low Stock

The system compares the current quantity with the configured low-stock level.

This helps identify supplies that may need to be reordered.

### Inventory Value and Expenses

Inventory data can also be used to calculate:

- Total inventory value
- Weekly expense
- Monthly expense
- Yearly expense
- Number of low-stock items

---

# 10. Technician Income

The Technician Income section shows earnings grouped by technician.

Reports can include:

- Service subtotal
- Technician percentage/share
- Tips
- Technician total
- Number of turns
- Individual checkout details

The owner can review technician performance and income for selected dates and reporting ranges.

---

# 11. Nail Salon Income

The Nail Salon Income section summarizes salon financial activity.

Reports can include:

- Income before discounts
- Total discounts
- Income after discounts
- Technician share
- Technician tips
- Total paid to technicians
- Salon income after technician pay
- Number of completed turns

Reports support date-based views including:

```text
Day
Week
Year
```

The dashboard also provides reporting views for reviewing salon income over different periods.

---

# 12. Checkout History

Completed checkout records are retained for salon reporting and review.

Checkout history can include:

- Customer
- Technician
- Service
- Payment method
- Service subtotal
- Discount
- Net service amount
- Technician share
- Tip
- Technician total
- Salon revenue
- Customer payment
- Checkout date/time

This history is also used by income reporting.

---

# Running the Owner Dashboard

## 1. Open the Project

Open a terminal and navigate to the backend:

```powershell
cd backend
```

## 2. Create the Virtual Environment

For the first setup:

```powershell
py -m venv venv
```

Activate it:

```powershell
venv\Scripts\Activate
```

## 3. Install Dependencies

```powershell
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Start the Owner Backend

```powershell
python -m uvicorn main:app --reload --port 8001
```

The backend will run at:

```text
http://127.0.0.1:8001
```

FastAPI documentation:

```text
http://127.0.0.1:8001/docs
```

---

# Running the Customer Check-In System

For the complete salon workflow, also start the separate Customer Check-In backend on:

```text
http://127.0.0.1:8000
```

The Owner Dashboard uses this backend to retrieve the live customer waiting queue.

---

# Running the Frontend

From the backend folder, the frontend can be opened with:

```powershell
start ../frontend\index.html
```

For development, VS Code Live Server can also be used.

---

# Running Tests

Open a terminal in the Owner Dashboard backend folder.

Run:

```powershell
python -m pytest Test-main.py -q
```

Expected test result for the current tested version:

```text
101 passed
```

The test database is separate from the production/development salon database.

```text
Development database:
backend/nail_system.db

Test database:
backend/test_owner.db
```

---

# Database

The Owner Dashboard currently uses SQLite.

Main database:

```text
backend/nail_system.db
```

The database stores:

- Technicians
- Appointments
- Turns
- Checkouts
- Inventory

Database indexes are used on frequently filtered fields such as turn dates, turn statuses, technician assignments, and checkout dates.

---

# Date Format

User-facing date inputs use:

```text
MM-DD-YYYY
```

Example:

```text
10-01-2026
```

Year inputs are limited to four digits.

---

# Important Business Rules

The system follows several rules to protect salon data:

- A technician must match the customer's requested service.
- An unavailable technician cannot receive a new customer.
- A technician cannot handle multiple active customers at the same time.
- Inactive technicians are excluded from normal assignment.
- Technician history is preserved when an employee leaves.
- Completed or cancelled turns cannot be reassigned.
- Completed turn statuses cannot move backward.
- A turn cannot be checked out twice.
- Checkout calculations are performed by the backend.
- Invalid discount amounts are rejected.
- Historical appointments connected to checkout records are protected.

---

# Development Notes

The Owner Dashboard and Customer Check-In System are separate applications that communicate during the customer workflow.

For complete local testing, run:

```text
Customer Check-In Backend : port 8000
Owner Dashboard Backend   : port 8001
Owner Frontend            : browser / Live Server
```

The project is designed so customer check-in remains separate from salon management while still allowing the Owner Dashboard to receive live customer information.

---

# Current Development Status

The system currently supports the main salon workflow:

```text
Customer Check-In
        ↓
Live Queue
        ↓
Technician Assignment
        ↓
Appointment / Service Management
        ↓
Checkout
        ↓
Checkout History
        ↓
Technician & Salon Income Reporting
```

Additional production security, including authentication and authorization, should be added before exposing the Owner Dashboard API publicly.