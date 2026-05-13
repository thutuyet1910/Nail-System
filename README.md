# Nail Salon Fullstack Project

This project has two parts:

- `frontend/` — the salon user interface built with HTML, CSS, and JavaScript
- `backend/` — the FastAPI server for technicians, turns, appointments, checkout, and inventory

## How to run the full project

### 1. Open the project folder
Open the whole `nail_salon_fullstack` folder in VS Code so the `frontend` and `backend` folders stay together.

---

### 2. Run the backend
Open a terminal in the `backend` folder and run:

```bash
python -m venv venv
venv\Scripts\Activate.ps1
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
