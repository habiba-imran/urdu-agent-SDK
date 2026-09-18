# Worker Time-to-First-Audio Optimization Research

**Project context:** AwaazLabs UVA worker cold start / time-to-first-audio  
**Prepared:** 2026-09-17  
**Scope:** Worker-side optimizations from LiveKit job assignment / worker startup through the first audible PCM reaching the room.  
**Primary objective:** Make the agent *ready* and capable of producing audio as soon as possible after the room is joined, while STT, LLM, TTS, interruption handling, and the media pipeline are becoming usable in parallel.

---

## 1. Scope and boundaries

This document is based on the existing `WORKER_COLD_START_RESEARCH_BRIEF.md` and current LiveKit/provider documentation.

The relevant worker path is approximately:

```text
LiveKit assigns job
    ↓
worker entrypoint
    ↓
ctx.connect()
    ↓
resolve identity/config
    ↓
construct/reuse STT
    ↓
construct/reuse LLM
    ↓
construct/reuse TTS
    ↓
construct AgentSession
    ↓
session.start()
    ↓
outbound audio track ready
    ↓
TTS / prerecorded audio produces PCM
    ↓
FIRST AUDIBLE AUDIO
```

This research intentionally does **not** recommend changes to:

- `control_plane/`
- mint → dispatch TLS/session behavior
- Ehsan-owned dispatch work
- portal / CI / package metadata
- prompt-humanization work
- general per-turn LLM quality work

Those can affect the total **button → first audio** experience, but they are outside this worker-focused document.

---

# 2. The main optimization principle

The worker should avoid this architecture:

```text
CONNECT
   ↓
CONFIG
   ↓
BUILD STT
   ↓
BUILD LLM
   ↓
BUILD TTS
   ↓
WARM PROVIDERS
   ↓
CREATE SESSION
   ↓
START SESSION
   ↓
SPEAK
```

That serializes many independent operations.

The desired architecture is closer to:

```text
                         JOB ASSIGNED
                              │
              ┌───────────────┼────────────────┐
              │               │                │
              ▼               ▼                ▼
        ROOM CONNECT      CONFIG/CACHE    PROVIDER PREP
              │               │           STT ─────────►
              │               │           LLM ─────────►
              │               │           TTS ─────────►
              │               │
              │          BUILD SESSION
              │               │
              └───────────────┴───────────────┐
                                               ▼
                                        SESSION.START
                                               │
                                               ▼
                                       FIRST AUDIO PCM
```

The goal is not necessarily to make every component fully warm before audio starts.

The goal is:

> **Start every useful initialization as early as possible, but allow only the minimum dependency chain to block first audio.**

---

# 3. What is already implemented in the current codebase

These items are already described as shipped in the existing research brief. Do not count them as new wins unless improving them further.

## 3.1 Greeting PCM cache

Current behavior:

- Process-local LRU.
- Cache key includes agent, provider, voice, greeting hash, and channel.
- Cache hit bypasses live TTS.
- Cache miss fills asynchronously.
- Helps repeat calls but not the first call after process boot.

Possible improvement remains: populate cache *before* a real call needs it.

---

## 3.2 Shortened opening prewarm gates

Current behavior:

- Cache hit: no opening prewarm wait.
- Static miss: short wait.
- LLM-generated opening: slightly longer wait.
- LLM warmup does not normally block first audio.

This is already better than serially waiting several seconds.

---

## 3.3 Thread-local provider client cache

Existing provider/plugin objects may be reused across sequential jobs on the same Windows thread runner.

Remaining questions:

- Does a new job actually land on the same worker/thread often enough?
- Are transport connections themselves reused?
- Is the cache keyed too narrowly?
- Could a safe process-level transport cache outperform a thread-local plugin cache?

---

## 3.4 DB connection reuse

A process-local connection is reused for worker hot-path DB operations.

Remaining issue:

- Avoid the DB entirely on the critical path whenever data is already available in dispatch metadata or an in-memory config snapshot.

---

## 3.5 Agent config TTL cache

Current TTL is short.

This reduces repeated remote configuration work, but a first request after expiration can still pay the lookup cost.

---

## 3.6 Connect-first worker ordering

`ctx.connect()` is intentionally issued early to avoid LiveKit assignment/connect timeout problems.

This should remain a safety constraint unless a tested LiveKit SDK version proves another order is safe.

---

## 3.7 Participant wait removed from opening critical path

The worker no longer unnecessarily waits for a participant to become fully ACTIVE before beginning the opening path when early identity is known.

This is a major optimization already shipped.

---

## 3.8 Local VAD interruption mode

Using local VAD avoids the startup cost previously observed with a heavier/adaptive interruption path.

---

## 3.9 Recording disabled for demos unless explicitly enabled

Recorder initialization is not forced into the startup path.

---

## 3.10 Plugin import prewarm

Provider plugin modules are imported when the process starts, avoiding import and plugin-registration work during each job.

---

# 4. Highest-value remaining optimizations

The following are the changes I would investigate first.

---

# 4.1 Overlap worker construction with `ctx.connect()`

## Idea

Do not interpret “connect first” as “nothing else may execute until `ctx.connect()` has completely returned.”

If job metadata contains enough information to identify the agent/config, start safe worker preparation while LiveKit room connection is in flight.

Current serial shape:

```python
await ctx.connect()

metadata = parse_dispatch_metadata(...)
session = await build_session(...)
await session.start(...)
```

Candidate concurrent shape:

```python
connect_task = asyncio.create_task(ctx.connect())

metadata = parse_dispatch_metadata(...)

build_task = asyncio.create_task(
    build_session_from_early_metadata(metadata)
)

await connect_task
session = await build_task

await session.start(...)
```

## Why it helps

If:

```text
ctx.connect     = 1.5 s
build_session   = 2.0 s
session.start   = 1.0 s
```

Serial critical path:

```text
1.5 + 2.0 + 1.0 = 4.5 s
```

Overlapped:

```text
max(1.5, 2.0) + 1.0 = 3.0 s
```

The important gain is that **room-joined → first-audio** can approach only:

```text
remaining build time + session.start + TTS TTFB
```

instead of paying the entire build after connection.

## What may safely run concurrently

Potentially:

- dispatch metadata parsing
- in-memory config cache lookup
- local voice-ID mapping
- provider object lookup
- `Agent` prompt object construction
- `AgentSession` construction
- provider `.prewarm()` scheduling
- non-room-dependent setup

## What must be checked

Some LiveKit/plugin objects may require a running event loop or a connected room.

Do not move anything before `ctx.connect()` merely because it is syntactically possible. Test each stage.

## Measurements

Compare:

- `connect_ms`
- `config_ms`
- `components_ms`
- `session_ctor_ms`
- `build_ms`
- time from connect completion → `session.start()` call
- time from connect completion → first PCM

---

# 4.2 Test `AgentSession.start()` ordering against current LiveKit behavior

This deserves a dedicated experiment.

Current LiveKit documentation and recipes frequently show:

```python
await session.start(agent=agent, room=ctx.room)
await ctx.connect()
```

rather than always requiring:

