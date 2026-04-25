# Nail Salon Backend

Basic FastAPI backend for:
- technician turns
- customer appointments

## Files
- `main.py`
- `database.py`
- `models.py`
- `schemas.py`
- `crud.py`
- `requirements.txt`

## Setup

### 1. Open terminal in this folder
### 2. Create virtual environment
```bash
python -m venv venv
```

### 3. Activate virtual environment

#### Windows PowerShell
```bash
venv\Scripts\Activate.ps1
```

#### Windows CMD
```bash
venv\Scripts\activate
```

### 4. Install packages
```bash
pip install -r requirements.txt
```

### 5. Run server
```bash
uvicorn main:app --reload
```

Server:
- API root: `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Main endpoints

### Technicians
- `POST /technicians`
- `GET /technicians`
- `GET /technicians/{id}`

### Appointments
- `POST /appointments`
- `GET /appointments`
- `GET /appointments/{id}`
- `PUT /appointments/{id}`
- `DELETE /appointments/{id}`

### Turns
- `POST /turns`
- `GET /turns`
- `GET /turns/today`
- `POST /turns/assign-next`
- `PUT /turns/{id}/status`

## Example technician
```json
{
  "full_name": "Jenny",
  "skills": "Gel, Pedicure, Manicure",
  "phone": "555-123-4567"
}
```

## Example appointment
```json
{
  "customer_name": "Anna Tran",
  "customer_phone": "555-987-6543",
  "service_name": "Gel Manicure",
  "appointment_time": "2026-04-07T10:00:00",
  "note": "Prefers pink color",
  "technician_id": 1
}
```

## Example turn
```json
{
  "customer_name": "Linda Pham",
  "service_name": "Pedicure",
  "technician_id": 1
}
```
