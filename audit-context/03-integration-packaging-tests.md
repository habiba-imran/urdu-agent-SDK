# Integration path, contracts, packaging, examples, tests

Index: `audit-context/01-structural-map.md` (filename on disk; not `01-structure.md`).

Scope note [VERIFIED]: graphify-out absent (`graphify-out/`, `graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md`). Published npm packages covered file-by-file under `sdk/`, `sdk-server/`, `telephony/`. Examples/docs/CI read as cited. NOT READ in full: `client-integration-test/frontend/src/main.ts` beyond connect/init/event bind slices; `client-integration-test/frontend/src/telephonyPanel.ts` body beyond import/header; `dashboard/src/content/docs/pages/*.ts` bodies beyond cited greps/reads; `client-deliverables-final/*.md` beyond cited slices; `worker/**` provider adapters (extension for STT/TTS/LLM is via agents API fields, not npm package adapters); `docs/**` beyond `HOST_BACKEND_CONTRACT.md` and provenance-grep hits.

---

## Cross-package README / docs vs code disagreements

| Observation | Tag | Citation |
|---|---|---|
| `sdk/README.md` Constructor lists `publishableKey`, `sessionEndpoint`, `refreshEndpoint`, `fetchTimeoutMs` only; code also accepts `sessionHeaders`, `sessionCredentials` | [VERIFIED] | `sdk/README.md:L62-L69`; `sdk/src/index.ts:L26-L48` |
| `sdk/README.md` Read-only properties omit `connectTiming`; code exposes getter | [VERIFIED] | `sdk/README.md:L80-L82`; `sdk/src/index.ts:L224-L227` |
| `ConnectOptions.voiceId` exists in types; `connect()` POST body sends only `publishableKey` + `agentId` (no `voiceId` read) | [VERIFIED] | `sdk/src/index.ts:L52-L55`; `sdk/src/index.ts:L275-L278` |
| `sdk/README.md` links `docs/HOST_BACKEND_CONTRACT.md` as session contract; that file states it is superseded | [VERIFIED] | `sdk/README.md:L21`; `sdk/README.md:L123`; `docs/HOST_BACKEND_CONTRACT.md:L1-L12` |
| `telephony/README.md` claims releases publish “with npm provenance”; `release-sdk.yml` comment and publish step omit `--provenance` | [VERIFIED] | `telephony/README.md:L23`; `.github/workflows/release-sdk.yml:L14-L15`; `.github/workflows/release-sdk.yml:L155-L156` |
| `telephony/CHANGELOG.md` states release path publishes “with npm provenance”; workflow omits `--provenance` | [VERIFIED] | `telephony/CHANGELOG.md:L31-L32`; `.github/workflows/release-sdk.yml:L155-L156` |
| Dashboard lifecycle doc sketch is `idle → connect() → connected → …`; code emits `connect_timing` then `connected` | [VERIFIED] | `dashboard/src/content/docs/pages/events-and-lifecycle.ts:L11-L13`; `sdk/src/index.ts:L328-L331` |

---

## Package: `@awaazlabs-uva/voice` (`sdk/`)

### 1. Integration path (code-required)

| Step | What code requires | Tag | Citation |
|---|---|---|---|
| Install | npm package `@awaazlabs-uva/voice`; dependency `livekit-client ^2.0.0` | [VERIFIED] | `sdk/package.json:L2`; `sdk/package.json:L45-L47` |
| Import | ESM named export `AwaazLabsUvaVoice` from package root | [VERIFIED] | `sdk/src/index.ts:L151`; `sdk/package.json:L25-L33` |
| Construct | `new AwaazLabsUvaVoice({ publishableKey, sessionEndpoint, … })`; throws if either string is blank after trim | [VERIFIED] | `sdk/src/index.ts:L185-L192` |
| Optional construct fields | `refreshEndpoint?`, `sessionHeaders?`, `sessionCredentials?` (default `'same-origin'`), `fetchTimeoutMs?` (default `15000`) | [VERIFIED] | `sdk/src/index.ts:L26-L48`; `sdk/src/internal/http.ts:L8-L9`; `sdk/src/index.ts:L195-L197`; `sdk/src/index.ts:L270` |
| Prerequisite (host) | Host must implement POST session endpoint returning `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }` | [VERIFIED] | `sdk/src/index.ts:L109-L115`; `sdk/src/index.ts:L266-L290` |
| Prerequisite (browser) | Mic enable after LiveKit join; failure throws `session_failed` “microphone permission denied or unavailable” | [VERIFIED] | `sdk/src/index.ts:L333-L346` |
| First call | `await voice.connect({ agentId })` — POST JSON `{ publishableKey, agentId }` to `sessionEndpoint`, then `room.connect(wsUrl, token)` | [VERIFIED] | `sdk/src/index.ts:L240-L306` |
| Events | `on`/`off` available; `connect` emits `connect_timing`/`connected` without requiring prior registration | [VERIFIED] | `sdk/src/index.ts:L354-L365`; `sdk/src/index.ts:L328-L331` |
| Teardown | `await voice.disconnect()` | [VERIFIED] | `sdk/src/index.ts:L367-L398` |

