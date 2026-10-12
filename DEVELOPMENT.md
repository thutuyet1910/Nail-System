# Development and start-up guide (Windows PowerShell)

Everything below assumes Windows PowerShell and these two repositories side by side:

```text
C:\Users\<you>\source\repos\Nail-System-check-in-git       Check-In (kiosk + queue)
C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git   Owner dashboard (this repository)
```

| What | Address |
|---|---|
| Check-In backend | `127.0.0.1:8000` |
| Owner backend | `127.0.0.1:8001` |
| Check-In frontend | `127.0.0.1:5500` |
| Owner frontend | `127.0.0.1:5501` |

**Secrets:** this guide only names variables. Put the real values in your own PowerShell session (or a
local script that is **not** committed). Never paste them into a file in either repository.

Start order: Check-In backend -> Owner backend -> the two frontends -> (optional) tunnel.
Use one PowerShell window per process.

---

## One-time setup

```powershell
# Owner backend
cd C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git\backend
py -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

# Check-In backend
cd C:\Users\<you>\source\repos\Nail-System-check-in-git\backend
py -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## 1. Check-In backend (port 8000)

```powershell
cd C:\Users\<you>\source\repos\Nail-System-check-in-git\backend
$env:DATABASE_URL = "sqlite:///./nail_system-private-test.db"      # use a private-test file while testing
$env:CHECKIN_INTERNAL_SERVICE_TOKEN = "<same long random value as the Owner backend>"
$env:OWNER_API_BASE = "http://127.0.0.1:8001"
$env:ALLOWED_ORIGINS = "http://127.0.0.1:5500,http://localhost:5500"   # the kiosk origin
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check: <http://127.0.0.1:8000/docs> opens.

## 2. Owner backend (port 8001)

```powershell
cd C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git\backend

# Database and owner login
$env:DATABASE_URL = "sqlite:///./nail_system-private-test.db"          # or the default nail_system.db
$env:OWNER_BOOTSTRAP_PASSWORD = "<owner password; used only when no owner credential exists yet>"
$env:OWNER_COOKIE_SECURE = "false"                                       # true only behind https

# The Owner frontend origin MUST be listed (the page cannot start its staff session otherwise)
$env:ALLOWED_ORIGINS = "http://127.0.0.1:5501,http://localhost:5501"

# Link to Check-In
$env:CHECKIN_API_BASE = "http://127.0.0.1:8000"
$env:CHECKIN_INTERNAL_SERVICE_TOKEN = "<same long random value as the Check-In backend>"

# AI phone receptionist (leave these three lines out to run without voice)
$env:PUBLIC_BASE_URL = "https://<your public https origin>"            # see "Tunnel" below
$env:VOICE_ENABLED = "true"
$env:VOICE_ALLOW_REAL_CALLS = "true"                                     # only for an intentional private test
$env:TWILIO_ACCOUNT_SID = "<twilio account sid>"
$env:TWILIO_AUTH_TOKEN = "<twilio auth token>"
$env:TWILIO_PHONE_NUMBER = "+1XXXXXXXXXX"
$env:OPENAI_API_KEY = "<openai api key>"
# optional: OPENAI_REALTIME_MODEL, OPENAI_REALTIME_VOICE, VOICE_MAX_CALL_MINUTES, ...

venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Check: <http://127.0.0.1:8001/> returns the status JSON; <http://127.0.0.1:8001/docs> opens. Database
upgrades run automatically at start-up and can be repeated safely.

## 3. Check-In frontend (port 5500)

```powershell
cd C:\Users\<you>\source\repos\Nail-System-check-in-git\frontend
python -m http.server 5500 --bind 127.0.0.1
```

Open <http://127.0.0.1:5500>.

## 4. Owner frontend (port 5501)

```powershell
cd C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git\frontend
python -m http.server 5501 --bind 127.0.0.1
```

Open <http://127.0.0.1:5501>. It starts in **Staff mode** (no password). **Owner Management** asks for the
owner password. After changing frontend files, hard-refresh (Ctrl+Shift+R): the static server sends no
cache headers, so a browser can keep serving an old page.

---

## Tunnel and Twilio (voice only; development)

Twilio cannot reach `localhost`, so expose the Owner backend over https. A **Cloudflare Quick Tunnel is for
development only**: its address changes every time. Production needs a stable hosted https endpoint.

```powershell
cloudflared tunnel --url http://127.0.0.1:8001 --no-autoupdate
```

It prints an address like `https://<random-words>.trycloudflare.com`.

