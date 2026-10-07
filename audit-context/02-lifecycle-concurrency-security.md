# Lifecycle / concurrency / audio / errors / security / observability

Package order matches `audit-context/01-structural-map.md` section B. Graphify: NOT FOUND (`graphify-out/`, `graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md` absent). Tags: [VERIFIED] = opened cited source; [INFERRED] = deduced, not presented as fact.

---

## Package: `@awaazlabs-uva/voice` (`sdk/`)

### 1. Lifecycle and state

- [VERIFIED] Session create: `connect(opts)` requires no existing room, non-empty `agentId`, sets `state='connecting'`, constructs `new Room({ audioCaptureDefaults: MIC_CAPTURE_OPTIONS })`, wires events, POSTs `sessionEndpoint` with `{ publishableKey, agentId }`, then `room.connect(wsUrl, token)`. `sdk/src/index.ts:L240-L306`
- [VERIFIED] Hold: instance fields `room`, `session`, `sessionReceivedAt`, `state`, refresh timer, speaking flags. `sdk/src/index.ts:L151-L165`
- [VERIFIED] Teardown: `disconnect()` clears refresh timer, calls `room.disconnect()`, nulls room/session/speaking flags, sets `idle`. `sdk/src/index.ts:L367-L397`
- [VERIFIED] `RoomEvent.Disconnected` also clears timer/audio/room/session and emits `disconnected`/`ended`. `sdk/src/index.ts:L429-L439`
- [VERIFIED] Token refresh: timer at `(expiresIn-60)s` (min 5s), POSTs refresh endpoint with `Authorization: Bearer ${session.token}`, applies token via `applyRefreshedLiveKitToken`, reschedules. `sdk/src/index.ts:L564-L643`; `sdk/src/internal/livekitToken.ts:L28-L56`
- [VERIFIED] State lives on the class instance (no module-global session registry). `sdk/src/index.ts:L151-L165`
- Growing structures:
  | Structure | Cleanup |
  |---|---|
  | `listeners: Map<event, Set<Listener>>` — grows with `on()` registrations `sdk/src/index.ts:L153`, `L354-L358` | `off()` deletes callback `L362-L364`; NO CLEANUP PATH FOUND for emptying Sets when disconnecting |
  | `remoteAudioElements: Map<trackSid, HTMLMediaElement>` `L154` | `detachRemoteAudio` / `detachAllRemoteAudio` on unsubscribe/disconnect `L544-L561`, `L431` |
  | Per-instance `session` / `room` | nulled on disconnect / Disconnected `L385-L392`, `L432-L434` |

### 2. Concurrency model

- [VERIFIED] Async: `async connect`/`disconnect`/`refreshToken`; mic enable raced with mint via `micPromise`. `sdk/src/index.ts:L255-L260`, `L333`
- [VERIFIED] `refreshInFlight` single-flight prevents overlapping refresh loops. `sdk/src/index.ts:L156-L157`, `L582-L591`
- [VERIFIED] No worker threads / child processes / locks in package source (searched `sdk/src`).
- [VERIFIED] Fetch timeout via `AbortController` default 15000 ms (`fetchTimeoutMs`). `sdk/src/internal/http.ts:L8-L27`; `sdk/src/index.ts:L43-L47`, `L195-L197`
- [VERIFIED] LiveKit connect timeouts: `peerConnectionTimeout` / `websocketTimeout` = `fetchTimeoutMs`. `sdk/src/index.ts:L303-L306`
- [VERIFIED] Refresh retry: backoff 1s→2s→4s→8s cap, until JWT deadline, max 20 attempts. `sdk/src/index.ts:L600-L678`
- Limits: `fetchTimeoutMs` default 15000 — `sdk/src/internal/http.ts:L8-L9`. Refresh attempt cap 20 — `sdk/src/index.ts:L676-L678`. NO LIMIT FOUND: max concurrent SDK instances / sessions per page. NO LIMIT FOUND: listener count. NO LIMIT FOUND: rate limit client-side.

### 3. Real-time audio/data path

- [VERIFIED] Mic capture options: `echoCancellation`, `noiseSuppression`, `autoGainControl` true. `sdk/src/index.ts:L15-L18`, `L250-L252`
- [VERIFIED] Inbound remote audio: `TrackSubscribed` → `track.attach()` → hidden `<audio>` appended to `document.body`, `.play()`. `sdk/src/index.ts:L481-L541`
- [VERIFIED] Outbound mic: `setMicrophoneEnabled(true, MIC_CAPTURE_OPTIONS)` before/after connect. `sdk/src/index.ts:L256-L257`, `L336-L337`
- [VERIFIED] Transcripts: `RoomEvent.TranscriptionReceived` → emit `transcript` with `speaker` local=`user` else `agent`. `sdk/src/index.ts:L451-L458`
- [VERIFIED] Speaking: `ActiveSpeakersChanged` → `speaking` (local) / `agent_speaking` (remote). `sdk/src/index.ts:L461-L474`
- [VERIFIED] Latency/metrics inbound: `RoomMetadataChanged` / `DataReceived` JSON with `type` `metrics_updated`|`turn_latency`. `sdk/src/index.ts:L505-L719`
- [VERIFIED] Connect timing measured: `mintMs`, `livekitConnectMs` via `performance.now()`. `sdk/src/index.ts:L263-L328`
- [VERIFIED] Autoplay block: `AudioPlaybackStatusChanged` → `audio_blocked`; unlock via `startAudio()` → `room.startAudio()`. `sdk/src/index.ts:L520-L523`, `L406-L409`
- STT/LLM/TTS: N/A inside this package — media/STT/LLM/TTS run outside browser SDK (package only LiveKit client + session HTTP). Codec/sample-rate: NOT FOUND in `sdk/src` (searched). Barge-in: NOT FOUND as SDK logic (comment references worker Silero) `sdk/src/index.ts:L11-L13`. Reconnect/resume media path: NOT FOUND beyond token refresh writing engine token `sdk/src/internal/livekitToken.ts:L28-L56`.

### 4. Error handling and resilience

- [VERIFIED] Error class `AwaazLabsUvaVoiceError` with codes union. `sdk/src/internal/errors.ts:L18-L36`
- [VERIFIED] HTTP mapping: 404→`agent_not_found`; 429 body→`rate_limit`|`quota_exceeded`|opaque `quota_exceeded`; body signals→`worker_not_ready`|`provider_limit`; else `session_failed`. `sdk/src/internal/errors.ts:L58-L87`
- [VERIFIED] Abort → `timeout`. `sdk/src/internal/http.ts:L20-L23`
- [VERIFIED] Mint/LiveKit failures reset state, disable mic, disconnect on LiveKit fail. `sdk/src/index.ts:L291-L312`
- [VERIFIED] Empty/log-only catches: mic pre-enable `.catch(() => {})` `L258-L260`; mint cleanup `.catch(() => {})` `L293`; disconnect `.catch(() => {})` `L381`; `element.play().catch(() => {})` `L539-L541`; refresh transient `catch { }` `L645-L647`; listener throw → `console.error` then continue `L416-L418`
- [VERIFIED] Auth refresh 401/403 → emit `token_refresh_failed`, `disconnect`. `sdk/src/index.ts:L622-L658`
- [VERIFIED] Exhausted refresh → emit `token_refresh_failed`, disconnect. `sdk/src/index.ts:L681-L687`
- Circuit breaker / `unhandledRejection` handler: NOT FOUND (searched `sdk/src`).

