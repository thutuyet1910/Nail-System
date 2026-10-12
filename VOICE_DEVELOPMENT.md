# AI phone receptionist: development notes

## Protocol

The backend uses the Twilio Python SDK request validator and TwiML builder with Programmable Voice
webhooks and bidirectional `<Connect><Stream>` Media Streams. It connects to OpenAI's GA Realtime
WebSocket API (`wss://api.openai.com/v1/realtime`) with the model from `OPENAI_REALTIME_MODEL` (default
`gpt-realtime-2.1`). Audio is `audio/pcmu` both ways: Twilio's 8 kHz mu-law frames are forwarded unchanged,
and OpenAI's PCMU deltas are sent back unchanged (no transcoding).

## Call lifecycle

1. Twilio posts `/voice/twilio/incoming` (signature checked). The reply is TwiML with the stream URL, a
   single-use stream token and, after the stream, one generic spoken line used only if the stream ends
   while the caller is still on the line.
2. Twilio opens `/voice/twilio/media`; the `start` message is authenticated (account, format, token).
3. The bridge connects to OpenAI and waits for `session.created`, sends `session.update`, and waits for
   `session.updated` (10 s timeout). Only then does it send the greeting and start forwarding caller audio.
4. Tool calls run against the backend; several tool calls in one model response are answered together
   with a single `response.create`.
5. The call ends on hangup, a provider close or failure, or `VOICE_MAX_CALL_MINUTES`. Failures are recorded
   as sanitized `failed` / `provider_error` events (stage, error type and code, close code); a normal
   hangup is never labelled a failure.

## Booking by phone

`get_available_slots` returns real availability for the chosen service ids (it uses the same booking
hours, durations, buffers, schedules, blocks and overlaps as the dashboard) plus an opaque `slot_id`.
`create_booking` is two-step: prepare (returns a backend summary, books nothing), then commit after the
caller clearly confirms. The booking is idempotent per call and slot, one per call. A named technician
(`technician_name`) is a hard constraint; with no preference any eligible technician may be assigned.
Rescheduling and cancelling are not supported by phone: the assistant offers an owner callback.

The configured weekly hours are **scheduling hours**: the assistant never offers a time outside them or a
service that would finish after closing, and says nothing about walk-ins.

## Local setup

See [DEVELOPMENT.md](DEVELOPMENT.md) for the exact commands, the tunnel and the Twilio webhook settings.
Use a private-test database, enable `VOICE_ENABLED` / `VOICE_ALLOW_REAL_CALLS` only for an intentional test,
and check provider spend limits first.

## Behaviour notes

- Past start times are rejected and never offered, using the salon (America/Phoenix) clock.
- Anonymous, blocked or non-US caller IDs still get valid TwiML: the call has no trusted phone, customer
  lookup reports no match, and a callback requires the caller to say a number (stored as untrusted).
- Exactly one owner callback is recorded per call; deduplication is server-owned.
- `identify_customer_candidate` returns only `{"matched": true|false}`.
- A finished call can never be reopened by a late media stream.
- OpenAI `error` events: errors caused by our own truncate request, or on a short allow-list, are audited
  and the call continues; auth / quota / server / unknown errors end the call (fail closed).
- Prices that are unknown stay unknown; the assistant says so instead of inventing one.

## Development seed data

The salon name, weekly hours, services, durations, buffers and technician eligibility seeded by
`booking_migrations.py` are development placeholders, not confirmed by the owner. Review all of it in
Owner Management before a real salon pilot.

## Not implemented

Recording, transcript storage, caller identity verification above caller-ID matching, SMS / OTP,
rescheduling and cancelling by phone, payments, multi-salon routing, shared (multi-process) rate limiting
and production monitoring.
