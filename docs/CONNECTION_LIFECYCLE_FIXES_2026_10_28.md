# Connection lifecycle implementation and verification

This working-tree change follows `CONNECTION_LIFECYCLE_AUDIT_2026_10_27.md`.
It covers browser SDK sessions, the shared voice worker, inbound/outbound phone calls,
admission/settlement, the dashboard, and the demo in `client-integration-test`.
No npm release, deployment, existing phone-route change, or test phone call was made.

## Agreed policy and public contract

- Configure `maxCallDurationSeconds` on agent create/update in the Agents SDK.
  The HTTP/database name is `max_call_duration_seconds`. Default: 1800 seconds;
  allowed range: 60–7200 whole seconds. API PATCH omission preserves the saved
  value; API null resets the default. SDK callers can reset by sending 1800.
- The saved setting applies to new web, inbound, and outbound calls. An active
  call retains its initial setting. Its timer starts after STT establishment and
  caller presence; SIP must be active/answered. Reconnect does not reset the timer.
- At the limit, notify `max_duration_reached` and terminate the session/room.
  Orphan cleanup is independent of this duration setting.
- Provider errors, exhausted quota/rate limits, and exhausted connection/progress
  budgets terminate promptly with a classified failure. No automatic provider
  substitution or long outage-recovery window was added. A vendor outage, rejected
  credential, or unavailable account cannot be made to succeed by SDK code.
- Mint and refresh expose optional `sessionId`. Host proxies should preserve it.
  The browser accepts worker lifecycle/metrics packets only from agent participants
  and checks the session ID when supplied by mint.
- Browser `connect()` waits for room join, microphone enablement, and the worker's
  STT-ready packet. Default worker-ready wait: 30 seconds (`agentReadyTimeoutMs`).
  Browser autoplay remains separately observable through `audio_ready`/`audio_blocked`.
- New browser events: `connection_state_changed` (including `reconnecting`) and
  `session_outcome`. Existing `ended`/`disconnected` events retain terminal reasons.
- Agents/Telephony SDK HTTP operations have `requestTimeoutMs` (default 15000),
  covering response bodies. The demo preserves its 120-second telephony operation
  budget and combines the SDK abort signal with its shorter read deadlines.

```ts
await agents.updateAgent(agentId, { maxCallDurationSeconds: 1800 });
```

## Finding-by-finding implementation

