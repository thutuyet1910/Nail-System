# Nail Salon Owner Dashboard

The salon's day-to-day operations system: customer queue and turns, appointments and calendar,
checkout, technicians, services, inventory, income reports, an AI phone receptionist, and salon
settings. It runs next to a separate **Customer Check-In** application (kiosk) that feeds it the live
customer queue.

This repository contains the Owner application only (`backend/` FastAPI + SQLite, `frontend/` plain
HTML/CSS/JS, `frontend-tests/` browser-logic tests). Exact start-up commands are in
[DEVELOPMENT.md](DEVELOPMENT.md); security details are in [SECURITY.md](SECURITY.md); the phone
receptionist is described in [VOICE_DEVELOPMENT.md](VOICE_DEVELOPMENT.md).

---

## Contents

1. [Architecture](#architecture)
2. [Staff mode and Owner Management](#staff-mode-and-owner-management)
3. [Booking hours (important semantics)](#booking-hours-important-semantics)
4. [Calendar and appointments](#calendar-and-appointments)
5. [Services and technicians](#services-and-technicians)
6. [Queue, turns and checkout](#queue-turns-and-checkout)
7. [AI phone receptionist](#ai-phone-receptionist)
8. [Salon Settings](#salon-settings)
9. [Check-In integration](#check-in-integration)
10. [Project structure](#project-structure)
11. [Configuration (environment variable names)](#configuration-environment-variable-names)
12. [Database](#database)
13. [Security model](#security-model)
14. [Tests](#tests)
15. [Current limitations](#current-limitations)
16. [Production notes](#production-notes)

---

## Architecture

```text
 Customer kiosk (Check-In frontend :5500)
          |
          v
 Check-In backend :8000  <--- internal service token --->  Owner backend :8001  <--- Owner frontend :5501
                                                              |        ^
                                    Twilio webhooks / media   |        |  OpenAI Realtime (WebSocket)
                                    (public https URL) -------+--------+
```

| Part | Port (local) | Notes |
|---|---|---|
| Check-In backend | 8000 | separate repository; owns customers and the live queue |
| Owner backend | 8001 | this repository; the single source of truth for salon operations |
| Check-In frontend | 5500 | kiosk page |
| Owner frontend | 5501 | static files served from `frontend/` |

The Owner backend is the **authority** for services, booking hours, technicians, appointments,
turns and checkouts. The browser, the AI receptionist and the Check-In system all read the same data.

---

## Staff mode and Owner Management

The dashboard opens in **Staff mode with no password**. Owner Management sits on top of it and needs
the owner password.

| | Staff mode (no password) | Owner Management (password) |
|---|---|---|
| Screens | Customer List, Make Appointment / Calendar, Checkout | Nail Technician, Services, Inventory, Technician Income, Nail Salon Income, Salon Settings, notifications |
| Can | view the queue, assign and run turns, create / edit / reschedule / cancel appointments, check customers out | manage technicians, services, inventory, hours, settings; read income reports and history |
| Cannot | read income, inventory, notifications or settings; edit technicians or services; see full checkout history | n/a |

How it is enforced (the browser is not trusted):

- The backend gives every route an owner-only default. A short allow-list of daily-operation routes
  (`STAFF_ROUTES` in `backend/main.py`) is open to a **staff session**; everything else needs the
  **owner session**. A new route is therefore private until someone deliberately opens it.
- Staff data is also reduced: staff see technician names/availability only (no phone, notes or
  schedules), only **today's** checkouts, and checkout receipts without the salon/technician split.
- A staff session is created automatically by the page (`POST /auth/staff-session`), held in memory
  on the server, carries its own CSRF token, and has **no per-user authentication yet**
  (see [Current limitations](#current-limitations)).

**Owner security**

- The owner signs in with the **owner password** (scrypt hash, throttled login, HttpOnly + SameSite
  cookies, CSRF header on every write).
- After **3 minutes without owner activity** the owner session is **revoked on the server**, all owner
  data is wiped from the page, and the dashboard returns to Staff mode, which keeps working. Staff
  clicking around in daily screens does **not** keep Owner mode alive; only trusted input while an owner
  screen is in use counts.
- **Change Password** is in Salon Settings (current password required; every owner session is signed
  out afterwards).
- If the password is forgotten, an administrator resets it **on the salon computer** with
  `backend/reset_owner_password.py` (an emergency path, deliberately not part of the web UI).
- SMS password recovery is **not available**. The backend can store an owner recovery phone for a future
  release, but nothing in the UI exposes it.

---

## Booking hours (important semantics)

The weekly hours (Salon Settings, stored in `business_hours`) are the **appointment booking hours**.
They define when **new** appointments may be scheduled and are the single source used by:

manual booking, availability, the AI receptionist's availability and booking, preferred-technician
availability, the calendar's displayed range and non-bookable shading, the latest valid start for a
service combination, and `get_salon_info`.

An appointment must **start and finish** inside the day's hours (for example, Monday 9:00 AM - 6:00 PM
with a 2 hr 30 min service: latest start 3:30 PM).

They are **not** a shutdown time. After closing, Staff can still see customers and appointments,
continue active turns, complete services and check customers out. Changing the hours never moves or
deletes existing appointments; an existing appointment outside new hours stays visible at its real time.

---

## Calendar and appointments

- The calendar shows the span from the earliest opening to the latest closing of the week and labels the
  **closing boundary** (a 9-6 day reads 9 am ... 5 pm, 6 pm). Time that cannot be booked that day is shaded.
  Late appointments and active turns outside the hours are still drawn at their true time (the span grows
  to include them).
- A thin red **current-time line** follows the salon clock (**America/Phoenix**, independent of the
  browser's timezone) and is minute-accurate.
- The calendar refreshes by itself every 5 seconds (appointments created by phone or from another
  screen appear without reloading). Returning to the calendar shows the last good data immediately and
  refreshes in the background; a failed refresh never blanks it.
- Appointments are stored with a UTC instant plus the salon-local time, durations/buffers are snapshotted,
  and creation is idempotent and transactionally rechecked (overlaps, technician schedule, blocked time,
  eligibility, business hours).
- Dates in the UI use `MM-DD-YYYY`.

---

## Services and technicians

- **Services** (Owner Management) are the authoritative catalog: name, category, duration, price
  (optional - an unknown price stays unknown), buffers, active/inactive. Services are never deleted,
  only deactivated; existing appointments keep their own snapshots.
- **Technician eligibility** lives in `technician_services`. It can be edited per service on the Services
  page. Saving a technician only recomputes eligibility from the technician's *specialties* text when the
  specialties actually changed.
- **Specialties / service groups** (Nail Technician form) are still in use: they seed eligibility for new
  technicians and are the matching key for legacy name-only check-in visits. They are not obsolete.
- **Technician availability:** "unavailable today" resets on the next **salon (Phoenix) day**, on the
  server, without anyone opening Owner Management. Multi-day "date off" entries are left alone.

---

## Queue, turns and checkout

A **turn** is a customer's service workflow after assignment: `waiting -> assigned -> in_service -> done`
(or `cancelled`). Completed and cancelled turns are final; turn numbers restart each day.

- **Auto assignment** filters technicians (active employee, working, available today, eligible for the
  service, free right now) and then balances by the day's turn counts. **Preferred** assignment is a hard
  requirement: the technician must exist, be available, be eligible for the service and be free.
- **Checkout** inputs are the service subtotal, discount, tip and payment method. The backend calculates
  discount, net service, technician share (60%), salon share, technician total and salon revenue; the
  frontend's numbers are never trusted. A turn can be checked out once, and checkout completes the turn.
- **Inventory**, **Technician Income** and **Nail Salon Income** (day / week / year) are Owner Management
  screens built on the checkout history.

Business rules that are always enforced: a technician must match the requested service, an unavailable
technician cannot receive a customer, one active customer per technician, inactive technicians are
excluded but their history is kept, completed turns cannot move backward, invalid discounts are rejected.

---

## AI phone receptionist

A Twilio phone number connects (Media Streams) to the backend, which bridges the call to the OpenAI
Realtime API. The assistant:

- tells the caller once, at the start, that it is the salon's AI receptionist;
- answers from tools only: `get_salon_info`, `list_services`, `get_service_details`,
  `get_available_slots`, `identify_customer_candidate`, `request_owner_callback`, `create_booking`;
- books **one new appointment per call** through the same booking service as the dashboard: slots come
  only from `get_available_slots` (opaque, call-bound slot ids), the caller must hear a backend-built
  summary and clearly confirm, and the booking is transactionally rechecked and idempotent;
- treats a **named technician as a hard requirement** (never silently substituted), and does not volunteer
  technician names unless asked;
- cannot reschedule, cancel, look up appointments, or change anything else: those requests go to
  `request_owner_callback`.

Safety: Twilio webhooks are signature-checked, the media stream needs a single-use token, the Realtime
session must be confirmed ready before audio flows, provider errors are recorded as sanitized metadata,
and **no audio or transcript is stored**. The AI is switched on only with `VOICE_ENABLED` and
`VOICE_ALLOW_REAL_CALLS`. See [VOICE_DEVELOPMENT.md](VOICE_DEVELOPMENT.md).

---

## Salon Settings

Owner Management -> Salon Settings:

1. **Salon Information** - salon name and public phone. The time zone is shown but read-only (appointments
   are stored against it, so changing it later would silently move real appointments).
2. **Appointment / Booking Hours** - all seven days, saved as one validated, atomic change. Takes effect
   everywhere immediately.
3. **Phone / AI Receptionist** - read-only status (configured / not configured, Twilio number, voice
   on/off). Secrets are never shown. The **public salon phone** is what customers know; the **Twilio number**
   is the line the AI answers. They are separate settings, and changing the salon phone does not change Twilio.
4. **Owner Security** - Change Password.

---

## Check-In integration

- The Owner backend reads the live queue from the Check-In backend (`CHECKIN_API_BASE`) with the shared
  internal service token.
- Check-In reads the active service catalog from `GET /internal/services` (service token, read-only) and
  sends **service ids**; Owner resolves by id first and falls back to names only for old name-only visits.
  An unknown or deactivated id never falls back to a name; the visit stays in the queue with a warning.
- Booking hours do not gate check-in or the queue.

---

## Project structure

```text
backend/
  main.py               routes, access middleware (owner / staff / public), staff allow-list
  auth_service.py       owner + staff sessions, CSRF, password hashing, login throttling
  settings_service.py   salon profile, weekly hours, AI status (no secrets), owner security
  booking_service.py    availability, validation, transactional booking, idempotency
  booking_migrations.py idempotent schema upgrades and development seed data
  service_catalog.py    owner service catalog + internal read model
  crud.py               technicians, turns, assignment, checkout, income, rollover
  checkin_service.py    check-in <-> appointment matching, service-id parsing
  customer_gateway.py   Owner -> Check-In client
  voice_*.py, realtime_bridge.py, twilio_voice.py   AI phone receptionist
  reset_owner_password.py   local emergency password reset
  Test-main.py          backend test suite
frontend/
  index.html, styles.css
  js/                   dashboard (calendar, queue, checkout, technicians, services, inventory,
                        income, notifications), owner lock, salon settings, dashboard loading
frontend-tests/         browser-logic tests (run with Node, no dependencies)
```

---

## Configuration (environment variable names)

Values are never stored in the repository. The backend reads the **process environment** (it does not
load a `.env` file); `.env.example` lists the names with placeholder values.

| Area | Names |
|---|---|
| Database | `DATABASE_URL` |
| Owner login | `OWNER_BOOTSTRAP_PASSWORD` (first start only, when no credential exists), `OWNER_PASSWORD_HASH` (alternative), `OWNER_SESSION_TTL_MINUTES`, `OWNER_COOKIE_SECURE`, `OWNER_LOGIN_ATTEMPTS_PER_5_MINUTES`, `STAFF_SESSION_TTL_MINUTES` |
| Browser origins | `ALLOWED_ORIGINS` (must include the Owner frontend origin, e.g. `http://127.0.0.1:5501`) |
| Check-In link | `CHECKIN_API_BASE`, `CHECKIN_INTERNAL_SERVICE_TOKEN` |
| Public address | `PUBLIC_BASE_URL` (https origin Twilio can reach) |
| Voice switches | `VOICE_ENABLED`, `VOICE_ALLOW_REAL_CALLS` (both default off) |
| Twilio | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_REALTIME_MODEL`, `OPENAI_REALTIME_VOICE` |
| Voice tuning | `VOICE_STREAM_TOKEN_TTL_SECONDS`, `VOICE_MAX_CALL_MINUTES`, `VOICE_TOOL_TIMEOUT_SECONDS` |

---

## Database

SQLite (`DATABASE_URL`, default `backend/nail_system.db`). Database files are git-ignored: never commit
them. Schema upgrades run at start-up and are **idempotent and non-destructive** (columns are added, nothing
is rewritten); foreign keys are enforced. Use a separate file (for example `nail_system-private-test.db`)
for private call tests. The seed data (salon name, hours Mon-Sat 9-6, services, durations, technician
eligibility) is a development placeholder: review it before a real pilot.

---

## Security model

Summary (details in [SECURITY.md](SECURITY.md)): fail-closed route access; owner and staff sessions with
CSRF; owner-only data never reaches staff; Twilio signature validation and single-use media tokens; secrets
only in the server environment; no audio/transcript storage; the recovery phone (reserved for later) never
leaves the owner endpoints.

---

## Tests

```powershell
# backend (from backend\, venv active)
python -m pytest Test-main.py -q

# browser logic (from the repository root; needs Node)
node frontend-tests/owner-ui.test.js
Get-ChildItem frontend\js\*.js | ForEach-Object { node --check $_.FullName }
```

The backend suite uses a throwaway database and fake Twilio/OpenAI connections: it never places a call
or sends data to a provider.

---

## Current limitations

- **Staff mode has no per-user authentication** (anyone using the salon computer is staff). The server is
  meant to be reachable only from that machine / the salon network.
- **SMS password recovery is not available.** The local reset tool is the only recovery path.
- The weekly hours can be edited per weekday; there are no per-date exceptions (holidays) yet.
- Walk-in acceptance has no cut-off time; booking hours do not limit it.
- One owner login (no multiple owner accounts); one salon per installation; one AI booking per call.
- The in-process login throttle is for a single server process.

## Production notes

- A **Cloudflare Quick Tunnel is for development only** (its URL changes). Production needs a stable
  hosted https endpoint / domain for `PUBLIC_BASE_URL`, and the Twilio webhooks pointed at it.
- Set `OWNER_COOKIE_SECURE=true` behind https, restrict `ALLOWED_ORIGINS` to the deployed frontend, use a
  reverse proxy for TLS and request limits, and run real secret management.
- Review spend limits and monitoring for Twilio and OpenAI before enabling real calls.