| Topic | Fact | Tag | Citation |
|---|---|---|---|
| Required init order | Construct → `connect` → (`setMicMuted` / `startAudio` while connected) → `disconnect`. Second `connect` without disconnect throws “already connected” | [VERIFIED] | `sdk/src/index.ts:L185-L192`; `sdk/src/index.ts:L234-L238`; `sdk/src/index.ts:L240-L243`; `sdk/src/index.ts:L406-L409`; `sdk/src/index.ts:L367-L398` |
| Implicit env var reads in package | NOT FOUND (searched: `process.env`, `import.meta` under `sdk/src`) | [VERIFIED] | NOT FOUND (searched: `process.env`, `import.meta` in `sdk/src/**/*.ts`) |
| Global singletons in package | NOT FOUND — per-instance `Map` listeners / room state on class instance | [VERIFIED] | `sdk/src/index.ts:L151-L165` |
| Import-time side effects (this package) | Top-level: `livekit-client` import + `MIC_CAPTURE_OPTIONS` const; no `document` access at import | [VERIFIED] | `sdk/src/index.ts:L1-L19`; DOM guarded at `sdk/src/index.ts:L531-L536` |
| Hidden host refresh | If response has `refreshUrl`, refresh uses it (resolved against `sessionEndpoint`); else `refreshEndpoint`; else `<sessionEndpoint>/refresh` (special-case if endpoint ends with `/v1/session`) | [VERIFIED] | `sdk/src/index.ts:L690-L710` |

### 2. Extension points

| Mechanism | Role | Documented? | Tag | Citation |
|---|---|---|---|---|
| Host `sessionEndpoint` / refresh | Swap mint/refresh backend; SDK only `fetch`es host | yes (`sdk/README.md` session contract) | [VERIFIED] | `sdk/src/index.ts:L26-L32`; `sdk/README.md:L115-L123` |
| `sessionHeaders` / `sessionCredentials` | Inject auth to host mint/refresh (e.g. portal cookie) | partial — JSDoc on options; omitted from README Constructor list | [VERIFIED] | `sdk/src/index.ts:L33-L42`; `sdk/README.md:L62-L69`; usage `dashboard/src/app/test-studio/page.tsx:L62-L76` |
| `on` / `off` event callbacks | Host UI handlers | yes README events table | [VERIFIED] | `sdk/src/index.ts:L354-L365`; `sdk/README.md:L84-L98` |
| `fetchTimeoutMs` | Tune hung-request abort | yes README | [VERIFIED] | `sdk/src/index.ts:L43-L47`; `sdk/README.md:L69` |
| STT / TTS / LLM adapter interfaces in this package | NOT FOUND | — | [VERIFIED] | NOT FOUND (searched: adapter/provider interface symbols in `sdk/src/**/*.ts`); public surface `sdk/src/index.ts:L21-L744` |
| Telephony / tools / storage plugins in this package | NOT FOUND | — | [VERIFIED] | NOT FOUND (searched: plugin/middleware/storage in `sdk/src/**/*.ts`); public surface `sdk/src/index.ts:L21-L744` |

| Hard-coded assumption | Tag | Citation |
|---|---|---|
| WebRTC transport is `livekit-client` `Room` / `RoomEvent` / `Track` | [VERIFIED] | `sdk/src/index.ts:L1-L2`; `sdk/src/index.ts:L250-L306`; `sdk/package.json:L45-L47` |
| Mic capture always requests echoCancellation / noiseSuppression / autoGainControl | [VERIFIED] | `sdk/src/index.ts:L15-L19`; `sdk/src/index.ts:L250-L252` |
| Metrics only parsed when room metadata/data JSON has `type` `metrics_updated` or `turn_latency` | [VERIFIED] | `sdk/src/index.ts:L730-L740` |

### 3. Contracts

#### Events (`AwaazLabsUvaVoiceEvent` / `AwaazLabsUvaVoiceEventMap`)

| Event | Payload shape | Tag | Citation |
|---|---|---|---|
| `transcript` | `{ id, text, final, speaker: 'user'\|'agent' }` | [VERIFIED] | `sdk/src/index.ts:L94-L102`; `sdk/src/index.ts:L118` |
| `speaking` | `[boolean]` | [VERIFIED] | `sdk/src/index.ts:L119` |
| `error` | `[AwaazLabsUvaVoiceError]` | [VERIFIED] | `sdk/src/index.ts:L120` |
| `ended` | `[unknown]` | [VERIFIED] | `sdk/src/index.ts:L121` |
| `connected` | `[]` | [VERIFIED] | `sdk/src/index.ts:L122` |
| `connect_timing` | `[ConnectTiming]` `{ mintMs, livekitConnectMs, livekitUrlHost?, connectionQuality? }` | [VERIFIED] | `sdk/src/index.ts:L58-L65`; `sdk/src/index.ts:L124` |
| `disconnected` | `[unknown]` | [VERIFIED] | `sdk/src/index.ts:L125` |
| `agent_speaking` | `[boolean]` | [VERIFIED] | `sdk/src/index.ts:L126` |
| `metrics_updated` | `[MetricsEvent]` `{ type; [key: string]: unknown }` | [VERIFIED] | `sdk/src/index.ts:L104-L107`; `sdk/src/index.ts:L127` |
| `audio_blocked` | `[boolean]` | [VERIFIED] | `sdk/src/index.ts:L135` |
| `turn_latency` | `[MetricsEvent]` | [VERIFIED] | `sdk/src/index.ts:L129` |

Callback signature: `on<K>(event: K, cb: (...args: EventMap[K]) => void): this` [VERIFIED] `sdk/src/index.ts:L354-L360`.

#### Error class / codes / message quality