```python
await ctx.connect()
await session.start(...)
```

However, LiveKit's E2EE documentation explicitly requires connecting first when encryption options must be passed through `ctx.connect()`.

Therefore:

> Treat `session.start()` before/concurrent-with `ctx.connect()` as a version-specific experiment, **not** as an automatic refactor.

Possible test variants:

### Variant A — Current

```text
await ctx.connect()
await session.start()
```

### Variant B — Build first, connect first

```text
construct session
start all provider warmups
await ctx.connect()
await session.start()
```

### Variant C — Session start first, if SDK supports it safely

```text
await session.start(...)
await ctx.connect()
```

### Variant D — Concurrent startup, only if supported

```text
connect_task = create_task(ctx.connect())
start_task   = create_task(session.start(...))
await ...
```

## Why test this

If `session.start()` performs initialization unrelated to actual media attachment, beginning it sooner could remove part of `start_ms` from post-connect latency.

## Do not use Variant C/D when

- E2EE connection options require explicit `ctx.connect(...)`
- your LiveKit SDK version does not support it
- it causes job-assignment timeout
- the room object/media state is not ready
- startup races create flaky subscriptions/publications

---

# 4.3 Use LiveKit process prewarm / `setup_fnc` more aggressively

LiveKit provides process startup/prewarm specifically to move expensive initialization before jobs are assigned.

Typical use:

```python
def prewarm(proc):
    proc.userdata["vad"] = ...
    proc.userdata["resource"] = ...
```

Candidate resources to initialize here:

- Silero VAD
- heavy local models
- provider SDK/client shells
- shared async-independent configuration
- local voice maps
- parsed configuration defaults
- HTTP connection pools where safe
- DNS lookup warmups where safe
- TLS-capable client objects
- tokenizers
- prompt/template parsing
- local files/resources
- audio files
- cache indexes
- reusable codecs/resamplers if expensive

## Goal

Worker state before job:

```text
PROCESS ALREADY RUNNING

imports loaded
VAD loaded
default provider objects created
DB connection/pool initialized
common config in memory
common audio assets loaded
cache containers allocated
```

Then:

```text
JOB → mostly bindings + session-specific streams
```

---

# 4.4 Explicitly configure `num_idle_processes`

Current LiveKit documentation states that development mode can default to **0 idle processes**, while production keeps prewarmed workers.

That means local tests may unintentionally measure:

```text
call arrives
→ executor/process/thread starts
→ setup runs
→ job runs
```

instead of the desired production shape:

```text
warm executor already idle
→ job assigned instantly
```

Test:

```text
num_idle_processes = 0
num_idle_processes = 1
num_idle_processes = 2
num_idle_processes = 4
```

Measure first-call latency for each.

## Important

Do not blindly maximize this value.

More idle processes consume:

- RAM
- provider sockets
- file descriptors
- provider connection quotas
- DB connections
- CPU during prewarm

Set enough warm capacity for realistic simultaneous calls.

---

# 4.5 Keep the container/VM itself warm

LiveKit process prewarm cannot help if the entire host/container is cold.

For worker deployment:

- avoid scale-to-zero for latency-sensitive demos
- keep at least one application instance alive
- configure minimum replicas/min instances
- avoid serverless runtimes with large cold starts for the core voice worker
- ensure autoscaling has headroom before traffic spikes
- use health/readiness checks that only mark workers ready after prewarm finishes
- warm replacement instances before draining old ones

Desired deployment:

```text
new instance starts
    ↓
imports
    ↓
models
    ↓
provider clients
    ↓
cache seed
    ↓
READY
    ↓
receives voice jobs
```

Not:

```text
instance is considered READY
    ↓
first real caller triggers initialization
```

---

# 4.6 Warm the most common provider combinations before jobs arrive

If your demo/default stack is predictable, proactively construct it.

Example:

```text
STT: Deepgram/Gladia
LLM: Groq
TTS: Cartesia
Language: en
Channel: WebRTC
```

Precreate/cache that specific stack.

If 80% of demo calls use one stack, optimize that path intentionally.

## More advanced option

Maintain warm pools by common configuration:

```text
Pool A → EN / Deepgram / Groq / Cartesia
Pool B → EN / Gladia / Groq / Cartesia
Pool C → telephony mapping
```

This reduces generalized flexibility slightly but improves cache hit rate.

---

# 4.7 Worker affinity / sticky routing by provider or agent

Your thread/process-local caches are much more valuable if repeat jobs for the same agent/provider combination land on the same warm worker.

Possible dispatch/load-balancing idea inside allowed worker infrastructure:

```text
agent A calls → worker group A
agent B calls → worker group B
```

or:

```text
Cartesia+Groq jobs → warm pool X
Gemini+ElevenLabs jobs → warm pool Y
```

Benefits:

- higher config-cache hit rate
- higher provider-client-cache hit rate
- higher greeting/audio-cache hit rate
- less object churn
- better CPU cache/locality

Risk:

- uneven load distribution
- complicated scheduling
- hot agents can overload one pool

Use only if routing architecture permits it without modifying frozen control-plane ownership.

---

# 5. Provider initialization and transport reuse

The difference between “object exists” and “provider is actually hot” is critical.

A provider client can exist while the first real request still pays:

```text
DNS
TCP
TLS
HTTP/WebSocket upgrade
authentication
model/session setup
region discovery
```

---

# 5.1 Separate reusable provider transport from per-call stream state

The safe model is often:

```text
SHARED / CACHED

provider client
HTTP session
connection pool
DNS state
TLS session
model metadata
voice metadata
```

while keeping:

```text
PER CALL

STT stream
TTS stream
LLM request
conversation state
audio buffers
cancellation state
```

Do **not** share mutable streaming state between simultaneous calls.

This is especially important under Windows THREAD workers.

---

# 5.2 Reuse HTTP clients

Avoid:

```python
async with httpx.AsyncClient() as client:
    ...
```

for every startup request.

Prefer long-lived clients where the SDK permits:

```text
worker/process
    ↓
single HTTP pool
    ↓
many sequential requests
```

Benefits:

- TCP reuse
- TLS reuse
- DNS reuse
- keep-alive

Check provider SDK ownership rules before injecting custom transports.

---

# 5.3 Reuse WebSocket connections only when provider protocol supports it

Do not assume every provider WebSocket can span calls.

Possible cases:

1. **Client connection is reusable across utterances.**
2. **Connection is reusable within a call but not across calls.**
3. **Every synthesis/transcription stream needs a new WebSocket.**
4. **Socket can stay open only while keepalive/audio flows.**

Research per provider.

For example, Deepgram documents keepalive behavior for streaming STT and persistent WebSocket streaming for TTS.

If a provider supports connection reuse:

- open earlier
- send keepalive correctly
- close gracefully
- handle server idle limits
- ensure tenant/voice/config changes are supported

---

# 5.4 Prewarm TTS transport

For time-to-first-audio, TTS is often the provider that matters most.

The first TTS request may pay:

```text
DNS
TLS
WebSocket
provider routing
voice/model setup
first inference chunk
```

