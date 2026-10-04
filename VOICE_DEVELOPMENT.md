# Read-only AI phone receptionist development

## Implemented protocol

The server uses the Twilio Python SDK 9.x request validator/TwiML builder with current Programmable
Voice webhooks and bidirectional `<Connect><Stream>` Media Streams. It connects directly to OpenAI's
GA Realtime WebSocket API at `wss://api.openai.com/v1/realtime` (no deprecated beta header), with the
model selected by `OPENAI_REALTIME_MODEL` and defaulting to the current `gpt-realtime-2.1`. The
session uses `audio/pcmu` for input and output.

Twilio sends base64-encoded `audio/x-mulaw`, 8 kHz, mono bytes. Those bytes are forwarded unchanged
to OpenAI as `input_audio_buffer.append`. OpenAI `response.output_audio.delta` PCMU bytes are sent
unchanged to Twilio `media` messages. There is no transcoding or resampling.

## Local setup

1. Install `backend/requirements.txt` and run the owner FastAPI backend.
2. Create a secure HTTPS/WSS tunnel to that backend. `localhost` is not reachable by Twilio.
3. Set `PUBLIC_BASE_URL` to the public HTTPS origin only (no trailing slash).
4. Configure the Twilio number's incoming voice webhook as an HTTP `POST` to
   `${PUBLIC_BASE_URL}/voice/twilio/incoming`.
5. Configure call status callbacks as HTTP `POST` to `${PUBLIC_BASE_URL}/voice/twilio/status`.
   The generated TwiML also uses this route for stream lifecycle callbacks.
6. Set the Twilio/OpenAI variables documented in `.env.example`.
7. Enable `VOICE_ENABLED=true` and `VOICE_ALLOW_REAL_CALLS=true` only for an intentional private
   test. Leave both false otherwise.

The app derives the `wss://.../voice/twilio/media` URL from `PUBLIC_BASE_URL`; tunnel-provider details
are not part of the business logic. The URL used to compute Twilio signatures must exactly match the
public webhook URL, so proxy-local scheme/host values are deliberately ignored.

## Safe test flow

The automated suite signs simulated Twilio forms with a test token and uses fake media/OpenAI
connections. It never places a paid call and never sends data to OpenAI. Before a private test call,
also verify the tunnel's TLS certificate, Twilio webhook error logs, environment isolation, spend
limits, and owner failure notifications.

## Repair-pass behavior (read before a private test call)

- Past start times are rejected by the booking domain (create, reschedule) and never offered as slots,
  using the salon (America/Phoenix) clock.
- Anonymous, blocked, or non-US caller IDs still receive valid TwiML. The call has **no trusted phone**;
  customer lookup reports "no match", and a callback requires the caller to *say* a number. A spoken
  number is stored only as an untrusted contact detail (`phone_source: spoken_by_caller`).
- Exactly one owner callback is recorded per call; deduplication is server-owned, not model-chosen.
- `identify_customer_candidate` returns only `{"matched": true|false}` (caller ID is spoofable).
- A finished (completed/failed) call can never be reopened by a late media stream.
- OpenAI Realtime `error` events: errors caused by our best-effort truncate, or on a short allow-list,
  are audited (`provider_error` event) and the call continues; auth/quota/server/unknown errors end the
  call (fail closed). More than 10 recoverable errors in one call also ends it.

## DEVELOPMENT / UNCONFIRMED salon data

The salon name ("Nail Salon"), business hours (Mon-Sat 09:00-18:00), service list, durations, buffers
and technician eligibility seeded by `booking_migrations.py` are development placeholders, **not
confirmed by the owner**. Prices are NULL (unknown) and the assistant says so. Review all of it before
a real salon pilot.

## Current limitations

This phase is read-only. It cannot create, reschedule, cancel, or reveal an appointment. Caller ID is
only a candidate match, not authentication. Level-2 verification, OTP/SMS, recording, transcript
persistence, payments, multi-salon routing, shared distributed rate limiting, and production
operational monitoring remain out of scope.
