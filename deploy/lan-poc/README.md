# LAN proof of concept: kiosk tablet + salon PC

Phase 1 of the two-device deployment. One Windows PC runs both backends and a Caddy reverse proxy. A
tablet on the same Wi-Fi opens **only** the Check-In kiosk. This is a manual proof of concept: no installer,
no launcher, no auto-start.

```text
Tablet --http--> PC :8080 (Caddy, LAN)  ---> /checkin  (static kiosk)
                                        ---> /api/checkin/<allowlist only>  --> 127.0.0.1:8000  Check-In backend
Owner browser -> PC 127.0.0.1:8081 (Caddy, this PC only)
                                        ---> /owner                         (static dashboard)
                                        ---> /api/owner/*  (not /internal, not /voice) --> 127.0.0.1:8001  Owner backend
Check-In backend <== X-Internal-Service-Token, loopback, never through Caddy ==> Owner backend
```

| Process | Address | Reachable from the LAN? |
|---|---|---|
| Check-In backend | `127.0.0.1:8000` | No (bound to loopback) |
| Owner backend | `127.0.0.1:8001` | No (bound to loopback) |
| Caddy, kiosk listener | `0.0.0.0:8080` | **Yes**, kiosk only |
| Caddy, Owner listener | `127.0.0.1:8081` | No (this PC only) |

The browsers use same-origin paths only (`/api/checkin`, `/api/owner`). No IP address, host name or port is
hard-coded in either frontend; Caddy decides where each path goes.

## Run it (Windows PowerShell, one window per process)

Both repositories sit side by side, for example
`C:\Users\<you>\source\repos\Nail-System-check-in-git` and `...\Nail-System-owner-dashboard-git`. Real values
for the placeholders stay in your own session; never put them in a file in either repository.

```powershell
# 1. Check-In backend  (127.0.0.1:8000)
cd C:\Users\<you>\source\repos\Nail-System-check-in-git\backend
$env:DATABASE_URL = "sqlite:///./nail_system-private-test.db"
$env:OWNER_API_BASE = "http://127.0.0.1:8001"
$env:CHECKIN_INTERNAL_SERVICE_TOKEN = "<long random value, same as the Owner backend>"
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log

# 2. Owner backend  (127.0.0.1:8001)
cd C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git\backend
$env:DATABASE_URL = "sqlite:///./nail_system-private-test.db"
$env:ALLOWED_ORIGINS = "http://127.0.0.1:8081,http://localhost:8081"   # the Owner page's origin (staff-session check)
$env:CHECKIN_API_BASE = "http://127.0.0.1:8000"
$env:CHECKIN_INTERNAL_SERVICE_TOKEN = "<same value>"
$env:OWNER_COOKIE_SECURE = "false"                                      # plain http on this PC; true behind https
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001 --no-access-log

# 3. Caddy (LAN :8080 + loopback :8081). Install once: winget install CaddyServer.Caddy
cd C:\Users\<you>\source\repos\Nail-System-check-in-git
$env:CHECKIN_FRONTEND_DIR = "C:\Users\<you>\source\repos\Nail-System-check-in-git\frontend"
$env:OWNER_FRONTEND_DIR   = "C:\Users\<you>\source\repos\Nail-System-owner-dashboard-git\frontend"
caddy validate --config deploy\lan-poc\Caddyfile --adapter caddyfile
caddy run      --config deploy\lan-poc\Caddyfile --adapter caddyfile
```

`--no-access-log` matters: kiosk URLs contain customer phone numbers, and neither Caddy (no access log is
configured) nor the backends should write them to disk.

Owner Dashboard on this PC: <http://127.0.0.1:8081/owner/>. Kiosk preview on this PC:
<http://127.0.0.1:8081/checkin/>. The old standalone ports (5500/5501 static servers) no longer work with
these frontends because the API base is now relative; use Caddy for development too.

## Find the PC's LAN address

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Select-Object InterfaceAlias, IPAddress
# or: ipconfig   (use the Wi-Fi/Ethernet adapter that is on the salon network; ignore VPN/virtual adapters)
```

Tablet URL: `http://<PC_IP>:8080/checkin/` (typing just `http://<PC_IP>:8080` redirects there).
The address can change when the router reassigns it; reserve it in the router (DHCP reservation) for tests.

## Windows Firewall (manual, temporary)

Nothing here changes the firewall automatically. If the tablet cannot connect, add a rule for **8080 only**,
from an **Administrator** PowerShell, and only on the Private network profile:

```powershell
New-NetFirewallRule -DisplayName "Nail System kiosk POC (TCP 8080)" -Direction Inbound -Protocol TCP `
  -LocalPort 8080 -Action Allow -Profile Private