### 5. Security surface

- Auth: [VERIFIED] `publishableKey` sent in mint body; comment says never authorises. `sdk/src/index.ts:L26-L28`, `L275-L278`. Tokens from host session response held in `session.token`. `L109-L115`, `L348-L349`. Refresh sends Bearer session token. `L616-L617`. Key rotation: N/A in client package.
- Webhook verification: N/A (no webhook server).
- Input validation: [VERIFIED] non-empty `publishableKey`, `sessionEndpoint`, `agentId`; incomplete session response rejected. `sdk/src/index.ts:L187-L192`, `L244-L246`, `L287-L289`. NO LIMIT FOUND on JSON body size (browser fetch).
- Multi-tenant: [VERIFIED] tenant identity via host-supplied `publishableKey` + `agentId` only; no org ID enforcement in SDK. `sdk/src/index.ts:L275-L278`
- Secrets: [VERIFIED] package description "zero secrets" `sdk/package.json:L4`. Session JWT held in memory field; NOT FOUND logged in `sdk/src` (only `console.error` for listener throws `sdk/src/index.ts:L418`).
- Outbound URL: [VERIFIED] `sessionEndpoint`, `refreshEndpoint`, `listVoices(endpointUrl)`, `session.refreshUrl` resolved with `new URL(..., sessionEndpoint)`. `sdk/src/index.ts:L167-L172`, `L266-L267`, `L690-L710`. child_process/eval/new Function: NOT FOUND (searched `sdk/src`).
- User text → LLM/tools: N/A in this package (transcripts emitted to host listeners only) `sdk/src/index.ts:L451-L457`.
- PII: [VERIFIED] transcript text emitted to listeners `L456`; remote audio elements in DOM `L533-L535`. Storage/logging of recordings: NOT FOUND in package.
- Dependencies: [VERIFIED] runtime `livekit-client ^2.0.0` `sdk/package.json:L45-L47`. Lockfile: optional `fsevents` has `"hasInstallScript": true` `sdk/package-lock.json:L561-L567`. Peer `"*"` ranges appear under transitive optional peers (e.g. `@types/deep-eql": "*"`, `rxjs": "*"`) `sdk/package-lock.json:L332`, `L1125`. `"deprecated"` / git URL deps: NOT FOUND (searched lockfile). `prepublishOnly` runs build+lint `sdk/package.json:L43`.

### 6. Observability

- [VERIFIED] Logger: `console.error` only for throwing event listeners. `sdk/src/index.ts:L416-L418`
- [VERIFIED] Events: `connect_timing`, `turn_latency`, `metrics_updated`, `error`, etc. `sdk/src/index.ts:L79-L90`, `L117-L136`
- Metrics/tracing frameworks: NOT FOUND in `sdk/src`. Correlation IDs: NOT FOUND. Hot-path logging of secrets/PII: NOT FOUND beyond listener error object dump `L418`.

NOT READ: `sdk/README.md`, `sdk/CHANGELOG.md`, `sdk/dist/**`, test files bodies beyond existence noted in structural map.

---

## Package: `@awaazlabs-uva/agents` (`sdk-server/`)

### 1. Lifecycle and state

- [VERIFIED] No session/call lifecycle; client constructs with `tenantId`/`tenantSecret`/`baseUrl` and issues signed HTTP to `/machine/*`. `sdk-server/src/index.ts:L184-L189`, `L191-L211`, `L240-L267`
- [VERIFIED] No module globals / Maps of sessions. State = constructor options only. `sdk-server/src/index.ts:L185`
- Growing structures: N/A — NO CLEANUP PATH FOUND (stateless per request).

### 2. Concurrency model

- [VERIFIED] Async `fetch` per `request()`. `sdk-server/src/index.ts:L240-L267`
- Workers/queues/locks: NOT FOUND. AbortController/timeout: NOT FOUND (NO LIMIT FOUND for fetch timeout). Retry/backoff/circuit breaker: NOT FOUND (NO LIMIT FOUND). Max in-flight: NO LIMIT FOUND.

### 3. Real-time audio/data path

N/A: package is agent-management HTTP client only (`createAgent`/`listAgents`/`updateAgent`/capabilities/numbers). `sdk-server/src/index.ts:L191-L310`

### 4. Error handling and resilience

- [VERIFIED] Non-OK → `AwaazLabsUvaAgentsError(status, message, code?)`; object `detail.reason`/`detail.code` parsed. `sdk-server/src/index.ts:L143-L155`, `L270-L280`
- [VERIFIED] Constructor throws plain `Error` if options empty. `sdk-server/src/index.ts:L186-L188`
- [VERIFIED] `JSON.parse(text)` on response with no try/catch around parse. `sdk-server/src/index.ts:L269`
- Unhandled rejection handler: NOT FOUND. Retries/fallbacks: NOT FOUND.

### 5. Security surface

- Auth: [VERIFIED] HMAC-SHA256 over `tenantId.ts.nonce.action.bodyHash`; headers `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature`; body hash = SHA-256 of canonical JSON. `sdk-server/src/index.ts:L160-L182`, `L246-L259`. Secret held in `options.tenantSecret` (file header SERVER-SIDE ONLY). `L1-L9`, `L16-L17`. Rotation: N/A in client.
- Webhook verification: N/A.
- Input validation: [VERIFIED] non-empty constructor fields; method params passed through to JSON body without schema/size limits in client. `sdk-server/src/index.ts:L186-L211`. Prompt size: NO LIMIT FOUND client-side.
- Multi-tenant: [VERIFIED] `X-Tenant-Id` = constructor `tenantId`. `sdk-server/src/index.ts:L255`
- Secrets: [VERIFIED] `toolsAuthSecret` may be sent in create/update body. `sdk-server/src/index.ts:L80-L81`, `L210`, `L236`. Response field documents secret never returned (`tools_auth_secret_configured`). `L50-L51`. Logging of secret: NOT FOUND (no logger in package).
- Outbound: [VERIFIED] `fetch(`${baseUrl}${path}`)` — baseUrl user-supplied. `sdk-server/src/index.ts:L262`. eval/child_process: NOT FOUND. Uses `node:crypto` `createHmac`/`randomUUID` and `crypto.subtle.digest`. `L11`, `L178-L181`
- User text → LLM: [VERIFIED] `prompt` / `greeting` fields forwarded to API as agent config (stored remotely; not local LLM call). `sdk-server/src/index.ts:L54-L71`, `L192-L208`
- PII: phone numbers appear on `ManagedNumberRecord.e164_number` response type. `sdk-server/src/index.ts:L129-L134`
- Dependencies: [VERIFIED] `"dependencies": {}` `sdk-server/package.json:L45`. `"*"/"latest"/git/deprecated/hasInstallScript` in `sdk-server/package-lock.json`: NOT FOUND (searched).

