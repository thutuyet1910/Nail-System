# Development Guide (Windows PowerShell)

Ports: Check-In backend `127.0.0.1:8000`, Check-In frontend `127.0.0.1:5500`, Owner backend `127.0.0.1:8001`.

## One-time setup

```powershell
cd <repo>\backend
py -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Environment

Check-In reads these from the process environment; an optional `backend\.env` fills in only the variables that are not already set. Load the shared token from your Windows **User** environment without printing it:

```powershell
$env:CHECKIN_INTERNAL_SERVICE_TOKEN = [Environment]::GetEnvironmentVariable("CHECKIN_INTERNAL_SERVICE_TOKEN", "User")
if (-not $env:CHECKIN_INTERNAL_SERVICE_TOKEN) { Write-Warning "token is not set in the User environment" }
$env:OWNER_API_BASE = "http://127.0.0.1:8001"
```

The Owner backend must use the **same** token value. To set it once (do not paste the value into chat, commits or logs):
`[Environment]::SetEnvironmentVariable("CHECKIN_INTERNAL_SERVICE_TOKEN", "<long random value>", "User")`, then open a new terminal.

Optional: `SALON_TIMEZONE`, `ALLOWED_ORIGINS`, `DATABASE_URL`, `OWNER_CATALOG_CACHE_SECONDS`, `OWNER_CATALOG_MAX_STALE_SECONDS` (see README).

## Startup order

1. **Owner backend** (port 8001), per the Owner repo's instructions.
2. **Check-In backend:**
   ```powershell
   cd <repo>\backend
   venv\Scripts\Activate.ps1
   # load the env vars above in this same terminal
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
3. **Check-In frontend** (static files; origin must be in `ALLOWED_ORIGINS`):
   ```powershell
   cd <repo>\frontend
   python -m http.server 5500 --bind 127.0.0.1
   ```
   Open `http://127.0.0.1:5500/`. (VS Code Live Server on 5500 also works.)

Quick check: `http://127.0.0.1:8000/services` should list the Owner's active services. A 503 means the Owner catalog is unreachable or misconfigured.

## Tests

```powershell
cd <repo>\backend
python -m pytest app -q                       # full suite
python -m pytest app\test_owner_catalog.py -q # Owner catalog / service ids
node --check ..\frontend\script.js
node --check ..\frontend\translations.js
```

Tests never touch the network or a real Owner (`app/conftest.py` fakes it) and use `backend\test_checkin.db`.

## Common failures

| Problem | Fix |
|---|---|
| `/services` returns 503 | Start the Owner; check `OWNER_API_BASE`; confirm the token is set in this terminal and matches the Owner's. |
| Owner reports 401 from Check-In | Token mismatch between the two backends. |
| Browser CORS error | Frontend origin missing from `ALLOWED_ORIGINS`. |
| Kiosk list stale after an Owner edit | Cache refreshes within `OWNER_CATALOG_CACHE_SECONDS` (default 45 s); reopening the service screen reloads it. |
| Owner down | Last good catalog is served up to `OWNER_CATALOG_MAX_STALE_SECONDS` (default 300 s), then 503. Nothing is invented locally. |
| `.env` value seems ignored | A variable already set in the shell / User environment wins over `backend\.env`. Check with `$env:DATABASE_URL` (don't print secrets). |

## Rules

Never commit `.env`, `*.db`, tokens or customer data. Do not add a service list to Check-In; services come from the Owner.
