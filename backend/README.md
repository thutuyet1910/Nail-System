# Owner Dashboard Backend

FastAPI + SQLite backend for the nail salon Owner Dashboard. The full description of the system is in the
repository [README](../README.md); exact start-up commands are in [DEVELOPMENT.md](../DEVELOPMENT.md).

## Responsibilities

- Staff and owner sessions, access control, CSRF, login throttling
- Technicians, availability (with a server-side daily rollover), schedules and eligibility
- Owner service catalog, weekly booking hours, salon settings
- Appointments, availability and the transactional booking service
- Queue, turns, assignment, checkout, inventory and income reports
- Owner notifications
- Check-In integration (live queue, service catalog for Check-In)
- AI phone receptionist (Twilio Media Streams + OpenAI Realtime)

## Run

```powershell
cd <repository>\backend
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```

The backend reads its settings from the process environment (names in `../.env.example`). API root:
`http://127.0.0.1:8001/`, interactive docs: `http://127.0.0.1:8001/docs`.

## Test

```powershell
venv\Scripts\python.exe -m pytest Test-main.py -q
```

## Main endpoint groups

| Group | Who may call it |
|---|---|
| `/auth/*` | public by design (login, staff session, logout, session status) |
| `/`, `/salon`, `/business-hours`, `/services`, `/availability` | public reads |
| `/appointments*`, `/turns/*` (assign, start, complete, reassign, status, today), `/checkins/*`, `/checkouts` (POST, GET today), `/technicians` (GET) | staff session or owner session |
| `/technicians*` (write), `/booking-services*`, `/business-hours` (PUT), `/settings/*`, `/inventory*`, `/income/*`, `/notifications*`, `/callbacks` | owner session only |
| `/internal/services` | Check-In, internal service token, read-only |
| `/voice/twilio/*` | Twilio (signature / stream token) |

Anything not listed is owner-only by default.

## Local data and tools

- Database files (`*.db`) are local only and git-ignored.
- `reset_owner_password.py` resets the owner password on this computer (emergency recovery).