### 6. Observability

- Logger/metrics/tracing: NOT FOUND in `sdk-server/src/index.ts`. Correlation IDs: NOT FOUND.

NOT READ: `sdk-server/README.md`, `sdk-server/dist/**`, `sdk-server/test/**` bodies.

---

## Package: `@awaazlabs-uva/telephony` (`telephony/`)

### 1. Lifecycle and state

- [VERIFIED] Client ctor stores `#tenantId`, `#tenantSecret`, `#baseUrl`, `#extraHeaders`, `#fetcher`, `#nowSeconds`, `#nonceFactory`. `telephony/src/index.ts:L58-L80`
- [VERIFIED] Operations are request/response (connect Telnyx, numbers, outbound calls, call status, etc.); no local call session object. `telephony/src/index.ts:L82-L219`
- Growing structures: N/A (stateless). `#extraHeaders` fixed at construct. `L76`

### 2. Concurrency model

- [VERIFIED] Async `request` → `send` → injected/global `fetch`. `telephony/src/index.ts:L221-L251`; `telephony/src/transport.ts:L83-L87`
- Timeout/AbortController/retry/backoff/queue/lock: NOT FOUND in `telephony/src` (NO LIMIT FOUND for fetch timeout, retries, max in-flight).
- [VERIFIED] `assertBackendRuntime` requires `process.versions.node`. `telephony/src/transport.ts:L90-L94`

### 3. Real-time audio/data path

N/A: HTTP client to `/machine/telephony/*` and `/machine/sessions/get` only. `telephony/src/routes.ts:L3-L31`. No PCM/STT/TTS in package.

### 4. Error handling and resilience

- [VERIFIED] Network catch → `createNetworkError()` status 0. `telephony/src/index.ts:L247-L250`; `telephony/src/errors.ts:L34-L39`
- [VERIFIED] Non-OK → `errorFromResponse` with sanitized detail; invalid JSON → `telephony_invalid_response`. `telephony/src/index.ts:L255-L261`; `telephony/src/errors.ts:L42-L70`
- [VERIFIED] Error messages redacted (`sk_*`, 64-hex). `telephony/src/errors.ts:L111-L114`
- Retries/fallbacks: NOT FOUND.

### 5. Security surface

- Auth: [VERIFIED] HMAC over `tenantId.timestamp.nonce.action.payloadHash`; headers via `createSignedHeaders`. `telephony/src/signing.ts:L45-L72`. Secret in private field. `telephony/src/index.ts:L60`, `L74`
- Webhook verification: N/A (client does not receive webhooks).
- Input validation: [VERIFIED] `assertNonEmpty` on selected params (apiKey, e164, idempotencyKey, agentId, etc.). `telephony/src/index.ts:L83-L218`; `telephony/src/transport.ts:L97-L100`. Schema/size limits: NO LIMIT FOUND beyond non-empty string checks.
- Multi-tenant: [VERIFIED] `X-Tenant-Id` from options. `telephony/src/signing.ts:L67`
- Secrets: [VERIFIED] `apiKey` / `sipSecret` sent in request bodies for connect/rotate/SIP upsert. `telephony/src/types.ts:L112-L176`; `telephony/src/index.ts:L82-L89`, `L165-L166`. Response sanitizer strips keys including `api_key`, `sip_secret`, `tenant_secret`, `encrypted_*`, `payload`, etc. `telephony/src/transport.ts:L15-L29`, `L111-L118`. Error detail sanitizes sensitive key parts. `telephony/src/errors.ts:L3-L13`, `L87-L108`
- Outbound URL: [VERIFIED] `buildUrl(baseUrl, path)` with path forced to start `/machine/`. `telephony/src/transport.ts:L53-L67`. Auth header override blocked in `sanitizeExtraHeaders`. `L74-L80`. eval/child_process: NOT FOUND.
- User text → LLM: N/A. Outbound call `context` / `recipient` forwarded as JSON. `telephony/src/types.ts:L187-L195`
- PII: [VERIFIED] `toNumber`, `e164Number`, call records returned as API JSON (sanitized keys only). `telephony/src/types.ts:L128-L215`
- Dependencies: [VERIFIED] no `dependencies` key `telephony/package.json:L45-L50`. `"*"/"latest"/git/deprecated/hasInstallScript` in `telephony/package-lock.json`: NOT FOUND (searched).

### 6. Observability

- Logger/console/metrics/tracing: NOT FOUND in `telephony/src`.

NOT READ: `telephony/README.md`, `telephony/dist/**`, `telephony/test/**` bodies.

---

## Package: `uva-tenant-dashboard` (`dashboard/`)

### 1. Lifecycle and state

- [VERIFIED] Browser Supabase client singleton `client` with `persistSession` / `autoRefreshToken`. `dashboard/src/lib/supabaseBrowser.ts:L3-L26`
- [VERIFIED] Portal JWT kept in module `memoryPortalToken` (not localStorage); legacy localStorage key cleared. `dashboard/src/lib/portalAuth.ts:L3-L15`, `L39-L47`, `L87-L97`
- [VERIFIED] Role cached in `sessionStorage` key `uva_portal_role`. `dashboard/src/lib/portalAuth.ts:L6`, `L63-L79`
- [VERIFIED] Overview snapshot cache in `sessionStorage` key `uva_overview_snapshot_v1`, TTL 15 min. `dashboard/src/lib/overviewCache.ts:L3-L19`
- [VERIFIED] Test Studio uses `@awaazlabs-uva/voice` (import). `dashboard/src/app/test-studio/page.tsx:L6` (from structural map; file present)
- Growing structures: sessionStorage caches above — browser clears on tab/session end; overview TTL expiry `dashboard/src/lib/overviewCache.ts:L18`. Module singleton Supabase client — NO CLEANUP PATH FOUND beyond page unload.

### 2. Concurrency model

- [VERIFIED] `SWRConfig`: `revalidateOnFocus: false`, `revalidateOnReconnect: true`, `dedupingInterval: 5000`, `errorRetryCount: 2`. `dashboard/src/components/SwrProvider.tsx:L11-L19`
- Worker threads / rate limits in sampled dashboard libs: NOT FOUND (searched `dashboard/src/lib`, `dashboard/src/components/SwrProvider.tsx`).

### 3. Real-time audio/data path

- [VERIFIED] Voice path delegated to `@awaazlabs-uva/voice` in Test Studio. `dashboard/src/app/test-studio/page.tsx:L6`; `dashboard/package.json:L12-L13`
- STT/LLM/TTS inside dashboard: N/A (browser SDK + portal APIs). Codecs: NOT FOUND in sampled dashboard libs.

### 4. Error handling and resilience

- [VERIFIED] `PortalAuthError` class. `dashboard/src/lib/portalAuth.ts:L37`
- [VERIFIED] overview cache read/write empty catches. `dashboard/src/lib/overviewCache.ts:L20-L21`, `L30-L31`
- Full page-level try/catch inventory: NOT READ (dashboard `src` 73 files; sampled libs + grep only).

### 5. Security surface

