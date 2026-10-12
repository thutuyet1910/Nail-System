# Security model

## Trust boundaries

```text
Owner browser  -- HttpOnly owner session + CSRF -------------> Owner API (owner-only routes)
Staff browser  -- HttpOnly staff session + staff CSRF -------> Owner API (staff allow-list only)
Check-In       -- internal service token (read-only) ------> GET /internal/services
Owner API      -- internal service token ------------------> Check-In internal queue
Twilio webhook -- Twilio signature + called number ---------> /voice/twilio/incoming, /status
Twilio stream  -- single-call expiring token ---------------> /voice/twilio/media (OpenAI Realtime bridge)
Voice runtime  -- database-backed call context -------------> VoiceBookingFacade --> booking service
```

## Access control

- **Fail closed.** `owner_authorization_boundary` (in `backend/main.py`) refuses every route unless it is
  deliberately public (`/`, `/salon`, `/business-hours`, `/services`, `/availability`), an auth route, a
  Twilio webhook, the token-protected `/internal/services`, or on the `STAFF_ROUTES` allow-list. Anything
  new is owner-only until someone opens it on purpose. `TestRouteAccessInventory` walks every route and
  checks it for anonymous, staff and owner callers.
- **Owner session:** password login (scrypt hash, throttled), server-side revocable session, opaque
  HttpOnly + SameSite=Strict cookie, session-bound CSRF value in `X-CSRF-Token` on every write. It expires
  after 480 minutes at most and is revoked by the dashboard after 3 minutes without owner activity.
- **Staff session:** created without a password (`POST /auth/staff-session`, allowed Origin required),
  in memory only, own HttpOnly cookie and CSRF header (`X-Staff-CSRF-Token`). It reaches only the staff
  allow-list and receives reduced data (no technician phone/notes/schedules, today's checkouts only,
  no income split). **Staff mode has no per-user authentication.**
- **Change Password** re-verifies the current password (throttled) and revokes every owner session.
  `backend/reset_owner_password.py` is the local, emergency reset path.
- **Recovery phone:** the backend can store an owner recovery phone (owner-only endpoints, current password
  required, only a masked value is ever returned). There is **no SMS recovery** and the UI does not expose it.

## Secrets

Secrets live only in the server's process environment (see `.env.example` for names). They are never in the
repository, in frontend files, or in any API response; the AI-status endpoint returns only yes/no flags and
the public Twilio number. A repository test scans source, docs and frontend files for credential-shaped
values.

## Voice (AI phone receptionist)

- HTTP webhooks are validated with Twilio's official validator against the deterministic `PUBLIC_BASE_URL`
  and all form fields, and the called number must match the configured Twilio number.
- The media WebSocket must present a random, hashed, short-lived, single-use token bound to one call and
  one StreamSid. OpenAI is connected only after that check, and audio flows only after the Realtime session
  is confirmed ready (`session.created` -> `session.update` -> `session.updated`, with a timeout).
- **Tool allow-list:** `get_salon_info`, `list_services`, `get_service_details`, `get_available_slots`,
  `identify_customer_candidate` (returns only matched yes/no), `request_owner_callback`, `create_booking`.
  There is no cancel, reschedule, appointment lookup, customer update, technician, checkout, income,
  inventory or service tool.
- **`create_booking`** books at most one new appointment per call, only in a slot id the backend issued on
  that call, after a backend-built summary, a new caller utterance and an explicit confirmation, through
  the same transactional, idempotent booking service as the dashboard. The caller ID wins over any phone
  number the model supplies; a named technician cannot be changed by the model.
- Caller verification: caller ID is evidence, not authentication. Existing appointment details are never
  disclosed by phone.
- Provider and stream failures are recorded as **sanitized metadata only** (error type/code, stage, close
  code). No raw audio, transcript, confirmation wording, provider message text, header or key is stored.

## Deployment notes

- Set long, independent owner and internal-service secrets through the process environment.
- Set `OWNER_COOKIE_SECURE=true` behind https; restrict `ALLOWED_ORIGINS` to the deployed frontend origin.
- Use a reverse proxy for TLS, request-size limits and IP throttling. The in-process login limiter is for a
  single process only; multi-worker deployments need a shared limiter.
- `VOICE_ENABLED` and `VOICE_ALLOW_REAL_CALLS` default off. They are rollout guards, not a replacement for
  monitoring, spend limits and a deployment review.
- A Cloudflare Quick Tunnel is a development convenience only. Production needs a stable hosted endpoint.
- Bind the backend to `127.0.0.1` (or the salon network) only: staff mode is password-less by design.