| Item | Fact | Tag | Citation |
|---|---|---|---|
| Class | `AwaazLabsUvaVoiceError` with `code` + optional `message` (defaults to `code`) | [VERIFIED] | `sdk/src/internal/errors.ts:L28-L35` |
| Codes | `quota_exceeded` \| `agent_not_found` \| `session_failed` \| `rate_limit` \| `worker_not_ready` \| `provider_limit` \| `timeout` \| `token_refresh_failed` | [VERIFIED] | `sdk/src/internal/errors.ts:L18-L26` |
| HTTP mapping | Status/body → code via `mapSessionHttpError`; opaque 429 → `quota_exceeded` with default message = code | [VERIFIED] | `sdk/src/internal/errors.ts:L58-L87` |
| Example messages | `'publishableKey is required'`; `'could not reach sessionEndpoint'`; `'LiveKit connection failed'`; `'microphone permission denied or unavailable'`; `'request timed out after ${timeoutMs}ms'`; `'token refresh rejected'` / `'token refresh failed'`; body text forwarded when present for some mappings | [VERIFIED] | `sdk/src/index.ts:L187-L191`; `sdk/src/index.ts:L295`; `sdk/src/index.ts:L312`; `sdk/src/index.ts:L345`; `sdk/src/internal/http.ts:L21-L22`; `sdk/src/index.ts:L651-L655`; `sdk/src/index.ts:L683-L686`; `sdk/src/internal/errors.ts:L61-L87` |

#### Lifecycle ordering (code behavior vs documentation)

| Fact | Documented? | Tag | Citation |
|---|---|---|---|
| On success path: emit `connect_timing` then set state `connected` then emit `connected` | `connect_timing` listed in README/events doc; order vs `connected` not stated in lifecycle sketch | [VERIFIED] | `sdk/src/index.ts:L328-L331`; `sdk/README.md:L98`; `dashboard/src/content/docs/pages/events-and-lifecycle.ts:L11-L13` |
| On LiveKit disconnect: emit `disconnected` then `ended` with same reason | README: both listed; order not explicit | [VERIFIED] | `sdk/src/index.ts:L429-L439`; `sdk/README.md:L88-L90` |
| Throwing listener does not stop later listeners | yes README | [VERIFIED] | `sdk/src/index.ts:L412-L420`; `sdk/README.md:L100` |
| `MetricsEvent` extra keys undocumented as stable schema | README: “passthrough — not a stable public schema beyond delivery” | [VERIFIED] | `sdk/README.md:L128`; `sdk/src/index.ts:L104-L107` |

### 4. Packaging and compatibility

| Fact | Tag | Citation |
|---|---|---|
| `"type": "module"`; `main`/`types`/`exports["."]` → `dist/index.js` / `dist/index.d.ts`; `exports` conditions: `types`, `import`, `default` — no `require` condition | [VERIFIED] | `sdk/package.json:L25-L33` |
| After local build, `dist/index.js` and `dist/index.d.ts` exist on disk at collection time | [VERIFIED] | presence of `sdk/dist/index.js`, `sdk/dist/index.d.ts`; emit config `sdk/package.json:L40`; `sdk/tsconfig.json:L6-L8` |
| `dist/` is gitignored | [VERIFIED] | `.gitignore:L8` |
| `files`: `dist`, `README.md`, `CHANGELOG.md` | [VERIFIED] | `sdk/package.json:L34-L38` |
| `license` field | ABSENT in package.json; `sdk/LICENSE` / `sdk/LICENSE.md` ABSENT | [VERIFIED] | `sdk/package.json:L1-L52`; NOT FOUND (searched: `sdk/LICENSE`, `sdk/LICENSE.md`) |
| `engines` | ABSENT | [VERIFIED] | `sdk/package.json:L1-L52` |
| `peerDependencies` | ABSENT; `livekit-client` is a direct dependency | [VERIFIED] | `sdk/package.json:L45-L47` |
| TS emit | `target ES2020`, `module`/`moduleResolution` Node16 | [VERIFIED] | `sdk/tsconfig.json:L2-L5` |
| Publish script | `prepublishOnly`: `npm run build && npm run lint` | [VERIFIED] | `sdk/package.json:L43` |
| Semver / release | CHANGELOG Keep-a-Changelog + Semver; tag `voice-v*` / alias `sdk-v*` via `release-sdk.yml` | [VERIFIED] | `sdk/CHANGELOG.md:L3-L7`; `.github/workflows/release-sdk.yml:L6-L8`; `.github/workflows/release-sdk.yml:L63-L64` |
| Changesets | NOT FOUND (searched: `.changeset/`) | [VERIFIED] | NOT FOUND (searched: `.changeset/`) |
| Bundler / SSR note in code | `attachRemoteAudio` skips `document.body` when `document` undefined | [VERIFIED] | `sdk/src/index.ts:L531-L536` |
| Edge runtime APIs used | Uses browser `fetch` / `AbortController` / `performance` / optional `document`; `node:` imports NOT FOUND in `sdk/src` | [VERIFIED] | `sdk/src/internal/http.ts:L11-L24`; `sdk/src/index.ts:L263`; NOT FOUND (searched: `node:` in `sdk/src/**/*.ts`) |

### 5. Examples / consumers (API match by reading)

| Consumer | Imports public API? | Signature match vs current code | Tag | Citation |
|---|---|---|---|---|
| `sdk/README.md` minimal example | yes `AwaazLabsUvaVoice` | matches construct + `connect({ agentId })` + events | [VERIFIED] | `sdk/README.md:L35-L57`; `sdk/src/index.ts:L185`; `sdk/src/index.ts:L240` |
| `client-integration-test/frontend` | yes from `@awaazlabs-uva/voice` | `new AwaazLabsUvaVoice({ publishableKey, sessionEndpoint, refreshEndpoint?, fetchTimeoutMs })` + `connect({ agentId })` | [VERIFIED] | `client-integration-test/frontend/src/main.ts:L1-L6`; `L538-L546` |
| Vite config | `require('@awaazlabs-uva/voice/package.json')` — subpath outside `exports["."]` | [VERIFIED] | `client-integration-test/frontend/vite.config.ts:L8`; `sdk/package.json:L27-L33` |
| `dashboard` Test Studio | yes | uses `sessionCredentials: 'include'` + `sessionHeaders` | [VERIFIED] | `dashboard/src/app/test-studio/page.tsx:L6`; `L62-L76` |
| `client-deliverables-final/host-backend-starter` | does not import voice package; implements host session routes voice expects | [VERIFIED] | `client-deliverables-final/host-backend-starter/package.json:L14-L17`; `client-deliverables-final/host-backend-starter/src/createApp.js:L84-L144` |
| `examples/` folder | NOT FOUND (searched: `examples/**`) | — | [VERIFIED] | NOT FOUND (searched: `examples/**`) |

