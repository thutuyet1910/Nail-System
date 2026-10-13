# Nail Salon Customer Check-In System

Customer-facing kiosk for a nail salon. Customers enter a phone number, create or confirm their profile, pick services, receive any earned rewards, and join today's live queue. The Owner dashboard (separate repo, `Nail-System-owner-dashboard`) reads that queue to assign technicians.

Local setup and day-to-day commands: see [DEVELOPMENT.md](DEVELOPMENT.md).

## Architecture

```text
Tablet ─► Caddy :8080 (kiosk only) ─► /checkin (static)  +  /api/checkin/<allowlist> ─► Check-In backend (FastAPI, 127.0.0.1:8000) ──► Owner backend (127.0.0.1:8001)
                                                                                       │   ▲                                 GET /internal/services
                                                                                       ▼   └──── Owner polls GET /today-checkins
                                                                                  SQLite (nail_system.db)
```

The frontend uses the same-origin path `/api/checkin`, and the reverse proxy decides where it goes, so no host,
IP address or port is hard-coded in the browser code. Only an explicit allowlist of nine kiosk routes is
forwarded; the rest of the API (customer lists, birthday reminders, internal routes, docs) is not reachable from
the LAN. Both backends bind to `127.0.0.1`. See [deploy/lan-poc/README.md](deploy/lan-poc/README.md) for the
Caddy setup, the allowlist, the privacy risks that remain for this proof of concept, and the real-tablet test.

- The browser only ever talks to the Check-In backend. It never contacts the Owner and never sees the internal token.
- **The Owner service catalog is authoritative.** Check-In has no service management and no editable catalog. `GET /services` returns the Owner's *active* services (cached briefly in memory, see below).
- Services are selected by the Owner's stable service **id**. For each new visit Check-In stores the Owner id plus a **name snapshot** (the name at check-in time) in `visit_owner_services`.
- `GET /today-checkins` (internal token required) returns, per visit, `service_ids` (Owner ids) and the legacy `services` name list. The Owner uses the ids to decide technician eligibility.
- An unknown or deactivated id is rejected at check-in ("please reselect") and is never matched by name or remapped. The Owner applies the same rule on its side.

### Legacy compatibility

Older visits point at the local `services` table through `visit_services`. That table and those rows are kept, never rewritten, and are only read for history:

| Visit has | `services` | `service_ids` |
|---|---|---|
| Owner ids (new) | snapshot names | the ids |
| legacy rows only | legacy names | `[]` (Owner uses its name-based legacy path) |

The `services` table is no longer seeded and is never used for new selections.

### Rename / deactivation

- **Rename:** the Owner renames service 10. After the cache refreshes, new check-ins show the new name; id 10 is unchanged. Visits already stored keep their old name snapshot.
- **Deactivation:** after the cache refreshes the service disappears from new selections. Old visits remain readable. At check-in the catalog is force-refreshed (rate limited), so a just-deactivated service is rejected.

### Catalog cache and Owner outages

| Setting | Default | Meaning |
|---|---|---|
| `OWNER_CATALOG_CACHE_SECONDS` | 45 | how long a fetched catalog is considered fresh |
| `OWNER_CATALOG_MAX_STALE_SECONDS` | 300 | how long the last good catalog may be served if the Owner is unreachable |
| (fixed) | 5 s | minimum gap between forced refreshes; HTTP timeout is also 5 s |

If the Owner is down, the last good catalog is served until it is `OWNER_CATALOG_MAX_STALE_SECONDS` old. After that `/services` and check-in return **503** ("Services are temporarily unavailable. Please ask the front desk for help."). There is no hard-coded fallback list. A malformed Owner response (wrong shape, bad ids, duplicates) is treated like an outage.

## Configuration (names only; never commit values)

