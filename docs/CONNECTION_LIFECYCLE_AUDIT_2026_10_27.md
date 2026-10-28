# SDK connection lifecycle audit — 2026-10-27

Audit base: `1d2a20c6c5aeaa7495aa16080bb8c13dba39fa62`.

**Conclusion:** the normal connection and hangup paths exist, but the SDK does not yet provide a dependable end-to-end contract for “established”, “still operational”, or “successfully finalized”. Several failure paths can leave an apparently connected browser, lose the real failure reason, abandon provider work, or leave incomplete accounting. This is a source audit, not a claim that every deployment or provider currently fails.

No runtime code, configuration, dependencies, database records, or deployments were changed. This report is the only added repository artifact. Existing deletions and the modified usage ledger were preserved.

## Scope, evidence, and agreed behavior

- Reviewed the actual lifecycle branches in the browser SDK, control plane, worker, selectable provider adapters, installed LiveKit implementations, telephony orchestration/status/cleanup, session persistence, usage, recording shutdown, and reference host endpoints. Tests were consulted as context, not used as the authority for behavior.
- Browser SDK source is version `1.1.1`; its locally installed `livekit-client` is `2.20.1`. Local Python package metadata identifies LiveKit Agents and the relevant provider plugins as `1.6.5`, and RTC as `1.1.13`. Installed dependency source was inspected directly. These are local observations, not deployed-version verification.
- Used official provider/framework documentation where wire contracts mattered. The local installed implementation takes precedence when determining what this checkout actually executes.
- Ran an in-memory JavaScript harness against the current TypeScript source with fake rooms and fake fetch responses. It reproduced parallel connection leakage, ineffective cancellation during minting, cross-session refresh corruption, and the response-body timeout gap. No provider, microphone, carrier, or database was contacted by this harness.
- No live calls, provider syntheses/completions, DB queries, worker restarts, or reconciler executions were performed. No repository test suite was run. The local Python launcher cannot start because its configured Python 3.12 executable is missing; the `python3.11` shim also fails to spawn. Python behavior below is established from source, not an executed Python integration check.
- The root has no `graphify-out/graph.json`. A graph was discovered in the separate nested `self-serve-demo-UI` checkout; its scoped query was attempted and failed with `uv trampoline failed to canonicalize script path`. That graph was not treated as current evidence.
- **User decision:** provider outages should **end promptly with a clear failure**, rather than hold the call open for extended recovery. Therefore lack of provider fallback or long retry loops is not itself a defect in this audit. The issues are reliable detection, truthful classification, clear notification, complete disconnection, and finalization.
- **Duration proposal discussed with the user:** an optional agent create/update setting such as `maxCallDurationSeconds`, bounded by a platform ceiling, with a documented platform default when omitted. This is a proposal, not an implemented or finalized API. No numerical default was assumed. Orphan detection must be separate from intentional maximum duration.

Severity: **P1** = can strand/drop a session, misrepresent success/failure, or materially corrupt lifecycle/accounting; **P2** = important observability, resource-management, compatibility, or operational weakness. Findings describe deterministic code behavior or a concrete failure interleaving; their incidence in production is unmeasured.

## Actual provider coverage

Authority: `worker/providers/capabilities.py:106`, `worker/providers/registry.py:26`.

| Layer/provider | Selectable languages | Establishment and continuity path reviewed | Ending/cleanup assessment |
|---|---|---|---|
| STT / Gladia | Urdu, English | REST session initialization then continuous WebSocket; provider-specific stream loop | Unbounded-by-policy handshake/read paths and silent remote-close handling: F11–F12. No active audio-vs-transcription watchdog. |
| STT / Deepgram Nova-3 | English | WebSocket, continuous audio, 5-second application keepalive, unexpected-close error and one configured stream retry | Better explicit remote-close handling; final metrics can be detached before stream cleanup (F25). Recovery consumes a stream-lifetime retry allowance. |
| STT / Deepgram Flux | English, opt-in mode | `STTv2`, WebSocket with 30-second heartbeat, turn events; separate implementation inspected | No application KeepAlive task in this pinned v2 branch. Do not assume Nova's idle behavior applies. Muting/no-frame continuity needs direct verification (F12). |
| LLM / Gemini | Urdu, English | Google streaming HTTP; adapter HTTP timeout 30 seconds, useful-output watchdog 6 seconds | Fail-fast applies; no persistent conversation socket is required. Generic inherited prewarm is a no-op; model readiness is not demonstrated by warm logs (F13). |
| LLM / Groq | English | OpenAI-compatible streamed HTTP, owned HTTP pool, token-free models-list prewarm | Fail-fast applies; no Retry-After recovery is required under the user's chosen policy. Async prewarm signature conflicts with LiveKit's synchronous hook (F13); owned client cleanup is missing from baseline ownership (F17). |
| LLM / Anthropic | Urdu, English | Owned HTTP client; synchronous prewarm hook returns an owned task; streamed messages | Fail-fast applies. Per-request plugin timeout uses session options, so the 30-second client setting is not the effective voice request timeout (F16). Baseline cleanup ownership gap applies (F17). |
| TTS / Uplift | Urdu | Fixture by default; explicit live/record uses persistent Socket.IO, request IDs, reconnect enabled | Handshake races/readiness, partial-error completion, cancellation and cleanup gaps: F14–F17. |
| TTS / Cartesia | English | HTTP for cached/static synthesis; pooled WebSocket for streaming; custom interruption transport warm hook | Cancellation evicts pooled sockets; deferred socket reaping and missing baseline `aclose` ownership matter (F17). Opening cache success does not establish later live provider readiness. |
| TTS / ElevenLabs | English | HTTP synth plus shared multi-context WebSocket; lock protects current-connection creation; closed connection can be replaced | Plugin cleanup exists but baseline ownership is missing (F17). Actual inactivity constant is 180 seconds, within the current documented limit; the plugin docstring's 300 is stale. No separate active handshake-parameter defect was found. |
| TTS / Rime | English | HTTP synth plus pooled WebSocket; model/speaker/channel options resolved by adapter | Pool invalidates failed/cancelled sockets; baseline close/eviction ownership missing (F17). No custom interruption prewarm hook; this alone is not a continuity bug because next synthesis can acquire a new socket. |