### 6. Tests

| Fact | Tag | Citation |
|---|---|---|
| Framework | Vitest (`vitest run`); config `environment: 'node'`, include `src/**/*.test.ts` | [VERIFIED] | `sdk/package.json:L42`; `sdk/package.json:L50`; `sdk/vitest.config.ts:L4-L8` |
| Test files | 4: `index.test.ts`, `internal/errors.test.ts`, `internal/http.test.ts`, `internal/livekitToken.test.ts` | [VERIFIED] | paths under `sdk/src` |
| Approx case count | `index.test.ts` 9 `it(`; `errors.test.ts` 1 `it.each` with 12 rows; `http.test.ts` 2; `livekitToken.test.ts` 3 (26 cases if `it.each` expands) | [VERIFIED] | `sdk/src/index.test.ts` (`it(` count 9); `sdk/src/internal/errors.test.ts:L6-L27`; `sdk/src/internal/http.test.ts`; `sdk/src/internal/livekitToken.test.ts` |
| Mocks vs real | Stubbed `fetch` / fake timers / stub Room internals; no live LiveKit/providers | [VERIFIED] | `sdk/src/index.test.ts:L46-L50`; `sdk/src/index.test.ts:L128-L166`; `sdk/src/internal/livekitToken.test.ts:L5-L17` |
| Load / concurrency / soak / failure-injection suites | NOT FOUND (searched under `sdk/` for load|soak|concurrency|chaos|failure.?inject) | [VERIFIED] | NOT FOUND (searched: load|soak|concurrency|chaos|failure.?inject under `sdk/`) |

| Test file covers | Tag | Citation |
|---|---|---|
| `listVoices` HTTP error mapping | [VERIFIED] | `sdk/src/index.test.ts:L40-L66` |
| Listener throw isolation (`emit`) | [VERIFIED] | `sdk/src/index.test.ts:L69-L90` |
| `attachRemoteAudio` without `document` | [VERIFIED] | `sdk/src/index.test.ts:L93-L118` |
| Token refresh retry / 401 / deadline / backoff | [VERIFIED] | `sdk/src/index.test.ts:L121-L289` |
| `mapSessionHttpError` matrix | [VERIFIED] | `sdk/src/internal/errors.test.ts:L5-L30` |
| `fetchWithTimeout` abort → `timeout` | [VERIFIED] | `sdk/src/internal/http.test.ts:L6-L46` |
| `applyRefreshedLiveKitToken` | [VERIFIED] | `sdk/src/internal/livekitToken.test.ts:L4-L35` |

| Public API with no dedicated test found | Tag | Evidence |
|---|---|---|
| Full `connect()` happy path (mint + `room.connect` + mic) | [VERIFIED] | NOT FOUND as `connect(` integration test in `sdk/src/**/*.test.ts` (refresh tests call private `refreshToken`) |
| `disconnect`, `startAudio`, `setMicMuted` | [VERIFIED] | NOT FOUND method-named tests in those files |
| Getters `connectionState`, `isConnected`, `isMicMuted`, `connectTiming` | [VERIFIED] | NOT FOUND dedicated asserts |
| Alias `UrduVoiceAgent` | [VERIFIED] | export `sdk/src/index.ts:L744`; no test reference found in test files |

---

## Package: `@awaazlabs-uva/agents` (`sdk-server/`)

### 1. Integration path (code-required)

| Step | What code requires | Tag | Citation |
|---|---|---|---|
| Install | `@awaazlabs-uva/agents` (runtime deps `{}`) | [VERIFIED] | `sdk-server/package.json:L2`; `sdk-server/package.json:L45` |
| Runtime | Node (imports `node:crypto`); file header: SERVER-SIDE ONLY | [VERIFIED] | `sdk-server/src/index.ts:L1-L9`; `sdk-server/src/index.ts:L11` |
| Construct | `new AwaazLabsUvaAgentsClient({ tenantId, tenantSecret, baseUrl, extraHeaders? })`; blank required fields throw plain `Error` | [VERIFIED] | `sdk-server/src/index.ts:L13-L22`; `sdk-server/src/index.ts:L184-L189` |
| First working call | e.g. `createAgent({ name, prompt, voiceId, … })` → signed `POST {baseUrl}/machine/agents` | [VERIFIED] | `sdk-server/src/index.ts:L191-L211` |
| Prerequisites | Existing tenantId + tenantSecret (no signup in client); reachable portal/machine API `baseUrl` | [VERIFIED] | `sdk-server/src/index.ts:L8-L9`; `sdk-server/src/index.ts:L18-L19` |

| Topic | Fact | Tag | Citation |
|---|---|---|---|
| Implicit env in package | NOT FOUND (`process.env` / `import.meta` under `sdk-server/src`) | [VERIFIED] | NOT FOUND (searched: `process.env`, `import.meta` in `sdk-server/src/**/*.ts`) |
| Global singletons | NOT FOUND | [VERIFIED] | class holds `options` only `sdk-server/src/index.ts:L184-L189` |
| Import-time side effects | Top-level `node:crypto` import only | [VERIFIED] | `sdk-server/src/index.ts:L11` |
| Signing | HMAC-SHA256 over `tenantId.ts.nonce.action.bodyHash`; body hash = SHA-256 of canonical JSON via `crypto.subtle` | [VERIFIED] | `sdk-server/src/index.ts:L246-L250`; `sdk-server/src/index.ts:L178-L182` |
| Default on create | `llm_model` defaults to `'gemini-2.5-flash'` when `llmModel` omitted | [VERIFIED] | `sdk-server/src/index.ts:L196` |

