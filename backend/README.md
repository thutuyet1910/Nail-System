# Owner Dashboard Backend

FastAPI backend for the nail salon owner dashboard.

## Backend Responsibilities

- Technicians and technician cards
- Appointments and preferred technician booking
- Calendar data
- Dispatch turns and auto assignment
- Checkout and checkout history
- Inventory
- Technician income reports
- Nail salon income reports

## Run Server

Open this folder in a terminal:

```text
C:\Users\Flying Phoenix PCs\source\repos\Nail-System-complete\Nail-System-complete\backend
```

Then run:

```powershell
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8001
```

Server:

- API root: `http://127.0.0.1:8001`
- Swagger docs: `http://127.0.0.1:8001/docs`

## Run Tests

```powershell
venv\Scripts\Activate.ps1
python -m pytest Test-main.py -q
```

Current expected result:

```text
101 passed
```

## Main Endpoints

### Technicians

- `POST /technicians`
- `GET /technicians`
- `GET /technicians/cards`
- `GET /technicians/{id}`
- `PUT /technicians/{id}`
- `DELETE /technicians/{id}`

### Appointments

- `POST /appointments`
- `GET /appointments`
- `GET /appointments/{id}`
- `PUT /appointments/{id}`
- `DELETE /appointments/{id}`

Preferred technician appointments are included when filtering by `technician_id` if no assigned technician is set.

### Turns And Dispatch

- `POST /turns`
- `GET /turns`
- `GET /turns/today`
- `POST /turns/assign-next`
- `POST /turns/assign-auto`
- `POST /turns/assign-preferred`
- `PUT /turns/{id}/reassign`
- `PUT /turns/{id}/start`
- `PUT /turns/{id}/complete`
- `PUT /turns/{id}/status`

### Checkout

- `POST /checkouts`
- `GET /checkouts`
- `GET /checkouts/{id}`
- `DELETE /checkouts/{id}`

Creating a checkout with a `turn_id` marks that turn as `done`.

### Inventory

- `POST /inventory`
- `GET /inventory`
- `GET /inventory/summary`
- `GET /inventory/{id}`
- `PUT /inventory/{id}`
- `DELETE /inventory/{id}`

### Income

- `GET /income/tech`
- `GET /income/salon`

## Local Data

- App database: `nail_system.db`
- Test database: `test_owner.db`