Potential prewarm approaches:

- provider-native `.prewarm()`
- open WebSocket without synthesis if supported
- synthesize an extremely short throwaway token/phrase
- resolve voice/model metadata ahead of time
- maintain an idle TTS socket if supported

Important tradeoffs:

- billing
- websocket limits
- rate limits
- minimum request costs
- idle timeout
- wasted synthesis

Measure TTS **TTFB**, not total synthesis duration.

---

# 5.5 Stream TTS rather than waiting for complete audio

First audio should start from the first generated audio chunk.

Avoid:

```text
generate entire WAV
→ download whole WAV
→ decode
→ publish
```

Prefer:

```text
text
→ streaming TTS
→ first PCM chunk
→ publish immediately
→ remaining audio continues streaming
```

Live voice providers generally expose streaming APIs specifically for this reason.

---

# 5.6 Avoid unnecessary audio containers/encoding conversion

If the room wants PCM-like frames, avoid avoidable transformations:

```text
TTS → MP3
→ decode MP3
→ resample
→ PCM
→ LiveKit
```

Prefer compatible streaming output:

```text
TTS → linear PCM
→ minimal resample if required
→ LiveKit
```

Potential costs:

- codec initialization
- buffering
- minimum packet accumulation
- resampling
- extra copies

Choose the output format closest to the LiveKit target.

---

# 5.7 Prewarm STT immediately

Even if STT does not directly create first outbound audio, it must be usable as soon as the user can speak/interupt.

Do not intentionally delay STT startup until after the first output if you want true immediate barge-in.

Desired:

```text
STT warm/open ─────────────────────►

TTS first audio ─────────►

user interrupts
        ↓
STT is already ready
```

Not:

```text
first audio starts
        ↓
then STT connects
```

---

# 5.8 Do not make STT readiness a hard gate for first output unless required

STT should start early, but it normally should not create:

```text
await stt_ready()
↓
then first audio
```

Instead:

```text
start STT task
start TTS task
start LLM task

only await what first audio strictly needs
```

---

# 5.9 Prewarm LLM transport in parallel

Even when the opening output is not LLM-generated, warming the LLM early matters because a caller may interrupt instantly.

Without LLM warmup:

```text
agent begins speaking
user interrupts
STT returns text
LLM does first DNS/TLS/request setup
silence
```

With LLM warmup:

```text
LLM transport is already hot
user interrupts
response begins sooner
```

This does not necessarily reduce the exact first greeting PCM, but it reduces “agent actually became usable” latency.

---

# 5.10 Avoid expensive LLM warmup calls that consume meaningful quota

A fake one-token request can warm transport/model routing but may consume:

- tokens
- TPM
- RPM
- concurrency slots
- money

If your current Groq path intentionally skips active LLM prewarm to avoid TPM pressure, retain that unless measurements justify otherwise.

Alternatives:

- warm only HTTP/TLS transport
- create reusable client
- DNS warmup
- allow the first real request to use the already-open connection

---

# 6. Config and database hot-path reduction

Remote configuration is a common hidden cold-start cost.

---

# 6.1 Prefer job/dispatch metadata over DB lookups

If data is already known when the job is dispatched, carry the minimum runtime snapshot in metadata.

Possible fields:

```text
tenant_id
agent_id
language
effective STT provider/model
effective LLM provider/model
effective TTS provider/voice
first speaker
channel
configuration version
```

Then worker startup can avoid a synchronous DB fetch.

Security warning:

- metadata is data, not instructions
- validate types/allowed values
- do not trust arbitrary provider keys/URLs
- keep secrets server-side

---

# 6.2 Use configuration versioning

Instead of using a very short TTL solely to avoid stale configuration:

```text
metadata:
agent_id
config_version = 183
```

Worker cache:

```text
(agent_id, version=183) → config
```

If version matches, use cache with no DB round trip.

If version changes, fetch once.

This can provide both:

- long-lived cache
- immediate invalidation

without relying on a 30-second TTL.

---

# 6.3 Increase TTL where correctness permits

If agent configuration changes infrequently, a 30-second TTL may be unnecessarily conservative.

Possible strategy:

```text
cache indefinitely by config version
```

or:

```text
TTL = several minutes
+ explicit invalidation/version check
```

The best approach depends on how configuration changes propagate.

---

# 6.4 Cache resolved voice IDs

If provider voice names/slugs require a DB/API lookup:

```text
voice_slug → provider_voice_id
```

cache that mapping.

Better:

- encode known mappings in synchronized config
- resolve when agent config is saved
- store the resolved provider ID
- avoid runtime discovery

---

# 6.5 Remove nonessential DB reads from entrypoint

Audit every query between:

```text
job assigned
```

and:

```text
first PCM
```

For each query ask:

> If this query disappeared, could the agent still safely start?

If yes, defer it.

Potentially defer:

- analytics initialization
- recording metadata
- call history
- nonessential tenant metadata
- UI fields
- reporting state
- usage counters
- shutdown-related state

---

# 6.6 Never synchronously create a new DB TLS connection on the first-audio path

Ensure all startup helpers use the existing reused connection/pool.

Add metrics around:

```text
db_pool_hit
db_connect_ms
db_query_ms
```

A hidden “fallback fresh connection” can erase all worker-side gains.

---

# 7. `AgentSession` construction

---

# 7.1 Construct the `AgentSession` as early as safely possible

If construction itself is not room-dependent, perform it while room connection is happening.

Desired:

```text
ctx.connect ───────────────►

config ───────►
components ───────►
AgentSession ctor ─►
provider warmups ─────────►
```

Then, when room connection completes:

```text
session already exists
```

---

# 7.2 Reuse immutable/session-independent components

Possible reusable components:

- VAD model
- provider client shells
- tokenizer
- prompt templates
- voice metadata
- static transform definitions
- sanitizer compiled regexes
- codec helper configuration

Do not reuse:

- call-specific conversation state
- mutable streams
- room handles
- per-call audio buffers
- session event handlers containing call data

---

# 7.3 Audit TTS sanitizers/transforms

If Cartesia/Rime sanitization transforms are installed per session:

- precompile regexes
- reuse stateless sanitizer objects
- avoid large normalization work before first chunk
- make transformations streaming when possible

This may be a small optimization but is easy to benchmark.

---

# 7.4 Avoid unnecessary prompt construction work before first audio

Large instruction assembly can involve:

- DB data
- templates
- tool schemas
- JSON serialization
- RAG material
- long history
- dynamic policies

Even if LLM TTFT is a separate ticket, constructing all of this before `session.start()` can still increase worker startup.

Possible solution:

- create minimum viable `Agent`
- attach/defer nonessential context after session start
- lazy-load tool metadata where safe

Do not compromise correctness/security.

---

# 7.5 Defer tool initialization

If tools require:

- API clients
- database clients
- CRM connections
- schema loading
- third-party authentication

do not make those resources ready before first audio unless the opening turn needs them.

Use lazy tool clients.

---

# 8. `session.start()` optimization

Once build work has been overlapped/prewarmed, `start_ms` may become the dominant stage.

Do not guess. Measure it directly.