README usage shows `process.env.UVA_*` for host wiring [VERIFIED] `sdk-server/README.md:L25-L28` — those reads are not in the package source.

### 2. Extension points

| Mechanism | Role | Documented? | Tag | Citation |
|---|---|---|---|---|
| `CreateAgentParams` / `UpdateAgentParams` provider fields | `sttProvider`, `llmProvider`, `ttsProvider`, models/options, `agentLanguage` — string passthrough to machine API | yes README methods | [VERIFIED] | `sdk-server/src/index.ts:L54-L103`; `sdk-server/README.md:L49-L58` |
| `getProviderCapabilities()` | Discover enabled language/provider/model/voice maps | yes | [VERIFIED] | `sdk-server/src/index.ts:L285-L294`; `sdk-server/README.md:L52` |
| `toolsBaseUrl` / `toolsAuthSecret` | Point worker tool POSTs at client gateway | yes JSDoc + README | [VERIFIED] | `sdk-server/src/index.ts:L74-L81`; `sdk-server/README.md:L49` |
| `extraHeaders` | Non-auth headers (auth keys overwritten after spread) | yes README | [VERIFIED] | `sdk-server/src/index.ts:L20-L21`; `sdk-server/src/index.ts:L252-L259`; `sdk-server/README.md:L62` |
| Number assign helpers | `listManagedNumbers`, `assignAgentToNumber`, `unassignAgentFromNumber` | yes | [VERIFIED] | `sdk-server/src/index.ts:L297-L310`; `sdk-server/README.md:L53-L54` |
| Pluggable STT/TTS/LLM class adapters in this package | NOT FOUND | — | [VERIFIED] | single file client; no adapter interface |
| Middleware / storage hooks | NOT FOUND | — | [VERIFIED] | `sdk-server/src/index.ts` |

| Hard-coded assumption | Tag | Citation |
|---|---|---|
| Fixed machine paths/actions (`/machine/agents`, `agent.create`, etc.) | [VERIFIED] | `sdk-server/src/index.ts:L211`; `L215`; `L237`; `L291-L293`; `L300`; `L305` |
| Default LLM model string `gemini-2.5-flash` | [VERIFIED] | `sdk-server/src/index.ts:L196` |
| HMAC + `node:crypto` / WebCrypto digest required | [VERIFIED] | `sdk-server/src/index.ts:L11`; `L178-L182`; `L250` |

Host-tools demo gateway (not part of npm package) implements `/api/tools/*` with `x-tool-gateway-secret` [VERIFIED] `host-tools/src/createApp.js:L12-L55`.

### 3. Contracts

| Method | HTTP | Action string | Tag | Citation |
|---|---|---|---|---|
| `createAgent` | POST `/machine/agents` | `agent.create` | [VERIFIED] | `sdk-server/src/index.ts:L211` |
| `listAgents` | GET `/machine/agents` | `agent.list` | [VERIFIED] | `sdk-server/src/index.ts:L214-L215` |
| `updateAgent` | PATCH `/machine/agents/${agentId}` | `agent.update` | [VERIFIED] | `sdk-server/src/index.ts:L237` |
| `getProviderCapabilities` | GET `/machine/provider-capabilities` | `provider_capabilities.get` | [VERIFIED] | `sdk-server/src/index.ts:L288-L293` |
| `listManagedNumbers` | POST `/machine/telephony/numbers/list` | `telephony.managed_numbers.list` | [VERIFIED] | `sdk-server/src/index.ts:L297-L300` |
| `assignAgentToNumber` / `unassign` | PATCH `/machine/telephony/numbers/${id}/assignment` | `telephony.numbers.assign_agent` | [VERIFIED] | `sdk-server/src/index.ts:L303-L309` |

Auth headers: `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature` [VERIFIED] `sdk-server/src/index.ts:L255-L258`.

Error class: `AwaazLabsUvaAgentsError(status, message, code?)` [VERIFIED] `sdk-server/src/index.ts:L143-L155`.  
Provider-validation path: `detail.reason` → message, `detail.code` → `code` [VERIFIED] `sdk-server/src/index.ts:L271-L278`.  
Plain string `detail` → message, `code` undefined [VERIFIED] `sdk-server/src/index.ts:L280`.  
Constructor blank-field errors are plain `Error`, not `AwaazLabsUvaAgentsError` [VERIFIED] `sdk-server/src/index.ts:L186-L188`.

Lifecycle/event bus: NOT FOUND in this package (request/response only) [VERIFIED] `sdk-server/src/index.ts:L184-L311`.

### 4. Packaging and compatibility