The capability matrix permits **18 English provider-level combinations** (2 STT × 3 LLM × 3 TTS) and **2 Urdu combinations** (Gladia × Gemini/Anthropic × Uplift), before model, voice, transport, and feature-mode variants. Shared-path review covers their common code; this does not mean those combinations were live-tested.

Fish Audio TTS and Soniox STT have legacy adapter files but are absent from the selectable registry/capability matrix. `worker/factories.py` retains a script-only Soniox branch. Installing a Fish Audio plugin does not make it selectable. Neither should be advertised as audited live support.

## Lifecycle traced

1. Browser calls its host `sessionEndpoint`; the control plane validates HMAC/replay/origin/tenant/agent/quota, commits a session and increments concurrency.
2. Control plane schedules an asynchronous named LiveKit agent dispatch and returns a room token without worker/provider readiness acknowledgement.
3. Browser joins LiveKit, emits `connected`, completes microphone setup, reports playback permission, and schedules host-token refresh.
4. Worker connects to LiveKit while loading configuration/building provider objects. It resolves identity from dispatch, DB, or participant/SIP metadata, starts `AgentSession`, and opens the greeting path.
5. STT has a long-running media stream. LLM uses per-response HTTP streams. TTS uses HTTP or provider-specific WebSockets/contexts. Their transport lifetimes are different; “all three sockets stay connected” is not a valid universal requirement.
6. Normal agent ending validates the current caller turn and interruption state, attempts summary persistence, waits for closing playout, calls `shutdown(drain=True)`, and deletes the room. Provider failure calls `shutdown(drain=False)`.
7. Session-close handlers stop the job; shutdown callbacks write the terminal session, release quota, attach transcript, settle usage, and upload an eligible recording. Scheduled reconcilers repair some missed work.

## Findings

### F01 — P1: `connect()` has no single-flight guard

**Source:** `sdk/src/index.ts:267–280,357–359`.

The guard checks `this.room`, which remains null through mint and room join. Two simultaneous calls both pass and mint/join independently. The later assignment replaces the first room reference, so normal `disconnect()` can close only one of them. Shared event handlers can continue delivering both rooms' events.

**Observed offline:** `parallel_connect_mints=2`, `parallel_connect_unowned_open_rooms=1`.

**Required improvement:** one owned connection attempt, with a generation/attempt identity checked at every asynchronous boundary.

### F02 — P1: disconnecting during establishment does not cancel establishment

**Source:** `sdk/src/index.ts:282–339,357–380,396–406`.

Until `this.room` is assigned, `disconnect()` just clears local state and returns. It does not cancel the pending mint, close the local room created inside `connect`, or invalidate the attempt. The outstanding operation can subsequently become connected after the host has ended it. Late microphone acquisition also lacks a common finally/attempt cleanup path.

**Observed offline:** calling disconnect while mint was pending still ended in `connectionState=connected` after the fake response arrived.

**Required improvement:** cancellation must own the in-progress fetch, room, microphone acquisition, and any successfully minted server session.

### F03 — P1: an old refresh can overwrite or terminate a new session

**Source:** `sdk/src/index.ts:648–753`.

The refresh loop reads and mutates mutable `this.room`/`this.session` across awaits without capturing and revalidating the original room/session. Disconnect plus reconnect during the old fetch lets the old response replace the new session and write the old room's token into the new room's engine. An old 401/403 can likewise call `disconnect()` on the new call. Global `refreshInFlight` can also suppress a new call's refresh while old work remains pending.

**Observed offline:** after a fresh connection, resolving the prior refresh produced `sessionRoom=old-refreshed` and `engineToken=fake-old-refreshed` on the new room.

**Required improvement:** scope refresh, retry, timer, token application, and terminal failure to a captured session generation; cancel old work on close.

### F04 — P1: public “connected” is earlier than usable audio and does not prove agent establishment

**Source:** `sdk/src/index.ts:355–380,461–465`; `control_plane/app.py:862–879`; `worker/main.py:1479–1485`.

The SDK emits `connected` before awaiting microphone setup. A microphone prompt can remain unresolved with the SDK already reporting connected. The room join can also succeed when dispatch later fails, no worker accepts it, configuration construction crashes, or no provider can process a turn. The SDK has no agent-ready handshake/deadline and does not monitor agent participant departure as a distinct failure.

The microphone promise is not time-bounded or cancellable by the SDK. Clearing the early room reference issue in F02 alone would not settle a pending browser permission prompt safely.

**Required improvement:** distinguish room transport, microphone publication, agent initialization, and operational readiness; time-bound the attempt and report a terminal reason if the agent never becomes ready. A models-list request or cached greeting is not proof the conversational path works.

### F05 — P2: temporary reconnection is invisible through the public lifecycle

**Source:** `sdk/src/index.ts:77,239–248,461–562`; installed `sdk/node_modules/livekit-client/src/room/Room.ts:617–642,1786`.

LiveKit emits signal/full reconnect and reconnected events, but the wrapper exposes none and keeps its state as connected until terminal disconnection. `isConnected`/audio readiness therefore cannot distinguish normal operation from an ongoing outage. Connection-quality changes update a stored timing object without emitting a quality event.

**Required improvement:** observable reconnecting/reconnected transitions, attempt/outage duration, failure classification, and readiness invalidation/restoration.

### F06 — P1: browser fetch timeout ends at response headers

**Source:** `sdk/src/internal/http.ts:12–35`; `sdk/src/index.ts:309–317,688–695`.

`fetchWithTimeout` clears its timer when `fetch()` returns the Response. Subsequent `json()`/`text()` reads occur outside that timer. A response that sends headers but stalls its body can hang mint or refresh indefinitely. Async `sessionHeaders()` is outside the fetch timer too.

**Observed offline:** after immediate headers and waiting past the configured deadline, the captured abort signal remained un-aborted. A pending JSON body would remain pending.

**Required improvement:** a full-operation deadline covering headers, body, validation, and bounded host-auth preparation; refresh requests must also respect remaining token-policy time.

### F07 — P2: backend SDK/reference HTTP operations have no explicit operation deadline

