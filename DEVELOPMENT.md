# Development Guide (Windows PowerShell)

Ports: Check-In backend `127.0.0.1:8000`, Owner backend `127.0.0.1:8001`, and a Caddy reverse proxy that serves the
frontends: kiosk on `0.0.0.0:8080` (LAN) and Owner + kiosk preview on `127.0.0.1:8081` (this PC only).
The kiosk page calls the relative path `/api/checkin`, so it must be opened through Caddy; the full manual
procedure, firewall rule, route allowlist and tablet test are in [deploy/lan-poc/README.md](deploy/lan-poc/README.md).

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

Optional: `TRUSTED_PROXY_IPS`, `KIOSK_PAIRING_CODE_MINUTES`, `KIOSK_PROFILE_EDIT_SECONDS`, `SALON_TIMEZONE`, `ALLOWED_ORIGINS`, `DATABASE_URL`, `OWNER_CATALOG_CACHE_SECONDS`, `OWNER_CATALOG_MAX_STALE_SECONDS` (see README).

## Startup order

1. **Owner backend** (port 8001), per the Owner repo's instructions.
2. **Check-In backend:**
   ```powershell
   cd <repo>\backend
   venv\Scripts\Activate.ps1
   # load the env vars above in this same terminal
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
   ```
3. **Caddy** (serves the kiosk and routes `/api/checkin`; install once with `winget install CaddyServer.Caddy`):
   ```powershell
   cd <repo>
   $env:CHECKIN_FRONTEND_DIR = "<repo>\frontend"
   $env:OWNER_FRONTEND_DIR   = "<owner repo>\frontend"
   caddy run --config deploy\lan-poc\Caddyfile --adapter caddyfile
   ```
   Kiosk preview on this PC: `http://127.0.0.1:8081/checkin/`. A tablet on the salon Wi-Fi uses
   `http://<PC_IP>:8080/checkin/` (see [deploy/lan-poc/README.md](deploy/lan-poc/README.md)).
   The old `python -m http.server 5500` no longer works, because the page now uses same-origin API paths.

Pairing: the kiosk shows a **Pair this tablet** screen until the owner creates a one-time code (Owner Dashboard -> Salon Settings -> Check-In Device) and it is typed in. Every kiosk call then carries the device token, so `http://127.0.0.1:8000/services` needs the `X-Kiosk-Device-Token` header (a plain browser visit answers 401). Step-by-step test: [deploy/lan-poc/README.md](deploy/lan-poc/README.md). A 503 from `/services` means the Owner catalog is unreachable or misconfigured.

## Tests

```powershell
cd <repo>\backend
python -m pytest app -q                       # full suite (includes the runtime, backup and wiring tests)
python -m pytest app\test_owner_catalog.py -q # Owner catalog / service ids
node --check ..\frontend\script.js
node --check ..\frontend\translations.js
node --check ..\frontend\kiosk-device.js
cd ..; node frontend-tests\kiosk-device.test.js   # pairing, token storage, header injection, revoked tablet
```

Tests never touch the network or a real Owner (`app/conftest.py` fakes it) and use `backend\test_checkin.db`.

## Installed layout, secrets and backups

Everything above is **development mode**. A real install keeps data, settings, secrets, logs and backups under
`C:\ProgramData\NailSystem` (`NAILSYSTEM_MODE=product`; `.env` is then ignored). Full description: [deploy/RUNTIME.md](deploy/RUNTIME.md).
From `backend\`:

```powershell
python app\nailsystem_backup.py backup --app checkin --db .\nail_system.db     # online backup of the dev database (verified)
python app\nailsystem_backup.py list   --app checkin --db .\nail_system.db
```

## Common failures

| Problem | Fix |
|---|---|
| `/services` returns 503 | Start the Owner; check `OWNER_API_BASE`; confirm the token is set in this terminal and matches the Owner's. |
| Owner reports 401 from Check-In | Token mismatch between the two backends. |
| Kiosk page loads but every call fails (404) | The page was opened outside Caddy (for example a static server on another port). Open it via `http://127.0.0.1:8081/checkin/` or the LAN address. |
| A kiosk call returns 404 through Caddy | The route is not on the kiosk allowlist (`deploy/lan-poc/README.md`). Adding one means changing the Caddyfile, the table and the test together. |
| Browser CORS error | Only relevant if the page is served from a different origin than the API; `ALLOWED_ORIGINS` must then list it. |
| Kiosk list stale after an Owner edit | Cache refreshes within `OWNER_CATALOG_CACHE_SECONDS` (default 45 s); reopening the service screen reloads it. |
| Owner down | Last good catalog is served up to `OWNER_CATALOG_MAX_STALE_SECONDS` (default 300 s), then 503. Nothing is invented locally. |
| `.env` value seems ignored | A variable already set in the shell / User environment wins over `backend\.env`. Check with `$env:DATABASE_URL` (don't print secrets). |

## Rules

Never commit `.env`, `*.db`, tokens or customer data. Do not add a service list to Check-In; services come from the Owner.
