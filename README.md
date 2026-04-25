# Nail Salon Fullstack Project

This zip includes both:

- `frontend/` → HTML, CSS, JS salon calendar UI
- `backend/` → FastAPI backend for technicians, turns, and appointments

## Frontend
Open:
- `frontend/index.html`

You can use VS Code Live Server, or open `index.html` directly in your browser.

## Backend
Open terminal in the `backend` folder and run:

```bash
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend URLs:
- API root: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

## Suggested structure
Keep both folders together in one VS Code project so you can work on frontend and backend in the same place.