---

# 8.1 Keep recording off the demo critical path

Already implemented for demos.

For production, if recording is required, investigate whether recorder creation/upload setup can occur:

```text
after media session start
```

rather than delaying outbound track readiness.

This may depend on LiveKit APIs and compliance requirements.

---

# 8.2 Keep interruption detector startup lightweight

Your current local VAD mode already avoids a heavier adaptive detector startup.

Continue to benchmark:

```text
vad mode
vs
adaptive mode
```

separately.

Do not switch to a slower mode merely because it is more sophisticated unless product quality requires it.

---

# 8.3 Audit audio preprocessing

Current LiveKit includes optional/default audio processing such as automatic gain control, and additional noise-cancellation models can be configured.

For a controlled browser demo, benchmark:

```text
AGC on vs off
noise cancellation on vs off
voice isolation on vs off
```

Only disable them if:

- startup/CPU cost is measurable
- audio quality remains acceptable

Never assume preprocessing is free, but also do not remove it without evidence.

---

# 8.4 Preload any noise-cancellation model

If production uses a model-based noise canceller, ensure its weights/native library initialization happens before the job where possible.

---

# 8.5 Check whether track publication is being delayed by participant logic

Measure separately:

```text
session.start called
session_start event
agent audio track created
track published
first PCM sent
first PCM received by client
```

`start_ms` is too coarse if it includes multiple internal operations.

---

# 8.6 Remove any participant wait from the critical path

Already largely addressed.

Audit for hidden variants:

- browser/WebRTC
- inbound SIP
- outbound SIP
- reconnect
- anonymous/legacy dispatch
- missing metadata fallback

One path may still wait unnecessarily even if the main path does not.

---

# 8.7 Verify participant subscription settings

If the agent subscribes to media it does not need during startup, there may be unnecessary work.

Examples:

- video tracks
- screen-share tracks
- data channels
- extra audio participants

Use the minimum permissions/subscriptions needed for the voice worker.

---

# 8.8 Avoid unnecessary room RPC/API calls before first audio

Do not make startup depend on:

- room metadata update
- participant metadata update
- external room API query
- recording API call
- telemetry API call

unless required.

---

# 9. LiveKit worker/executor considerations

---

# 9.1 Compare THREAD vs PROCESS behavior on your actual deployment OS

Your local environment uses Windows THREAD behavior.

Production may differ.

Do not assume local thread creation/cache behavior represents Linux process workers.

Benchmark:

```text
Windows local dev
Linux local container
staging
production-like worker
```

Track:

- executor identity
- process ID
- thread ID
- cache hits
- setup duration

---

# 9.2 Verify cache locality under thread executors

A `threading.local()` cache helps only when calls land on the same thread.

Log:

```text
pid
thread_id
provider_cache_hit
agent_id
```

If repeated jobs constantly move threads, the cache is not providing the expected benefit.

---

# 9.3 Consider process-level immutable caches

For thread-runner environments, a process-level cache guarded by locks may improve hit rate.

Only use it for objects confirmed to be thread-safe.

Good candidates:

- immutable config
- mapping tables
- pre-parsed templates
- bytes/audio blobs
- metadata

Potentially dangerous:

- provider WebSocket streams
- mutable SDK clients not documented as thread-safe
- call/session objects

---

# 9.4 Pre-size executors

Avoid creating worker threads/processes in response to the first call.

Use an idle pool sized for expected burst concurrency.

---

# 9.5 Avoid worker churn

Frequent worker replacement destroys:

- provider caches
- config caches
- audio caches
- DNS/TLS reuse

Look for:

- memory limits causing restarts
- health check failures
- short process lifetime
- autoscaler aggressive downscaling
- deploy rollout behavior
- watchdog restarts

---

# 10. Python runtime / async hot path

---

# 10.1 Keep the event loop unblocked

A single synchronous operation can prevent:

- `ctx.connect()`
- provider WebSocket handshake
- STT startup
- TTS startup
- timers

from progressing concurrently.

Audit startup for:

```python
requests.get(...)
psycopg_sync_query(...)
time.sleep(...)
heavy JSON processing
file I/O
CPU-heavy regex/text transform
```

Move blocking I/O off the event loop.

---

# 10.2 Use `asyncio.to_thread()` only for genuinely blocking work

`to_thread` is useful for sync DB/library calls but also introduces:

- executor scheduling
- thread-context concerns
- thread-local cache consequences

Do not wrap trivial fast operations unnecessarily.

---

# 10.3 Avoid serial `await`s for independent tasks

Bad:

```python
await warm_stt()
await warm_llm()
await warm_tts()
```

Better:

```python
stt_task = create_task(warm_stt())
llm_task = create_task(warm_llm())
tts_task = create_task(warm_tts())
```

Then await only the dependency you actually need.

---

# 10.4 Use bounded concurrency for startup tasks

Unlimited warmups can overload providers during bursts.

Use semaphores or warmup budgets.

Example:

```text
100 simultaneous jobs
× 3 provider warmups
= 300 connection attempts
```

That may be slower than doing less.

---

# 10.5 Avoid unnecessary locks on the critical path

If a provider/config cache uses a global lock:

```text
call A obtains lock
call B waits
call C waits
```

startup can serialize.

Use:

- per-key locks
- lock-free reads where safe
- single-flight construction per cache key

---

# 10.6 Use single-flight initialization

When multiple jobs need the same resource simultaneously:

Bad:

```text
job 1 → construct client
job 2 → construct same client
job 3 → construct same client
```

Better:

```text
first job creates initialization task
others await same task
```

This avoids duplicate TLS/model/config work.

---

# 10.7 Precompile regex and static transformations

Small optimization, but essentially free.

Anything repeated on every job and constant across jobs should be created at module/process startup.

---

# 10.8 Avoid excessive startup logging

Logging itself is usually cheap, but synchronous handlers can be expensive.

Avoid:

- synchronous network log export
- logging giant prompt/config objects
- forced flushes
- remote logging HTTP calls

before first audio.

Use buffered/asynchronous telemetry.

---

# 11. Network topology

A warm application can still be slow if every provider is far away.

---

# 11.1 Place the worker near the LiveKit region

The worker ↔ LiveKit media/control RTT affects:

- room connection
- track publication
- packet delivery

Choose a worker region close to the relevant LiveKit region.

---

# 11.2 Also consider provider region

You may have:

```text
worker → LiveKit = 10 ms
worker → TTS provider = 180 ms
```

For first audio, TTS RTT may matter more.

Measure RTT to:

- LiveKit
- STT
- LLM
- TTS
- DB/config store

Then choose the best compromise.

---

# 11.3 Move DB/config storage closer to workers

If a configuration query costs 1–3 seconds due to cross-region TLS/networking, worker-side code cannot hide all of it.

Options:

- use a closer read replica
- use a nearby pooler
- cache config
- pass config snapshot in metadata
- prefetch before jobs

---

# 11.4 Reuse DNS/TLS

Do not throw away network clients after every call.

Persistent transports convert:

```text
DNS + TCP + TLS + request
```

into:

```text
request
```

for warm calls.

---

# 11.5 Check IPv6/IPv4 fallback delays

Rare but real.

Misconfigured networking can cause:

```text
attempt IPv6
timeout/fail
fallback IPv4
```

Add connection timing if unexplained 250 ms–several-second spikes appear.

---

# 11.6 Check proxies

An HTTP proxy can add:

- connection setup
- TLS interception
- DNS differences
- queueing

Benchmark provider calls directly versus through configured proxies where allowed.

---

# 12. CPU and memory

---

# 12.1 Give workers enough CPU

Low CPU can make “network latency” look worse because the event loop cannot run promptly.

Watch:

- CPU saturation
- CPU throttling
- container CPU quota
- event-loop lag

---

# 12.2 Avoid memory pressure

Swapping/GC pressure can make first-call timing unstable.

Track:

- RSS
- page faults
- container OOM/restarts
- GC pauses

---

# 12.3 Keep model assets resident

If VAD or other local models are repeatedly loaded/unloaded, fix lifecycle ownership.

---

# 12.4 Avoid copying large audio/config buffers

Use streaming and references where possible.

Unnecessary `bytes(...)`, list copies, and frame concatenation can add CPU/memory latency.

---

# 13. First-output / TTS-specific opportunities

Although this document focuses on worker readiness rather than greeting copy, these directly affect time-to-first-audible PCM.

---

# 13.1 Use pre-synthesized audio for known fixed output

LiveKit supports `session.say(text, audio=...)`.

For truly fixed phrases, this removes TTS network latency.

Your current greeting PCM cache already does this for hits.

Possible next steps:

- pre-synthesize on worker startup
- persist across process restarts
- preload common phrases
- synthesize when agent configuration is saved
- use an external/shared object cache

---

# 13.2 Persist audio cache across worker restarts

Current process-local LRU loses all entries on restart.

Alternatives:

### Local disk cache

Good when worker disk persists.

### Shared Redis/object storage metadata + local fetch

Good across replicas, but network fetch itself must be faster than TTS.

### Bake common audio into deployment artifact

Best for stable demo agents.

### Config-save synthesis

When greeting/voice changes:

```text
save config
→ synthesize
→ store audio
→ workers fetch/cache
```

Then the first live call is not the first synthesis.

---

# 13.3 Increase cache size based on real working set

Current cache max is small.

Measure:

- number of active agents per worker
- voices
- channels
- greeting variants
- eviction frequency

A cache that constantly evicts before reuse gives false confidence.

---

# 13.4 Avoid double synthesis on cache miss

Ensure one request does not:

```text
background cache fill → TTS request A
live say()             → TTS request B
```

for the same text concurrently.

Use single-flight synthesis:

```text
cache miss
→ one synthesis task
→ live playback can consume same stream/frames
→ cache stores result
```

if provider/LiveKit APIs allow streaming duplication safely.

---

# 13.5 Begin playback on partial cached/synthesized frames

Do not wait for the entire phrase to finish synthesizing before publication.

---

# 14. STT/interrupt readiness

Time-to-first-audio is not enough if the user cannot interrupt it.

The real product target should include:

```text
time-to-first-audio
AND
time-to-first-listenable-input
AND
time-to-first-interrupt-response
```

---

# 14.1 Start inbound audio/STT as early as possible

The user may speak immediately on room join.

Capture should not begin after outbound speech has already started.

---

# 14.2 Keep first audio interruptible

LiveKit `session.say` supports interruptible speech.

Avoid low-level audio publication that bypasses AgentSession state unless you also reproduce:

- interruption detection
- speech cancellation
- transcript truncation
- conversation context consistency

---

# 14.3 Measure “user speaks during first 300 ms”

Add a test where the caller intentionally speaks immediately.

Success means:

1. inbound audio is captured,
2. STT receives it,
3. outgoing speech can stop,
4. LLM is ready quickly,
5. replacement output begins.

---

# 15. Preemptive generation for later turns

This does not primarily change the very first startup audio, but it affects whether the agent continues to feel fast after startup.

LiveKit currently supports preemptive LLM generation and optional preemptive TTS.

Typical behavior:

```text
STT final transcript
↓
LLM begins before end-of-turn confirmation
↓
turn confirmed
↓
response already partly generated
```

Optional preemptive TTS goes further:

```text
LLM token stream
↓
TTS begins speculatively
↓
turn confirmed
↓
audio is closer to ready
```

Tradeoff:

- wasted tokens/audio when prediction is cancelled

Keep this separate from worker cold start in measurements.

---

# 16. Audio processing tradeoffs

---

# 16.1 Automatic gain control

Benchmark default AGC versus disabled AGC for controlled demos.

Do not disable it in noisy/variable environments just for theoretical startup savings.

---

# 16.2 Noise cancellation

Heavy noise-cancellation models can cost CPU/setup time.

If needed in production:

- preload model
- use telephony-appropriate model for SIP
- use simpler/no processing for clean browser demos if acceptable

---

# 16.3 Echo/AEC behavior

AEC warmup settings generally affect interruption handling more than first outbound audio, but verify they are not gating speech in your configuration.

---

# 17. Telephony-specific path

Your telephony path remaps providers, so it should be benchmarked separately.

Potential sources of extra latency:

- SIP participant establishment
- 8 kHz audio
- codec conversion
- telephony TTS provider remapping
- telephony-specific noise cancellation
- provider voice fallback
- PSTN jitter buffering

Do not combine WebRTC and telephony measurements into one average.

Create separate latency budgets:

```text
WEBRTC
job → connect
connect → session start
session start → first PCM
PCM → browser audible
```

and:

```text
PSTN
job → SIP participant ready
worker start
TTS PCM
LiveKit/SIP bridge
carrier
audible phone audio
```

---

# 18. Cache architecture improvements

---

# 18.1 Layered cache

Possible hierarchy:

```text
L1 thread-local
L2 process-local
L3 shared cache
L4 source of truth
```

Examples:

### Configuration

```text
thread/process memory
→ Redis/shared
→ DB
```

### Audio

```text
process LRU
→ local disk
→ object storage
→ synthesize
```

---

# 18.2 Measure hit rate

Every cache should expose:

```text
hits
misses
evictions
load_ms
construction_ms
key
```

Otherwise you cannot tell if it matters.

---

# 18.3 Avoid over-specific cache keys

If two configurations differ only in a setting that does not affect the reusable object, they should not necessarily produce separate clients.

Example:

```text
LLM client connection
```

may not need to be keyed by prompt text.

Conversely, never under-key objects that contain mutable tenant/session state.

---

# 18.4 Warm cache based on observed traffic

Instead of guessing, periodically identify:

```text
top agents
top voices
top provider combinations
```

and prewarm those.

---

# 19. Fail-fast behavior

A provider timeout of 30 seconds does not make normal calls slow, but it can make failures *feel* like catastrophic cold starts.

For startup:

- use realistic connect timeouts
- retry only when useful
- fail over quickly if supported
- avoid stacked 30-second timeouts
- do not retry three providers serially before speaking

Possible fallback:

```text
primary TTS fails fast
→ fallback TTS
```

rather than:

```text
primary waits 30 s
→ retry waits 30 s
→ fallback
```

---

# 20. Provider fallback prewarming

If fallbacks are important, decide whether to warm them too.

Tradeoff:

```text
warm only primary
→ cheapest
→ failover may be cold
```

versus:

```text
warm primary + fallback
→ faster failure recovery
→ more sockets/cost
```

For demos, warming only the primary is usually enough unless failures are common.

---

# 21. Avoid duplicate setup caused by multiple abstraction layers

Audit whether both your code and the LiveKit plugin perform:

- prewarm
- connection creation
- voice resolution
- session creation

A common performance bug is:

```text
custom wrapper warms provider
then plugin creates a completely new provider client
```

The warm connection is never actually used.

Verify object identity in logs.

---

# 22. Instrument the actual first-audio pipeline

The existing fields are good but should be expanded.

Current useful fields include:

```text
connect_ms
config_ms
components_ms
components_cache_hit
session_ctor_ms
build_ms
start_ms
prewarm_wait_ms
ms_since_connect
greeting_cache_hit
opening_mode
```

Add the following if possible.

---

## 22.1 Worker/executor startup

```text
job_received_at
executor_ready_ms
process_age_ms
thread_id
process_id
idle_worker_hit
```

---

## 22.2 Config

```text
config_cache_hit
config_db_ms
db_connection_reused
voice_mapping_cache_hit
```

---

## 22.3 Providers

```text
stt_client_cache_hit
llm_client_cache_hit
tts_client_cache_hit

stt_prewarm_started_at
stt_ready_at

llm_prewarm_started_at
llm_ready_at

tts_prewarm_started_at
tts_ready_at
```

---

## 22.4 Session/media

```text
session_start_called_at
session_started_at

audio_track_create_ms
audio_track_publish_ms
```

---

## 22.5 TTS

Use provider/LiveKit TTS metrics when available:

```text
tts_request_at
tts_ttfb_ms
first_tts_chunk_at
first_pcm_publish_at
```

LiveKit TTS metrics expose TTFB-style information, which is more useful than total speech duration for this problem.

---

## 22.6 Client-visible measurement

Server logs are not enough.

Measure in the browser:

```text
button_clicked_at
token_received_at
room_connected_at
agent_track_subscribed_at
first_audio_frame_received_at
first_audio_played_at
```

The browser may add:

- autoplay restrictions
- audio context resume delay
- buffering
- track subscription delay

Do not attribute these to the worker.

---

# 23. Build a proper cold/warm benchmark matrix

Test at least these states.

## State A — Full cold

```text
new VM/container
new worker
empty process caches
no DB connection
no provider clients
no audio cache
```

## State B — Warm host, new worker executor

```text
container warm
process/job runner cold
```

## State C — Warm process, cold agent/provider config

```text
executor warm
different provider combination
```

## State D — Warm provider, audio cache miss

```text
clients reused
greeting/audio not cached
```

## State E — Fully warm repeat

```text
same worker
same agent
same provider
same voice
cache hit
```

Never compare only A to E and call the difference one “cold-start problem.”

---

# 24. Test each stage independently

For every optimization, record:

```text
P50
P90
P95
P99
minimum
maximum
```

A voice system can feel bad because of tail latency even when the average is good.

Run enough calls to distinguish noise from improvement.

---

# 25. Recommended experimental order

This ordering is designed to avoid spending time on small changes before finding the largest blocker.

---

## Experiment 1 — Get a real stage breakdown

Collect:

```text
connect_ms
config_ms
components_ms
session_ctor_ms
start_ms
tts_ttfb_ms
first_pcm_ms
```

for:

- cold first call
- immediate second call
- call after several minutes
- new agent/provider combination

---

## Experiment 2 — Idle worker count

Test:

```text
0
1
2+
```

If the first-call penalty collapses with an idle worker, worker spawn/prewarm is a primary problem.

---

## Experiment 3 — Overlap connect + build

Keep semantics identical; only change scheduling.

Measure reduction in:

```text
connect complete → session.start
```

---

## Experiment 4 — More aggressive process prewarm

Preload:

- VAD
- config defaults
- common provider clients
- local mappings

Measure first job after process initialization.

---

## Experiment 5 — Provider connection warmness

For each provider separately:

```text
cold first API call
warm second API call
```

Measure:

```text
connection/setup
TTFB
```

This identifies whether Cartesia/Deepgram/Gladia/Groq is the real cold component.

---

## Experiment 6 — `session.start()` profile

If it remains >500–1000 ms, break it down further.

Test:

- VAD/adaptive
- recording
- preprocessing
- room options
- track publication
- participant state

---

## Experiment 7 — LiveKit startup ordering

Test current versus LiveKit-current recipe ordering in an isolated branch.

Do not merge until:

- assignment timeout is safe
- WebRTC works
- SIP works
- E2EE requirements are understood
- interruptions work
- cleanup works

---

## Experiment 8 — Deployment warmness

Restart entire staging worker and measure first call.

Then keep instance warm and repeat.

This isolates infrastructure cold start from code cold start.

---

# 26. Ranked opportunity table

| Optimization | Cold-call impact | Warm-call impact | Effort | Risk | Priority |
|---|---:|---:|---:|---:|---:|
| Overlap `ctx.connect()` + safe build work | High | Medium | Medium | Medium | **P0** |
| Explicit idle/prewarmed workers | Very high if currently cold | Low | Low | Low | **P0** |
| Keep host/container warm | Very high if scale-to-zero | Low | Medium | Low | **P0** |
| Process prewarm via LiveKit `setup_fnc` | High | Medium | Medium | Low-Med | **P0** |
| Measure TTS TTFB separately | Enables all other work | Enables all other work | Low | Low | **P0** |
| Prewarm/reuse TTS transport | High | Medium | Medium | Medium | **P0/P1** |
| Long-lived provider HTTP clients | Medium-High | Medium | Medium | Medium | **P1** |
| Config snapshot in job metadata | High if DB slow | Medium | Medium | Medium | **P1** |
| Versioned config cache | Medium-High | Medium | Medium | Low | **P1** |
| Process-level immutable caches | Medium | Medium | Medium | Medium | **P1** |
| Worker/provider affinity | Medium | Medium-High | High | Medium | **P1/P2** |
| Profile/reduce `session.start()` | High if dominant | High | Medium-High | Medium | **P1** |
| Remove optional audio processing | Low-Med | Low-Med | Low | Quality risk | **P2** |
| Defer tools/RAG/noncritical data | Medium | Medium | Medium | Medium | **P1** |
| Shared/persistent audio cache | High for known phrases | High | Medium | Low-Med | **P1** |
| Audio-format/resample cleanup | Low-Med | Low-Med | Medium | Low | **P2** |
| Logging/telemetry cleanup | Low unless misconfigured | Low | Low | Low | **P2** |
| CPU/memory tuning | High if throttled | High | Infra | Low | **P1** |
| Region/topology optimization | Medium-High | Medium-High | Infra | Medium | **P1** |
| Session start before connect experiment | Potentially high | Medium | Medium | High | **Research** |
| Raw audio publish before AgentSession | Potential | Potential | High | Very high | **Last resort** |