- Auth: [VERIFIED] Supabase browser anon client. `dashboard/src/lib/supabaseBrowser.ts:L10-L26`. Portal Bearer from memory + cookie flow described in comments. `dashboard/src/lib/portalAuth.ts:L8-L13`, `L55-L60`
- [VERIFIED] Credentials UI surfaces `hmac_secret` for owners (copy into host env). `dashboard/src/app/credentials/page.tsx:L147-L153`, `L192-L206`, `L322-L346`
- Webhook verification: N/A in dashboard.
- Input validation: portal bodies built in UI; server-side validation is portal API (outside this package). Client schema limits: NOT FOUND in sampled libs.
- Multi-tenant: [VERIFIED] portal JWT/`tenant_id` from login response type. `dashboard/src/lib/portalAuth.ts:L21-L27`
- Secrets: [VERIFIED] docs/UI state HMAC must not ship in frontend env. `dashboard/src/app/credentials/page.tsx:L177`, `L464`. Env reads: `NEXT_PUBLIC_*` only in sampled libs `dashboard/src/lib/supabaseBrowser.ts:L10-L11`; `dashboard/src/lib/portalApi.ts:L8`; `dashboard/src/lib/telephonyApi.ts:L3`
- Outbound fetch: [VERIFIED] `fetch(`${API_BASE}${path}`)` in telephonyApi. `dashboard/src/lib/telephonyApi.ts:L44`. eval/child_process: NOT FOUND (searched sampled paths).
- User→LLM: agent prompt edited via portal APIs from UI (page bodies NOT READ in full).
- PII: sessions/transcripts fetched via portalApi types include session fields — `dashboard/src/lib/portalApi.ts:L74-L80` (type); storage of transcripts in browser beyond overview cache: NOT FULLY INVENTORIED.
- Dependencies: [VERIFIED] includes `file:../sdk` voice. `dashboard/package.json:L12-L13`. Lockfile `"*"/"latest"/git/deprecated`: NOT FULLY SCANNED (dashboard/package-lock.json present per structural map; deep scan not run).

### 6. Observability

- Structured logger/metrics/tracing in dashboard: NOT FOUND in sampled libs. Console usage: present in various pages (not fully inventoried). Correlation IDs: NOT FOUND in sampled libs.

NOT READ in full: `dashboard/src/app/**` page/component bodies beyond env/import/HMAC greps; `dashboard/src/components/**` except SwrProvider comment; `dashboard/src/content/docs/**` bodies except grep hits.

---

## Package: `awaazlabs-uva-host-tools` (`host-tools/`)

### 1. Lifecycle and state

- [VERIFIED] Process start requires `TOOL_GATEWAY_SECRET`, listens on `PORT` default 3010. `host-tools/src/server.js:L4-L15`
- [VERIFIED] In-memory `appointments: Map` and `idempotency: Map`. `host-tools/src/store.js:L7-L10`
- [VERIFIED] Write tools book/reschedule/cancel mutate appointments; idempotency begin/complete/abort. `host-tools/src/createApp.js:L79-L211`, `L224-L261`; `host-tools/src/store.js:L45-L78`
- Growing structures:
  | Structure | Cleanup |
  |---|---|
  | `appointments` Map | `reset()` clears `host-tools/src/store.js:L81-L83`; NO CLEANUP PATH FOUND on cancel (status set cancelled, entry retained) `host-tools/src/createApp.js:L197-L200` |
  | `idempotency` Map | `abortIdempotent` deletes in_progress only `host-tools/src/store.js:L72-L78`; completed entries retained — NO CLEANUP PATH FOUND for completed keys |

### 2. Concurrency model

- [VERIFIED] Express sync handlers; idempotency gate returns 409 if in progress. `host-tools/src/createApp.js:L234-L239`
- [VERIFIED] JSON body limit `64kb`. `host-tools/src/createApp.js:L40`
- Workers/locks/timeouts/retries: NOT FOUND. Rate limit: NO LIMIT FOUND. Max appointments: NO LIMIT FOUND.

### 3. Real-time audio/data path

N/A: HTTP tool gateway (`/api/tools/*`), no audio processing. `host-tools/src/createApp.js:L54-L219`

### 4. Error handling and resilience

- [VERIFIED] Auth failure 401; missing secret 503. `host-tools/src/createApp.js:L14-L28`
- [VERIFIED] `handleWrite` catch → 500 with `err.message`. `host-tools/src/createApp.js:L244-L252`
- Retries: NOT FOUND.

### 5. Security surface

- Auth: [VERIFIED] Header `x-tool-gateway-secret` or `Authorization: Bearer …` compared with `!==` to config secret. `host-tools/src/createApp.js:L21-L28`
- Webhook verification: N/A (shared-secret header only).
- Input validation: [VERIFIED] required fields for book/reschedule/cancel; strings coerced. `host-tools/src/createApp.js:L95-L103`, `L141-L148`, `L182-L186`
- Multi-tenant: [VERIFIED] `tenant_id` taken from request body and used in store lookup; not bound to authenticated identity beyond shared secret. `host-tools/src/createApp.js:L81`, `L151`, `L225`
- Secrets: [VERIFIED] secret from env; process exits if missing. `host-tools/src/server.js:L5-L9`. Secret not logged in sampled code.
- Debug endpoint lists appointments (includes phone/name) behind same auth. `host-tools/src/createApp.js:L214-L217`
- Outbound fetch/eval/child_process: NOT FOUND.
- User text → LLM: N/A (returns JSON to worker).
- PII: [VERIFIED] stores `customer_name`, `customer_phone` in Map. `host-tools/src/createApp.js:L105-L115`
- Dependencies: [VERIFIED] `dotenv`, `express` `host-tools/package.json` (engines/deps per structural map). Lockfile deep scan: NOT RUN.

### 6. Observability

- [VERIFIED] `console.error` / `console.log` on startup. `host-tools/src/server.js:L8`, `L14-L15`
- Metrics/tracing/correlation: NOT FOUND.

NOT READ: `host-tools` tests beyond existence.

---

## Package: `client-integration-test` (meta, `client-integration-test/`)

### 1. Lifecycle and state

N/A: scripts-only meta package (`install:all`, `dev:*`). `client-integration-test/package.json:L6-L10`. No src.

### 2. Concurrency model

N/A: no runtime source.

### 3. Real-time audio/data path

N/A.

### 4. Error handling and resilience

N/A.

### 5. Security surface

N/A (no runtime). Dependencies: none in package.json. `client-integration-test/package.json:L1-L11`

### 6. Observability

N/A.

---

## Package: `client-integration-test-frontend` (`client-integration-test/frontend/`)

### 1. Lifecycle and state

- [VERIFIED] Module `agent: AwaazLabsUvaVoice | null` and `state` object (transcript array, debugLog, timing). `client-integration-test/frontend/src/main.ts:L129-L150`
- [VERIFIED] Env defaults for publishableKey/sessionEndpoint/refresh/agentId/fetchTimeoutMs. `client-integration-test/frontend/src/main.ts:L95-L101`
- Growing: `state.transcript` / `state.debugLog` — cleanup path NOT FULLY READ (file 1601 LOC; read L1-L150 only).