| Audit finding | Change and source boundary |
|---|---|
| F01 simultaneous connects | `sdk/src/index.ts`: room ownership and single-flight guard before mint. |
| F02 cancelled startup | Generation/abort ownership through mint, room join, mic permission and readiness; late tracks are disabled. Late `setMicMuted(false)` is guarded too. |
| F03 old refresh corrupts new call | Room/generation/token-bound refresh, aborted on disconnect, same-room/session validation and bounded total wait. |
| F04 premature connected | Authenticated worker readiness after real STT handshake; bounded microphone and readiness waits. Autoplay is a separate state. |
| F05 hidden reconnection | Public reconnecting/reconnected state and dashboard/demo display. |
| F06 body/auth hangs | `sdk/src/internal/http.ts`: operation deadline includes async host headers and response body. |
| F07 backend SDK hangs | Agents/Telephony SDK request deadlines and demo propagation of cancellation. |
| F08 setup bypasses finalization | Outer worker lifecycle/shutdown callback registered before connecting/building, including startup metrics/usage and partial-provider ownership. |
| F09 dispatch rollback/stale races | Conditional transactional rollback, retained shared dispatch client, bounded dispatch/room compensation even if rollback fails; persisted stale-job validation always runs. |
| F10 DB/admission waits | Checkout deadlines, transaction-local statement/lock timeouts, shared tenant quota lock, pool replacement-capacity recovery. |
| F11 Gladia connection budget | Session-init REST and WS upgrade share one attempt budget; HTTP status and retryability survive. |
| F12 STT transport loss | Gladia unexpected receive-end/error propagation, WS heartbeat, Deepgram handshake reporting and metering wrapper. Silence itself does not trigger failure. A live socket whose recognizer silently stops producing results is still not proven healthy; see limits below. |
| F13 false warm readiness | Groq synchronous hook owns its task/client; prewarm reports unsupported/hook-completed separately from readiness, and inherited LLM no-op warm hooks are recognized. Cancelled prewarm joins child tasks. |
| F14 Uplift handshake races | One locked Socket.IO connection; explicit application-ready event and five-second deadline; no transport-only fake readiness. |
| F15 Uplift partial-error success | Error-aware queues preserve 402/429 and disconnect failures after partial audio. Cancellation clears maps and closes the owned socket; next request reconnects. |
| F16 conflicting deadlines | Effective STT/LLM/TTS deadlines and useful-output watchdog are reflected in telemetry; provider stream close is bounded. |
| F17 unowned providers/warm work | All baseline provider instances and warm tasks are session-owned; partial construction is owned immediately. Shared greeting cache retains PCM rather than borrowing another call's transport. |
| F18 age cleanup ends healthy calls | Worker lease every 20 seconds; cleanup requires expired lease and confirmed absence of a worker. Unknown LiveKit presence preserves the row. Shared agent limit replaces fixed age as normal termination policy. |
| F19 lost failure/reason | Idempotent retained failure task publishes before shutdown, classifies quota failures, retains reason and deletes the room with a bounded request. |
| F20 partial settlement | Close, quota, usage, transcript and finalization marker share one transaction. Private durable payloads retry failed settlement; ended-but-unsettled rows can resume without a second quota decrement. |
| F21 outbound effects before records | Session/call/quota/idempotency attempt committed before dispatch/dial. Ambiguous failure retains the key, compensates the known room and records a failed cached response. |
| F22 lost SIP status | Ordered retained write tasks; rank/answered/finalized state advances after DB success; bounded retries and close-time join. |
| F23 untracked inbound | Quota, persistence and commit failures reject setup. Metadata-only resolution does not reserve a slot. |
| F24 blocking shutdown I/O | DB/file/storage settlement work moves off the event loop; recording DB statements and storage requests have explicit timeouts; recorder close is bounded. |
| F25 teardown usage loss | Provider listeners remain through provider close. Direct STT metering flushes tail usage even after the framework event channel closes. Final usage snapshot precedes settlement. |
| F26 mismatched session IDs | Database UUID carried through JWT, dispatch, host proxy, worker telemetry and lifecycle packets. |
| F27 lifecycle evidence | Persist attempted/ready/end/elapsed/close/finalization state and deployed revision provenance. Existing transport diagnostics remain honest about unavailable RTT/jitter/loss. Fleet reliability rates and live measurements are not fabricated. |
| F28 unauthenticated metrics | Agent-sender check, session correlation, safe sequence validation/deduplication; room metadata is not accepted as authoritative metrics. |
| F29 unsettled usage/rollover | Browser/phone admission and ongoing enforcement include active elapsed minutes and reset stale monthly quota periods. Settlement attributes only elapsed time within the current month to its current-month counter. |
| F30 consumer drift | Dashboard and demo install independently built local tarball snapshots with integrity checks, rather than source-directory links or old registry code. |

The shared ownership/failure/settlement path covers Gladia and Deepgram (Nova/Flux),
Gemini/Groq/Anthropic, and Uplift/Cartesia/ElevenLabs/Rime. Existing model-selection,
Claude caching/effort, audio-format and business-tool policies were preserved.

## Database and rollout

Migration: `supabase/migrations/20261028095529_connection_lifecycle.sql`.
It adds the agent duration, session lease, lifecycle JSON and finalization marker,
plus an open-session lease index. It changes no grants or RLS policies.

The user applied the migration. A subsequent read-only query using the configured
database connection verified all four columns, the validated 60–7200 constraint,
the 1800 default, and the lease index. An isolated PGlite PostgreSQL run additionally
executed the migration, checked valid/invalid durations, parsed eleven source SQL
statements, exercised active-minute calculation and the resumable-settlement guard.
That does not prove hosted lock contention or transaction-pool behavior under load.

Deploy matching APIs and worker before the browser snapshot. The old hosted agent
list currently omits the new duration field, so the applied schema alone does not
establish deployment of this source. Old workers do not emit the readiness packet
required by the new browser build.