| Fact | Tag | Citation |
|---|---|---|
| ESM `"type":"module"`; exports map same shape as voice (types/import/default only) | [VERIFIED] | `sdk-server/package.json:L25-L33` |
| `dist/index.js` + `.d.ts` present after build; `declaration: true` | [VERIFIED] | presence of `sdk-server/dist/index.js`, `sdk-server/dist/index.d.ts`; `sdk-server/tsconfig.json:L8-L10` |
| `files`: dist, README, CHANGELOG | [VERIFIED] | `sdk-server/package.json:L34-L38` |
| `license` / LICENSE file | ABSENT in package.json; LICENSE files ABSENT | [VERIFIED] | `sdk-server/package.json:L1-L50`; NOT FOUND (searched: `sdk-server/LICENSE`, `sdk-server/LICENSE.md`) |
| `engines` | ABSENT | [VERIFIED] | `sdk-server/package.json:L1-L50` |
| `peerDependencies` | ABSENT; `dependencies: {}` | [VERIFIED] | `sdk-server/package.json:L45` |
| `@types/node` / `types: ["node"]` | [VERIFIED] | `sdk-server/package.json:L47`; `sdk-server/tsconfig.json:L5-L7` |
| Uses `node:crypto`, `Buffer`, `crypto.subtle` | [VERIFIED] | `sdk-server/src/index.ts:L11`; `sdk-server/src/index.ts:L180-L181` |
| `prepublishOnly` build+lint | [VERIFIED] | `sdk-server/package.json:L43` |
| Release tag | `agents-v*` | [VERIFIED] | `.github/workflows/release-sdk.yml:L8`; `.github/workflows/release-sdk.yml:L65` |
| Changesets | NOT FOUND | [VERIFIED] | NOT FOUND (searched: `.changeset/`) |
| Browser / edge | File header forbids browser; Node crypto APIs | [VERIFIED] | `sdk-server/src/index.ts:L1-L6`; `sdk-server/src/index.ts:L11` |

### 5. Examples / consumers

| Consumer | Public API import? | Match | Tag | Citation |
|---|---|---|---|---|
| `sdk-server/README.md` | yes | matches ctor + `createAgent` fields | [VERIFIED] | `sdk-server/README.md:L22-L40`; `sdk-server/src/index.ts:L191-L211` |
| `client-integration-test/backend` | dynamic `import('@awaazlabs-uva/agents')` → `AwaazLabsUvaAgentsClient` | matches options `{ baseUrl, tenantId, tenantSecret }` | [VERIFIED] | `client-integration-test/backend/src/createApp.js:L68-L73` |
| Dashboard docs strings | markdown examples only | [VERIFIED] | `dashboard/src/content/docs/pages/backend-setup.ts:L218` |
| `host-backend-starter` | does not depend on agents package | [VERIFIED] | `client-deliverables-final/host-backend-starter/package.json:L14-L17` |

### 6. Tests

| Fact | Tag | Citation |
|---|---|---|
| Framework | Node built-in test runner after build: `npm run build && node --test test/client.test.mjs` | [VERIFIED] | `sdk-server/package.json:L42` |
| File | 1: `sdk-server/test/client.test.mjs` | [VERIFIED] | `sdk-server/test/client.test.mjs:L1-L10` |
| `it(` count | 12 | [VERIFIED] | `sdk-server/test/client.test.mjs` (`it(` occurrences: 12) |
| Mocks | Stubbed `globalThis.fetch`; timers for Date; no live portal | [VERIFIED] | `sdk-server/test/client.test.mjs:L4`; `sdk-server/test/client.test.mjs:L42-L49`; `sdk-server/test/client.test.mjs:L63-L70` |
| Load/soak/concurrency/failure-injection | NOT FOUND under `sdk-server/test` | [VERIFIED] | NOT FOUND (searched: load|soak|concurrency|chaos|failure.?inject in `sdk-server/test/**`) |

| Covered | Tag | Citation |
|---|---|---|
| Constructor validation + aliases | [VERIFIED] | `sdk-server/test/client.test.mjs:L73-L84` |
| HMAC signing / GET empty body / extraHeaders | [VERIFIED] | `sdk-server/test/client.test.mjs:L86-L134` |
| createAgent camel→snake + default llm_model | [VERIFIED] | `sdk-server/test/client.test.mjs:L137-L165` |
| updateAgent partial + empty greeting | [VERIFIED] | `sdk-server/test/client.test.mjs:L167-L175` |
| unassignAgentFromNumber | [VERIFIED] | `sdk-server/test/client.test.mjs:L177-L184` |
| Error mapping object/string/empty | [VERIFIED] | `sdk-server/test/client.test.mjs:L187-L222` |

| Public API with no test found | Tag | Citation |
|---|---|---|
| `getProviderCapabilities` | [VERIFIED] | NOT FOUND (searched: `getProviderCapabilities` in `sdk-server/test/client.test.mjs`) |
| `listManagedNumbers` | [VERIFIED] | NOT FOUND (searched: `listManagedNumbers` in `sdk-server/test/client.test.mjs`) |
| `assignAgentToNumber` | [VERIFIED] | NOT FOUND (searched: `assignAgentToNumber` in `sdk-server/test/client.test.mjs`); `unassignAgentFromNumber` covered `sdk-server/test/client.test.mjs:L177-L184` |
| `listAgents` beyond signing GET | [VERIFIED] | signing/error paths `sdk-server/test/client.test.mjs:L113-L121`; `sdk-server/test/client.test.mjs:L203-L221` |

---

## Package: `@awaazlabs-uva/telephony` (`telephony/`)

### 1. Integration path (code-required)

| Step | What code requires | Tag | Citation |
|---|---|---|---|
| Install | `@awaazlabs-uva/telephony`; `engines.node: >=20` | [VERIFIED] | `telephony/package.json:L2`; `L45-L47` |
| Construct | `new TelephonyClient({ tenantId, tenantSecret, baseUrl, extraHeaders?, fetch?, nowSeconds?, nonceFactory? })` | [VERIFIED] | `telephony/src/types.ts:L39-L47`; `telephony/src/index.ts:L67-L79` |
| Runtime gate | `assertBackendRuntime()` throws if `process.versions.node` missing | [VERIFIED] | `telephony/src/transport.ts:L90-L94`; called `telephony/src/index.ts:L68` |
| First call example | e.g. `getConnectionStatus()` or `connectTelnyxAccount({ apiKey })` — signed machine HTTP | [VERIFIED] | `telephony/src/index.ts:L82-L102`; `telephony/README.md:L51-L65` |

