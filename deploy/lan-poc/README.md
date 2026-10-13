# LAN deployment: kiosk tablet + salon PC (proof of concept, Phase 2: kiosk hardening)

One Windows PC runs both backends and a Caddy reverse proxy. A tablet on the same Wi-Fi opens **only** the
Check-In kiosk, and only after the salon owner has **paired** it. This is a manual set-up: no installer, no
launcher, no auto-start.

```text
Tablet --http--> PC :8080 (Caddy, LAN)  ---> /checkin  (static kiosk, strict CSP)
                                        ---> /api/checkin/<allowlist only> --> 127.0.0.1:8000  Check-In backend
                                             + X-Kiosk-Client-Ip (written by Caddy)   (device token required)
Owner browser -> PC 127.0.0.1:8081 (Caddy, this PC only)
                                        ---> /owner                         (static dashboard)
                                        ---> /api/owner/*  (not /internal, not /voice) --> 127.0.0.1:8001  Owner backend
Owner backend --(loopback, X-Internal-Service-Token)--> Check-In backend   (queue, catalog, tablet pairing)
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
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log --no-proxy-headers

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
configured) nor the backends should write them to disk. `--no-proxy-headers` keeps the Check-In backend's view of
the TCP peer exact (see "Client address" below).

Owner Dashboard on this PC: <http://127.0.0.1:8081/owner/>. Kiosk preview on this PC:
<http://127.0.0.1:8081/checkin/>. The old standalone static servers (ports 5500/5501) no longer work with
these frontends because the API base is relative; use Caddy for development too.

## Find the PC's LAN address

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Select-Object InterfaceAlias, IPAddress
# or: ipconfig   (use the Wi-Fi/Ethernet adapter that is on the salon network; ignore VPN/virtual adapters)
```

Tablet URL: `http://<PC_IP>:8080/checkin/` (typing just `http://<PC_IP>:8080` redirects there).
The address can change when the router reassigns it; reserve it in the router (DHCP reservation) for tests.

## Pairing a tablet

A tablet gets no data until it is paired. Pairing hands it a random, per-device **device token**.