| Variable | Purpose |
|---|---|
| `OWNER_API_BASE` | Owner backend base URL, e.g. `http://127.0.0.1:8001`. Server-side only. |
| `CHECKIN_INTERNAL_SERVICE_TOKEN` | Shared secret. Authenticates the Owner calling Check-In internal routes **and** Check-In calling the Owner's `/internal/services`. Server-side only. |
| `ALLOWED_ORIGINS` | CORS origins for the kiosk frontend. |
| `DATABASE_URL` | SQLite URL (default `sqlite:///./nail_system.db`). |
| `SALON_TIMEZONE` | Salon timezone (default `America/Phoenix`); "today" and visit dates use it. |
| `OWNER_CATALOG_CACHE_SECONDS`, `OWNER_CATALOG_MAX_STALE_SECONDS` | Cache tuning (above). |
| `SMTP_SERVER`, `EMAIL_SENDER`, `EMAIL_PASSWORD` (see `email_utils.py`) | Optional birthday / referral emails. |

`backend/.env` (optional, git-ignored; template in `.env.example`) is loaded once at package import by `app/config.py`, before any setting is read. **Variables already set in the process / Windows User environment always win**; `.env` only fills in missing ones. `CHECKIN_ENV_FILE` can point at a different file.

## Project structure

```text
backend/
  requirements.txt
  app/
    main.py             routes, rewards, check-in logic, startup migrations
    models.py           Customer, Visit, VisitOwnerService (new), Service/VisitService (legacy)
    schemas.py          request/response models and validation
    owner_catalog.py    read-only Owner catalog client + bounded in-memory cache
    config.py           loads backend/.env at import (never overrides real env vars)
    security.py         internal-token dependency (constant-time compare)
    phone_normalization.py, timeutils.py, database.py, email_utils.py, scheduler.py
    conftest.py         fake Owner for tests (no network in tests)
    test_main.py, test_owner_catalog.py
frontend/               index.html, script.js, translations.js, style.css (static, no build step)
```

## Main API

Public (kiosk): `GET /services`, `POST /customers/new`, `GET /customers/by-phone/{phone}`, `GET /customers/check-in-status/{phone}`, `POST /customers/check-in/{phone}`, `POST /referrals/validate`, `POST /referrals/apply`, `PATCH /customers/{phone}/update-phone`, `PATCH /customers/{phone}/profile`, `GET /queue-status` (anonymised).

Internal (`X-Internal-Service-Token` required): `GET /today-checkins`, `GET /customers`, `GET /customers/id/{id}`, `GET /customers/{phone}/visits`, `GET /internal/customers/by-phone/{phone}`, `GET /birthday-reminders`, `POST /birthday-reminders/send`.

## Database

SQLite, created on startup with `create_all` plus idempotent additive `ALTER TABLE ADD COLUMN` helpers; nothing is dropped or rewritten. `visit_owner_services` is the only table added for the shared catalog: `(visit_id, owner_service_id, service_name)` with a unique `(visit_id, owner_service_id)` index. Database files are git-ignored. Back up `backend/nail_system.db` before upgrading a live salon.

## Security notes

- Internal routes use `hmac.compare_digest`; a missing server token returns 503, a wrong/missing header 401.
- The token is read from the server environment only and is sent only to `OWNER_API_BASE` (redirects are not followed, only http/https). It is not logged or returned in any response.
- `/queue-status` is anonymised (position + services only).
- Check-in accepts at most 20 services per visit (the Owner rejects larger payloads).

## Current limitations

- **One shared token in both directions.** Recommended for production hardening: separate directional credentials plus rotation.
- Some public routes (e.g. `GET /customers/by-phone/{phone}`, profile updates) are unauthenticated by phone number, as in the kiosk design; production should add rate limiting / a reverse proxy.
- No explicit length limits on free-text fields; rely on the reverse proxy for request size.
- The catalog cache is per process (run a single worker or accept per-worker caches).
- If the Owner deactivates a service *after* a customer checked in, the Owner flags that queue entry; Check-In does not learn of it.
- SQLite foreign keys are not enforced by the engine (pragma off); integrity relies on the ORM.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Kiosk shows "unable to load services" / 503 | Owner not running, `OWNER_API_BASE` unset or wrong, or token mismatch (Owner returns 401/503). |
| Owner shows empty queue / 401 | `CHECKIN_INTERNAL_SERVICE_TOKEN` differs between the two backends. |
| Renamed service still old on kiosk | wait up to `OWNER_CATALOG_CACHE_SECONDS` (kiosk reloads the list when the service screen opens). |
| "no longer available, please reselect" | the chosen service was deactivated; select another. |