| Topic | Fact | Tag | Citation |
|---|---|---|---|
| Implicit env in package | NOT FOUND under `telephony/src` | [VERIFIED] | NOT FOUND (searched: `process.env`, `import.meta` in `telephony/src/**/*.ts`) |
| README env names | Documents `UVA_TENANT_ID`, `UVA_HMAC_SECRET`, `UVA_TELEPHONY_API_URL`, `TELNYX_API_KEY` for host process | [VERIFIED] | `telephony/README.md:L27-L34` |
| Global singletons | NOT FOUND — private fields on instance | [VERIFIED] | `telephony/src/index.ts:L58-L79` |
| Import-time side effects | Re-exports + class definition; runtime assert only in constructor | [VERIFIED] | `telephony/src/index.ts:L45-L80` |
| Optional injectables | Custom `fetch`, `nowSeconds`, `nonceFactory` | [VERIFIED] | `telephony/src/types.ts:L44-L46`; `telephony/src/index.ts:L77-L79` |

### 2. Extension points

| Mechanism | Role | Documented? | Tag | Citation |
|---|---|---|---|---|
| Injectable `fetch` / clock / nonce | Test doubles / alternate HTTP | types only (README usage shows default) | [VERIFIED] | `telephony/src/types.ts:L39-L47` |
| `extraHeaders` (auth names stripped) | Proxies/tunnels | README security section mentions signing headers; sanitize in transport | [VERIFIED] | `telephony/src/transport.ts:L74-L80`; `telephony/README.md:L125-L129` |
| Alternate telephony provider SDK interface | NOT FOUND — methods are Telnyx-named against fixed routes | [VERIFIED] | `telephony/src/routes.ts:L3-L32`; `telephony/src/index.ts:L82-L219` |
| STT/TTS/LLM / tools / middleware / storage | NOT FOUND in this package | — | [VERIFIED] | public API `telephony/src/index.ts:L45-L56` |

| Hard-coded assumption | Tag | Citation |
|---|---|---|
| 28 frozen `TELEPHONY_MACHINE_OPERATIONS` paths/actions | [VERIFIED] | `telephony/src/routes.ts:L3-L32`; count asserted `telephony/test/phase8-smoke.mjs:L72` |
| Node.js required | [VERIFIED] | `telephony/src/transport.ts:L90-L94`; `telephony/package.json:L45-L47` |
| Uses `node:crypto` for HMAC | [VERIFIED] | `telephony/src/signing.ts:L1` |

### 3. Contracts

Operations map (method, path, action) [VERIFIED] `telephony/src/routes.ts:L3-L32` (28 entries including `getSessionByRoom` → `POST /machine/sessions/get` action `session.get`).

Error class: `AwaazLabsUvaTelephonyError(status, code, message, detail?)` with redacted message [VERIFIED] `telephony/src/errors.ts:L15-L31`; `L111-L114`.  
`TelephonyErrorCode` union lists many codes [VERIFIED] `telephony/src/types.ts:L55-L110`.  
Network failure → status `0`, code `telephony_request_failed`, message `'Telephony API request failed.'` [VERIFIED] `telephony/src/errors.ts:L34-L39`.  
Invalid JSON → `502` / `telephony_invalid_response` [VERIFIED] `telephony/src/errors.ts:L42-L47`.  
README documents a subset of codes for “typical handling” [VERIFIED] `telephony/README.md:L99-L113` (subset vs full union in `types.ts:L55-L110`).

Response sanitization drops restricted keys (e.g. `api_key`, `sip_secret`, `payload`, …) [VERIFIED] `telephony/src/transport.ts:L15-L29`; `telephony/src/transport.ts:L111-L119`.

Lifecycle/event ordering: NOT FOUND (RPC client) [VERIFIED] `telephony/src/index.ts:L221-L252`.

### 4. Packaging and compatibility

| Fact | Tag | Citation |
|---|---|---|
| ESM; exports types/import/default only | [VERIFIED] | `telephony/package.json:L25-L33` |
| `engines.node >=20` | [VERIFIED] | `telephony/package.json:L45-L47` |
| TS `target ES2022` | [VERIFIED] | `telephony/tsconfig.json:L3` |
| `files`: dist, README, CHANGELOG | [VERIFIED] | `telephony/package.json:L34-L38` |
| `license` / LICENSE file | ABSENT in package.json; LICENSE files ABSENT | [VERIFIED] | `telephony/package.json:L1-L51`; NOT FOUND (searched: `telephony/LICENSE`, `telephony/LICENSE.md`) |
| `peerDependencies` / `dependencies` | ABSENT (uses Node built-ins + global `fetch`) | [VERIFIED] | `telephony/package.json:L45-L50` |
| `dist` after build present; gitignored | [VERIFIED] | presence of `telephony/dist/index.js`, `telephony/dist/index.d.ts`; `.gitignore:L8` |
| `prepublishOnly` build+lint | [VERIFIED] | `telephony/package.json:L43` |
| Release | tag `telephony-v*`; publish without `--provenance` | [VERIFIED] | `.github/workflows/release-sdk.yml:L9`; `.github/workflows/release-sdk.yml:L66`; `.github/workflows/release-sdk.yml:L155-L156` |
| Changesets | NOT FOUND | [VERIFIED] | NOT FOUND (searched: `.changeset/`) |
| Edge | Constructor fails without Node `process.versions.node` | [VERIFIED] | `telephony/src/transport.ts:L90-L94` |

### 5. Examples / consumers

| Consumer | Public API? | Match | Tag | Citation |
|---|---|---|---|---|
| `telephony/README.md` | `TelephonyClient`, `AwaazLabsUvaTelephonyError` | matches ctor + methods named | [VERIFIED] | `telephony/README.md:L38-L79`; `telephony/src/index.ts:L58-L80` |
| `client-integration-test/backend` telephony routes | dynamic import `TelephonyClient` | matches options | [VERIFIED] | `client-integration-test/backend/src/telephonyRoutes.js:L27-L32` |
| Dashboard telephony docs | markdown import string | [VERIFIED] | `dashboard/src/content/docs/pages/telephony.ts:L26` |