---

# 27. Ideas that are possible but should not be first choices

---

## 27.1 Publish raw audio before `AgentSession.start()`

Concept:

```text
worker joins room
→ manually create audio source/track
→ publish PCM
→ initialize AgentSession later
```

Possible benefit:

- earliest possible audio

Major problems:

- bypasses AgentSession speech state
- interruption handling becomes custom
- conversation history may not match what user heard
- audio cancellation becomes custom
- duplicate track/race risks
- handoff into normal session becomes complex

Recommendation:

> Only investigate if profiling proves `AgentSession.start()` is irreducibly the dominant latency and product requires sub-second output.

---

## 27.2 Replace STT + LLM + TTS with a realtime speech-to-speech model

Potentially removes pipeline boundaries.

However, it changes:

- provider architecture
- prompting
- observability
- cost
- interruption behavior
- voice control
- tool behavior

It is outside this worker cold-start wave and should be treated as a separate architecture option.

---

## 27.3 Local TTS fallback

A tiny local TTS model could speak immediately while cloud providers initialize.

Advantages:

- no network first-output dependency

Problems:

- different voice
- poorer quality
- model load cost
- inconsistent experience

Only useful for specialized fallback scenarios.

---

## 27.4 “Fake” filler audio

Examples:

- tone
- earcon
- “one moment”
- ambient audio

This makes *audio* happen sooner but does not make the agent ready sooner.

Do not use it to hide avoidable engineering latency.

---

# 28. Things that may improve perceived latency but not true worker TTFA

Keep these separate from worker TTFA metrics:

- UI animation
- loading state
- connecting sound
- browser spinner
- background music
- typing sound
- call-progress tone

They can improve experience but must not be reported as faster agent audio.

---

# 29. Do-not-do list

Do not:

1. Move slow DB/network work before LiveKit job acceptance.
2. Violate the worker's connect/assignment deadline.
3. Block greeting/audio on STT warmup unless strictly necessary.
4. Block greeting/audio on LLM warmup unless the first output requires LLM.
5. Share mutable STT/TTS streams across concurrent calls.
6. Assume a provider SDK client is thread-safe without verifying.
7. Open unlimited prewarm sockets during traffic bursts.
8. create duplicate provider clients in multiple abstraction layers.
9. add synchronous telemetry/network logging before first audio.
10. wait for full participant ACTIVE state when it is not required.
11. benchmark only the second warm call.
12. mix WebRTC and PSTN numbers.
13. mix control-plane latency with worker latency.
14. measure only server-side PCM generation and call it “audible” latency.
15. optimize prompt/LLM per-turn TTFT under this worker cold-start ticket unless it directly blocks startup.
16. change control-plane dispatch code under this work item.
17. bypass `AgentSession` for raw audio before proving it is necessary.
18. keep very long startup timeouts that make failures look like cold starts.
19. prewarm expensive provider inference blindly without considering quotas.
20. disable audio-quality features without A/B testing real calls.

---

# 30. Suggested target architecture

```text
==============================================================
                 WORKER / PROCESS STARTUP
==============================================================

Import all plugins
       │
Load local models / VAD
       │
Initialize DB pool
       │
Build static config maps
       │
Create safe provider client shells
       │
Warm common transports where supported
       │
Seed high-value caches
       │
Keep N executor(s) idle
       │
       ▼
                 WORKER READY


==============================================================
                    JOB ASSIGNED
==============================================================

                   JOB RECEIVED
                        │
         ┌──────────────┼───────────────────────┐
         │              │                       │
         ▼              ▼                       ▼
   ctx.connect()    parse metadata       cached config lookup
         │                                      │
         │                              resolve provider combo
         │                                      │
         │                              acquire warm clients
         │                                      │
         │                             construct Agent/Session
         │                                      │
         │               ┌──────────────────────┼────────────┐
         │               │                      │            │
         │          STT warm/open          LLM warm      TTS warm/open
         │               │                      │            │
         └───────────────┴──────────────────────┴────────────┘
                                  │
                                  ▼
                           ROOM CONNECTED
                                  │
                           minimal remaining
                              setup only
                                  │
                                  ▼
                          session.start()
                                  │
                                  ▼
                       outbound track ready
                                  │
                                  ▼
                          FIRST PCM CHUNK
                                  │
                                  ▼
                         CALLER HEARS AUDIO

Meanwhile:

STT ───────────────────────────────────────────────► ready
LLM ───────────────────────────────────────────────► ready
TTS ───────────────────────────────────────────────► ready
```

---

# 31. Practical target metrics

Instead of one total number, define a latency budget.

Example engineering targets to investigate:

```text
job assigned → worker entrypoint          < 100–300 ms warm
ctx.connect                                 < 1 s ideal
config hot path                            < 50–100 ms cached
component acquisition                      < 50–150 ms cached
AgentSession constructor                   < 50–100 ms
session.start                              < 500–1000 ms target
TTS request → first PCM                    < 300–700 ms target
room joined → first PCM                    ~1–2 s desirable
```

These are **engineering targets, not guarantees**. Actual values depend on LiveKit region, deployment, providers, traffic, and channel.

The first goal should be to establish your own P50/P95 for every stage.

---

# 32. New metrics I would add first

If only a small observability patch is possible, add:

```text
job_received_ts
connect_start_ts
connect_done_ts

config_start_ts
config_done_ts
config_cache_hit

components_start_ts
components_done_ts
provider_cache_hits

session_ctor_done_ts

session_start_call_ts
session_start_done_ts

tts_request_ts
tts_first_byte_ts

first_pcm_publish_ts
first_audio_track_publish_ts

worker_process_age_ms
pid
thread_id
idle_worker_hit
```

Then calculate:

```text
JOB → CONNECT
CONNECT → SESSION START
SESSION START → TTS REQUEST
TTS REQUEST → FIRST BYTE
FIRST BYTE → FIRST PCM PUBLISH
CONNECT → FIRST PCM
JOB → FIRST PCM
```

---

# 33. Recommended first five code investigations

If you want the shortest actionable shortlist, inspect these first:

## 1. Does `build_session()` really have to wait until `ctx.connect()` finishes?

If no, overlap them.

## 2. Is your local/staging worker running with `num_idle_processes=0`?

If yes, test an explicit warm idle worker.

## 3. What exactly makes up `start_ms`?

If `start_ms` is >1 second after the existing VAD/recording changes, profile it.

## 4. Does the TTS provider client reuse an actual warm transport?

A cached Python object is not enough if every `say()` opens a new connection.

## 5. Is configuration still doing a network round trip on the first call?

If yes, pass/version/cache enough config to remove it from the hot path.

---

# 34. Current LiveKit findings relevant to this research

As of 2026-09-17, current LiveKit documentation indicates:

1. `AgentServer` exposes `setup_fnc` for prewarming expensive process resources.
2. `num_idle_processes` controls how many workers remain prewarmed.
3. Development mode can default to zero idle processes.
4. `AgentSession` orchestrates STT/LLM/TTS and room I/O.
5. Current recipes commonly show `session.start(...)` followed by `ctx.connect()`, although other configurations such as E2EE explicitly require `ctx.connect()` first.
6. `session.say()` can use pre-synthesized audio.
7. LiveKit exposes interruption handling and preemptive generation.
8. Preemptive LLM generation is enabled in current turn-handling defaults, with optional preemptive TTS.
9. TTS metrics can expose time-to-first-byte style measurements.
10. Audio preprocessing such as AGC/noise cancellation should be treated as measurable pipeline work rather than assumed free.

Because LiveKit APIs evolve, verify the exact behavior against the version pinned by the UVA worker before changing lifecycle ordering.

---

# 35. Provider-specific research points for the UVA stack

For each configured provider, answer these questions.

## STT — Deepgram / Gladia

- Is the SDK client reusable?
- Is the WebSocket stream per call?
- Can connection establishment happen before real audio arrives?
- What keepalive is required?
- What is the idle timeout?
- Can one socket change language/model?
- What is cold vs warm connection time?
- Does it support region selection?
- Can the worker reuse an underlying HTTP pool?

## LLM — Groq / others

- Does the SDK reuse HTTP keep-alive?
- Can a long-lived async client be injected?
- Does `.prewarm()` perform inference or only transport warmup?
- What quota does warmup consume?
- Is prompt/schema construction occurring before network request?
- Is TLS reused across calls?

## TTS — Cartesia / ElevenLabs / Rime / FishAudio

- Does the LiveKit plugin use streaming WebSocket?
- Is WebSocket created per utterance or per session?
- Can it be opened before first text?
- Can it stay alive across utterances?
- Can it stay alive across calls?
- What is TTFB cold vs warm?
- Is voice lookup remote?
- Is there unnecessary audio decoding/resampling?
- Is partial audio published immediately?

---

# 36. Decision tree

Use measured timings rather than assumptions.

```text
Is worker process/executor cold?
│
├─ YES → prewarm / idle workers / keep host warm
│
└─ NO
    │
    Is config_ms high?
    │
    ├─ YES → metadata snapshot / config cache / versioning / DB region
    │
    └─ NO
        │
        Is components_ms high?
        │
        ├─ YES → provider caches / preconstruction / transport reuse
        │
        └─ NO
            │
            Is start_ms high?
            │
            ├─ YES → profile AgentSession.start / I/O / detector / recording
            │
            └─ NO
                │
                Is TTS TTFB high?
                │
                ├─ YES → websocket warmup / streaming / region / cache
                │
                └─ NO
                    │
                    Is client audible delay high?
                    │
                    ├─ YES → browser track/audio-context/buffering
                    │
                    └─ NO → TTFA should already be low
```

---

# 37. Final priority order

My current suggested order for investigation is:

1. **Measure actual cold vs warm stage timings.**
2. **Verify idle worker/prewarm configuration.**
3. **Overlap `ctx.connect()` with safe session/component construction.**
4. **Move more initialization into LiveKit process prewarm.**
5. **Keep host/container warm.**
6. **Measure and warm actual TTS transport, not merely the Python object.**
7. **Remove remote config/DB work from the critical path.**
8. **Profile `session.start()` internally if it still dominates.**
9. **Warm STT and LLM concurrently so the agent is immediately usable once audio begins.**
10. **Improve cache locality and provider-client reuse.**
11. **Tune deployment region, CPU, memory, networking.**
12. **Experiment with LiveKit startup ordering only after the above are measured.**
13. **Use low-level/raw-audio approaches only as a last resort.**

---

# 38. Success criteria

A successful worker architecture should have these properties:

- an idle worker already exists before the call when feasible
- most heavy imports/models are already loaded
- room connection and worker build overlap where safe
- configuration is in memory or arrives with the job
- provider client shells are already available
- provider network warmups run concurrently
- no unnecessary participant wait blocks output
- no DB/TLS setup is serialized immediately before audio
- `session.start()` has a measured, controlled cost
- TTS streams the first PCM chunk instead of buffering full audio
- STT is already becoming/listening ready while initial output plays
- LLM is warming in parallel and can respond quickly to an interruption
- caches are measured and actually hit
- cold-call tests are run after full restart, not only after one warm-up call
- browser-side first-audible latency is measured separately from worker PCM generation
- WebRTC and telephony have separate latency budgets

The conceptual end state is:

```text
ROOM CONNECTED
      ↓
almost nothing remains except:
      ↓
attach/start media pipeline
      ↓
first TTS/audio chunk
      ↓
AUDIBLE AUDIO
```

rather than:

```text
ROOM CONNECTED
      ↓
fetch config
      ↓
construct clients
      ↓
warm providers
      ↓
construct session
      ↓
initialize media
      ↓
start TTS
      ↓
AUDIBLE AUDIO
```

---

# Sources / documentation reviewed

## Project source

- `WORKER_COLD_START_RESEARCH_BRIEF.md` — user-provided architecture, ownership, current mitigations, existing latency logs, and constraints.

## LiveKit

- Server options / prewarm / idle processes  
  https://docs.livekit.io/agents/server/options/

- Python Agents API / `AgentServer` options  
  https://docs.livekit.io/reference/python/livekit/agents/

- Agent session  
  https://docs.livekit.io/agents/logic/sessions/

- Agent speech and audio / preemptive generation  
  https://docs.livekit.io/agents/multimodality/audio/

- Audio customization / pre-synthesized audio / caching  
  https://docs.livekit.io/agents/multimodality/audio/customization/

- Turn-taking tuning  
  https://docs.livekit.io/agents/logic/turns/tuning/

- Turns / interruptions  
  https://docs.livekit.io/agents/logic/turns/

- External data / startup load-time guidance  
  https://docs.livekit.io/agents/logic/external-data/

- E2EE agent lifecycle note  
  https://docs.livekit.io/transport/encryption/agents/

- TTS metrics recipe  
  https://docs.livekit.io/reference/recipes/metrics_tts/

- Realtime metrics recipe  
  https://docs.livekit.io/reference/recipes/metrics_realtime/

## Deepgram

- Streaming TTS over WebSocket  
  https://developers.deepgram.com/docs/tts-websocket-streaming

- TTS WebSocket overview  
  https://developers.deepgram.com/docs/tts-websocket

- STT audio keepalive  
  https://developers.deepgram.com/docs/audio-keep-alive

- STT WebSocket troubleshooting / timeouts  
  https://developers.deepgram.com/docs/stt-troubleshooting-websocket-data-and-net-errors

- TTS latency guidance  
  https://developers.deepgram.com/docs/text-to-speech-latency

---

# Notes

- This document intentionally lists **possible** optimizations, including experiments that may turn out not to apply to the UVA codebase.
- Do not implement every item. Use the stage metrics to identify the actual critical path first.
- Any lifecycle-ordering experiment should be tested against the exact pinned LiveKit Agents SDK version.
- Provider connection reuse must be verified against each SDK's concurrency/thread-safety guarantees.