**Source:** `sdk-server/src/index.ts:291–338`; `telephony/src/index.ts:242–264`; `client-integration-test/backend/src/createApp.js:428–433,493–498`.

Agent management, outbound-call initiation/status, and reference-host mint/refresh use fetch without an SDK-owned timeout or abort signal. Runtime defaults are not an explicit SDK deadline. A browser timing out does not cancel the host's outstanding mint. Non-idempotent mint can finish after the caller has retried.

**Required improvement:** bounded operations and propagation of cancellation, preserving “external outcome unknown” for outbound side effects. Do not blindly retry dialing.

### F08 — P1: setup failures occur before session finalization is registered

**Source:** `worker/main.py:1271–1295,1337–1380,1506–1551,1588–1609`; installed `livekit/agents/ipc/job_proc_lazy_main.py:354–365`.

Config read, provider construction, snapshot creation, VAD/agent construction, and caller binding can fail before `_setup_and_start` registers the quota/session callbacks. LiveKit does shut down a crashed job, but application finalization callbacks that were never registered cannot run. The dispatch watcher sees successful dispatch creation, not this later startup failure. Without started RoomIO there is no guaranteed application room deletion or browser failure packet.

**Required improvement:** register minimal attempt cleanup immediately after identity/reservation is known; wrap the whole setup in a failure boundary, publishing a classified initialization failure and cleaning all partial resources.

### F09 — P1: dispatch acknowledgement, rollback, and stale-job logic are not one lifecycle

**Source:** `control_plane/app.py:696–704,739–821,862–879`; `worker/main.py:1308–1310`; `worker/stale_jobs.py:223–244`.

HTTP success means dispatch was scheduled, not that a worker accepted or became operational. A dispatch timeout is ambiguous: the server may have created it even if its response was lost. The watcher cancels its future and updates DB/quota but does not delete the dispatch/room or notify a joined browser.

Rollback decrements concurrency unconditionally even if its `UPDATE ... ended_at is null` updated no row. A worker close followed by a late watcher rollback can release another active session's slot. The writes are separate autocommit statements.

Also, any parseable dispatch identity sets `skip_db=True`. Metadata presence is not proof the queued job is fresh; a delayed job can run after rollback/closure without consulting the terminal session row.

Dispatch requests share one client/session. A failure or cancellation in one `_dispatch_agent` calls `_reset_dispatch_client`, closing that shared session even if another dispatch is still using it. Concurrent otherwise-healthy attempts can therefore inherit a transport failure from the first attempt.

**Required improvement:** durable attempt state and idempotent compensation tied to the reservation, explicit worker-ready/failure signalling, and freshness validation independent of metadata presence.

### F10 — P1: admission and database waits can violate connection bounds

**Source:** `control_plane/mint.py:90–99,183–229`; `control_plane/mint_db.py:58–95`; `worker/db_pool.py:60–135`; `tenant_portal_api/telephony_queries.py:274–334`; `tenant_portal_api/telephony_service.py:1216–1250`.

Browser mint reads quota then increments later without the DB row lock/conditional reservation used by telephony. Its process-local mutex does not serialize another control-plane process or the telephony service. Concurrent admissions can both see capacity and exceed it.

Both local “pools” hold an unbounded `threading.Lock` around one process-wide connection. `connect_timeout` does not bound waiting for that mutex or executing SQL on an established connection. There is no application statement/lock timeout in these paths. Telephony holds the quota row transaction lock across external dispatch and SIP calls. A slow external call can consequently block another admission or refresh beyond the browser deadline.

**Required improvement:** common atomic reservation semantics, short DB transactions around state changes, bounded pool checkout/query/lock time, and a deliberate capacity model. This is a source-level race; no live load was run.

### F11 — P1: Gladia does not obey the claimed five-second STT connection budget

**Source:** `worker/provider_retries.py:122–138`; installed `livekit/plugins/gladia/stt.py:862–935`.

The wrapper calculates two 2.45-second attempts plus retry delay and logs a five-second budget. Gladia's streaming REST init instead uses `total=30` with only `sock_connect=2.45`; its subsequent WebSocket connect supplies no matching per-attempt application deadline. The outer STT stream retry loop does not wrap `_run()` in that deadline. A server that accepts TCP/TLS but stalls init can consume much more than five seconds before the retry.

The init method wraps status failures as `APIConnectionError`, so the nearby special `APIStatusError(429)` branch does not reliably receive init rate limits as written.

**Required improvement:** provider-specific bounded initialization covering the complete REST + WS handshake, and preservation of status/error class. Under the agreed policy, report and terminate once the bound expires.

### F12 — P1: STT can stop working while the room remains connected

**Source:** installed `livekit/plugins/gladia/stt.py:886–912,993–1012`; installed `livekit/agents/stt/stt.py:455–494`; `worker/humanization/agent.py:22–56`; `worker/provider_retries.py:146–148`.

Gladia's receive loop exits normally on a remote WebSocket close. `_run()` can then break and return normally, rather than classify an unexpected close and trigger the error/termination path. The generic STT runner returns successfully when `_run()` returns. The custom STT node does not turn unexpected exhaustion into session failure.

There is also no worker distinction between valid idle silence and “audio is arriving/VAD detected speech but transcription transport/results are stalled”. LLM/TTS have a useful-output watchdog; STT has no equivalent input-aware check. This can strand a caller in dead air without activating the intended prompt-failure policy.

Deepgram Nova explicitly raises on unexpected close and sends keepalives. Its configured retry counter is consumed over the stream lifetime, not reset after a healthy connection. Flux has its own implementation and a WS heartbeat but no Nova-style KeepAlive task; muted/no-frame behavior needs a targeted live check. Do not fix this by timing out normal user silence.

**Required improvement:** terminal/error handling for unexpected STT exhaustion and an input-aware STT health contract, with per-provider disconnect diagnostics.

**Conditional dependency concern, not a default-path finding:** Gladia's optional energy-filter/flush branch sends `stop_recording`, which the vendor documents as ending recording and eventually closing the socket. The adapter leaves `energy_filter=False`, so this audit does **not** claim normal default silence executes that branch. See the [official completion contract](https://docs.gladia.io/chapters/live-stt/quickstart).

### F13 — P2: “prewarm finished” often means no connection was verified