### 2. Concurrency model

- [VERIFIED] `pipelineApplyTimer` / `pipelineApplyInFlight` for pipeline apply. `client-integration-test/frontend/src/main.ts:L149-L150`
- [VERIFIED] Default fetch timeout 15000 from env. `client-integration-test/frontend/src/main.ts:L100`
- Full concurrency inventory: NOT READ (remainder of `main.ts`, `telephonyPanel`).

### 3. Real-time audio/data path

- [VERIFIED] Uses `@awaazlabs-uva/voice` events (`TranscriptEvent`, `MetricsEvent`). `client-integration-test/frontend/src/main.ts:L1-L6`
- Timing snapshot fields for mint/LiveKit/turn stages. `client-integration-test/frontend/src/main.ts:L46-L66`
- STT/LLM/TTS: via worker after SDK connect (not implemented in frontend). Codec details: NOT FOUND in read portion.

### 4. Error handling and resilience

- [VERIFIED] Local `ERROR_TAXONOMY` documents SDK codes. `client-integration-test/frontend/src/main.ts:L84-L93`
- Full catch coverage: NOT READ (remainder of file).

### 5. Security surface

- [VERIFIED] Browser env `VITE_UVA_*` publishable key + session endpoints. `client-integration-test/frontend/src/main.ts:L95-L101`
- HMAC secret in frontend: NOT FOUND in read portion (uses host sessionEndpoint).
- Vite config deep-imports voice `package.json` (structural map). Dependencies: `@awaazlabs-uva/voice 1.1.0` per structural map.

### 6. Observability

- [VERIFIED] In-UI `debugLog` / timing snapshot (client-side). `client-integration-test/frontend/src/main.ts:L37-L66`, `L141-L142`
- Remote telemetry: NOT FOUND in read portion.

NOT READ: `client-integration-test/frontend/src/main.ts` after L150; `telephonyPanel` module; `style.css`.

---

## Package: `client-integration-test-backend` (`client-integration-test/backend/`)

### 1. Lifecycle and state

- [VERIFIED] Express app; session mint proxies to control plane; agents/telephony demos. `client-integration-test/backend/src/createApp.js:L260-L367` (partial)
- [VERIFIED] Process-local `_capsCache` (TTL 60s) and `_pipelineAppliedByAgent: Map`. `client-integration-test/backend/src/createApp.js:L90-L99`, `L101-L108`, `L251`
- Growing: `_pipelineAppliedByAgent` — NO CLEANUP PATH FOUND (Map set only at L251). `_capsCache` overwritten on TTL refresh `L106-L107`.

### 2. Concurrency model

- [VERIFIED] `express.json()` with no size limit argument. `client-integration-test/backend/src/createApp.js:L262`
- [VERIFIED] CORS: if `allowedOrigins.length === 0` OR origin listed, reflect Origin. `client-integration-test/backend/src/createApp.js:L54-L59`
- Fetch timeout to control plane: NO LIMIT FOUND in createApp mint path (uses fetchImpl without AbortController in read sections).
- Demo hang endpoint never responds (timeout test). `client-integration-test/backend/src/createApp.js:L287-L290`

### 3. Real-time audio/data path

N/A: session mint + pipeline PATCH HTTP only. `client-integration-test/backend/src/createApp.js:L328-L367`

### 4. Error handling and resilience

- [VERIFIED] `normalizeSessionFailure` maps 429/404/worker_not_ready/provider_limit. `client-integration-test/backend/src/createApp.js:L28-L52`
- [VERIFIED] Pipeline/capabilities errors return status + `err.message`. `client-integration-test/backend/src/createApp.js:L305-L348`

### 5. Security surface

- Auth: [VERIFIED] `createControlPlaneHeaders` imported; HMAC over `tenantId.ts.nonce.agentId`. `client-integration-test/backend/src/createApp.js:L2`; `client-integration-test/backend/src/signing.js:L7-L31`
- [VERIFIED] Session mint requires `publishableKey`/`agentId`; rejects unknown publishable key. `client-integration-test/backend/src/createApp.js:L352-L369`
- [VERIFIED] Dynamic import of agents SDK with `tenantSecret: config.hmacSecret`. `client-integration-test/backend/src/createApp.js:L68-L73`
- Secrets in env: [VERIFIED] `UVA_HMAC_SECRET`, `UVA_TENANT_ID`, `UVA_PUBLISHABLE_KEY`, `UVA_CONTROL_PLANE_URL` required; optional `TELNYX_API_KEY` / SIP fields. `client-integration-test/backend/src/config.js:L28-L52`
- Multi-tenant: [VERIFIED] single process `tenantId` from env. `client-integration-test/backend/src/config.js:L38`
- CORS: [VERIFIED] empty allowlist or listed origin reflects `Origin`. `client-integration-test/backend/src/createApp.js:L54-L59`
- [VERIFIED] `/api/demo/config` returns publishableKey + tenantId. `client-integration-test/backend/src/createApp.js:L292-L297`

### 6. Observability

- Structured logger: NOT FOUND in read portions. Healthz JSON. `client-integration-test/backend/src/createApp.js:L276-L284`

NOT READ: remainder of `createApp.js` after ~L370; `telephonyRoutes.js` body; `config.js` body this pass; `server.js` beyond structural map.

---

## Package: `awaazlabs-uva-host-backend-starter` (`client-deliverables-final/host-backend-starter/`)

### 1. Lifecycle and state

- [VERIFIED] Stateless Express: mint + refresh proxy to control plane; no session Map. `client-deliverables-final/host-backend-starter/src/createApp.js:L60-L197`
- Growing structures: N/A.

### 2. Concurrency model

- [VERIFIED] `express.json({ limit: '32kb' })`. `client-deliverables-final/host-backend-starter/src/createApp.js:L63`
- [VERIFIED] CORS: empty allowlist does not reflect Origin. `client-deliverables-final/host-backend-starter/src/createApp.js:L44-L53`
- Upstream fetch timeout / retry: NOT FOUND (searched `client-deliverables-final/host-backend-starter/src/createApp.js` for `AbortController`, `timeout`, `retry`).

### 3. Real-time audio/data path

N/A: Express session mint/refresh proxy only. `client-deliverables-final/host-backend-starter/src/createApp.js:L84-L197`

### 4. Error handling and resilience

- [VERIFIED] Upstream unreachable → 502 with controlPlaneUrl in detail. `client-deliverables-final/host-backend-starter/src/createApp.js:L118-L124`
- [VERIFIED] `normalizeSessionFailure` for 429/404/worker/provider. `client-deliverables-final/host-backend-starter/src/createApp.js:L22-L41`
- [VERIFIED] `readJsonSafely` catch returns `{ raw: text }`. `client-deliverables-final/host-backend-starter/src/createApp.js:L4-L12`

### 5. Security surface

