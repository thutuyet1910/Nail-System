# Security boundaries and read-only voice policy

## Trust boundaries

```text
Owner browser -- HttpOnly session + CSRF --> Owner API
Public kiosk  -- limited public routes ------> Check-in API
Owner API     -- internal service token -----> Check-in internal queue
Twilio webhook -- Twilio signature + called number --> dedicated voice adapter
Twilio stream  -- single-call expiring token -------> realtime bridge
Voice runtime  -- database-backed call context -----> VoiceBookingFacade --> domain services
```

The browser never receives the owner session token, password hash, or internal-service token. The
owner session is server-side, expiring, revocable, and referenced by an opaque HttpOnly cookie.
Unsafe owner requests also require the session-bound CSRF cookie value in `X-CSRF-Token`.

Only `/voice/twilio/incoming`, `/voice/twilio/status`, and `/voice/twilio/media` bypass owner-browser
authentication. HTTP webhooks are checked with Twilio's official validator against the deterministic
`PUBLIC_BASE_URL` URL and all form fields. The media WebSocket must present a random, hashed,
short-lived token in the Twilio `start.customParameters`; it is bound to an existing call and one
StreamSid. OpenAI is connected only after this check succeeds.

The current AI tool allow-list contains public salon information, active services, service details,
generic availability, minimal caller-ID candidate matching, and owner callback requests. It does not
contain appointment creation, lookup, rescheduling, cancellation, customer updates, checkout,
technician assignment, or administrative writes. Caller-ID matching remains Level 1 and never
authorizes disclosure of appointment data.

## Caller verification policy (design only)

Level 0, unverified: salon hours, generic services/prices, and generic availability only.

Level 1, caller-number candidate: caller ID matches a customer candidate. May request an owner
callback, but must not reveal existing booking details, create, or modify a booking.
Caller ID is evidence, not authentication.

Level 2, verified customer: the call is tied to a database-backed customer after a future challenge
using an appointment code plus corroborating information, or a future OTP. May view that customer's
bookings, reschedule, or cancel subject to booking rules. Partial DOB should only be used after a
privacy review and must never be spoken back in full.

Minimum levels:

| Operation | Level |
|---|---:|
| Generic salon/service/availability information | 0 |
| Create booking | Not exposed in Phase 4 |
| Request owner callback (one per call; number must be caller ID or a spoken, untrusted contact number) | 0 |
| View own booking details | 2 |
| Reschedule booking | 2 |
| Cancel booking | 2 |

Every future mutation must carry an idempotency key and append a safe `VoiceCallEvent`. Event
metadata must not contain credentials, provider auth values, raw audio, or transcripts.

## Deployment notes

- Set long independent owner and internal-service secrets through the process environment.
- Set `OWNER_COOKIE_SECURE=true` behind HTTPS.
- Restrict `ALLOWED_ORIGINS` to the deployed owner UI origin.
- Use a reverse proxy for TLS, request-size limits, IP throttling, and future provider-webhook limits.
- The in-process login limiter is suitable for one process only; multi-worker production needs a
  shared limiter.
- `VOICE_ENABLED` and `VOICE_ALLOW_REAL_CALLS` both default off. They are rollout guards, not a
  substitute for rate limiting, monitoring, secret management, and a deployment security review.
- No raw audio or full transcript is stored. Call/event records contain lifecycle and safe tool names.