1. **Owner Dashboard** (<http://127.0.0.1:8081/owner/>) -> Owner Management -> **Salon Settings** -> *4. Check-In
   Device* -> **Generate Pairing Code**. A code like `K7QM-4TXD` appears (once). It works one time and expires in
   10 minutes.
2. **Tablet:** open the kiosk. The "Pair this tablet" screen is shown. Type the code and press **Pair tablet**.
3. The screen closes and the kiosk works. In Salon Settings the tablet changes from *Waiting for code* to *Paired*
   and shows when it was last seen.
4. **Revoke** (same card) at any time: the tablet is refused on its very next request and returns to the pairing
   screen. A lost or replaced tablet is simply revoked and a new code issued.

On an iPad, pair inside the same place you will use it: a page added to the Home Screen keeps its own storage,
separate from Safari. Several tablets can be paired (up to 10 active); each has its own token and can be
revoked on its own.

### How the credentials work

| Credential | Created by | Stored | Lives | Grants |
|---|---|---|---|---|
| Pairing code (8 characters, e.g. `K7QM-4TXD`, no `0/O/1/I`) | Check-In, when the Owner asks | SHA-256 hash only | 10 minutes, **one use**; cleared on redemption or revocation | Only the right to redeem it at `POST /kiosk/pair` |
| Device token (`<device id>.<random secret>`, 256-bit secret) | Check-In, on redemption | hash only on the server; `localStorage` on the tablet | until revoked | **Kiosk routes only** (the table below) |
| Profile-edit token | Check-In, after the birth date is confirmed | memory only, hashed | 5 minutes, one edit, one customer, one device | `PATCH /customers/{phone}/profile` |
| Internal service token | the salon's own environment | never stored by the apps | n/a | Backend-to-backend routes. **Never** sent to, or accepted from, a browser |

- The device token is **not** derived from the pairing code and is **not** the internal service token. Using the
  internal token as a device token (or the reverse) is refused. A device token opens no Owner, staff or internal
  route.
- Header: `X-Kiosk-Device-Token: <token>` on every kiosk request (chosen over `Authorization` so it can never be
  mistaken for, or collide with, another credential). Missing, malformed, unknown, unpaired and revoked tokens all
  get the same `401` answer, so nothing about validity leaks. Verification is constant-time.
- The Owner Dashboard never sees a device token or a stored hash: its backend relays only the one-time pairing
  code (shown once, wiped when owner mode ends) and device *status* (paired/pending/revoked, last seen).

### Where the token lives on the tablet (evaluation)

`localStorage` is script-readable, so a script injected into the kiosk page could read the token. This was weighed
against an `HttpOnly` cookie (invisible to scripts, but it ties the credential to the browser's cookie rules and
needs CSRF handling). For this phase the header + `localStorage` is used because it is explicit and testable, and
the injection risk is closed from three sides: customer text is escaped before it is rendered (this fixed a real
stored-XSS path in the old "welcome back" card), names containing `<` or `>` are refused by the API, and the proxy
sends a strict Content-Security-Policy for the kiosk pages (no inline or foreign script, `connect-src 'self'`).
The token only unlocks kiosk routes and can be revoked in one click. An `HttpOnly` cookie is the planned upgrade
when HTTPS is added. If browser storage is blocked, the token is kept in memory for that session only.

## Kiosk route allowlist (11 routes)

These are the only backend routes Caddy forwards from the LAN (and from the loopback preview). Every one except
`POST /kiosk/pair` requires the device token. A test compares this table, the Caddyfile and the kiosk scripts, and
checks that every other Check-In route is refused.

<!-- kiosk-allowlist:start -->
| Method | Route | Why the kiosk needs it | What it returns | Privacy risk |
|---|---|---|---|---|
| POST | `/kiosk/pair` | Redeems a pairing code (no device token yet) | The device token, once | Low: rate limited per address and for the whole salon; the code is single-use and expires |
| GET | `/services` | Shows the service picker | Active catalog from the Owner: id, name, category, duration | None (not personal) |
| GET | `/queue-status` | "Check-in order" board | Position, `Customer #n`, check-in time | Low: names are anonymised |
| GET | `/customers/by-phone/{phone}` | Recognises a returning customer | **First name, the phone typed, a masked email hint, a has-referral-code flag.** No last name, birth date, id, discounts or full email | Low-medium: confirms that a number is a customer and reveals a first name; limited to 20 lookups/minute and 15 misses/10 minutes per device |
| GET | `/customers/check-in-status/{phone}` | "Already checked in today?" | First name and yes/no | Low-medium: same limits as the lookup |
| POST | `/customers/new` | New-customer registration | The created record (what the visitor just typed) | Medium: lets a paired tablet create customers; names with `<` or `>` are refused |
| POST | `/customers/check-in/{phone}` | The actual check-in | Confirmation, visit counts, services, rewards for this visit, first name | Medium: any paired tablet can check a known phone number in (the same as today's front-desk process) |
| POST | `/customers/{phone}/profile-access` | Second factor before "Update my details" | The editable details **only after the correct birth date**, plus a 5-minute edit token | Medium: birth-date guessing; 5 wrong answers lock that customer for 15 minutes, 10 per device |
| POST | `/referrals/validate` | Validates a referral code while registering | `{valid: true}` | Low-medium: 10 calls/minute and 10 failures/10 minutes per device |
| POST | `/referrals/apply` | Applies a referral code | Discount result with **first names only** | Medium: same limits as validate |
| PATCH | `/customers/{phone}/profile` | Saves "Update my details" | The updated first name / phone / email hint | Medium: **requires the profile-edit token**; a phone number alone is refused (403) |
<!-- kiosk-allowlist:end -->

Static files served under `/checkin/`: `index.html`, `config.js`, `kiosk-device.js`, `script.js`, `style.css`,
`translations.js`. Nothing else in the frontend folder is reachable.

What changed for customers: the returning-customer screen greets by first name, shows the phone number they just
typed and a masked email, and no longer shows their birth date. "Update Profile" first asks for the birth date
(the only second factor available without SMS), then opens the full details for one edit.

Also in force on kiosk requests: request bodies over 64 KB are refused (413); `X-Internal-Service-Token` is
removed from anything a browser sends; answers are `Cache-Control: no-store`; no access log is written.

### Routes intentionally blocked (404 on the LAN listener)

Everything not in the table, including `GET /customers` (list every customer), `/customers/id/{id}`,
`PATCH /customers/{phone}/update-phone` (also now internal-token only inside the backend),
`GET /customers/{phone}/visits`, `GET /today-checkins`, `GET /birthday-reminders`,
`POST /birthday-reminders/send`, `/internal/*` (including the pairing-code and device-management routes),
`/docs`, `/openapi.json`, and on the Owner side `/owner`, `/api/owner/*`, `/internal/*`, `/auth/*`,
`/settings/*` and `/voice/*`. The Owner listener (`:8081`) is bound to this PC only and additionally refuses
`/api/owner/internal/*` and `/api/owner/voice/*`.

## Rate limits (in-process, one backend)

| What | Limit | Key |
|---|---|---|
| Wrong or expired pairing codes | 5 per 10 minutes | client address |
| ... and for the whole salon | 20 per 10 minutes | all addresses |
| Phone lookup + check-in status | 20 per minute | device |
| Lookups that find nobody (enumeration) | 15 per 10 minutes | device |
| Referral validate/apply | 10 per minute; 10 failures per 10 minutes | device |
| Wrong birth dates | 5 per 15 minutes | customer |
| Wrong birth dates / missing edit token | 10 per 15 minutes | device |
| Unknown or revoked device tokens | 30 per 10 minutes | client address |
| Any kiosk request | 120 per minute | device |

Answers are `429` with `Retry-After`. Normal use is far below these (a new customer costs one lookup miss). The
counters live in the backend process and reset on restart; a multi-process or cloud deployment needs a shared
store.

## Client address and the trust boundary

Every request reaches the backend from the proxy, so the backend cannot see the tablet's address by itself.
Caddy therefore writes it into **`X-Kiosk-Client-Ip`**, *replacing* anything the client sent (`header_up` sets,
it never merges). The Check-In backend believes that header **only when the TCP peer is a trusted proxy**:
loopback (`127.0.0.1`, `::1`) by default, changeable with `TRUSTED_PROXY_IPS`. From any other peer the header is
ignored and the peer's own address is used, so a direct caller cannot dodge a limit by rotating the header. A
malformed header value falls back to the peer. The backends listen on `127.0.0.1` only, which is what makes
"peer is loopback" mean "it came through Caddy (or something already on this PC)". Run the Check-In backend with
`--no-proxy-headers` so uvicorn does not rewrite the peer from `X-Forwarded-For` on its own.

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

## Manual test A: this PC only (no firewall change)

1. Start the Check-In backend, the Owner backend and Caddy (above). Open <http://127.0.0.1:8081/checkin/>:
   the **Pair this tablet** screen covers the kiosk.
2. Open <http://127.0.0.1:8081/owner/> in another tab -> Owner Management (owner password) -> Salon Settings ->
   *Check-In Device* -> **Generate Pairing Code**.
3. In the kiosk tab type the code -> **Pair tablet**. The screen closes and the services load. In Salon Settings
   the tablet shows *Paired*.
4. Register a fake customer (name "Test Person", phone `555-010-0101`, any birth date), pick a service and check
   in. On the dashboard the customer appears in the live queue.
5. Check in again with the same number as a returning customer: the screen shows the first name and a masked email,
   no birth date. Press **Update Profile**: it asks for the birth date first (a wrong one is refused).
6. In Salon Settings press **Revoke** on the tablet. In the kiosk tab the next action (or within 10 seconds, the
   queue refresh) returns to the **Pair this tablet** screen, and the stored token is gone.

## Manual test B: a real second device (later; needs the firewall rule for 8080)

1. Do test A steps 1-3 but open `http://<PC_IP>:8080/checkin/` on the tablet and pair it there.
2. Register a fake customer and check in from the tablet; confirm it appears on the dashboard.
3. Every one of these must fail from the tablet (404 or "can't connect"): `http://<PC_IP>:8080/owner/`,
   `http://<PC_IP>:8080/api/owner/services`, `http://<PC_IP>:8080/api/checkin/customers`,
   `http://<PC_IP>:8000/`, `http://<PC_IP>:8001/`, `http://<PC_IP>:8081/owner/`.
4. Without pairing (a second browser, or clear the site's data), `http://<PC_IP>:8080/api/checkin/services` must
   answer 401.
5. Revoke in Salon Settings: the tablet returns to the pairing screen. Remove the firewall rule when finished.

A run on the PC itself (loopback plus its own LAN address) proves the routing, the allowlist and the pairing
logic, but it is **not** a second-device test.

## Remaining risks and later work

- **Check-in by phone number is still open to any paired tablet.** Anyone standing at the tablet can type a known
  number and check that customer in, exactly as at a front desk. The kiosk no longer shows or lets them edit private
  data without the birth date.
- **Birth date is a weak second factor** (guessable with enough tries; limited, not eliminated). Real
  verification (SMS or a code to the email on file) is deliberately not built yet.
- **Plain HTTP on the LAN.** Anyone on the Wi-Fi can sniff the token and phone numbers. Use a Wi-Fi network you
  control; HTTPS (and the `HttpOnly` cookie upgrade) comes with the installer phase.
- **Limits are per process** and reset on restart; the client-address trust relies on the backends staying on
  loopback.
- **Pairing is manual.** No QR code, no launcher, no auto-start, no automatic firewall rule (all later phases).
- Persisting the last good service catalog for Owner outages is still open.