# remove it when the test is over:
Remove-NetFirewallRule -DisplayName "Nail System kiosk POC (TCP 8080)"
```

Do **not** open 8000, 8001 or 8081. If Windows classified the Wi-Fi as Public, set it to Private first
(Settings > Network) or the rule will not apply, which is also the safer default on a shared network.

## Kiosk route allowlist

These nine rows are the only backend routes Caddy forwards from the LAN (and from the loopback preview). A
test compares this table, the Caddyfile and the kiosk script, and checks that every other Check-In route is
refused.

<!-- kiosk-allowlist:start -->
| Method | Route | Why the kiosk needs it | What it returns | Privacy risk (POC) |
|---|---|---|---|---|
| GET | `/services` | Shows the service picker | Active catalog from the Owner: id, name, category, duration | None (not personal) |
| GET | `/queue-status` | "Check-in order" board | Position, `Customer #n`, check-in time, service names | Low: names are anonymised |
| GET | `/customers/by-phone/{phone}` | Recognises a returning customer | The full customer record: name, phone, email, date of birth, referral code/counts, discount flags | **High**: anyone on the Wi-Fi who knows or guesses a phone number can read that customer's profile |
| GET | `/customers/check-in-status/{phone}` | "Already checked in today?" | Phone, full name, yes/no | **Medium**: confirms a customer and reveals their name by phone number |
| POST | `/customers/new` | New-customer registration | The created customer record | Medium: lets any LAN device create customers |
| POST | `/customers/check-in/{phone}` | The actual check-in | Confirmation, visit counts, services | Medium: lets any LAN device check a known phone number in |
| POST | `/referrals/validate` | Validates a referral code while registering | Whether the code is valid and its discount | Low-medium: lets codes be guessed one by one |
| POST | `/referrals/apply` | Applies a referral code | Discount result | Medium: changes discount state for a phone number |
| PATCH | `/customers/{phone}/profile` | "Update my details" screen | The updated customer record | **High**: anyone on the Wi-Fi who knows a phone number can change that customer's name, phone and email |
<!-- kiosk-allowlist:end -->

Static files served under `/checkin/`: `index.html`, `config.js`, `script.js`, `style.css`,
`translations.js`. Nothing else in the frontend folder is reachable.

Also in force on kiosk requests: request bodies over 64 KB are refused (413); `X-Internal-Service-Token`
is removed from anything a browser sends; no access log is written.

### Routes intentionally blocked (404 on the LAN listener)

Everything not in the table, including `GET /customers` (list every customer), `/customers/id/{id}`,
`PATCH /customers/{phone}/update-phone`, `GET /customers/{phone}/visits`, `GET /today-checkins`,
`GET /birthday-reminders`, `POST /birthday-reminders/send`, `/internal/*`, `/docs`, `/openapi.json`, and on
the Owner side `/owner`, `/api/owner/*`, `/internal/*`, `/auth/*`, `/settings/*` and `/voice/*`. The
Owner listener (`:8081`) is bound to this PC only and additionally refuses `/api/owner/internal/*` and
`/api/owner/voice/*`.

## Security notes for this POC

- The two **High** rows are the privacy cost of a kiosk that looks customers up by phone number alone, on a
  network where any device can reach `:8080`. They are temporary and accepted only for the proof of concept.
  Use a private test database, a Wi-Fi network you control, and do not use real customer data.
- The Owner backend (and with it staff mode, which has no password) is never reachable from the LAN: it is
  bound to loopback, and the LAN listener has no route to it.
- Owner pages and APIs share the origin `http://127.0.0.1:8081` (or `localhost`); the kiosk lives on a
  different origin (the LAN address), so a kiosk page cannot use the Owner session cookies.
- CORS is unchanged: no wildcard, and with same-origin pages no cross-origin request is needed at all.
  The Owner backend's `ALLOWED_ORIGINS` must list the Owner page origin; its staff-session endpoint refuses
  any other `Origin`. CSRF checks and `HttpOnly` / `SameSite=Strict` cookies are unchanged.
- The backends see every request as coming from `127.0.0.1` (the proxy). Per-client rate limiting must read
  the forwarded address (Phase 2).

## Real tablet test (needs a second device)

PC:
1. Start the Check-In backend, then the Owner backend, then Caddy (above).
2. Find the LAN IPv4 address. Add the 8080 firewall rule only if the tablet cannot connect.

Tablet (same Wi-Fi):
1. Open `http://<PC_IP>:8080/checkin/`. The page must load and show the service list from the Owner.
2. Register a test customer (fake name, `555` phone) and check in with one service.
3. On the PC, open `http://127.0.0.1:8081/owner/`. The customer must appear in the live queue with the
   service.

Security checks from the tablet (every one must fail, i.e. 404 or "can't connect"):
- `http://<PC_IP>:8080/owner/`
- `http://<PC_IP>:8080/api/owner/services`
- `http://<PC_IP>:8080/api/checkin/customers`
- `http://<PC_IP>:8000/`, `http://<PC_IP>:8001/`, `http://<PC_IP>:8081/owner/` (nothing listens on the LAN)

Remove the firewall rule when finished. A test run on the PC itself (loopback plus its own LAN address)
proves the routing and the allowlist, but it is **not** a second-device test.

## Phase 2 (not done here)

Device pairing and a kiosk credential, rate limiting on the phone lookups (behind the forwarded client
address), reducing what `by-phone` and `profile` expose or require, a kiosk-side lock for profile edits,
persisting the last good service catalog for Owner outages, HTTPS, and a launcher that starts everything.