1. Set `PUBLIC_BASE_URL` to that address (https origin only, no trailing slash) **before** starting the Owner
   backend, and restart the backend whenever the tunnel address changes.
2. In the Twilio console, for the phone number:
   - **A call comes in**: Webhook, `POST`, `https://<public address>/voice/twilio/incoming`
   - **Call status changes**: `POST`, `https://<public address>/voice/twilio/status`
3. The WebSocket address (`wss://<public address>/voice/twilio/media`) is derived from `PUBLIC_BASE_URL`.
   The address Twilio signs must match `PUBLIC_BASE_URL` exactly.

Safe call test: use a **private-test database**, turn `VOICE_ENABLED` / `VOICE_ALLOW_REAL_CALLS` on only for
the test, and check Twilio and OpenAI spend limits first.

---

## Tests

```powershell
# Backend (about 4 minutes)
cd C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git\backend
venv\Scripts\python.exe -m pytest Test-main.py -q
venv\Scripts\python.exe -m pytest Test-main.py -q -k "StaffAccess or RouteAccessInventory"   # access rules only

# Browser logic and syntax (from the repository root; needs Node)
cd C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git
node frontend-tests/owner-ui.test.js
Get-ChildItem frontend\js\*.js | ForEach-Object { node --check $_.FullName }
```

The tests use their own throwaway database and fake Twilio / OpenAI connections.

---

## Forgotten owner password

On the salon computer (the database must be the one the app uses):

```powershell
cd C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git\backend
$env:DATABASE_URL = "<same value the app uses>"
venv\Scripts\python.exe reset_owner_password.py
```

It asks for the new password twice (hidden), applies the normal password rules and signs out every owner
session. SMS recovery does not exist yet.

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Dashboard says it cannot start / staff session fails (`403 Origin not allowed`) | `ALLOWED_ORIGINS` on the Owner backend does not include `http://127.0.0.1:5501`; fix and restart. |
| "Could not connect to backend" | Owner backend not running on 8001, or a different port; check `Get-NetTCPConnection -LocalPort 8001 -State Listen`. |
| Old page / old behaviour after an update | Hard-refresh (Ctrl+Shift+R); the static server does not set cache headers. |
| `401 Staff session required` once after a restart | Normal: staff sessions live in memory; the page renews it by itself. |
| Owner prompt keeps refusing the password | Wrong password, or throttled (5 tries / 5 minutes). Use the reset tool if forgotten. |
| Customer queue empty / link errors | Check-In backend not running on 8000, or the two `CHECKIN_INTERNAL_SERVICE_TOKEN` values differ (queue calls return 502). |
| Twilio webhook returns 403 | `PUBLIC_BASE_URL` does not exactly match the address Twilio calls, or the auth token is wrong. |
| Twilio webhook returns 503 | Voice switches off or a voice variable is missing (Salon Settings -> Phone / AI Receptionist shows what is missing). |
| Calls connect but the AI is silent | Check the call's events in the database (`voice_call_events`): provider errors are recorded with type and code, never audio or text. |
| `database is locked` / port already in use | Another copy of the backend is running; stop it (`Get-NetTCPConnection`, `Stop-Process -Id <pid>`). |
| New calendar hours not showing | Save in Salon Settings, then hard-refresh; hours are read from the database on every load. |