Set `WORKER_FINALIZATION_DIR` to **private persistent worker storage**. Pending JSON
contains transcripts and usage. It must survive process/container replacement and
follow the session-data access/retention policy. The default workspace state path
is ignored by git. The parent retries pending payloads every 30 seconds, and jobs
also attempt replay. Ephemeral disk cannot provide restart durability.

Set `WORKER_REVISION` to the actual deployment revision. Worker process readiness
does not claim every provider's credentials/entitlements have been tested.

Consumers use the artifacts and hashes listed in
`client-integration-test/packages/lifecycle-manifest.json`. They are unpublished
working-tree snapshots; the internal package versions are not a new npm release.
If SDK source changes again, rebuild/repack and regenerate the manifest and
consumer locks before deployment. Existing historical snapshots were preserved.

## Verification completed

- Browser SDK: **44 passed**, plus TypeScript build.
- Agents SDK: **20 passed**, including duration serialization/validation and a hung response body.
- Telephony SDK: phase-8 smoke, phase-9 contract and signing compatibility checks passed.
- Affected Python suite: **374 passed, 4 skipped** at its broad checkpoint.
- Follow-up contract/lifecycle suite: **43 passed**; a subsequent final lifecycle
  run including the ambiguous-outbound regression: **24 passed**. These overlap;
  they must not be added together as independent coverage.
- Focused phone/settlement follow-up: **73 passed** before the additional
  idempotency-response assertion.
- Release/deploy-script checks: **21 passed**.
- Recording policy/upload/handler regression checks: **21 passed** after the
  explicit recording storage/DB/recorder timeout changes.
- Demo: **40 backend tests**, **27 frontend tests**, frontend typecheck/build and
  installed-package independence/integrity checks passed.
- Dashboard TypeScript check passed after the duration display/docs update.
- Ruff undefined-name/local checks passed; whitespace review uses CRLF-aware git settings.
- Python tests run with the isolated workspace Python 3.12.10 and existing 3.12
  dependencies. No system interpreter or user-managed worker was replaced.

The full offline Python run was **1523 passed, 30 failed, 133 skipped, 3 deselected**.
Three of those failures were subsequently corrected and verified in the focused
contract checks (refresh session-ID shape, monthly-query mock and isolated mint
rejection auditing). The full suite was not rerun after that checkpoint. Remaining
failures include DB-dependent tests that exit when the offline DB URL is deliberately
blank, an environment-sensitive Flux default test, existing documentation version
pins, and duplicate SDK source found in unrelated local handoff directories.
This is **not** a fully green repository-wide suite.

Staging read-only checks passed for provider capabilities, agents, call history and
managed numbers through the demo's actual installed SDK factories. Initial HTTP
502 responses cleared after portal warm-up; one control-plane health request timed
out. Those observations do not validate a new voice connection.

A temporary separately named worker registered successfully with LiveKit using
the repaired runtime. It accepted no test calls and was stopped afterward. No
existing worker/process or phone assignment was changed.

## Live evidence still required

The computer-use tool stopped browser automation because it could not confidently
identify Chrome's current URL. No further browser interaction was attempted. No
browser microphone/audible-playback, inbound phone, or authorized outbound test
call was completed. The supplied test destination was not dialled.

After matching source is deployed, verify every selectable provider with real
credentials, repeated turns, silence/mute, transport loss, quota exhaustion and
normal/error teardown. Verify the actual SIP leg ends and records/usage finalize.
No SDK can infer a recognizer's semantic health solely from a live WebSocket, or
promise that a provider will never reject/fail a connection. Transport heartbeats
do not prove accurate transcription, and provider audio is not caller-heard proof.

Actual network RTT/jitter/loss, fleet establishment/failure rates, long-duration
resource counts, monthly rollover under load, durable-volume restart replay and
storage failure behavior remain live/operational acceptance items. Metrics that
are unavailable remain unknown rather than estimated as successful measurements.

`graphify update .` was attempted after changes but failed with
`uv trampoline failed to canonicalize script path`; no graph refresh is claimed.
The original unrelated document deletions and usage-ledger change were preserved.