**Source:** `worker/latency.py:264–288,418–444,447–491,532–591`; `worker/providers/llm/groq.py:138–149`; installed `livekit/agents/voice/agent_activity.py:635–641`; installed `livekit/agents/llm/llm.py:146–150`.

Generic inherited `prewarm()` hooks are callable no-ops. The LLM helper accepts that hook and returns, so Gemini does not reach the intended fallback warm request. Gladia/Deepgram similarly do not establish their STT streams through the generic inherited hook. Pool-based TTS prewarm schedules its own task and returns before the socket handshake completes, yet the wrapper can log “finished”.

Groq overrides the synchronous LiveKit hook with `async def prewarm`. The explicit wrapper awaits it, but LiveKit's own `self.llm.prewarm()` call does not. That invocation creates an unawaited coroutine. Anthropic's implementation already handles this contract by synchronously returning an owned task.

**Required improvement:** distinguish unsupported/no-op, scheduled, handshake success, failure, timeout, and later synthesis/model readiness; align every adapter with the installed hook contract. This is correctness/diagnostics, not a request to optimize greeting latency.

### F14 — P1: Uplift connection creation is not single-flight and “connected” can precede ready

**Source:** `worker/providers/tts/uplift.py:229–283`; installed `livekit/plugins/upliftai/tts.py:227–279,314–329`.

Explicit warm-up and first synthesis can both enter `WebSocketClient.connect()` while `connected=False`. There is no connection lock/shared connect task. Every invocation replaces `self.sio` with a new Socket.IO client. A prior half-built or reconnecting client is not explicitly retired. The method also sets its own connected flag after five seconds if Socket.IO transport is connected even if the application `ready` message has not arrived.

The adapter's 12-second warm timeout and plugin's 10-second transport wait plus readiness polling differ from the session's five-second connect setting. Failed connect returns False and can leave a partially constructed client, while `disconnect()` only closes it if the custom flag is True.

**Required improvement:** one owned handshake, separate transport/auth/application-ready states, bounded close of partial clients, and one recovery owner.

### F15 — P1: Uplift errors/disconnects can become successful partial synthesis; cancellation leaves server work

**Source:** installed `livekit/plugins/upliftai/tts.py:341–366,398–417,481–531`; `worker/provider_retries.py:189–205`.

`audio_end`, request `error`, and transport disconnect all ultimately put the same `None` sentinel into a request queue. Consumers treat it as ordinary end-of-audio. Once any audio was emitted, the useful-output wrapper considers normal iterator exhaustion successful. Thus partial speech followed by a provider error/disconnect can be reported as complete instead of ending with a clear failure. The plugin's inner 30-second audio timeout also breaks normally, although the worker watchdog usually fires earlier when frames stop.

