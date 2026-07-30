# 60-RUNBOOK-CAP-EXHAUSTION.md — what actually happens when a tenant hits a cap

P8-T03. Written from the real code (`control_plane/mint.py`, `sdk/src/index.ts`), not from
memory of the design — every claim below is a line reference, not a guess.

## 1. What can be "the cap"

Three independent limits, checked in this order inside `mint_session()`
(`control_plane/mint.py` lines 121-130), all AFTER the request has already passed HMAC/replay/
nonce/tenant-active/IDOR/origin checks:

1. **Rate limit** — `control_plane/app.py::_rate_limited()`, `RATE_LIMIT_PER_MIN = 120`
   requests/tenant/minute (confirmed as the deliberate value, ADR-023). Checked BEFORE the mint
   even runs (`app.py` line 67), so this is the first gate a request can fail.
2. **Concurrent cap** — `tenants.max_concurrent` vs `quota_state.concurrent_now`
   (`mint.py` line 127).
3. **Monthly minutes cap** — `tenants.max_minutes_month` vs `quota_state.minutes_this_month`
   (`mint.py` line 129).

**All three return HTTP 429.** The response body differs server-side (`{"error": "rate
limited"}` vs `{"error": "concurrent cap reached"}` vs `{"error": "monthly minutes cap
reached"}` — see `app.py` line 69 and the `MintError` reasons raised at `mint.py` lines 128/130),
but **the client SDK does not distinguish them** — see §3.

## 2. Does it queue or fail?

**It fails. There is no queue, anywhere in this system, at any layer.**

- The control plane (`control_plane/app.py`) returns 429 synchronously and immediately — no
  retry-after header, no background queueing, no "try again in N seconds" mechanism. Confirmed by
  reading the full route handler (`app.py::create_session`, lines 58-83): every branch either
  returns a response or raises within the same request, nothing defers work.
- The worker (`worker/`) is never even reached in a cap-exhaustion case — the mint rejects the
  request before a LiveKit token exists, so no job is ever dispatched.
- The client SDK (`sdk/src/index.ts::connect()`) makes exactly one `fetch()` call to the host's
  `sessionEndpoint`, checks the status code once, and either succeeds or throws. **No retry loop,
  no backoff, no queueing exists in the SDK itself** (confirmed: `connect()`, lines 71-126, has
  no loop, no `setTimeout`, no retry counter of any kind).

**Practical consequence for an integrator:** if a host platform wants "queue the caller and
retry," they have to build it themselves, calling `sdk.connect()` again later. Nothing in this
system does it for them. This is worth stating plainly in whatever integration docs eventually
ship — a naive integration will show the caller an immediate failure with no automatic recovery.

## 3. What does the SDK show?

Exactly one of these is thrown by `await sdk.connect({ agentId })` (never emitted as an event —
these are Promise rejections the caller's own `try/catch` must handle):

| Server condition | HTTP status | `AwaazLabsUvaVoiceError.code` | Notes |
|---|---|---|---|
| Rate limit (120/tenant/min) | 429 | `quota_exceeded` | **Indistinguishable from the two below** |
| Concurrent cap reached | 429 | `quota_exceeded` | **Indistinguishable from the other two** |
| Monthly minutes cap reached | 429 | `quota_exceeded` | **Indistinguishable from the other two** |
| Agent doesn't belong to tenant / doesn't exist | 404 | `agent_not_found` | |
| Any other non-2xx from `sessionEndpoint` | any | `session_failed` | |
| Network/JSON failure reaching `sessionEndpoint` | — | `session_failed` | raw error dropped, never leaked (`sdk/src/index.ts` line 104) |
| LiveKit `room.connect()` itself fails (token was valid, WebRTC failed) | — | `session_failed` | e.g. LiveKit's own concurrency enforcement, if any — see §4 |
| Mic permission denied/unavailable | — | `session_failed` | room is disconnected first, then thrown (line 121-122) |

**🔴 Real, current limitation, not a bug:** a host platform's integration code CANNOT currently
tell "you're rate-limited, retry in a few seconds" apart from "you're out of concurrent slots for
the rest of this call" apart from "you're out of minutes until next month" — all three collapse
to the same `quota_exceeded` code client-side. `sdk/src/index.ts` would need to forward the
server's actual JSON body (or a more specific error taxonomy) for an integrator to build a smart
retry UI (e.g., "retry in 5s" vs. "you're out of minutes, contact support"). Not fixed here —
flagged for whoever builds real host-platform integration UX next.

## 4. What about LiveKit's own cap (not our token mint's)?

If a request GETS a token (passed all our checks) but LiveKit itself is at its own concurrency
limit, that would surface as a `room.connect()` failure → `AwaazLabsUvaVoiceError('session_failed', 'LiveKit
connection failed')` (same generic code as any other WebRTC failure — LiveKit's specific
rejection reason is not threaded through). **Whether this can actually happen is unresolved**:
ADR-014 (3 separate live tests) and P8-T01 (a 4th, today) have never once reproduced LiveKit
Build's documented "5 concurrent" cap up to n=6 real connections — see ADR-024. So in practice,
this path has never been observed to fire; it's documented here because the code exists to handle
it, not because it's been seen live.

## 5. What SHOULD an integrator's UI do, given the above?

Not prescribed by this codebase (no reference host-platform integration exists yet) — but given
§2 and §3's real constraints, a reasonable minimum:

- Treat `quota_exceeded` as "this specific agent/tenant is at capacity right now" and show a
  generic "please try again shortly" message — NOT a hard failure state, since it's frequently
  transient (rate limit resets every 60s, a concurrent slot frees when another call ends).
  Cannot currently distinguish "retry in 5s" from "retry next month" — build for the worse case
  (assume it could be either) until the SDK exposes more detail.
- Treat `agent_not_found` as a configuration error (wrong `agentId`, or the agent was deleted/
  disabled) — not something the end user can fix by retrying.
- Treat `session_failed` as a generic connectivity failure — retry is reasonable, but there's no
  guarantee it's transient (could be a real outage).
- **Do not build automatic infinite-retry loops** against `quota_exceeded` — the rate-limit case
  specifically will keep re-triggering the SAME rate limit if retried too fast (120/min is
  per-tenant, not per-request; a tight retry loop would just keep consuming that budget).

## Evidence

`control_plane/mint.py` lines 121-130 (the three cap checks, in order); `control_plane/app.py`
lines 48-83 (rate limiter + route handler, no queueing anywhere); `sdk/src/index.ts` lines 71-126
(`connect()`, full method, no retry/queue logic); `tests/test_mint.py`
(`test_over_concurrent_cap_429`, `test_over_monthly_minutes_429`, both re-verified fresh this
session); `scripts/verify_rate_limit_live.py` (real live rate-limit test, ADR-023); ADR-014 +
P8-T01 (LiveKit's own cap never reproduced, §4).