- Auth: [VERIFIED] publishableKey equality check. `client-deliverables-final/host-backend-starter/src/createApp.js:L91-L94`
- [VERIFIED] HMAC headers for CP: `X-Tenant-Id`/`X-Timestamp`/`X-Nonce`/`X-Signature` over `tenantId.ts.nonce.agentId`. `client-deliverables-final/host-backend-starter/src/signing.js:L9-L39`
- [VERIFIED] Optional `verified_caller_phone` forwarded to mint body. `client-deliverables-final/host-backend-starter/src/createApp.js:L103-L107`
- Refresh: Bearer or body token to CP. `client-deliverables-final/host-backend-starter/src/createApp.js:L147-L170`
- Secrets: [VERIFIED] session response returns `token`/`wsUrl`/`roomName`/`refreshUrl`/`expiresIn` (not HMAC secret). `client-deliverables-final/host-backend-starter/src/createApp.js:L138-L144`
- eval/child_process: NOT FOUND (searched `client-deliverables-final/host-backend-starter/src`).

### 6. Observability

- Logger/metrics: NOT FOUND (searched `client-deliverables-final/host-backend-starter/src/createApp.js`, `signing.js`).

NOT READ: `client-deliverables-final/host-backend-starter/src/config.js`, `server.js` bodies.

---

## Package: `control_plane` (`control_plane/`)

### 1. Lifecycle and state

- [VERIFIED] `POST /v1/session` sync handler; mint uses sync psycopg off event loop (threadpool). `control_plane/app.py:L1-L8`, `L957`
- [VERIFIED] Mint JWT TTL 120s; replay window 60s; HMAC `tenant_id.ts.nonce.agent_id`. `control_plane/mint.py:L27-L28`, `L40-L44`
- [VERIFIED] Mint inserts into `used_nonces` (unique violation → nonce replay). `control_plane/mint.py:L138-L145`
- [VERIFIED] Mint checks agent belongs to tenant; origin allowlist (hosted empty list fails closed). `control_plane/mint.py:L151-L178`
- [VERIFIED] Refresh hard-cap `MAX_REFRESHES = 720`. `control_plane/app.py:L479-L481`
- [VERIFIED] Dispatch failure rollback: `_rollback_dispatched_session` sets `sessions.ended_at` and decrements `quota_state.concurrent_now`. `control_plane/app.py:L751-L766`
- [VERIFIED] In-process `_hits` rate buckets, `_MAX_TRACKED_KEYS=10_000`, prune. `control_plane/app.py:L406-L435`
- Growing structures:
  | Structure | Cleanup |
  |---|---|
  | `_hits` rate buckets | cap 10k + prune `control_plane/app.py:L410-L435` |
  | DB `used_nonces` | insert only in mint `control_plane/mint.py:L138-L145`; prune/delete path: NOT FOUND (searched `control_plane/mint.py`) |
  | DB `sessions` / `quota_state` | rollback on dispatch fail `control_plane/app.py:L751-L766`; normal successful-call teardown endpoint in CP: NOT FOUND (searched `control_plane/app.py` for session-end routes beyond rollback/refresh gates) |

### 2. Concurrency model

- [VERIFIED] Tenant mint rate 120/min; IP pre-auth 240/min. `control_plane/app.py:L71`, `L410`, `L437-L455`
- [VERIFIED] Tenant hit recorded after HMAC success (F-H4 comments). `control_plane/app.py:L401-L404`
- [VERIFIED] `_hits_lock` threading.Lock. `control_plane/app.py:L412`
- [VERIFIED] JWT TTL 120; replay 60. `control_plane/mint.py:L27-L28`
- [VERIFIED] `login_guard` constants 8/identity, 30/IP, 15 min exist in module. `control_plane/login_guard.py:L23-L25`. Import of `login_guard` in `control_plane/app.py`: NOT FOUND (searched `control_plane/app.py` for `login_guard`).
- Circuit breaker: NOT FOUND (searched `control_plane/*.py` for circuit). Concurrent/monthly quota gates described in mint module docstring. `control_plane/mint.py:L3-L7`

### 3. Real-time audio/data path

N/A: mint returns LiveKit token/room; no PCM/STT/TTS codecs in mint/app slices read. `control_plane/mint.py:L3-L7`; `control_plane/app.py:L1-L4`

### 4. Error handling and resilience

- [VERIFIED] `MintError(status, reason)`. `control_plane/mint.py:L31-L37`
- [VERIFIED] Sentry init failure logged, mint continues. `control_plane/app.py:L130-L144`
- Dedicated provider-timeout error class: NOT FOUND (searched `control_plane/mint.py`, `control_plane/app.py` for `TimeoutError` class definitions).

### 5. Security surface

- Auth: [VERIFIED] HMAC-SHA256 mint signature. `control_plane/mint.py:L40-L44`
- Multi-tenant: [VERIFIED] agent ownership IDOR guard + origin allowlist in mint. `control_plane/mint.py:L151-L178`
- Secrets: [VERIFIED] `DbSecretProvider` / `EnvSecretProvider` imported. `control_plane/app.py:L52-L53`. Raw secret logging in `mint.py`: NOT FOUND (searched `control_plane/mint.py` for `secret` log calls).
- eval/subprocess: NOT FOUND (searched `control_plane/*.py` for `eval(`, `subprocess`).
- Webhooks: N/A in control_plane.

### 6. Observability

- [VERIFIED] Optional Sentry `traces_sample_rate=0.1`. `control_plane/app.py:L130-L137`
- [VERIFIED] Imports `record_mint_rejection` from `admin.audit`. `control_plane/app.py:L58`
- Prometheus/OTel: NOT FOUND (searched `control_plane/*.py` for `prometheus`, `opentelemetry`).

NOT READ in full: `control_plane/static/dev_sandbox.html`; full dispatch/refresh handler bodies in `app.py`; `secrets_db.py`; `warm.py`.

---

## Package: `worker` (`worker/`)

### 1. Lifecycle and state

- [VERIFIED] Entry: load `.env.local`, `prewarm`, optional health HTTP, `cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, …))`. `worker/main.py:L1575-L1629`
- [VERIFIED] Idle processes default 3 (`LIVEKIT_NUM_IDLE_PROCESSES`); init timeout default 60s. `worker/main.py:L1622-L1628`
- [VERIFIED] Close/quota release via `release_session_quota_slot` (sets session ended, decrements concurrent). `worker/session_close.py:L72-L86`
- Growing structures (verified subset):
  | Structure | Cleanup |
  |---|---|
  | `_http_client` tools httpx client | aclose on loop change `worker/tools.py:L36-L37`, `L170-L186` |
  | Other session Maps/caches (`config.py`, `provider_client_cache.py`, `greeting_cache.py`, `latency.py` `_turns`) | NOT READ this pass — see NOT READ list |

### 2. Concurrency model

- [VERIFIED] Provider connect retries default max_retry=1, interval=1.0s, timeout=30s; env caps max_retry≤5. `worker/provider_retries.py:L17-L19`, `L83-L107`, `L110-L133`
- [VERIFIED] Tool HTTP timeouts connect 1 / read 4 / write 2 / pool 1; max_connections 16. `worker/tools.py:L32-L33`
- [VERIFIED] Interruption defaults WebRTC min_duration 0.65; telephony 0.55; mode env `UVA_INTERRUPTION_MODE` default `vad`. `worker/latency.py:L51-L57`, `L73-L80`, `L91-L101`
- [VERIFIED] Job runners: `num_idle_processes` / `initialize_process_timeout`; stale reject via `request_fnc`. `worker/main.py:L1614-L1628`
- [VERIFIED] Tools comment: tool RTT on critical path before second LLM+TTS turn. `worker/tools.py:L31-L32`