On interruption/cancellation there is no per-request finally path removing the request maps or sending the documented server `cancel` message. Cancelled local streams can leave generation/queued audio alive until a later server end/disconnect. The transport warm hook does not cancel those requests. The distinct ready/error/end and cancel messages are defined in [Uplift's official protocol](https://docs.upliftai.org/websocket-tts).

**Required improvement:** distinct success/error/cancelled terminal states, explicit exception propagation after partial output, and request cleanup/server cancellation. This concerns connection/resource integrity as well as correct speech outcome.

### F16 — P2: timeout telemetry and effective provider deadlines disagree

**Source:** `worker/providers/llm/anthropic.py:149–171,212–216`; `worker/providers/llm/gemini.py:98–105`; `worker/provider_retries.py:111–148`; `worker/telemetry.py:164–177`; installed `livekit/plugins/anthropic/llm.py:247–265`; installed `livekit/plugins/google/llm.py:480–485`.

Anthropic constructs a client with a 30-second timeout and reports `timeout_seconds=30` in its voice options/snapshot. The installed plugin explicitly supplies `timeout=conn_options.timeout` on each messages request, so the voice request instead receives the session default of 5 seconds. Gemini retains its explicit 30-second HTTP setting even when session options specify 5 seconds. Both also have a separate 6-second useful-output watchdog. A single snapshot field does not describe these different deadlines.

Static greeting synthesis has another boundary: its shared task owns a 6-second lifetime, while the opening waits only 5 seconds and then terminates the session. A synthesis that would finish between those limits is abandoned as an opening failure. This is a deadline-policy inconsistency to decide explicitly, not a request to optimize first-greeting latency.

**Required improvement:** define and report distinct connect, first useful output, inter-chunk idle, total request, and opening deadlines per provider. Ensure the outer lifecycle's failure point matches the intended bounded operation. Fail-fast is valid; inaccurate deadline reporting is not.

**Verified non-finding:** ElevenLabs's installed `WS_INACTIVITY_TIMEOUT` constant at `tts.py:96` is 180 seconds, consistent with the [current vendor limit](https://elevenlabs.io/docs/api-reference/text-to-speech/v-1-text-to-speech-voice-id-multi-stream-input/). Its nearby docstring says 300 but does not control behavior. The adapter does not override the valid constant.

### F17 — P1: baseline provider objects and background warm work lack explicit teardown ownership

**Source:** `worker/provider_client_cache.py:63–67,133–160`; `worker/main.py:1378–1385`; `worker/latency.py:590–605,407–412`; installed `livekit/agents/voice/agent_activity.py:1087–1137`; installed `livekit/agents/utils/connection_pool.py:81–94,147–196`.

The baseline cache removes entries without `aclose()` on eviction or clear. Job shutdown registers application bookkeeping and optional delivery-context close, but not closure of the cached baseline STT/LLM/TTS objects. LiveKit closes activity/streams and detaches plugin listeners; that does not call each baseline provider object's `aclose()`.

This matters for Groq/Anthropic's owned HTTP clients, Uplift's persistent Socket.IO client, ElevenLabs's shared connection, and Cartesia/Rime pools. Pool cancellation marks a socket for deferred close; if it is never borrowed again, explicit pool close is what drains it. The job's shared HTTP-context cleanup is not equivalent to closing custom HTTP/Socket.IO clients and owned tasks.

The scheduled LLM warm task is not retained by `schedule_provider_prewarm`; the greeting wait shields work and there is no general normal-close cancel/join for those tasks. The interruption hook cancels only its own special warm task.

**Required improvement:** define cache/job/session ownership, close or retire on eviction and shutdown, join background tasks, and prohibit reuse of closed clients. The exact externally retained resources depend on runner/process teardown; no production leak rate was measured.

### F18 — P1: age-based reconciliation confuses active calls with dead sessions

**Source:** `scripts/reconcile_sessions.py:71–84,98–183`; `.github/workflows/reconcile.yml:16–17,67–76,90–99`; `tenant_portal_api/telephony_reconcile.py:77–104`; `worker/stale_jobs.py:323–342`.

Scheduled reconciliation applies every 15 minutes by default, with browser stale age 30 minutes. It checks `started_at`, not room presence, worker lease, heartbeat, or recent media activity. It can close a healthy long browser session, zero its stored duration, write an estimated usage event, and release its slot. The next host refresh returns 409; the browser treats that as transient and later disconnects. A subsequent real worker close sees an already-closed session and skips transcript/actual usage finalization.

Telephony reconciliation uses `created_at < now() - 2 hours` despite a comment referring to “without updates”. It can mark a healthy long phone call failed and release quota while media continues; it does not verify/hang up the live SIP leg. The manual orphan-drain helper similarly uses session age and can delete a live room when invoked.

**Required improvement:** separate an explicit agent/platform maximum-duration policy from orphan detection based on live evidence. A maximum-duration event must actually end media, retain true duration/usage, and carry a distinct reason. Deployment/scheduler execution was not checked.

### F19 — P1: provider fail-fast notification and terminal reason are not dependable

**Source:** `worker/provider_retries.py:159–179,222–244`; `worker/main.py:647–652,679–697,1400–1419`; `sdk/src/index.ts:539–549,564–578`.

`fail_session` schedules an unawaited reliable data publish and immediately starts shutdown. Reliable transport does not acknowledge that the host application received/processed the failure before room deletion. Opening TTS, playback, and disclosure failure branches call it without `room`, so they send no failure packet at all.

`shutdown(drain=False)` supplies no error object and uses LiveKit's `user_initiated` close reason. `_on_session_close` persists that generic reason rather than `runtime.failure_outcome`. The SDK error reduces the payload to a stage string; `ended` only receives the room disconnect reason. Telephony `_telephony_end_status` returns completed immediately for any answered call, even one ended by an application/provider failure.

**Required improvement:** one structured terminal outcome, preserved from detection through notification, room deletion, session row, phone status, and SDK `ended`. For PSTN the caller cannot receive a browser data packet; a clear caller-facing failure needs a separately agreed delivery mechanism. No synthesized fallback is currently promised (`spokenFallback=False`).

### F20 — P1: finalization is not atomic or retryable after partial success

**Source:** `worker/session_close.py:167–175,247–298,327–369,450–495`; `worker/stale_jobs.py:125–176`; `tenant_portal_api/telephony_queries.py:337–355`; `scripts/reconcile_sessions.py:98–109,138–183`.

Clean close uses autocommit: mark session ended, release slot, attach transcript, write individual usage rows, mark phone usage recorded, update monthly minutes. If a later stage fails, another normal close sees `ended_at` and skips those extras. The session reconciler's usage backfill runs only for open rows it is closing, so it does not repair all already-closed partial-finalization cases.

Phone quota release first commits `quota_released_at` and then decrements the counter. If decrement fails, retry cannot claim the marker again; the “unreleased” repair query also cannot see it. A later full counter recomputation may repair this, but the ledger itself has falsely recorded successful release. Browser close has the analogous ended-row-before-decrement gap.

Individual usage inserts can partly commit. There is no per-session finalization ledger or per-kind idempotent settlement to resume safely. `usage_recorded_at` is set before the monthly-minute update, so it does not mean all settlement finished.

`finalize_call` also selects status `FOR UPDATE` before issuing a separate transition with no `only_from` condition. On an autocommit worker connection, that select's lock ends before the transition. Two finalizers can both read a nonterminal status, then overwrite each other's terminal outcome. The comment promising terminal preservation is not fully enforced in that connection mode.

**Required improvement:** atomic reservation release and a resumable/idempotent finalization ledger for terminal status, transcript, usage, quota minutes, and recording. “Already ended” must not mean “all side effects succeeded”.

### F21 — P1: outbound dialing occurs before durable call/session records and compensation is incomplete

**Source:** `tenant_portal_api/telephony_service.py:76–88,1223–1253,1270–1332`; `tenant_portal_api/livekit_sip.py:436–461,482–511`; `tenant_portal_api/telephony_queries.py:623–632`.

Agent dispatch and SIP participant creation occur before the session/call inserts and before the transaction commits. A fast failure, answer, or worker shutdown can reach the worker before the row is visible. If dialing succeeds but a DB insert/commit or response fails, there is no matching compensation that terminates the SIP participant and room or records a durable unknown outcome.

The outer error path deletes the idempotency key, making a later retry eligible to dial again even if the first external action actually happened. When SIP creation fails after dispatch, quota is released but the dispatch/room is not cancelled here.

**Required improvement:** persist an attempt before external side effects; track dispatched/dialing/unknown outcomes and reconcile by external IDs. Preserve idempotency across ambiguous outcomes. Avoid holding tenant quota locks across slow network calls (F10).

### F22 — P1: SIP status persistence can permanently drop early or failed events

**Source:** `worker/telephony_call_status.py:81–97,191–232,250–295`; `worker/latency.py:226–260`; `worker/main.py:1393–1398`.

The tracker advances `_last_rank`, `answered`, and `finalized` before the asynchronous DB write succeeds. If the call row is not yet committed (F21), lookup logs and returns; the same status is then suppressed by rank/finalized state. A failed DB write has the same suppression problem. Executor futures are not retained/joined before job shutdown, so final transitions can race the close path.

The fast dispatch parser also drops `telephony_call_id`, despite `_setup_and_start` expecting it. Room lookup remains a fallback, but the explicit correlation ID is lost.

**Required improvement:** queued/persisted state distinction, bounded retry/replay of uncommitted transitions, shutdown flush, preserved dispatch correlation, and arbitration between phone status events and worker finalization.

### F23 — P1: inbound persistence/quota errors intentionally allow untracked live sessions

**Source:** `worker/telephony_runtime.py:315–369`; `worker/main.py:889–945`.

Inbound resolution logs and continues after non-validation quota errors, failed session/call persistence, or failed commit. This can run a provider call without durable history, accounting, or a releasable reservation. Rolling back the reservation avoids one leak, but does not restore lifecycle traceability. A later close can find no session/call row and become a no-op.

**Required improvement:** an explicit policy consistent with the user's fail-fast requirement: either refuse before entering the conversational pipeline, or durably queue a recoverable tracking attempt. Do not silently treat an untracked call as normally established.

### F24 — P1: synchronous shutdown I/O can block other cleanup beyond its budget

**Source:** `worker/main.py:1337–1352,1365–1367`; `worker/session_recording.py:84–130,198–243`; installed `livekit/agents/ipc/job_proc_lazy_main.py:426–443`; installed `livekit/agents/worker.py:211`.

The async quota shutdown callback directly calls synchronous psycopg finalization and `gc.collect`. Recording finalization directly reads the file, performs synchronous Storage operations, and writes DB rows on the job loop. LiveKit schedules shutdown callbacks concurrently with `gather`, but synchronous work prevents those callbacks from actually progressing concurrently. No query/lock timeout bounds these SQL operations; network recording operations can also outlast a runner's shutdown allowance.

**Required improvement:** move blocking I/O off the loop, bound each stage, keep quota/terminal state independent of recording upload, and persist retryable cleanup work. Framework cancellation cannot interrupt a blocking synchronous DB call on the event loop.

### F25 — P1: provider usage can be lost before collection or during teardown

**Source:** `worker/main.py:452–458,1433–1437`; `worker/usage.py:62–89`; installed `livekit/agents/voice/agent_activity.py:1090–1137,1651–1670`; installed `livekit/plugins/deepgram/stt.py:703–716`.

Greeting synthesis can start before session metric listeners are attached. Events emitted before attachment are not replayed into `session.usage`. Cached PCM playback produces no new provider synthesis event, which is correct for cache hits, but cache-fill work needs its own attribution rather than timing-dependent attachment.

During activity close, STT metric listeners are detached before audio-recognition stream cleanup. Deepgram's stream finally flushes remaining duration and connection-lifetime remainder during that cleanup. Those final plugin metrics can therefore miss the session collector used by `collect_model_usage`. This is a concrete source ordering gap, not a claim about exact invoice loss.

The billing writer also discards provider/model identity and input/output/cache token distinctions, collapsing usage into four quantities. Missing usage returns `{}` and then `agent_sec` alone can still settle, without durable “provider usage incomplete” state.

**Required improvement:** collect to a session/attempt owner through final provider close, separately attribute cache-fill/prewarm/cancelled work, and mark incomplete measurement. Provider billing units and model rates cannot be reconstructed faithfully from aggregate token counts alone.

### F26 — P2: the telemetry session ID usually differs from the database session ID

**Source:** `control_plane/mint.py:216–229`; `control_plane/app.py:747–752`; `worker/latency.py:194–223,226–260,736–739`; `worker/main.py:381,558,907–925`.

Browser mint/dispatch does not carry the inserted session ID. The early DB identity lookup returns tenant/agent only. Inbound flattening preserves call ID but drops session ID. The telemetry tracker then generates a new session ID, while the humanization runtime may use the room name, and the DB has its own UUID. Dispatch metadata parsing also discards a supplied session ID.

**Required improvement:** one durable session/attempt ID propagated through mint response, dispatch, worker, events, phone rows, usage, and close; retain separate room/job/participant/provider-request identifiers.

### F27 — P2: current metrics do not establish lifecycle reliability, and some labels describe configuration rather than behavior

**Source:** `sdk/src/index.ts:57–65,349–355,471–478`; `worker/latency.py:967–1029,1041–1055,1076–1147,1273–1297`; `worker/telemetry.py:45–54,137–184`; `worker/telephony_runtime.py:470–481`; `worker/health_http.py:99–117`.

Current strength: turn traces distinguish interrupted/cancelled/error outcomes, avoid treating failed turns as successful e2e latency, label e2e as a server proxy, and gate p95/p99 on sample counts. Those distinctions should be preserved.

Remaining gaps:

- No unified attempt denominator or structured establishment-success, agent-ready, unexpected-drop, recovery, hangup-success, or cleanup-success rate. Successful browser timing is emitted; failed attempts do not emit equivalent phase timings.
- STT connection acquisition/reuse metrics are ignored by the turn parser; the lifecycle lacks normalized connection/handshake/disconnect/retry events for each component.
- Retry activity has no attempt/status/backoff/recovery duration or measured usage. `retry_usage` and `unplayed_audio_seconds` are explicitly null. Prewarm activity records scheduling, not proven handshake success.
- Turn publication defaults off, and when enabled is fire-and-forget with no terminal flush/ack. Durable session history stores transcript/summary/usage, not a complete lifecycle event ledger.
- `e2eMs` is an additive diagnostic from EOU/LLM/TTS measurements, not receiver playback. Summation can overlap preemptive stages and omit transport/mic/output buffering. Do not use it as connection readiness or caller-heard proof.
- Transport diagnostic RTT, jitter, and loss are always null, and route/provider/codec are often unknown. Browser quality is categorical, not a packet-loss/RTT time series. No offline duration or repeated reconnect metrics are exposed.
- `worker_runtime_identity` uses a hardcoded runtime revision label rather than the audited commit/deployment version.
- Effective deadline reporting is inconsistent across providers (F16); configuration snapshots alone are not proof of the actual request boundary.
- Health readiness checks only credential presence, local VAD, and DB `SELECT 1`; it does not prove worker registration/dispatch capacity, provider credentials/entitlements, active stream health, or startup completion.

**Required improvement:** the metrics inventory below, with defined phase boundaries, failure classes, null/unknown semantics, safe IDs, durable terminal events, and deployed provenance.

### F28 — P2: room metrics are accepted without sender authority or envelope validation

**Source:** `sdk/src/index.ts:534–549,799–805`; `control_plane/mint.py:205–211`.

Session-failure packets check `participant.isAgent`, but metrics packets only check a JSON `type` string. Another participant able to publish data can submit a matching metrics envelope. There is also no session/room generation validation or cross-channel sequence deduplication before forwarding data/metadata metrics to hosts.

**Required improvement:** accept worker-owned metrics from the expected participant/topic/session with schema validation and deduplication. Host dashboards should not treat arbitrary room JSON as measured system health.

### F29 — P1: minute limits are based on settled past usage, not ongoing calls; rollover can block a fresh month

**Source:** `control_plane/mint.py:183–194`; `control_plane/app.py:538–546`; `tenant_portal_api/telephony_queries.py:308–324`; `worker/session_close.py:465–477`.

Admission and refresh compare `minutes_this_month`, but active session minutes are added on close. An ongoing call can exceed the monthly allowance without these gates seeing its accrued time. Phone calls have no browser refresh gate. Separately, checks do not normalize `period_start` to the current month; the worker resets it only during a later close. A tenant capped in the previous period can be refused new sessions before any new call can close and reset it.

**Required improvement:** define current-period accounting and active-call budget enforcement independently from post-call settlement and maximum duration. No numeric policy was assumed.

### F30 — P2: bundled client delivery uses a different connection implementation

**Source:** nested checkout `self-serve-demo-UI/frontend/package.json:15`; `self-serve-demo-UI/client-submission_v2/sdk/@awaazlabs-uva/voice/src/index.ts` refresh block; compare root `sdk/package.json:3`, `sdk/src/internal/livekitToken.ts` and current refresh loop.

The nested frontend references a local `1.0.1` tarball, whereas the root SDK source is `1.1.1` and the current integration-test frontend references registry `1.1.1`. The bundled source's refresh path uses unbounded fetch, a hypothetical `Room.updateToken`, and no equivalent current retry/termination logic. Root fixes would not automatically reach that delivery.

**Evidence boundary:** source/dependency declaration comparison only. The tarball contents, installed nested bundle, and hosted frontend were not treated as verified equivalents.

**Required improvement:** inventory the actual consumer artifacts, version/lock their SDK implementation, and validate lifecycle behavior against what clients install. Do not infer deployed parity from matching package names.

## Metrics inventory and gaps

“Missing” means not present as a coherent SDK lifecycle metric in the reviewed path, not that no debug log anywhere contains a similar timestamp.

| Metric / evidence | Present behavior | Gap / interpretation |
|---|---|---|
| Connection attempt ID and count | Independent session/room/job identifiers | No unified attempt denominator/correlation (F26–F27). |
| Mint success/failure and HTTP status | Rejection records, logs, browser errors | Failed phase timing and end-to-end outcome absent. |
| Mint latency | Browser `mintMs`, host upstream logs | Successful path only; includes different work at different boundaries. |
| Dispatch request latency | Watcher log | Creation acknowledgement is not worker acceptance/readiness. |
| Worker acceptance / startup failure | Framework logs | No host-facing readiness/failure handshake. |
| DB checkout/query/lock delay | Some coarse build timings | No separate bounded metrics or phase deadline. |
| Room connect latency | `livekitConnectMs` | No normalized failed-connect timing or cause chain. |
| Microphone permission/publication | Enabled check and device error | No duration, cancellable deadline, or separate public ready state. |
| Playback permission | `audio_ready`, `audio_blocked` | Explicitly not proof of received/heard audio. |
| Agent/provider operational ready | Provider shells, startup logs | No common readiness contract; HTTP model listing does not prove generation. |
| STT handshake/init | Plugin/log details | Gladia multi-stage timing not normalized or bounded as claimed. |
| STT live health | Transcripts/VAD events | No input-aware stale stream detection; silent close possible. |
| LLM request progress | 6-second useful-output watchdog; TTFT | Fail-fast classification/reason not preserved across lifecycle. |
| TTS synthesis health | TTFB/audio frames/watchdog | Partial Uplift error can look like normal completion. |
| Provider connection reuse/acquire time | Available in some pinned plugin metrics | Not surfaced uniformly; STT parser skips these. |
| Retries | Recoverable error hook and activity category | No complete per-attempt reason, status, time, recovery result, or usage. |
| Reconnecting / recovered | Native LiveKit events | Wrapper does not expose transitions, counts, outage duration. |
| RTT/jitter/loss | Unknown fields; categorical browser quality | No measured transport time series. |
| Unexpected disconnect | Native room reason and worker logs | Error/normal caller hangup/agent exit not a consistent terminal model. |
| Turn outcome/stages | Structured traces and distributions | Useful diagnostics; separate from connection success. |
| e2e/round trip | Server diagnostic proxy | Not receiver playback, and overlapping stages limit summation. |
| Greeting delay | Detailed opening logs | Audited only where it determines startup failure; optimization deferred. |
| Intended hangup and goodbye playout | Tool guards, 15-second playout wait | Server playout is not acoustic confirmation at caller. |
| Room/SIP deletion acknowledgement | Framework deletion task | No durable SDK/application hangup-complete receipt. |
| Session duration | Worker elapsed seconds | Begins before `session.start`; differs from mint age and SIP answered talk time. |
| Phone talk duration | `answered_at` to terminal status | Early lost answer event can make this wrong (F22). |
| Provider usage | `session.usage` mapped to four quantities | Start/end listener ordering and incomplete settlement gaps. |
| Cache/prewarm/cancelled/retry cost | Diagnostic categories, some nulls | Not invoice-accurate; do not silently interpret missing as zero. |
| Quota slot release | Session conditional close / phone marker | Partial commit and rollback can corrupt counters. |
| Transcript/summary saved | Best-effort DB writes | No resumable per-stage completion ledger; summary update does not check affected-row count. |
| Recording finalized/uploaded | Best-effort callback | Blocking I/O, no durable retry/terminal acknowledgement here. |
| Cleanup success/duration | Logs and callback result type | Result is not surfaced as a durable lifecycle completion. |
| Orphan recovered | Scheduled reconciliation counts | Age alone does not prove orphan; estimates lack actual media evidence. |
| Maximum duration | Age cleanup and refresh-chain cap | No intentional agent-level media timer/policy currently. |
| Provider/worker provenance | Constructor snapshots/plugin versions | Not proof of actual deployed credentials/models/build or provider availability. |

## Existing safeguards that should be retained

- Registry rejects unknown selectable providers rather than silently changing provider.
- Agent config is tenant-scoped; microphone capture and playback permission are handled explicitly.
- Token refresh has single-flight within its current loop, exponential delay, permanent 401/403 termination, and private-token application for the installed LiveKit client. F03 concerns ownership across sessions, not absence of those mechanisms.
- Provider failure handler does not terminate merely on a `recoverable=True` event. LLM/TTS useful-output guards prevent indefinite empty-output calls. Fail-fast aligns with the user's preference.
- Normal ending uses the LLM's ending intent, requires a committed current caller turn, rejects stale/interrupted endings, waits for closing playout, and drains before shutdown. Summary persistence is bounded by the tool orchestrator and is not meant to veto hangup.
- Both transport channels request room deletion on session close. The browser's `finishDisconnect` rejects duplicate/late close events for an already-replaced room and emits terminal events once for the active room.
- Phone status transitions have forward-only guards, a shared release marker, webhook support, and scheduled repair. F20/F22 concern atomicity and delivery gaps around those guards.
- Optional delivery clients have a separate session-owned pool with explicit retirement/close. That good ownership does not cover the baseline cached components in F17.

## Suggested improvement order — no implementation performed

1. **Make connection attempts and terminal outcomes owned and observable:** F01–F06, F08–F09, F19, F26. Cancellation and stale responses must never affect another call; report failure before declaring final teardown.
2. **Make provider failures honest and bounded:** Gladia F11–F12, Uplift F14–F15, effective deadlines F16, teardown ownership F17. Preserve the chosen prompt-end policy.
3. **Make DB and phone effects durable:** F10, F20–F24, F29. Persist attempts before dialing; keep unknown outcomes idempotent; resume partial finalization.
4. **Separate duration limits from orphan cleanup:** F18. Add an agent-level setting only after deciding units, default, platform ceiling, grace/closing behavior, and live-call edit semantics. Enforce on the worker for both browser and SIP, with accurate close reason and settlement.
5. **Finish lifecycle metrics and consumer parity:** F05, F13, F25–F28, F30. Keep “unknown/unverified” explicit; publish deployed provenance and failure denominators.

## Required live evidence before claiming lifecycle reliability

The source findings above do not require a live call to be actionable. The following acceptance evidence remains open:

- Each of the nine selectable providers, and each supported transport/language path: real authentication/entitlement, successful first request, repeated turns, normal remote/client/agent hangup, and terminal records.
- Gladia silent remote closure, init-response stall, provider error response, and STT media-vs-result stall.
- Deepgram Nova and opt-in Flux: long silence, actual mute/no input frames, remote close, and repeated disconnects across a long stream. Silence and no incoming audio are distinct scenarios.
- Uplift: simultaneous warm/synthesize, cancellation/reconnect, provider error after partial audio, and actual socket/request cleanup.
- ElevenLabs: idle-expired shared socket replacement, the configured 180-second inactivity policy, and interrupted-context cleanup.
- Cartesia/Rime: cancelled and idle-expired pool connections, repeated turns, and closure without another subsequent borrow.
- Gemini/Groq/Anthropic: authentication, 429/5xx/timeout/empty or partial stream, useful-output deadline, exact terminal outcome, and owned client close. Model/account availability remains provider evidence, not a registry claim.
- Browser: cancel at every startup phase, deny/leave mic prompt pending, simultaneous connects, delayed old refresh after new connect, network reconnect/recovery/terminal loss, blocked autoplay, and prompt visible terminal failure.
- SIP: no-answer, busy, rejected, trunk failure, answer-before-DB-commit, caller hangup, agent hangup after playout, and provider failure while answered. Verify the actual phone leg ends, not only its DB status.
- Worker crash/restart, lost dispatch response, DB failure between finalization stages, recording upload failure, long active sessions crossing both reconciliation thresholds, and a month boundary.
- Compare worker/provider resource counts before and after repeated sessions; a clean UI event or passing test suite alone does not establish resource cleanup.

No assertion is made here about current production scheduler enablement, applied migrations, running worker revision, provider account limits, regional routing, or real caller-heard behavior.

## External sources consulted

These explain contracts, not this deployment's live success:

- [LiveKit job lifecycle](https://docs.livekit.io/agents/server/job/) — shutdown, asynchronous close, room deletion, cleanup.
- [LiveKit session options and lifecycle](https://docs.livekit.io/agents/logic/sessions/) — phases and linked-participant close behavior.
- [LiveKit errors/events](https://docs.livekit.io/reference/agents/events/) — recoverable errors and terminal close reasons.
- [LiveKit token lifecycle](https://docs.livekit.io/frontends/reference/tokens-grants/) — server token refresh/reconnection; original JWT expiry alone is not proof an active connection dies. The wrapper imposes a separate host-refresh policy.
- [Gladia live quickstart](https://docs.gladia.io/chapters/live-stt/quickstart) and [WebSocket reference](https://docs.gladia.io/api-reference/v2/live/websocket) — init/stream lifecycle and `stop_recording` completion.
- [Deepgram WebSocket troubleshooting](https://developers.deepgram.com/docs/stt-troubleshooting-websocket-data-and-net-errors) — audio/no-audio, keepalive and explicit closure distinctions.
- [Deepgram Flux WebSocket reference](https://developers.deepgram.com/reference/speech-to-text/listen-flux) — separate v2 protocol; do not assume Nova controls are interchangeable.
- [Groq rate limits](https://console.groq.com/docs/rate-limits) — 429 and Retry-After are available classifications. This report does not propose waiting through them against the user's selected policy.
- [Uplift WebSocket TTS](https://docs.upliftai.org/websocket-tts) — application ready, per-request error/end messages, persistent connection and cancel command.
- [ElevenLabs multi-context TTS reference](https://elevenlabs.io/docs/api-reference/text-to-speech/v-1-text-to-speech-voice-id-multi-stream-input/) — documented inactivity maximum and context/socket lifecycle.

The Supabase changelog fetch was attempted but the browser tool could not parse its Markdown content type. No Supabase feature was implemented or changed; DB findings are grounded in this checkout's SQL and transaction boundaries.