### 6. Tests

| Fact | Tag | Citation |
|---|---|---|
| Runner | `npm run build && node test/phase8-smoke.mjs && node test/phase9-contract.mjs` | [VERIFIED] | `telephony/package.json:L42` |
| Files | 2 | [VERIFIED] | `telephony/test/phase8-smoke.mjs`; `telephony/test/phase9-contract.mjs` |
| phase8 functions | 9 `async function test*` | [VERIFIED] | `telephony/test/phase8-smoke.mjs:L31-L266` |
| phase9 functions | 6 `async function test*` including loop over 28 `routeCases` | [VERIFIED] | `telephony/test/phase9-contract.mjs:L68-L97`; `telephony/test/phase9-contract.mjs:L115-L154`; `telephony/test/phase9-contract.mjs:L299-L304` |
| Mocks | Injected `fetch`; no live Telnyx/portal | [VERIFIED] | `telephony/test/phase8-smoke.mjs:L110-L113` |
| Load/soak/concurrency/failure-injection | NOT FOUND as dedicated suites | [VERIFIED] | NOT FOUND (searched: load|soak|concurrency|chaos|failure.?inject in `telephony/test/**`) |

| Coverage note | Tag | Citation |
|---|---|---|
| All 28 `TelephonyClient` operations have frozen route/body/signature cases in phase9 | [VERIFIED] | `telephony/test/phase9-contract.mjs:L115-L122`; `telephony/test/phase9-contract.mjs:L68-L97` |
| Signing, sanitization, error redaction, path escape, getSessionByRoom regression | [VERIFIED] | `telephony/test/phase8-smoke.mjs:L31-L266`; `telephony/test/phase9-contract.mjs:L173-L259` |

---

## Examples and docs inventory (cross-package)

| Path | Role | Imports npm public API? | Tag | Citation |
|---|---|---|---|---|
| `client-deliverables-final/host-backend-starter/` | Minimal Express session mint/refresh | no SDK package dep | [VERIFIED] | `client-deliverables-final/host-backend-starter/package.json:L14-L17`; `client-deliverables-final/host-backend-starter/src/createApp.js:L84-L197` |
| `client-deliverables-final/01-INTEGRATION_GUIDE.md` | Guide with voice/agents/telephony snippets | docs only | [VERIFIED] | `client-deliverables-final/01-INTEGRATION_GUIDE.md:L162-L183` |
| `client-integration-test/` | Meta scripts + FE/BE smoke | FE: voice; BE: agents + telephony | [VERIFIED] | `client-integration-test/frontend/package.json:L12`; `client-integration-test/backend/package.json:L14-L15` |
| `dashboard/src/content/docs/pages/*` | In-console docs markdown strings | string examples, not runtime | [VERIFIED] | `dashboard/src/content/docs/pages/quickstart.ts:L44` |
| `dashboard/src/app/test-studio/page.tsx` | Live voice consumer | yes `@awaazlabs-uva/voice` | [VERIFIED] | `dashboard/src/app/test-studio/page.tsx:L6` |
| `host-tools/` | Tool gateway demo for worker | no `@awaazlabs-uva/*` import | [VERIFIED] | `host-tools/package.json:L2-L18`; `host-tools/src/createApp.js:L37-L55` |
| `examples/` | NOT FOUND | — | [VERIFIED] | NOT FOUND (searched: `examples/**`) |

Host starter session response shape matches voice `SessionResponse` fields [VERIFIED] `client-deliverables-final/host-backend-starter/src/createApp.js:L138-L144`; `sdk/src/index.ts:L109-L115`.

---

## CI (repo)

| Job / step | What runs | Tag | Citation |
|---|---|---|---|
| `pytest-unit` | Python offline suite | [VERIFIED] | `.github/workflows/ci.yml:L11-L37` |
| `pytest-integration` | Full pytest if `SUPABASE_DB_URL` set; else skip exit 0 | [VERIFIED] | `.github/workflows/ci.yml:L40-L70` |
| `sdk-build` | Node 20; for each of `sdk`, `sdk-server`, `telephony`: `npm ci`, build/lint/test (voice also explicit build) | [VERIFIED] | `.github/workflows/ci.yml:L72-L105` |
| `dashboard` | Build voice SDK then dashboard typecheck + `next build` | [VERIFIED] | `.github/workflows/ci.yml:L113-L150` |
| `security-scan` | pip-audit / npm audit (continue-on-error); gitleaks; grep secret shapes in `sdk/dist` | [VERIFIED] | `.github/workflows/ci.yml:L152-L206` |
| `docker-smoke` | Docker build four service images | [VERIFIED] | `.github/workflows/ci.yml:L208-L226` |
| `release-sdk.yml` | Tag or workflow_dispatch: build/lint/test; publish `npm publish --access public` without `--provenance` | [VERIFIED] | `.github/workflows/release-sdk.yml:L19-L36`; `.github/workflows/release-sdk.yml:L120-L156` |
| Makefile `test` | `@pytest` only (not npm package tests) | [VERIFIED] | `Makefile:L9-L10` |
| Makefile `lint` | ruff + optional `cd sdk && npm run lint` | [VERIFIED] | `Makefile:L11-L12` |

Node version in CI: `20` [VERIFIED] `.github/workflows/ci.yml:L80-L83`.

---

## Graphify cross-check

| Item | Status | Citation |
|---|---|---|
| Navigation via graphify | NOT FOUND (searched: `graphify-out/`, `graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md`, `graphify-out/wiki/index.md`) | NOT FOUND (searched paths above) |