### 3. Real-time audio/data path

- [VERIFIED] Assembly registry: STT gladia|deepgram; LLM gemini|groq; TTS uplift|cartesia|elevenlabs|rime; unrecognized raises `UnsupportedProviderError` (no silent fallback). `worker/providers/registry.py:L11-L12`, `L32-L80`
- [VERIFIED] Turn handling: interruption enabled, endpointing min/max delay, preemptive generation/TTS (WebRTC profile). `worker/latency.py:L43-L66`
- [VERIFIED] Telephony profile disables preemptive by default in `TELEPHONY_TURN_HANDLING_OPTIONS`. `worker/latency.py:L73-L88`
- [VERIFIED] Latency publish to room opt-in `UVA_PUBLISH_TURN_LATENCY` default off; server INFO always. `worker/latency.py:L7-L8`, `L28-L37`
- [VERIFIED] Tools POST to `{base}{path}` with SSRF guard `prepare_tools_post_url`. `worker/tools.py:L236-L274`; `worker/ssrf_guard.py:L1-L5`, `L31-L34`
- Codec/sample-rate constants in TTS/STT adapters: NOT READ this pass (searched not opened: `worker/providers/tts/*`, `worker/providers/stt/*` beyond registry).
- [VERIFIED] Voice SDK documents AEC to reduce Silero barge-in; worker interruption min_duration settings as above. `sdk/src/index.ts:L11-L13`; `worker/latency.py:L47-L56`

### 4. Error handling and resilience

- [VERIFIED] Tool failures → `{"error": …, "success": False}` catch-all. `worker/tools.py:L291-L292`
- [VERIFIED] SSRF → structured error without POST. `worker/tools.py:L271-L274`
- [VERIFIED] `UnsupportedProviderError`. `worker/providers/registry.py:L20-L21`, `L43`
- [VERIFIED] `ToolsSsrfError`. `worker/ssrf_guard.py:L31-L34`
- Empty-catch inventory across `worker/main.py`: NOT READ in full (`worker/main.py` ~1630 lines; only entry + cited slices).

### 5. Security surface

- Auth to tools: [VERIFIED] `x-tool-gateway-secret`; refuse POST without secret. `worker/tools.py:L164-L167`, `L249-L255`
- [VERIFIED] Env fallbacks `UVA_TOOLS_BASE_URL`, `TOOL_GATEWAY_SECRET`. `worker/tools.py:L144-L161`
- [VERIFIED] SSRF: hosted checks, block private/metadata names. `worker/ssrf_guard.py:L1-L5`, `L19-L28`
- User text → LLM/tools: [VERIFIED] tool JSON includes `tenant_id`/`agent_id` plus tool payload. `worker/tools.py:L259-L263`. Prompt framing: `worker/main.py:L1-L7`
- PII: [VERIFIED] `UVA_LOG_TRANSCRIPTS` default off; when on, text capped (`UVA_LOG_TRANSCRIPT_CHARS` default 200). `worker/transcript_logging.py:L1-L5`, `L17-L22`, `L25-L49`. Close path accepts `transcript` arg. `worker/session_close.py:L72-L79`
- eval/subprocess: NOT FOUND (searched `worker/*.py` for `eval(`, `subprocess.`); process model comments at `worker/main.py:L1614-L1615`

### 6. Observability

- [VERIFIED] Logger `worker.latency`, `worker.tools`. `worker/latency.py:L22`; `worker/tools.py:L29`
- [VERIFIED] Optional health HTTP via `UVA_WORKER_HEALTH_PORT`. `worker/main.py:L1607-L1610`
- [VERIFIED] Turn latency room publish gated. `worker/latency.py:L28-L37`

NOT READ in full: majority of 63 worker modules (adapters, humanization, recording, telephony_runtime, usage, prompt_dump, etc.). See structural map scope.

---

## Package: `tenant_portal_api` (`tenant_portal_api/`)

### 1. Lifecycle and state

- [VERIFIED] Machine auth burns nonce into `used_nonces`. `tenant_portal_api/machine_auth.py:L173-L179`
- [VERIFIED] Webhook seen-signature / seen-event-id OrderedDicts max 20_000. `tenant_portal_api/telephony_webhooks.py:L40-L45`, `L71-L75`
- [VERIFIED] Call platform status mapping from Telnyx event types. `tenant_portal_api/telephony_webhooks.py:L123-L140`
- Growing structures:
  | Structure | Cleanup |
  |---|---|
  | `_hits` machine rate windows | prune + 10k cap `tenant_portal_api/machine_auth.py:L37-L44`, `L79-L87` |
  | `_seen_webhook_signatures` / `_seen_webhook_event_ids` | LRU trim 20k `tenant_portal_api/telephony_webhooks.py:L43-L45`, `L71-L75` |
  | `_webhook_hits` | trim while > max `tenant_portal_api/telephony_webhooks.py:L66-L67` |
  | DB telephony tables / idempotency | `telephony_service.py`, `telephony_reconcile.py`, `telephony_queries.py` NOT READ this pass |

### 2. Concurrency model

- [VERIFIED] Machine rate: 30/min per tenant (after auth), 120/min per IP pre-auth. `tenant_portal_api/machine_auth.py:L37-L39`, `L135-L142`, `L184-L185`
- [VERIFIED] Webhook IP rate 600/min before signature verify. `tenant_portal_api/telephony_webhooks.py:L52-L68`
- [VERIFIED] Webhook body cap 256 KiB; replay window 300s; signature replay key rejected. `tenant_portal_api/telephony_webhooks.py:L35-L36`, `L40`, `L169-L174`
- Telnyx/LiveKit client timeouts: NOT READ (`tenant_portal_api/telnyx_client.py`, `livekit_sip.py` bodies).

### 3. Real-time audio/data path

- [VERIFIED] Telnyx webhook path verifies Ed25519 signatures (no media decode in this module). `tenant_portal_api/telephony_webhooks.py:L143-L190`
- PCM/STT/TTS in portal: NOT FOUND (searched `tenant_portal_api/telephony_webhooks.py`, `machine_auth.py`). SIP/LiveKit orchestration modules: NOT READ (`tenant_portal_api/livekit_sip.py`, `telephony_service.py`).

### 4. Error handling and resilience

- [VERIFIED] `MachineAuthError` with status/reason. `tenant_portal_api/machine_auth.py:L48-L54`
- [VERIFIED] Webhook signature fail path returns False / logged exception class name. `tenant_portal_api/telephony_webhooks.py:L183-L187`
- Provider error redaction: NOT READ (`tenant_portal_api/telephony_errors.py`).

### 5. Security surface

- Auth (machine): [VERIFIED] HMAC message `tenant_id.ts.nonce.action.body_hash`; `hmac.compare_digest`; skew vs `REPLAY_WINDOW_SEC` imported from `control_plane.mint`. `tenant_portal_api/machine_auth.py:L34`, `L57-L76`, `L157-L171`; `control_plane/mint.py:L27`
- Webhook: [VERIFIED] Ed25519 over `{timestamp}|{raw_body}`; mock mode may return True when no public key. `tenant_portal_api/telephony_webhooks.py:L143-L160`, `L176-L182`
- Input validation: [VERIFIED] `MAX_AGENTS_PER_TENANT` from `PORTAL_MAX_AGENTS_PER_TENANT` default `"100"`; `MAX_PROMPT_CHARS=24000`; `MAX_GREETING_CHARS=2000`; `MAX_PAGE_LIMIT=200`; `CreateAgentBody.prompt` max_length uses `MAX_PROMPT_CHARS`. `tenant_portal_api/app.py:L150-L161`. Remaining route schemas: NOT READ (`tenant_portal_api/app.py` remainder, `telephony_models.py`).
- Multi-tenant: [VERIFIED] machine auth loads tenant status + secret by `tenant_id`. `tenant_portal_api/machine_auth.py:L144-L161`
- Secrets / credential encryption / tools_base_url save-time SSRF: NOT READ (`tenant_portal_api/telephony_credentials.py`, `tools_webhook.py`). Worker request-time tools SSRF: `worker/ssrf_guard.py:L1-L5`
- child_process/eval: NOT FOUND (searched `tenant_portal_api/**/*.py` for `subprocess`, `eval(`).
- PII storage paths (phones/transcripts/recordings): NOT READ (`tenant_portal_api/recording_urls.py`, `telephony_service.py` call rows).

### 6. Observability

- [VERIFIED] `logging.getLogger(__name__)` in webhooks. `tenant_portal_api/telephony_webhooks.py:L33`
- Prometheus/OTel: NOT FOUND (searched `tenant_portal_api/**/*.py` for `prometheus`, `opentelemetry`).

NOT READ in full: `telephony_service.py`, most of `app.py` routes, `queries.py`, `provider_validation.py`, `test_studio.py`, `membership.py`, `telnyx_client.py`, `livekit_sip.py`, `telephony_credentials.py`, `tools_webhook.py`, `recording_urls.py`.

---

## Package: `admin` (`admin/`)

### 1. Lifecycle and state

- [VERIFIED] Admin JWT secret from env or local generation into `.env.local`. `admin/app.py:L73-L102` (function `_ensure_admin_jwt_secret`)
- [VERIFIED] Login route uses `assert_not_throttled` / `record_attempt` from login_guard. `admin/app.py:L240-L276`
- Server-side session Map: NOT FOUND (searched `admin/app.py` for `Map`/`dict` session stores).
- Growing: login throttle uses `login_attempts` table when present. `control_plane/login_guard.py:L23-L25`, `L35-L41`

### 2. Concurrency model

- [VERIFIED] Login throttle limits: 8 failures/identity, 30/IP, 15-minute window. `control_plane/login_guard.py:L23-L25`
- [VERIFIED] Comment on login_route documents prior lack of rate limit (F-H14) now using throttle. `admin/app.py:L242-L244`
- DB connect_timeout=10 on admin conn helper. `admin/app.py:L153`

### 3. Real-time audio/data path

N/A: admin is HTTP portal for tenants/secrets (no media modules in `admin/*.py` sampled). Searched: `admin/app.py`, `admin/auth.py`, `admin/security.py`.

### 4. Error handling and resilience

- [VERIFIED] `LoginThrottled` → HTTP 429 with Retry-After. `admin/app.py:L251-L256`
- [VERIFIED] `AdminAuthError` → HTTP with reason; failed attempt recorded. `admin/app.py:L266-L276`

### 5. Security surface

- Auth: [VERIFIED] Admin auth documented as separate domain from tenant/LiveKit mint. `admin/auth.py:L1-L8`. Password PBKDF2 + TOTP HMAC. `admin/security.py:L30-L50`, `L63`
- [VERIFIED] Rotate tenant secret returns raw `new_hmac_secret` once. `admin/app.py:L366-L387`
- Multi-tenant: [VERIFIED] rotate route takes any `tenant_id` path param under admin auth. `admin/app.py:L366-L386`
- Secrets: [VERIFIED] rotate response includes `new_hmac_secret`. `admin/app.py:L383-L387`. Logging of that secret in route: NOT FOUND (searched `admin/app.py` rotate handler).
- eval/subprocess: NOT FOUND (searched `admin/*.py` for `eval(`, `subprocess`).

### 6. Observability

- [VERIFIED] `admin.audit` logger for mint_rejections insert failures. `admin/audit.py:L29`, `L51`
- `record_admin_action` on routes (e.g. rotate). `admin/app.py:L377-L381`

NOT READ: full `admin/queries.py`, all admin routes, frontend if any.

---

## Package: `services` (`services/`)

### 1. Lifecycle and state

- [VERIFIED] Package marker only. `services/__init__.py:L1`
- [VERIFIED] `tts_cache.get/require` reads fixture WAV files under `tests/fixtures/tts` via manifest; no process session registry. `services/tts_cache.py:L7-L42`

### 2. Concurrency model

- Locks/queues/limits: NOT FOUND (searched `services/tts_cache.py`). File reads per call. `services/tts_cache.py:L19-L34`

### 3. Real-time audio/data path

- [VERIFIED] Fixture PCM/WAV helpers; `SAMPLE_RATE = 22050`, 16-bit mono. `services/tts_cache.py:L10-L12`, `L55-L62`
- Not a live STT/LLM/TTS pipeline.

### 4. Error handling and resilience

- [VERIFIED] Manifest JSON parse failure → `{}`. `services/tts_cache.py:L21-L24`
- [VERIFIED] `require` raises `LookupError` on miss. `services/tts_cache.py:L45-L52`

### 5. Security surface

- Auth/webhooks/multi-tenant: N/A.
- [VERIFIED] Cache key = sha256(`voice_id|text`) hex truncate 32. `services/tts_cache.py:L15-L16`
- Path ops: reads under fixed `FIX_DIR`. `services/tts_cache.py:L7-L8`, `L32-L34`
- eval/child_process: NOT FOUND.

### 6. Observability

- Logger/metrics: NOT FOUND in `services/tts_cache.py`.

---

## Cross-cutting note (graphify)

| Item | Status | Citation |
|---|---|---|
| graphify navigation | NOT FOUND | searched `graphify-out/`, `graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md` |

## Files intentionally not fully read (global)

- `worker/**` except cited slices (~63 modules)
- `tenant_portal_api/telephony_service.py`, most of `app.py` route bodies, `queries.py`, `telnyx_client.py`, `livekit_sip.py`, `telephony_credentials.py`, `tools_webhook.py`
- `control_plane/app.py` beyond rate-limit/Sentry/refresh-cap slices; `secrets_db.py` body
- `dashboard/src/app/**` and most components
- `docs/**`, `tests/**`, `supabase/migrations/**`, `self-serve-demo-UI/`, `voice-picker/`, `state/`, `scripts/**`
- All `dist/` and most README bodies
