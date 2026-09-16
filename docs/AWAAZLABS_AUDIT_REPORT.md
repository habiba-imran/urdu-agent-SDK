9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

```
P R O D U C T A U D I T2026-09-13 · MAIN @ 94E7000
```

# AwaazLabs UVA Product Audit Report 

A full-stack technical, security, and compliance review of the Urdu/English Voice-Agent-as-a-Service platform — browser SDK, control plane, LiveKit worker, telephony subsystem, and consoles — audited against the QualiCall Product Audit Guidelines evidence standard. 

NOT GO for general availability or any “enterprise-grade” claim. NOT GO for paid telephony. Conditional GO for a controlled, browser-only pilot with known tenants — only after the seven Critical findings are closed. 

7 

18 `HIGH` 15 

```
CRITICALHIGH
```

30 

```
MEDIUMLOW
```

```
Repository Finova-Solutions/urdu-voice-agent-SDKCommit 94e7000
Scans run OSV.dev · git history (278 commits) · pytest collection
```

## 0. Scope, method, and what was not audited 

### What was audited 

Every directory in the repository at HEAD, not only the ones named in prior planning documents: 

`control_plane/` · `worker/` (incl. `worker/providers/` ) · `tenant_portal_api/` (incl. the full telephony subsystem) · `admin/` · `sdk/` · `sdk-server/` · `telephony/` · `dashboard/` · `supabase/migrations/` · `docker/` · `.github/workflows/` · `scripts/` · `tests/` · `services/` · `docs/` · `state/` · root configuration ( `Makefile` , `pytest.ini` , `requirements.txt` , `.gitleaks.toml` , `.gitignore` , `.env.example` ). 

### Scans actually executed (not asserted) 

|`SCAN`|`TOOL / METHOD`|`RESULT`|
|---|---|---|
|Python|OSV.dev batch API against every `==`-pinned package in|6 advisories, all in `aiohttp==3.14.1`, one rated HIGH. The two slim|
|dependency|`requirements.txt`, `docker/requirements-admin.txt`,|Docker requirement files are clean.|
|CVEs|`docker/requirements-control-plane.txt`||



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

1/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

|npm<br>dependency<br>CVEs|OSV.dev batch API against the resolved trees in `sdk/`,<br>`sdk-server/`, `telephony/`, `dashboard/` lockfiles|29 advisories, all in dashboard/ — 1 CRITICAL, 7 HIGH. The three<br>_published_ SDK packages are clean.|
|---|---|---|
|Secrets in git<br>history|Pattern scan across all 278 reachable commits for<br>provider key shapes, private keys and JWTs; plus `git log`<br>`--diff-filter=A` filename scan for `.env*`, `*.pem`, `*.key`,<br>`*.p12`|No real secret found. Only `.env.example` templates and elided<br>placeholder JWTs in `docs/api-reference.md`. Note: `gitleaks` is not<br>installed on the audit machine, so the repo's own `make secrets` gate<br>could not be executed — see F-M22.|
|Test collection|`python -m pytest --collect-only -q`|Zero telephony test modules collected. See F-H1.|
|Build-artifact<br>hygiene in git|`git ls-files` for `node_modules/`, `.next/`, `dist/`|Clean, except four intentionally-vendored `client-`<br>`submission_v2/**/dist/` files.|



### What was NOT audited — stated explicitly rather than papered over 

Per guideline §9 (" _'Not yet reviewed — flagging for follow-up' is a legitimate, honest line_ "): 

- No live penetration test, load test, or soak test was run. Every exploit path described below is derived from reading code, not from executing it against a running system. Items marked _needs live confirmation_ require a controlled test. 

- No access to the running production or staging environment, the Render dashboard, Supabase project settings, LiveKit Cloud, the Telnyx account, or GitHub repository settings. Consequently: actual environment-variable values, actual branch-protection rules, actual CI pass/fail history, backup configuration, and MFA status on third-party accounts could not be verified. Section 6 is therefore delivered as the inventory template the guideline asks for, with the questions that must be answered by whoever holds that access. Every cell marked _UNKNOWN — owner must fill_ is itself a finding. 

- No live prompt-injection test was executed against a real agent. Section 5b analyses the injection surface from code and states plainly which parts are proven by reading and which need a live test. 

- tenant_portal_api/telephony_service.py (2,451 lines) and telnyx_client.py (1,083 lines) were reviewed at the interface, authentication, quota, idempotency and error-handling level, not line-by-line in full. Deeper review of Telnyx provider-state reconciliation is flagged for follow-up. 

- pip-audit could not be run in-process (local interpreter is Python 3.10; `requirements.txt` pins `numpy==2.5.1` , which requires ≥3.12). The OSV.dev API was queried directly against the identical pinned versions instead — equivalent advisory data, different tool. 

- Frontend usability was assessed from source, not from a running instance. No screenshots, no measured load times, no accessibility tooling run. Section 7 is explicit about this. 

## 1. Executive summary 

Verdict: NOT GO for general availability or for any "enterprise-grade" claim. NOT GO for paid telephony. Conditional GO for a controlled, browser-only pilot with known tenants — only after the seven Critical findings below are closed. 

This is a real multi-tenant voice platform, not a demo. The architecture is sound in its bones: a properly ordered HMAC token mint with replay, nonce, ownership, origin and quota gates; genuine PostgreSQL row-level-security scoping in the worker's agent-config read; a provider-capability registry that refuses to silently substitute a provider; and a large, seriously engineered telephony subsystem with real idempotency locking. The code is unusually well commented, and several past mistakes are recorded honestly in-line rather than erased. 

S fi di g th l gh t bl k l h d https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

f th 

t li ti 

2/50 

9/13/26, 5:49 PM AwaazLabs UVA Audit Seven findings are nonetheless severe enough to block launch, and none of them are stylistic. 

1. A hardcoded authentication secret ships in production code. The entire telephony API verifies tenant identity against the literal string `"mock_jwt_secret_for_tests"` whenever `TENANT_PORTAL_JWT_SECRET` is unset in the environment — and that variable appears in neither `.env.example` nor the production environment-variable guide. Anyone able to read the source can forge a token for any tenant and buy phone numbers, place outbound PSTN calls, and rotate Telnyx credentials at that tenant's expense. 

2. An unauthenticated session-minting endpoint is live in the deployed control plane. `POST /v1/session/dev-mint` issues a real LiveKit session token to anyone who supplies an agent ID. It accepts a `publishableKey` field and never validates it. As a deliberate side effect it resets the tenant's concurrency counter to zero, defeating the concurrency cap outright. 

3. The control plane's CORS policy defaults to a credentialed wildcard when its allowlist variable is unset — which makes finding 2 callable from any website on the internet. 

4. Every call is audio-recorded unconditionally, with no consent capture, no caller disclosure, no per-tenant opt-out, and no retention or deletion mechanism. For phone calls this is direct legal exposure in all-party-consent US states; for all calls it is an unresolved GDPR/CCPA erasure problem. The data-governance migration that does exist adds retention columns to telephony _infrastructure_ tables and to none of the tables that actually hold recordings, transcripts, or caller phone numbers. 

5. The tenant dashboard ships a Next.js version with 19 known vulnerabilities, one rated CRITICAL (unauthenticated remote code execution on Windows-hosted servers) and seven HIGH. 

6. The tenant's raw signing secret is stored in plain text in the database and is retrievable into the browser by an endpoint the dashboard actively calls — while the schema comment, the module docstring, and the phase documentation all still state that the secret is never stored. The dashboard keeps its session token in `localStorage` , so a single XSS bug yields the tenant's permanent signing credential, and no self-service rotation exists. 

7. The agent can now write to customers' real calendars. `book_appointment` , `reschedule_appointment` and `cancel_appointment` are driven by whatever the caller says, with no confirmation gate and no check that the caller owns the booking being modified. The known prompt-injection residual is no longer limited to raising a support ticket. 

Two further findings undermine confidence in everything else that has been reported as done: 

- Roughly three-quarters of the test suite never runs. `pytest.ini` replaces pytest's default discovery with an explicit 22file whitelist. 53 of the 75 test files in `tests/` — 269 test functions, including the _entire_ telephony suite of ~170 tests — are collected by nothing, in `make gate` or in CI. The telephony test suite a commit message describes as complete has, mechanically, never been run by an automated gate. 

- Production deploys are not gated on tests. `deploy-prod.yml` fires on every push to `main` with no dependency on the CI workflow, and the CI workflow itself contains a job that cannot pass, because it builds two example applications that were deleted from the repository in an unrelated commit on 2026-08-18. 

Every statement above is evidenced with file paths and line numbers below. 

## 2. Component completeness matrix 

Guideline §1 asks for confirmation that each claimed component actually exists, with a file or endpoint reference, and for "partial" to say specifically what is missing. 

|`#`<br>`COMPONENT / CLAIM`|`STATUS`|`EVIDENCE`|`WHAT IS MISSING`|
|---|---|---|---|
|1<br>HMAC session mint with ordered|Present|`control_plane/mint.py:67–157` — tenant lookup,|—|
|security gates||HMAC compare, ±60s skew, single-use nonce,||
|||active check agent ownership IDOR guard||



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

3/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit active check, agent-ownership IDOR guard, origin allowlist, quota, then JWT 

|2|Scoped LiveKit JWT (120s, one<br>room, no admin grants)|Present|`control_plane/mint.py:28,133–146`|—|
|---|---|---|---|---|
|3|Session token refresh|Present,<br>unsafe|`control_plane/app.py:301–345,593–605`|Re-issues without re-checking<br>tenant status, quota, or session<br>end (F-H7)|
|4|Unauthenticated dev-mint<br>endpoint|Present —<br>should not be|`control_plane/app.py:577–590`|No auth at all (F-C2)|
|5|Per-tenant rate limiting|Partial|`control_plane/app.py:291–298`;<br>`tenant_portal_api/machine_auth.py:169–179`|In-process, unbounded, keyed on<br>unauthenticated input (F-H4, F-<br>H5)|
|6|Tenant portal API (agents CRUD,<br>credentials, sessions, usage)|Partial|`tenant_portal_api/app.py:287–461`|No agent delete; no tenant delete;<br>unbounded `limit` params|
|7|Machine (HMAC) agent-<br>management API|Present|`tenant_portal_api/app.py:471–616`;<br>`machine_auth.py:182–242`|Action+payload binding is<br>correctly implemented|
|8|Super-admin portal with TOTP|Present|`admin/app.py:114–249`; `admin/auth.py:308–367`;<br>`admin/security.py:390–457`|No rate limit, no lockout, no TOTP<br>replay guard, no failed-login audit<br>(F-H14)|
|9|Worker: STT → LLM → TTS<br>pipeline|Present|`worker/main.py:214–369`;<br>`worker/providers/registry.py:24–86`|No provider fallback or circuit<br>breaker (F-H10)|
|10|Worker-level RLS scoping of<br>agent config|Present|`worker/config.py:114–151` (`set local role`<br>`authenticated` + JWT claim)|—|
|11|Untrusted-prompt framing<br>(injection mitigation)|Present,<br>partial|`worker/main.py:57–63,126–132`|Framing only; no output validation<br>before tool execution (F-C7)|
|12|Platform lifecycle tools (end call,<br>escalate)|Present|`worker/tools.py:49–98,384`|`escalations` rows are unreadable —<br>no API, no UI (F-M12)|
|13|Client business tools (RAG,<br>booking, reschedule, cancel)|Present —<br>ungoverned|`worker/tools.py:233–392`|No confirmation gate, no<br>ownership check, no idempotency<br>(F-C7)|
|14|Per-agent tools webhook<br>gateway|Present|`worker/tools.py:193–230`;<br>`supabase/migrations/0026`|No SSRF controls (F-H8); secret<br>stored plaintext (F-M8)|
|15|Per-turn latency telemetry to<br>browser|Present|`worker/latency.py:496–528,680–698`;<br>`sdk/src/index.ts:466–473`|Leaks internal stage timings to end<br>users (F-L6)|
|16|Session recording (audio)|Present —<br>ungoverned|`worker/session_recording.py:1–198`;<br>`worker/main.py record={"audio": True,...}`|No consent, disclosure, opt-out or<br>retention (F-C4)|
|17|Session transcript persistence|Present —<br>ungoverned|`worker/main.py:735–760`;<br>`supabase/migrations/0011`|No redaction, no retention, no<br>erasure (F-C4)|
|18|Usage metering (`usage_events`)|Partial|`worker/usage.py:33–89`; `worker/main.py:788–806`|Written only on clean shutdown;<br>lost on crash (F-H18)|
|19|Quota: concurrent + monthly<br>minutes|Partial|`control_plane/mint.py:121–130`|Telephony path checks<br>concurrency only (F-H17)|



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

4/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

|20|Telephony: Telnyx + LiveKit SIP,<br>numbers, calls|Present|`tenant_portal_api/telephony_{routes,service,que`<br>`ries}.py`, `telnyx_client.py`, `livekit_sip.py`|Auth fallback secret (F-C1); live<br>carrier proof still open per<br>`state/PROGRESS.md`|
|---|---|---|---|---|
|21|Telnyx webhook Ed25519<br>verification|Present|`tenant_portal_api/telephony_webhooks.py:105–152`|Bypassed in mock mode;<br>unbounded replay set (F-H5)|
|22|Telnyx webhook durability /<br>dedupe|Partial —<br>defective|`telephony_webhooks.py:346–377`|In-memory dedupe in front of a<br>failable write → permanent event<br>loss (F-H6)|
|23|Telephony credential encryption<br>at rest|Present, non-<br>standard|`tenant_portal_api/telephony_credentials.py:26–`<br>`93`|Hand-rolled cipher while<br>`cryptography` is already a<br>dependency (F-M7)|
|24|Provider capability registry|Present|`worker/providers/capabilities.py:100–165`|Urdu has one provider per layer, no<br>redundancy (F-H10)|
|25|Browser SDK `@awaazlabs-`<br>`uva/voice`|Present|`sdk/src/index.ts` (497 lines)|No fetch timeout; terminal refresh<br>failure; 3 error codes (F-H12, F-<br>M14)|
|26|Server SDK `@awaazlabs-uva/agents`|Present|`sdk-server/src/index.ts` (313 lines)|No test script at all|
|27|Telephony SDK `@awaazlabs-`<br>`uva/telephony`|Present|`telephony/src/` (~900 lines), has smoke +<br>contract tests|Not published by CI (voice only)|
|28|Tenant dashboard (Next.js)|Present|`dashboard/src/` (39 files, 5,838 lines)|29 dependency advisories (F-C5);<br>no security headers (F-M10)|
|29|Platform admin UI|Absent|`admin/` is a JSON API only; no frontend in the<br>repo|Operator console exists only as<br>curl-able endpoints|
|30|Official integration examples|Absent —<br>actively<br>broken|Deleted in `df97bf6` (2026-08-18)|Still referenced by CI and 11 doc<br>links (F-H2)|
|31|Billing / plans / payments|Absent|No Stripe, no plans table, no invoice surface<br>anywhere in the repo|Metering exists; commerce does<br>not|
|32|SSO / RBAC / audit export|Absent|One credential pair per tenant; no roles, no user<br>table for tenants|Blocks any enterprise claim|
|33|Production migration runner|Absent|Only `scripts/db_reset.py`, which is DEV-ONLY<br>and re-applies `0001` (drops core tables)|No version table, no forward-only<br>path (F-H11)|
|34|Observability stack (traces,<br>metrics, alerts)|Absent|Optional Sentry (`control_plane/app.py:96–105`)<br>only; no OTel, Prometheus, alerting|Latency _hooks_ exist; an ops<br>product does not|
|35|Kill switch / rollback automation|Absent|No such control in any workflow or service|—|
|36|Public legal/trust pack (ToS,<br>Privacy, DPA)|Absent|Not present in the repository|Blocks honest commercial sale|



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

5/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

## 3. Per-component findings 

Guideline §2: for everything present or partial, check correctness, scalability, cost discipline, error handling and observability, test coverage and debt — not merely existence. 

### 3.1 Control plane (control_plane/) 

Correctness. The mint's gate ordering in `control_plane/mint.py:67–157` is correct and defensible: the HMAC is verified before the nonce is burned, the nonce insert is inside the same transaction as the session row and quota increment (so a replay cannot double-mint), and unknown tenants return 401 rather than 403 so the endpoint does not confirm which tenants exist. This is genuinely good work and should be preserved as-is. 

Three defects sit around it: 

- `mint.py:70,77` selects `hmac_secret_hash` into `stored_hash` and never uses it. The comparison is made against the raw secret returned by the provider. Dead code that implies a verification step that does not happen. 

- `mint.py:118` — `if allowed_origins and origin not in allowed_origins` means a tenant whose `allowed_origins` array is empty has no origin enforcement at all. `supabase/migrations/0001_schema.sql:30` defaults the column to `'{}'` , so every tenant is unrestricted until someone explicitly populates it. There is no admin or portal route that sets it. 

- `app.py:173–249` — `/v1/voices` is unauthenticated, and on any DB error it swallows the exception ( `app.py:204–205` ) and returns a hardcoded fallback catalogue of five voice IDs. A caller cannot distinguish "these are the voices" from "the database is down." This is precisely the silent-failure pattern guideline §2 asks about. 

Scalability. `_hits: dict[str, list[float]]` ( `app.py:253` ) is a `defaultdict` that is never pruned of tenant keys — only of timestamps within a key. Every distinct `X-Tenant-Id` header value ever seen creates a permanent entry. Since that header is unauthenticated (F-H4), an attacker can grow this dictionary without bound. 

Cost discipline. `_run_dispatch_background` ( `app.py:419–445` ) opens a new LiveKitAPI client per dispatch via `asyncio.run` in a threadpool thread. Every session pays a fresh TLS handshake and event-loop construction on the critical path to first audio. This is a concrete, measurable contributor to the ">20s to first audio" symptom recorded in the previous report, and it is fixable without touching the pipeline. 

Error handling. Good: dispatch failure rolls the session back and decrements the quota ( `app.py:390–405,438–445` ). Bad: `except Exception: pass` at `app.py:104` (Sentry init) and `app.py:204` (voices query). 

### 3.2 Worker (worker/) 

Correctness. `worker/config.py:114–151` is the strongest isolation code in the repository: it opens a transaction, sets the Postgres role to `authenticated` , injects the tenant's ID as a JWT claim, and reads the agent row under RLS — so a mismatched agent ID is invisible rather than merely rejected. That is a real second IDOR guard, independent of the mint's. 

`worker/main.py:126–132` places the untrusted tenant persona in a separate `ChatContext` system message behind a framing preamble, never concatenated into the platform instructions. The framing text itself ( `main.py:57–63` ) is well written. 

Scalability / event-loop correctness. `worker/tools.py:61` and `worker/tools.py:87` call synchronous psycopg.connect() directly inside async def coroutines. Every other database touch in the worker is carefully wrapped in `asyncio.to_thread` (see `main.py:214` , `main.py:463` ) precisely to avoid this. These two are not. When the agent ends a call or escalates, the event loop blocks for the duration of a TLS connection to Supabase — during a live audio session. This is a correctness bug with an audible symptom, and it contradicts the discipline the rest of the file follows. 

`worker/config.py:31` — `_config_cache` is a module-level dict keyed by `(tenant_id, agent_id)` with no eviction. It grows for the life of the process 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

6/50 

9/13/26, 5:49 PM life of the process. 

AwaazLabs UVA Audit 

Cost discipline. There is no upper bound on agents.prompt. `tenant_portal_api/app.py:107` sets `min_length=1` and no maximum; `supabase/migrations/0001_schema.sql:40` declares plain `text` . Every LLM call pays for the whole persona on every turn. This is the direct mechanism behind the recorded Groq tokens-per-minute exhaustion, and the mitigation that exists ( `worker/prompt_compact.py` , applied at `main.py:95–104` ) compacts only for Groq, at session build time, after the tenant has already stored an arbitrarily large prompt. The correct control — a server-side length cap at write time — does not exist. 

There is likewise no cap on the number of agents a tenant may create ( `tenant_portal_api/app.py:308` ). 

Error handling and observability. `_wire_session_diagnostics` ( `main.py:545–650` ) is thorough and surfaces provider errors that would otherwise be silent — good. But `_release_quota_slot` ( `main.py:730–835` ) wraps its entire body in `except Exception` → `logger.warning` , so a failure to record billing data or release the concurrency slot produces one warning line and nothing else. There is no alert, no dead-letter, and no retry. 

Resilience. Usage and quota release happen only in LiveKit shutdown callbacks ( `main.py:832–834` ). Any ungraceful worker exit — OOM, crash, container eviction — leaves the session row open forever, the concurrency slot consumed, and the call unbilled. `scripts/reconcile_sessions.py` exists to repair this, but nothing in the repository schedules it: there is no cron definition, no workflow, and no runbook step that runs it. 

### 3.3 Telephony (tenant_portal_api/telephony_*, telnyx_client.py, livekit_sip.py) 

This is the largest subsystem (≈5,000 lines) and the best-engineered in places — `create_outbound_call` ( `telephony_service.py:1065–1250` ) implements a real leader-election idempotency lock with request-hash comparison and correct 409 conflict semantics. That is production-grade design. 

It is also where the single most serious finding lives (F-C1), and where the quota model diverges: 

- `telephony_queries.py:308–338` ( `reserve_call_quota` ) reads only tenants.max_concurrent. It never reads `max_minutes_month` or `quota_state.minutes_this_month` . A tenant blocked from browser sessions by the monthly cap at `mint.py:129–130` can still place unlimited outbound PSTN calls. 

- `telephony_queries.py:314–315` — `if not tenant_row: return True` . An unrecognised tenant ID is granted quota. This fails open. 

- No rate limit exists on `POST /portal/telephony/outbound-calls` ( `telephony_routes.py:517` ), and no spend guard or circuit breaker exists anywhere in the call path. Guideline §4b asks this directly: _"if a bug causes runaway calls, is there any circuit breaker, or does the system just keep calling until someone notices the bill?"_ — the honest answer here is the latter. 

Webhook durability. `telephony_webhooks.py:357–359` adds the event ID to an in-memory set _before_ `_persist_telnyx_webhook_event` runs. If that durable write fails, the handler logs a warning ( `:371–374` ) and still returns HTTP 200 ( `:377` ). Telnyx therefore does not retry; and if it did, the in-memory set would reject the retry as a duplicate. Events are lost silently and permanently. 

Additionally, `_persist_telnyx_webhook_event:280–305` inserts into `telephony_call_events` only when a matching call row is found. Unmatched events — exactly the ones you need when debugging a failed call — are never persisted, so the databasebacked dedupe never gets a row for them either. 

Test-only backdoors in production code. `telephony_routes.py:73–74` returns a hardcoded tenant ID ( `"tenant_test_123"` ) with no token when `TELEPHONY_ALLOW_MOCK_PORTAL_AUTH=1` ; `telephony_routes.py:145–150` accepts the literal signature `"valid_mock_signature"` when `TELEPHONY_ALLOW_MOCK_MACHINE_AUTH=1` . Both default off and are documented as dev-only ( `docs/TELEPHONY_REAL_PROVIDER_STAGING.md:15,71` ), but they live in the same module that buys phone numbers and places calls, and nothing asserts at startup that they are off. 

3 4 Browser SDK ( dk/) https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

7/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

### 3.4 Browser SDK (sdk/) 

- `sdk/src/index.ts:181–188` — the session `fetch` has no timeout and no AbortController. If the host backend stalls, `connect()` never resolves and never rejects. The integrator has no hook to detect it. This is the exact shape of the ">20s of silence after a successful mint" symptom, from the client side. 

- `sdk/src/index.ts:411–441` — when token refresh fails, the SDK emits one `error` event and does not reschedule. `scheduleTokenRefresh` is called only on success ( `:437` ). A single transient network blip at the 60-second mark therefore kills the call when the 120-second LiveKit token expires, and from the user's perspective the agent simply stops responding. 

- `sdk/src/index.ts:46` — three error codes total. `:189–190` maps every HTTP 429 to `quota_exceeded` , so a host cannot distinguish "you hit your plan cap" from "you are being rate limited" from "the upstream LLM returned 429." 

- `sdk/src/index.ts:366` — `document.body.appendChild(el)` with no `typeof document` guard. In a Next.js app (which the project's own dashboard is) this throws during server-side rendering if the module is imported at module scope. 

- `sdk/src/index.ts:274–278` — `emit` iterates listeners without try/catch; one throwing listener silently prevents all later listeners from receiving the event. 

- Neither `sdk/package.json` nor `sdk-server/package.json` defines a `test` script. The browser SDK that runs in every customer's page has zero automated tests. 

### 3.5 Admin service (admin/) 

`admin/security.py` implements PBKDF2-HMAC-SHA256 at 600,000 iterations with a random 16-byte salt ( `:390–397` ) — that is a correct, current-standard choice, and TOTP is implemented faithfully to RFC 6238 including the ±1-step drift window ( `:440– 456` ). Credit where due. 

The surrounding operational model is where it fails: 

- `admin/app.py:46–68` — `_ensure_admin_jwt_secret()` generates a secret and appends it to .env.local when the env var is absent, at import time. `docker/admin.Dockerfile:20–26` documents at length why this is wrong in a container (read-only filesystem → crash; ephemeral filesystem → new secret every deploy, invalidating every admin session) — but the code still does it, and nothing fails fast. The same pattern is repeated verbatim in `tenant_portal_api/app.py:53–70` . 

- No rate limit or lockout on `POST /admin/login` ( `admin/app.py:114–126` ). With a 6-digit TOTP and a ±1-step window, an unthrottled endpoint makes online code-guessing tractable. 

- `totp_verify` has no replay guard — the same valid code is accepted repeatedly within its 90-second window. RFC 6238 §5.2 requires rejecting the second use. 

- Failed logins are never recorded. `record_admin_action` is called only on success ( `app.py:134,144,…` ), so `admin_audit_log` contains no evidence of an attempted break-in. 

- There is no admin JWT revocation list; an 8-hour token remains valid after an account is disabled (and there is no disable flag on `admin_users` anyway). 

### 3.6 Data layer (supabase/migrations/) 

   - No migration versioning. There is no `schema_migrations` table and no forward-only runner. The only automation is `scripts/db_reset.py` , whose own docstring says "DEV only — never prod," and which applies `0001_schema.sql` — a file that begins with `drop table if exists usage_events, quota_state, sessions, agents, voices, tenants cascade` ( `0001_schema.sql:6–11` ). There is consequently no safe, repeatable way to apply a schema change to production, and no record of which migrations any environment has received. 

   - Duplicate migration number. `0014_telephony_data_governance_audit.sql` and 

- `0014_telephony_idempotency_webhook_tenant_scope.sql` share a version. Ordering currently resolves alphabetically and deterministically but the numbering discipline the guideline asks about is broken and two later files switch to a 

- https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

8/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

- deterministically, but the numbering discipline the guideline asks about is broken, and two later files switch to a timestamp scheme ( `20260801185628_…` ), so the repository now has two incompatible conventions. 

- No down migrations anywhere. Guideline §3 asks specifically about irreversible operations with no documented rollback; every migration here is one-way. 

- 0013_telephony_constraints_indexes_status_idempotency.sql:192–293 creates 28 indexes without `IF NOT EXISTS` , so the file is not re-runnable — which only works because `db_reset.py` drops everything first. 

- Missing index: `usage_events` is indexed on `(tenant_id, at desc)` ( `0001:76` ) and `(tenant_id, kind, at)` ( `0010` ), but not on session_id. `tenant_portal_api/queries.py:61–67` joins `usage_events ue on ue.session_id = s.id` inside the `/portal/agents` query for every tenant. As `usage_events` grows this becomes a scan on the hottest dashboard page. 

- Unbounded table: `used_nonces` ( `0004` ) has one row per successful mint and no purge job anywhere in the repository — no cron, no script, no `delete` statement. The `used_nonces_used_at_idx` index on `used_at` suggests cleanup was intended and never written. At the documented 120 mints/minute ceiling this is ~5M rows/month per busy tenant. 

- RLS is effectively decorative. `0002_rls.sql` enables RLS and writes `for select` policies keyed on `auth.jwt() ->> 'tenant_id'` — but every service in this repository connects through `scripts/dbconn.py:30–50` as the database owner, which bypasses RLS. The single exception is `worker/config.py:122–123` , which genuinely assumes the `authenticated` role. This is documented as intentional (ADR-005), and it is a defensible design; but it means the RLS policies protect nothing in the request path except that one read, and should not be cited as tenant-isolation evidence for the other services. 

### 3.7 Test coverage and technical debt 

- F-H1 below is the headline: 53 of 75 test files never execute. 

- Positive: no `TODO` , `FIXME` , `HACK` or `XXX` markers exist anywhere in `control_plane/` , `worker/` , `tenant_portal_api/` , `admin/` , `services/` , `sdk*/src` , `telephony/src` , `dashboard/src` , `supabase/` or `scripts/` — a scan returned zero. That is unusually clean. 

- 28 exception handlers swallow errors silently (catch → `pass` /bare `return` ), 14 of them in production service code. Full inventory in Appendix A.3. 

- `scratch/` (5 files) and `graphify-out/` (generated documentation snapshots, including two dated subdirectories) are committed to the repository root. 

- `tests/test_tts.py` and `tests/test_harness.py` are documented in `pytest.ini:12–17` as retired-but-kept-on-disk. That is a reasonable, honest choice — but it is the same mechanism that now hides 51 _live_ test files. 

## 4. Codebase and engineering practices findings 

### Architecture and module boundaries 

Boundaries are mostly clean and deliberately so — three FastAPI apps with separate auth domains, and the separation is documented at the top of each module. Two real leaks: 

- `control_plane/app.py:51` imports `admin.audit.record_mint_rejection` , so the "completely separate" control-plane image must vendor part of `admin/` ( `docker/control-plane.Dockerfile:19` acknowledges this). 

- `tenant_portal_api/auth.py:22` and `telephony_routes.py:49–50` import from `control_plane.secrets` , coupling the portal to the control plane's module tree. 

Both are minor and documented. The more significant structural issue is `sys.path.insert` used in 12 separate modules to 

h h j h i ll bl k l i i l i https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

9/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

reach `scripts/dbconn.py` — the project has no installable package layout, so every service manipulates `sys.path` at import time. That works, but it makes the dependency graph implicit and is why `docker/tenant-portal-api.Dockerfile:7` has to `COPY scripts/ scripts/` (shipping every provisioning script into the runtime image). 

### Code quality 

Naming is consistent, functions are mostly appropriately sized. Two outliers: `telephony_service.py` at 2,451 lines and `telephony_routes.py` at 1,203 lines are approaching "god file" territory, and `worker/main.py:708–905` nests a 200-line closure ( `_setup_and_start` ) containing three further nested async closures inside the entrypoint — hard to test in isolation, which may be part of why the worker's shutdown path has no unit test. 

### Dependency hygiene 

- Pinning is good — `requirements.txt` and both Docker requirement files use `==` throughout; all four npm projects have lockfiles. 

- But requirements.txt is a monolith shipped to services that do not need it. `docker/tenant-portal-api.Dockerfile:6` installs the full file — pulling `livekit-agents` , `numpy` , `openai` , `python-socketio` , `loguru` into a service that imports none of them, and inheriting the vulnerable `aiohttp` in the process. The control-plane and admin images correctly use slim files; the portal image does not. 

- Vulnerabilities found: see F-C5 (dashboard) and F-H15 (aiohttp). Full scan output in Appendix A.1–A.2. 

### CI/CD and git discipline 

- `.github/workflows/ci.yml:69–99` — job `example-app-build` runs `npm ci` in `examples/web-client` and `examples/host-backend` . Neither path exists at HEAD; both were deleted in `df97bf6` ("Humanization of cartesia and rime", 2026-08-18) — a TTS commit that removed the entire quickstart. This job must fail on every push and pull request. 

- `.github/workflows/deploy-prod.yml:3–5` triggers on `push: [main]` with no needs: on the CI job. Tests and deployment are independent. A push to `main` deploys to production regardless of test outcome — and given the point above, the test outcome is always red. 

- Deploy steps are guarded by `if: env.HOOK_URL != ''` , so a missing secret produces a green build with no deployment and no warning. 

- No portal deploy hook exists in either deploy workflow, although `docker/tenant-portal-api.Dockerfile` exists and the portal is the backend for both the dashboard and all telephony. 

- No rollback job, no approval gate, no environment protection rules in any workflow. 

- `.github/workflows/release-sdk.yml:34` uses `if: ${{ secrets.NPM_TOKEN != '' }}` . The other two workflows use the documented workaround (map to `env:` , then test `env.` ) — this one does not. GitHub does not list `secrets` among the contexts available to a step-level `if` , so this condition is at best non-portable and should be verified against an actual run; the inconsistency with the sibling workflows is itself a smell. 

- `release-sdk.yml` publishes only sdk/. `@awaazlabs-uva/agents` and `@awaazlabs-uva/telephony` have no release automation. It declares `permissions: contents: read` and no `id-token: write` , so there is no npm provenance attestation, and there is no SBOM step anywhere. 

- No CODEOWNERS, no pull-request template. Branch protection could not be verified (no repository-settings access) — see Section 6. 

- `git log` shows large multi-concern commits ( `de77870` "Merge hamza telephony and dashboard work into main", `b5e88b1` five features in one commit). The `examples/` deletion inside a TTS commit is a concrete instance of the harm that causes. 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

10/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

### Documentation accuracy 

`docs/` contains 40+ files and the inline documentation is genuinely high quality. The problem is drift between documentation and code, and it is not cosmetic — in three places the documentation states a security property that the code no longer has: 

|`CLAIM`|`WHERE CLAIMED`|`REALITY`|
|---|---|---|
|"hash ONLY, never the secret"|`supabase/migrations/0001_schema.sql:27`|`0009_tenant_secrets.sql:4` added `tenants.hmac_secret`<br>holding the raw value|
|"must never live in a DB table"|`control_plane/secrets.py:3–5`|`control_plane/secrets_db.py:52` reads exactly that<br>column|
|"hash ONLY. never the secret."|`docs/21-PHASE-1-SUPABASE.md:12`|same|
|"no worker Dockerfile"|`docs/63-GUIDE-WORKER-DEPLOYMENT-DEFERRAL.md`|`docker/worker.Dockerfile` exists|
|Migrations run via<br>`reconcile_sessions.py --dry-run`|`README.md:62`|That script reconciles sessions; it applies no migrations|
|Links to<br>`VAAS_GODTIER_MASTER_PLAN_V2.md`,<br>`VAAS_COLLABORATION_GUIDE.md`|`README.md:45–46`|Neither file exists|
|Links to `examples/web-client`,<br>`examples/host-backend`|`README.md:31,85,104`;<br>`docs/CLIENT_QUICKSTART.md:10,11,40,69,134,135`;<br>sdk/README.md:22,23,129,130,165,166|Deleted 2026-08-18. `sdk/README.md` is the published<br>npm package README — these dead links are shipped<br>to every consumer.|



### AI-generated code 

Guideline §3 asks this directly. The commenting style, the ADR cross-references, the "verified against installed package via `inspect.signature` " notes, the `state/PROGRESS.md` / `state/BLOCKERS.md` structure, and phrases such as "JUDGMENT CALL (flagged for human review, not silently made)" at `admin/app.py:49` and "this is an unattended overnight session (no human available to review a new third-party dependency choice)" at `admin/security.py:370–375` indicate that a substantial portion of this codebase was produced by an AI coding assistant working autonomously, in sessions without a human in the loop. 

That is not a defect in itself, and the discipline shown (verifying library signatures rather than guessing, recording reversals rather than erasing them) is better than most human-written code. But it has three audit consequences that must be recorded: 

1. The two hardcoded-secret / auto-generated-secret patterns (F-C1, F-H13) both carry comments explaining that they are unsafe. The code knew; nobody acted on it. `docker/admin.Dockerfile:20–26` spends seven lines describing exactly why `_ensure_admin_jwt_secret` is wrong in a container, and the function is still there. 

2. pytest.ini's whitelist (F-H1) is the mechanism by which a growing, well-written test suite became invisible. Each phase added its new test file to the whitelist; the telephony work, contributed separately, never was. Nobody noticed because the gate stayed green. 

3. Guideline §3 requires a statement on review: it should be confirmed in writing which portions were reviewed line-byline by a human who understands them. Based on the artefacts in the repository, that confirmation does not exist for the telephony subsystem or the worker shutdown path. 

### Bus factor 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

11/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

`sdk/package.json:6–8` , `sdk-server/package.json` , `telephony/package.json` and the CI badge in `README.md:4` all point at github.com/habiba-imran/urdu-agent-SDK — an individual's repository — while `git remote -v` shows the actual origin is `github.com/Finova-Solutions/urdu-voice-agent-SDK` . Published npm packages therefore direct customers to a personal account that the company may not control. This is both a supply-chain risk (who can push to that repo?) and a bus-factor risk. 

## 5. Security findings 

### 5a. General application security 

|`AREA`|`FINDING`|`EVIDENCE`|
|---|---|---|
|Authentication|Hardcoded fallback JWT secret on the telephony surface|`tenant_portal_api/telephony_rou`<br>`tes.py:59–61` — F-C1|
||Unauthenticated session mint|`control_plane/app.py:577–590` —<br>F-C2|
||Auto-generated, non-persistent JWT signing keys|`admin/app.py:46–68`;<br>`tenant_portal_api/app.py:53–70`<br>— F-H13|
||No login throttling or lockout; no TOTP replay guard; no failed-login audit|`admin/app.py:114`;<br>`tenant_portal_api/app.py:287`;<br>`admin/security.py:440` — F-H14|
||Tenant "password" is the tenant's HMAC signing secret|`tenant_portal_api/auth.py:36–61`<br>— F-C6|
|Authorization|Enforced server-side on every route reviewed. `_require_tenant` / `_require_machine` /<br>`_require_admin` are applied consistently, and tenant scoping is by `claims["sub"]`, never by<br>a client-supplied ID. This is correct.|`tenant_portal_api/app.py:245–`<br>`279`; `admin/app.py:104–111`|
||Worker adds a second, independent RLS-backed ownership check|`worker/config.py:114–151` —<br>correct|
||`reserve_call_quota` fails open on unknown tenant|`tenant_portal_api/telephony_que`<br>`ries.py:314–315` — F-H17|
|Injection (SQL)|No SQL injection found. Every query reviewed uses parameterised placeholders. The<br>three f-string interpolations (`queries.py:85,114,176`) insert only the module-level<br>`_AGENT_COLUMNS` constant, never user input.|—|
|Injection<br>(command)|No `subprocess`/`os.system` call reachable from a request path. `scripts/db_reset.py:41`<br>shells out to `psql`, but it is an operator script.|—|
|Input validation|Unbounded `agents.prompt` (cost + latency vector)|`tenant_portal_api/app.py:107` —<br>F-M2|
||Unbounded `limit` on `/portal/sessions` and `/portal/telephony/calls`|`app.py:416`;<br>`telephony_routes.py:551` — F-M3|
||No request-body size limit on the public Telnyx webhook|`telephony_webhooks.py:339–341` —|



`telephony_webhooks.py:339–341` — 

F M4 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

12/50 

|9/13/26, 5:49 PM|AwaazLabs UVA Audit|F-M4|
|---|---|---|
|Rate limiting|Keyed on unauthenticated `X-Tenant-Id`, checked before signature verification → victim-<br>tenant denial of service|`control_plane/app.py:544`;<br>`machine_auth.py:201` — F-H4|
||In-process and unbounded; resets on every deploy|`control_plane/app.py:253`;<br>`machine_auth.py:169` — F-H5|
||None at all on `/portal/login`, `/admin/login`, `/portal/telephony/outbound-calls`, or the<br>Telnyx webhook|—|
|CORS|Control plane defaults to `["*"]` with `allow_credentials=True`|`control_plane/app.py:94,117–123`<br>— F-C3|
||Admin and portal CORS are correctly restricted to explicit allowlists|`admin/app.py:70–85`;<br>`tenant_portal_api/app.py:72–97`<br>— correct|
|Security headers|None anywhere. No CSP, HSTS, X-Frame-Options, X-Content-Type-Options on any<br>FastAPI service; `dashboard/next.config.js` defines no `headers()`. Material given the<br>dashboard holds a bearer token in `localStorage` and reveals the tenant signing secret.|— F-M10|
|Transport /<br>storage encryption|DB connections force `sslmode=require` (`scripts/dbconn.py:49`) — correct. But<br>`normalize_tools_base_url` explicitly permits `http://` (`tools_webhook.py:30`), so the tool-<br>gateway shared secret can be sent in cleartext.|F-H8|
||Tenant HMAC secret stored plaintext (`0009:4`); `agents.tools_auth_secret` stored plaintext<br>(`0026:8`); telephony credentials encrypted with a hand-rolled cipher<br>(`telephony_credentials.py:26–43`). Three different secret-handling standards in one<br>schema.|F-C6, F-M8, F-M7|
|Secrets exposure|`GET /portal/credentials/secret` returns the raw signing secret to the browser|`tenant_portal_api/app.py:405–`<br>`412`; `queries.py:248–261` — F-C6|
||No `.dockerignore`; `docker/worker.Dockerfile:34` does `COPY . .` → `.git/` (full history) and<br>any local `.env.local` are baked into the image|F-H16|
||Error responses interpolate raw exception text to clients: `telephony_routes.py:541`<br>returns `f"Outbound call setup failed: {e}"`|F-M5|
||`/docs` and `/redoc` enabled unauthenticated on the control plane|`control_plane/app.py:112–113` —<br>F-M6|
|Dependency CVEs|1 CRITICAL + 7 HIGH + 11 MODERATE in `dashboard/`; 1 HIGH + 2 MODERATE in `aiohttp`|F-C5, F-H15|
|Secrets in git<br>history|Scanned 278 commits — none found. Only `.env.example` templates and elided<br>placeholder JWTs. This is a clean result.|—|
|Container security|All four images run as root (no `USER` directive); all four pin floating tags (`python:3.12-slim`,<br>no digest); none define a `HEALTHCHECK`|`docker/*.Dockerfile` — F-M9|



### 5b. AI / LLM-specific security 

Guideline §4b applies squarely here: this system feeds untrusted, real-time speech from arbitrary callers into an LLM prompt, and that LLM controls tools that hang up calls, create support tickets, and write to third-party calendars. 

##### What is done correctly, verified by reading: 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

13/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

- The tenant persona is never string-concatenated into the platform system instructions. It is added as a separate `ChatContext` system message behind an explicit framing preamble ( `worker/main.py:126–132` , preamble at `:57–63` ), and the tools are fixed Python callables imported from `worker/tools.py` — never derived from tenant text ( `main.py:110` ). 

- Provider selection cannot be influenced by prompt content; it is read from the RLS-scoped agent row ( `worker/config.py` ) and dispatched by a closed registry that raises rather than substituting ( `worker/providers/registry.py:45,57,86` ). 

- Tool arguments that carry tenant identity are taken from `AgentUserdata` , populated from the verified config — never from tool arguments. `worker/tools.py:38` documents this explicitly and the code honours it ( `tools.py:60,86,200` ). This is the single most important thing to have got right, and it is right. 

What is not adequate: 

1. No output validation before tool execution. Guideline §4b asks whether LLM output is "validated against a strict schema before being stored or displayed, or is raw LLM text trusted." Here, LLM-produced arguments flow straight into `_post_client_tool` ( `tools.py:193–230` ) and into `INSERT` statements ( `tools.py:93–97` ). The only constraint is the Python type signature. 

2. The write-capable tools have no authorisation model. `cancel_appointment(customer_phone, existing_date, reason)` ( `tools.py:354–381` ) cancels a booking identified solely by a phone number the _caller_ supplied. Nothing verifies the caller owns that number. A caller who says "cancel the 3pm appointment for 0300-1234567" — or who delivers an injection payload that makes the model believe they should — gets that cancellation executed against the tenant's real calendar. `book_appointment` and `reschedule_appointment` have the same shape. Nothing marks these as irreversible, nothing requires confirmation, and no idempotency key is sent. 

3. escalate_to_human remains reachable by injection (the previously recorded `BLOCK-SEC` residual), but it is now the _least_ damaging of the six tools. 

4. No per-call LLM budget or circuit breaker. There is no `MAX_LLM_CALLS_PER_CALL` , no token ceiling per session, and no spend guard. `scripts/usage_guard.py` exists but is a reporting/gate script invoked by `make usage-check` , not a runtime control. 

5. No fallback when a provider is rate-limited. `registry.py` raises `UnsupportedProviderError` ; `worker/providers/llm/groq.py:70` and `tts/uplift.py:63` set `max_retry=0` . A 429 from the single Urdu LLM provider ends the turn. 

6. Prompts and transcripts are logged in plaintext. `worker/main.py:602,608` log full user and assistant turn text at INFO level; `worker/prompt_dump.py` writes the complete assembled prompt — including the tenant persona — to `docs/last_session_prompt.txt` , and `.env.example:44` shows `UVA_DUMP_PROMPTS=1` is the default on. Caller PII therefore reaches application logs and a file on the worker's filesystem, neither of which is covered by any retention rule. 

7. Sub-processor transparency gap. `worker/providers/llm/groq.py:42–51` silently remaps eight advertised model IDs to a single live model, and `worker/telephony_tts.py` (invoked at `main.py:236,248` ) silently substitutes both the TTS provider _and_ the LLM provider for telephony calls. The capabilities API continues to advertise the tenant's original choice. A tenant told their data goes to model X may have it sent to model Y. For a DPA/sub-processor disclosure this matters. 

8. No record sufficient to reconstruct an LLM incident. Guideline §4b asks for "a record of every LLM call made (which provider, what task, when)." `usage_events` records aggregate token counts per session ( `worker/usage.py:61–89` ); it records neither the provider nor the model. If a tenant disputes what the agent said or did, the only artefacts are the stored transcript and ephemeral logs. 

## 6. Infrastructure, hosting and ownership inventory 

Guideline §5 exists specifically to produce documentation that does not yet exist. This inventory could not be completed from the repository — that incompleteness is the finding. What follows is the required table with everything the code _does_ 

d li i O h h fill i h id li " k d i i " i https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

14/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

prove, and explicit UNKNOWNs that the account owner must fill in. Per the guideline, "unknown, need to investigate" is an acceptable cell value; silence is not. 

|`SERVICE`<br>GitHub org<br>(`Finova-`<br>`Solutions`)|`EVIDENCE IT IS USED`<br>`git remote -v`|`LEGAL/BILLING OWNER`<br>UNKNOWN — owner must<br>fill|`TECHNICAL ADM`<br>UNKNOWN|`INS`<br>`MFA ON?`<br>UNKNOWN|`WHERE CREDENTIALS LIVE`<br>—|
|---|---|---|---|---|---|
|Render<br>(hosting)|`.github/workflows/deploy-`<br>`*.yml`; `docs/61-GUIDE-DEV-`<br>`TO-PROD.md`|UNKNOWN|UNKNOWN|UNKNOWN|Render env vars (`docs/62-GUIDE-`<br>`PROD-ENV-VARS.md`)|
|Supabase<br>(PostgreSQL<br>+ Storage)|`scripts/dbconn.py`;<br>`worker/session_recording.p`<br>`y:17–18`|UNKNOWN|UNKNOWN|UNKNOWN|`SUPABASE_DB_URL`,<br>`SUPABASE_SERVICE_ROLE`|
|LiveKit<br>Cloud|`control_plane/app.py:58–63`;<br>worker|UNKNOWN|UNKNOWN|UNKNOWN|`LIVEKIT_API_KEY/SECRET`|
|Telnyx<br>(PSTN)|`tenant_portal_api/telnyx_c`<br>`lient.py`|UNKNOWN|UNKNOWN|UNKNOWN|Per-tenant keys encrypted in<br>`telephony_connections`; platform<br>key + `TELNYX_PUBLIC_KEY` in env|
|Google /<br>Gemini|`worker/providers/llm/gemin`<br>`i.py`; `GOOGLE_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|
|Gladia<br>(STT)|`worker/providers/stt/gladi`<br>`a.py`; `GLADIA_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|
|Uplift AI<br>(TTS)|`worker/providers/tts/uplif`<br>`t.py`; `UPLIFTAI_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|
|Deepgram<br>(STT, en)|`DEEPGRAM_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|
|Groq (LLM,<br>en)|`GROQ_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|
|Cartesia<br>(TTS, en)|`CARTESIA_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|
|ElevenLabs<br>(TTS, en)|`ELEVEN_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

15/50 

|9/13/26, 5:49 PM|||AwaazLabs UVA Audit|||
|---|---|---|---|---|---|
|Fish Audio<br>(TTS, en)|`FISH_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|
|Rime (TTS,<br>en)|`RIME_API_KEY`|UNKNOWN|UNKNOWN|UNKNOWN|env|
|Soniox<br>(STT)|`scripts/probe_soniox_402.p`<br>`y`; ADR-002|UNKNOWN|UNKNOWN|UNKNOWN|env|
|Sentry<br>(errors)|`control_plane/app.py:96–`<br>`105`|UNKNOWN|UNKNOWN|UNKNOWN|`SENTRY_DSN`|
|npm<br>registry|`release-sdk.yml:37–41`|UNKNOWN|UNKNOWN|UNKNOWN|`NPM_TOKEN` GitHub secret|
|Domain /<br>DNS|Not referenced anywhere in<br>the repo|UNKNOWN|UNKNOWN|UNKNOWN|UNKNOWN|
|Monitoring<br>/ on-call /<br>status page|Does not exist|—|—|—|—|
|Email /<br>notification<br>service|Does not exist|—|—|—|—|



### Questions the repository cannot answer — must be answered by the owner 

1. For each row above: if this account were suspended or its owner unreachable tomorrow, what breaks and how long does recovery take? Three provider accounts are _already_ in a payment-failure state (Fish Audio, Soniox, Cartesia partially), which suggests billing ownership is not being monitored. 

2. Are production secrets distinct from staging and development secrets? `.env.example` describes one set of variable names for all environments and the repo has no mechanism to distinguish them. 

3. Has a database restore ever been tested? Nothing in the repository references backups at all. 

4. Is any of this running on a personal card or personal account? The npm/GitHub metadata pointing at an individual's repository makes this a live question, not a hypothetical. 

5. Are branch protection and required reviews actually enabled on main? There is no `CODEOWNERS` and no PR template, and `deploy-prod.yml` fires on any push to `main` — so if protection is not enabled, a direct push deploys to production. 

6. Is TENANT_PORTAL_JWT_SECRET set in the Render environment for the portal service? This is the single most urgent question in this report — see F-C1. It is not in `.env.example` and not in `docs/62-GUIDE-PROD-ENV-VARS.md` . 

7 F d fi di https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

16/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

## 7. Frontend findings 

Method note: assessed from source only. No running instance, no screenshots, no measured load times, no accessibility tooling. Items below are what source review can establish; usability and performance items marked _needs live review_ genuinely have not been tested. 

### Does the frontend expose what the backend computes? 

|`BACKEND CAPABILITY`|`SURFACED IN DASHBOARD?`|`EVIDENCE`|
|---|---|---|
|Agent CRUD, provider/voice selection|Yes|`dashboard/src/app/agents/`, `VoiceCatalogueGrid.tsx`|
|Credentials (tenant ID, publishable key, secret<br>reveal)|Yes|`app/credentials/page.tsx`|
|Session history incl. transcript + recording<br>URL|Yes|`app/sessions/page.tsx`|
|Usage summary|Yes|`app/usage/page.tsx`|
|Telephony (numbers, trunks, calls)|Yes|`app/telephony/page.tsx`|
|Browser test call|Yes — but via `dev-mint`|`app/test-studio/page.tsx:64`|
|escalations (the escalate-to-human tool's<br>entire output)|No|No route, no API, no query. Rows are written by<br>`worker/tools.py:93–97` and read by nothing.|
|Per-turn latency metrics|Emitted by SDK, not rendered|`sdk/src/index.ts:466–473`|
|Agent deletion|No|No endpoint exists to delete|
|Credential rotation|No|Admin-only (`admin/app.py:206`); tenants can view but not<br>rotate|
|Origin allowlist management|No|`allowed_origins` is displayed read-only; nothing can set it|



### Security of the frontend 

- Session token in localStorage ( `dashboard/src/lib/portalAuth.ts:24` ). Combined with `GET /portal/credentials/secret` (which the credentials page calls at `app/credentials/page.tsx:58` ), any XSS in the dashboard yields the tenant's permanent signing secret — and there is no self-service rotation to recover. This chain is the reason F-C6 is rated Critical rather than High. 

- No Content-Security-Policy ( `dashboard/next.config.js` defines no `headers()` ), which removes the main mitigation for the above. 

- Route gating is client-side only — `AppShell.tsx:41–56` redirects in a `useEffect` . This is acceptable _because_ the backend enforces the JWT on every route (verified in §5a); the UI gate is cosmetic and should not be relied on. Rated Low, not High, on that basis. 

- No dangerouslySetInnerHTML, no eval anywhere in `dashboard/src/` or `sdk/src/` — clean. 

- The Test Studio points at `/v1/session/dev-mint` ( `app/test-studio/page.tsx:64` ), i.e. the unauthenticated endpoint of F-C2. So the product's own in-app test path depends on the endpoint that must be removed or gated. 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

17/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

### Usability and technical quality 

- Empty, loading and error states exist as shared components ( `components/ui/empty-state.tsx` , `skeleton.tsx` , `toast.tsx` ) and SWR is used for fetching ( `swr-keys.ts` ) — the structural foundations for good state handling are present. _Whether every view uses all three needs live review._ 

- Responsive handling is explicit ( `AppShell.tsx` mobile nav, `md:` breakpoints throughout) — better than most internal tools. 

- Accessibility not assessed. Colour-contrast on pass/fail indicators, keyboard navigation, and chart alt-text all need a live pass with tooling. Radix primitives are used for dialogs and selects, which gives a reasonable baseline for free. 

- "publishable_key" is literally the tenant's UUID — `tenant_portal_api/queries.py:238` and `admin/queries.py:262` both return `str(row[0])` , the primary key. It is displayed to the user as a distinct credential, but it is neither publishable-keyshaped nor separately revocable, and nothing validates it server-side. This is misleading in the UI and a design inconsistency in the API. 

No in-app guidance or first-run onboarding anywhere in `dashboard/src/` . 

## 8. Compliance and data-handling findings 

### Part A — verifying what is already claimed 

|`CLAIM`|`VERDICT`|`EVIDENCE`|
|---|---|---|
|"Zero client secrets — the<br>browser SDK holds zero provider<br>or tenant secrets" (`README.md:99`)|False as a system claim. True of `@awaazlabs-uva/voice` itself. Untrue of the product: the<br>dashboard browser fetches the raw tenant HMAC secret from `GET /portal/credentials/secret`<br>(`tenant_portal_api/app.py:405–412`) and holds a portal JWT in `localStorage`.|F-C6|
|"Tenant prompts are treated as<br>untrusted data… never<br>interpolated into system<br>operating rules" (`README.md:101`)|True. Verified at `worker/main.py:126–132`.|—|
|"HMAC signing… 60-second<br>replay window" (`README.md:100`)|True. `control_plane/mint.py:27,93`.|—|
|`hmac_secret_hash` stores "hash<br>ONLY, never the secret"<br>(`0001_schema.sql:27`)|False since migration 0009.|F-C6|
|Data-governance / retention<br>columns exist<br>(`0014_telephony_data_governance`<br>`_audit.sql`)|True but misdirected. `retention_until`, `deletion_requested_at`, `deleted_at`, `redacted_at` were<br>added to seven telephony _infrastructure_ tables (trunks, SIP connections, outbound profiles,<br>phone numbers, dispatch rules) and to none of `sessions`, `sessions.transcript`,<br>`sessions.recording_url`, `telephony_calls`, or `escalations`. The retention machinery exists where<br>there is no personal data and is absent everywhere there is.|F-C4|
|Retention is actually enforced|No. No scheduled job, no cron, no workflow, no `delete` statement anywhere applies any<br>retention rule. The columns are inert.|F-C4|
|PII redaction exists|No. No redaction function exists in the repository. `sessions.transcript` stores verbatim turn text<br>(`worker/main.py:742–747`); `escalations.contact_info` stores caller phone numbers<br>(`worker/tools.py:96`); booking tools transmit `customer_name` and `customer_phone` to third-party<br>gateways (`worker/tools.py:304–308`).|F-C4|



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

18/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

Legal holds survive purge N/A — no purge exists to survive. Deletion audit trail No. No deletion path exists at any layer: no `DELETE` agent endpoint, no tenant-deletion endpoint, no storage-object deletion, no transcript deletion. 

F-C4 

### Part B — obligations that were never claimed but apply anyway 

Given what this product actually does — it records, stores and transmits real customer phone calls, in Urdu and English, across Pakistan, the Gulf and (per the product's own positioning) Western markets — the following apply regardless of whether they were in scope: 

|`OBLIGATION`|`APPLIES?`|`HANDLED?`|`EVIDENCE / CONSEQUENCE`|
|---|---|---|---|
|Call-recording<br>consent (all-<br>party / two-<br>party consent<br>states)|Yes, the moment any call<br>touches a jurisdiction<br>requiring all-party<br>consent (California,<br>Illinois, Pennsylvania,<br>Washington and others).|No<br>mechanism<br>whatsoever.|`worker/main.py` starts `session.start(..., record={"audio": True, "traces":`<br>`False, ...})` on every job, with an inline comment stating it does so _"even when_<br>_LiveKit Cloud sends_`enable_recording=false`_"_. There is no per-tenant flag, no per-<br>call flag, no consent capture, and no spoken disclosure —<br>`worker/session_opening.py` plays only the greeting. This is a strict-liability<br>exposure, not a best-practice gap.|
|Recording<br>disclosure<br>announcement|Yes for PSTN in most<br>jurisdictions|No|No disclosure text exists in `session_opening.py` or anywhere else.|
|GDPR right to<br>erasure, end-to-<br>end|Yes, for any EU data<br>subject|No|A deletion request cannot be satisfied: no delete endpoint; `sessions.transcript`<br>and `sessions.recording_url` have no deletion path; the Supabase Storage object at<br>`{tenant_id}/{room_name}.ogg` (`worker/session_recording.py:70`) is never removed;<br>prompt dumps in `docs/last_session_prompt.txt` and application logs are outside<br>any policy; and data already sent to<br>Gemini/Groq/Gladia/Deepgram/Cartesia/ElevenLabs/Rime/Telnyx cannot be<br>recalled.|
|GDPR 72-hour<br>breach<br>notification|Yes|No|No documented incident-response or notification process exists in the repository.<br>There is no email or notification service at all, so there is also no mechanism to<br>notify tenants.|
|CCPA/CPRA<br>access and<br>deletion rights|Yes if any caller is a<br>California resident|No|Same absence as GDPR.|
|Biometric /<br>voiceprint law<br>(Illinois BIPA,<br>Texas CUBI)|Needs legal<br>determination. The<br>pipeline stores raw call<br>audio indefinitely. It does<br>not currently perform<br>speaker diarisation or<br>voiceprint matching,<br>which is the usual trigger<br>— but retained raw voice<br>recordings are treated as<br>biometric identifiers<br>under some readings of<br>BIPA.|Not<br>considered|`worker/session_recording.py` stores mixed-channel `audio.ogg` per call,<br>permanently. A legal opinion is required before selling into IL/TX.|
|Data residency|Yes for MENA/Gulf and<br>any EU client|No|Single Supabase project, single region, single Storage bucket (`session-`<br>`recordings`). No residency selection exists anywhere in the schema or code.|
|Sub-processor<br>DPAs|Yes — for every one of the<br>9+ AI vendors and Telnyx|UNKNOWN<br>**→** assume|No DPA references exist in the repository. Several vendors are on free tiers<br>(`GROQ_API_KEY` free tier per `worker/providers/llm/groq.py:12–16`; `UPLIFT_MODE`|



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

19/50 

|9/13/26, 5:49 PM|||AwaazLabs UVA Audit|
|---|---|---|---|
|||no|fixture/live), where a DPA typically does not exist at all. Customer call transcripts<br>are transmitted to these vendors.|
|Sub-processor<br>transparency|Yes|No|Silent model and provider remapping (`worker/providers/llm/groq.py:42–51`;<br>`worker/telephony_tts.py`) means the tenant's disclosed processor may not be the<br>actual one.|
|Signed data-<br>processing<br>terms with<br>tenants|Yes|No|No ToS, Privacy Policy or DPA exists in the repository.|
|Payment-card<br>data|No|N/A|No card data is handled — no billing exists at all. This is the one compliance<br>question with a clean answer.|



## 9. Consolidated prioritised findings 

Every finding, sorted Critical → High → Medium → Low, each with its location, what was checked, why it matters, and a concrete next step. 

`C R I T I C A L` — security holes, real data exposure, or legal exposure. Fix before anything else ships. 

```
F-C1
```

#### Hardcoded fallback JWT secret authenticates the entire telephony API 

`WHERE: tenant_portal_api/telephony_routes.py:59–61` _What was checked:_ Read the module; traced `TENANT_PORTAL_JWT_SECRET` across the codebase; confirmed `tenant_portal_api/app.py:53–70` uses a _different_ resolution path (env → `.env.local` → auto-generate); grepped `.env.example` and `docs/62-GUIDEPROD-ENV-VARS.md` for the variable. 

```
TENANT_PORTAL_JWT_SECRET = os.environ.get(
    "TENANT_PORTAL_JWT_SECRET", "mock_jwt_secret_for_tests"
)
```

`WHY IT MATTERS:` If `TENANT_PORTAL_JWT_SECRET` is not present as a real process environment variable on the portal service, every `/portal/telephony/*` route verifies tenant identity against a publicly-readable constant. Anyone can mint `{"sub": "<any tenant uuid>", "aud": "tenant-portal", "iss": "uvatenant-portal"}` signed with that string and then: connect or rotate Telnyx credentials, search and purchase phone numbers (real money), configure routing, place outbound PSTN calls, and read all call records — for any tenant. Secondly, this variable is absent from .env.example and absent from docs/62GUIDE-PROD-ENV-VARS.md (which documents `ADMIN_JWT_SECRET` in detail but not this one), so an operator following the project's own documentation will not set it. Thirdly, even when set only in `.env.local` , `app.py` finds it and `telephony_routes.py` does not — producing a silent split where legitimately issued tokens are rejected and forged ones accepted. _Fix:_ Delete the default. Import the resolved secret from a 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

20/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

single shared module and fail fast at import if it is unset, matching the pattern `control_plane/app.py:68–87` already uses. Add the variable to `.env.example` and `docs/62` . Then rotate it, and treat every telephony action taken to date as unattested until the production environment is confirmed. 

```
F-C2
```

#### Unauthenticated session-mint endpoint 

`WHERE: control_plane/app.py:577–590` , `:466–531` , `:263–268` _What was checked:_ Read the route and `_dev_mint_session` ; confirmed `DevSessionBody.publishableKey` ( `:265` ) is never referenced after declaration; confirmed the route is registered unconditionally with no env gate; confirmed `dashboard/src/app/test-studio/page.tsx:64` calls it in production. _Why it matters:_ `POST` 

`/v1/session/dev-mint` takes only `agentId` , looks up the owning tenant ( `:348–355` ), signs the mint request with the server's own copy of the tenant secret ( `:475–486` ), and returns a live LiveKit token. The `publishableKey` is accepted and discarded. Worse, it is called with `auto_reset_quota=True` ( `:587` ), so on hitting the concurrency cap it executes `_dev_reset_concurrency` — `update quota_state set concurrent_now = 0` ( `:358–363` ) — wiping the tenant's live concurrency count and defeating the cap for real sessions too. Anyone who obtains or guesses an agent UUID can consume a tenant's provider spend indefinitely. _Fix:_ Remove the route, or gate it behind an explicit `UVA_ENABLE_DEV_MINT=1` env flag that is asserted off in production, and move the Test Studio to an authenticated path. Never ship `auto_reset_quota` to a deployed environment. 

```
F-C3
```

#### Credentialed wildcard CORS on the control plane 

`WHERE: control_plane/app.py:91–94` , `:117–123` _What was checked:_ Read the middleware configuration. 

```
_CORS_ORIGINS = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()] or ["*"]
app.add_middleware(CORSMiddleware, allow_origins=_CORS_ORIGINS, allow_credentials=True, ...)
```

`WHY IT MATTERS: .env.example:31–32` documents that an empty `CP_ALLOWED_ORIGINS` "defaults to permissive (allow all) for dev" — but the same code runs in production, and nothing warns or fails if the variable is unset. Combined with F-C2, any website on the internet can mint sessions against this control plane from a visitor's browser. The admin and portal services get this right (explicit allowlists, no wildcard); the control plane does not. _Fix:_ Fail fast at startup if `CP_ALLOWED_ORIGINS` is unset and `ENVIRONMENT != "development"` . Never combine `allow_origins=["*"]` with `allow_credentials=True` . 

###### `F-C4` 

#### Unconditional call recording with no consent, disclosure, retention, or erasure 

`WHERE: worker/main.py` ( `session.start(..., record={"audio": True, "traces": False, "logs": False, "transcript": False})` ); `worker/session_recording.py:1–198` ; `worker/main.py:742–760` ; `supabase/migrations/0011` , `0014_telephony_data_governance_audit.sql` , `0027` _What was checked:_ Traced the recording path end to end; read migration `0014` in full to see which tables received retention columns; grepped the entire repository for any scheduled purge, deletion endpoint, or redaction 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

21/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

function (none exist). _Why it matters:_ Every call — browser and PSTN — is recorded to `audio.ogg` , uploaded to Supabase Storage at `{tenant_id}/{room_name}.ogg` ( `session_recording.py:70` ), and a 7-day signed URL is persisted in plaintext to `sessions.recording_url` ( `:89,126–134` ) where the portal returns it to any holder of a tenant JWT. The verbatim transcript is stored in `sessions.transcript` . Caller phone numbers are stored in `escalations.contact_info` . None of this is ever deleted, there is no consent capture, no recording disclosure, no per-tenant opt-out, and no erasure path. The one migration that added retention columns ( `0014` ) added them to trunks and SIP connections — tables containing no personal data — and to none of the tables above. In all-party-consent jurisdictions this is strict liability; under GDPR/CCPA it makes an erasure request impossible to satisfy. _Fix, in order:_ (1) Make recording opt-in per agent, defaulting off, and honour LiveKit's `enable_recording` signal rather than overriding it. (2) Add a spoken disclosure to `session_opening.py` when recording is on. (3) Add `retention_until` / `deleted_at` to `sessions` , `telephony_calls` and `escalations` , plus a scheduled purge that deletes the Storage object, the transcript, the recording URL and the contact info together. (4) Stop persisting longlived signed URLs; re-sign from `recording_storage_path` on demand. (5) Add a documented tenant- and end-user-level erasure procedure and test it. 

###### `F-C5` 

#### Dashboard ships Next.js with 1 CRITICAL and 7 HIGH vulnerabilities 

`WHERE: dashboard/package-lock.json` → `next@14.2.35` ; `dashboard/package.json:8` ( `"next": "^14.2.0"` ) _What was checked:_ OSV.dev batch query against the full resolved dependency tree. Full output in Appendix A.2. _Why it matters:_ 19 advisories on `next@14.2.35` alone, including GHSA-p293-qw3h-jr36 — unauthenticated remote code execution on Windows-hosted servers (CRITICAL) — plus 7 HIGH (two SSRF, four denial-of-service classes). `postcss@8.4.31` adds four more, two HIGH (arbitrary file read via attacker-controlled `sourceMappingURL` ). This is the surface that holds tenant session tokens and reveals tenant signing secrets. _Fix:_ Upgrade Next.js to a patched release and re-run the scan. Add `npm audit -- audit-level=high` as a blocking CI job (see F-M20). 

```
F-C6
```

#### Tenant signing secret stored in plaintext and retrievable into the browser 

`WHERE: supabase/migrations/0009_tenant_secrets.sql:4` ; `control_plane/secrets_db.py:52` ; `tenant_portal_api/app.py:405–412` ; `tenant_portal_api/queries.py:248–261` ; `dashboard/src/lib/portalAuth.ts:24` ; `dashboard/src/app/credentials/page.tsx:58` _What was checked:_ Traced the secret from schema to browser; compared against the three places the documentation states the opposite. _Why it matters:_ Four compounding facts. (1) The raw HMAC secret is stored unencrypted in `tenants.hmac_secret` — while `0001_schema.sql:27` , `control_plane/secrets.py:3–5` and `docs/21-PHASE-1-SUPABASE.md:12` all still assert "hash ONLY, never the secret." The vestigial `hmac_secret_hash` is selected by the mint ( `mint.py:70,77` ) and never used. (2) `GET /portal/credentials/secret` returns it to any holder of an 8-hour portal JWT. (3) That JWT lives in `localStorage` . (4) There is no self-service rotation — only an admin route ( `admin/app.py:206` ). So one XSS in the dashboard hands an attacker a credential that mints sessions and manages agents, permanently, with no tenant-side remedy. Separately, `secret_hash` ( `control_plane/secrets.py:57–59` ) is unsalted SHA-256 — acceptable only because the input is a 32-byte random token, and pointless given the plaintext sits in the same row. _Fix:_ Encrypt `hmac_secret` at rest with a KMS-backed key (or move it to a secret manager). Remove `GET /portal/credentials/secret` ; show the secret exactly once, at creation https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 22/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit `/p / /` ; y , 

g ) 

and at rotation, and never again. Ship tenant self-service rotation. Correct the three documentation lies. Move the portal token out of `localStorage` into an httpOnly cookie, or add a CSP. 

###### `F-C7` 

#### LLM-driven write tools have no confirmation gate and no ownership check 

`WHERE: worker/tools.py:284–381` ( `book_appointment` , `reschedule_appointment` , `cancel_appointment` ), `:193–230` ( `_post_client_tool` ) _What was checked:_ Read every tool definition and the dispatch path; confirmed tenant identity is correctly taken from `AgentUserdata` and not from tool arguments; confirmed no validation, confirmation, or authorisation layer exists between the LLM and the HTTP POST. _Why it matters:_ `cancel_appointment` identifies the booking to destroy by a `customer_phone` string that the caller supplied and the LLM transcribed. Nothing verifies the caller owns that number. `reschedule_appointment` has the same shape. Both are irreversible against a tenant's real calendar and real customers. The documented prompt-injection residual (an untrusted caller steering tool selection) previously reached only `escalate_to_human` , which writes a ticket; it now reaches three destructive writes. No idempotency key is sent, so a retry double-books. No `MAX_TOOL_CALLS` budget exists. _Fix:_ Require explicit spoken confirmation before any destructive tool (a two-step pattern the tool layer enforces, not the prompt). Bind mutations to the verified caller identity — for PSTN, the ANI already available in `telephony_calls` ; for browser sessions, an identifier the host backend passes at mint time. Send an idempotency key on every write. Validate all LLM-produced arguments against a strict schema before dispatch. Then run the live injection test that `tests/test_injection_live.py` was written for — and add it to a gate that actually runs (F-H1). 

###### `H I G H` 

— a claimed feature that is not done, or works incorrectly in a way that affects real output; scalability landmines that will hit soon. 

###### `F-H1` 

#### 53 of 75 test files (269 test functions) never execute 

`WHERE: pytest.ini:8` ( `python_files = …` ) _What was checked:_ Parsed the whitelist against the contents of `tests/` ; ran `python -m pytest --collect-only -q` and confirmed zero telephony modules appear in collection. _Why it matters:_ `python_files` overrides pytest's default `test_*.py` discovery with an explicit 22-file list. The 53 excluded files contain 269 test functions, including: the entire telephony suite (18 files, ~170 tests — `test_telephony_machine_routes_full.py` alone has 31), `test_tools_webhook.py` (the SSRF validation tests, 5), `test_session_recording.py` (3), `test_stale_jobs.py` (7), `test_interruption.py` , `test_injection_live.py` , `test_greeting_fields.py` (5), all four `test_latency_phase*.py` files (42), and every `test_phaseN_*_remediation.py` file. Commit `2fb14a5` describes "complete 4-phase telephony architectural gap remediation and test suite"; mechanically, that suite has never been run by `make gate` or by CI. Any new test file a contributor adds is also silently skipped unless they also edit `pytest.ini` . The 158 tests that do run give a false signal of coverage. _Fix:_ Remove the `python_files` override and restore default discovery. Move the two genuinely dead harness files ( `test_tts.py` , `test_harness.py` ) out of `tests/` or mark them with `pytest.mark.skip` and a reason. Mark the `*_live.py` money-spending tests 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

23/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

with a `live` marker and deselect by default. Then run the full suite and triage what breaks — that result is itself the next audit deliverable. 

```
F-H2
```

#### CI contains a job that cannot pass; 11 dead documentation links, including in a published npm README 

`WHERE: .github/workflows/ci.yml:69–99` ; `README.md:31,45,46,85,104` ; `docs/CLIENT_QUICKSTART.md:10,11,40,69,134,135` ; `sdk/README.md:22,23,129,130,165,166` _What was checked:_ `git log --diff-filter=D -- 'examples/*'` → deleted in `df97bf6` (2026-08-18); confirmed `git ls-files | grep '^examples/'` returns zero. _Why it matters:_ The `example-app-build` job runs `npm ci` in two directories that do not exist, so it fails on every push and pull request. A permanently red pipeline trains everyone to ignore CI — which is exactly how F-H3 becomes dangerous. Separately, 

`sdk/README.md` is the README published to npm, so every consumer of `@awaazlabs-uva/voice` gets six links to deleted files. And the quickstart the product's own onboarding depends on points at nothing. Note the paths never matched even before deletion: the historic directories were `examples/basic-webclient` and `examples/host-backend-node` . _Fix:_ Restore the examples (they exist in history at `df97bf6^` ) or delete the CI job and every reference. Do not leave a red pipeline. Re-publish the SDK README once corrected. 

```
F-H3
```

#### Production deploys are not gated on CI 

`WHERE: .github/workflows/deploy-prod.yml:3–5` ; `deploy-staging.yml:3–5` _What was checked:_ Read both workflows; confirmed no `needs:` clause and no `workflow_run` trigger anywhere. _Why it matters:_ Push to `main` → Render deploy hooks fire, unconditionally and in parallel with CI. Combined with F-H2 (CI is always red) and F-H1 (most tests never run anyway), there is no automated barrier between a commit and production. Additionally `if: env.HOOK_URL != ''` means a missing or rotated hook secret produces a green build that deployed nothing, with no signal. There is no approval step, no rollback job, and no portal deploy hook at all — so the service that backs both the dashboard and all telephony is deployed by some undocumented manual process. _Fix:_ Gate deploys on `workflow_run` completion of CI with `conclusion == 'success'` . Add the portal hook. Add a manual-approval environment for production and a rollback job that redeploys the previous image digest. Fail (not skip) when a required hook secret is absent. 

```
F-H4
```

#### Rate limits are keyed on unauthenticated input and checked before authentication 

`WHERE: control_plane/app.py:544` , `:291–298` ; `tenant_portal_api/machine_auth.py:201` , `:172–179` _What was checked:_ Traced the order of operations in both limiters. _Why it matters:_ `_rate_limited(x_tenant_id)` runs on a raw request header before any signature verification. An unauthenticated attacker who knows a tenant's UUID — which is also displayed in the dashboard as the "publishable key" — can send 120 junk requests per minute and lock that tenant out of session minting entirely, and 30/minute to lock them out of agent management. No credential is needed. _Fix:_ Verify the HMAC signature first, then apply the per-tenant limit. Apply a separate, stricter IP-based limit to unauthenticated traffic 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

24/50 

9/13/26, 5:49 PM unauthenticated traffic. 

AwaazLabs UVA Audit 

###### `F-H5` 

#### In-process, unbounded rate-limit and replay state 

`WHERE: control_plane/app.py:253` ; `machine_auth.py:169` ; `telephony_webhooks.py:36–37` _What was checked:_ Read all four in-memory structures; confirmed none has eviction. _Why it matters:_ Three security controls live in process memory: the mint rate limiter, the machine rate limiter, and the webhook signature/event replay sets. All reset to empty on every deploy or restart — so an attacker who can trigger churn gets a clean window — and none are shared across workers, so N uvicorn workers means N× the stated limit. `_hits` retains a key per distinct tenant ID ever seen, and `_seen_webhook_signatures` / `_seen_webhook_event_ids` grow monotonically for the life of the process: unbounded memory growth in a long-running service. _Fix:_ Move all four to Redis (or a small Postgres table) with TTLs. This closes the reliability, the abuse, and the memory-leak issues at once. 

###### `F-H6` 

#### Telnyx webhook events are lost permanently on durable-write failure 

`WHERE: tenant_portal_api/telephony_webhooks.py:357–359` , `:361–377` , `:280–305` _What was checked:_ Traced the ordering of the in-memory dedupe insert relative to the durable write and the HTTP response. _Why it matters:_ The handler adds `event_id` to an in-memory set before attempting `_persist_telnyx_webhook_event` . If that write fails, the exception is caught, a warning is logged ( `:371– 374` ), and the handler still returns HTTP 200 ( `:377` ) — so Telnyx never retries. If Telnyx did retry, the inmemory set would reject it as a duplicate. Either way the event is gone, and with it the call's terminal status, so `telephony_calls` keeps a stale `platform_status` and the quota slot is never released. Compounding this, `_persist_telnyx_webhook_event:280–305` only inserts an events row when a matching call is found, so unmatched events — precisely the diagnostic ones — never reach the database at all, and its `except Exception: pass` ( `:307` ) hides insert failures. _Fix:_ Persist first, then dedupe. Return 5xx on durable failure so the provider retries. Make the database the authority for dedupe (the unique index at `0013:221` already exists). Always insert the raw event, matched or not. Replace the bare `pass` . 

###### `F-H7` 

#### Token refresh bypasses tenant status, quota, and session state 

`WHERE: control_plane/app.py:301–345` , `:593–605` _What was checked:_ Read `_mint_refresh_token` in full. _Why it matters:_ Refresh verifies only the LiveKit JWT signature and re-issues with the same grants. It never re-reads `tenants.status` , never re-checks quota, and never checks whether the session row has been closed. A tenant suspended for non-payment or abuse keeps every in-flight call alive indefinitely, because there is also no cap on the number of refreshes. The suspend control the admin console offers is therefore not a stop control. _Fix:_ On refresh, re-read tenant status and the open session row; refuse if suspended or ended. Cap total session duration. 

```
F-H8
```

#### No SSRF protection on tenant-supplied tool gateway URLs, despite the docstring 

d 

_h_ 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

25/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

`WHERE: tenant_portal_api/tools_webhook.py:1` , `:19–48` ; consumed at `worker/tools.py:201–220` _What was checked:_ Read the validator line by line. _Why it matters:_ The module docstring reads "Validate tenant-supplied tools webhook URLs (SSRF-aware, local-dev friendly)." The function checks the scheme, rejects embedded credentials, and rejects query strings — and performs no host validation at all. `http://169.254.169.254/latest/meta-data/` (cloud metadata), `http://127.0.0.1:5432` , `http://10.0.0.5/internal` and any `.internal` hostname are all accepted. The worker then POSTs to that URL from inside the platform's network on every tool call, with the tenant's own tenant/agent IDs in the body. `http://` is explicitly permitted, so the `x-tool-gateway-secret` header travels in cleartext. The five tests that cover this file ( `tests/test_tools_webhook.py` ) are among those that never run (F-H1). _Fix:_ Resolve the hostname at save time and reject any address in a private, loopback, link-local, or uniquelocal range; re-resolve at call time or pin the resolved address to defeat DNS rebinding. Require `https` outside development. Disable redirects on the client. Then either remove "SSRF-aware" from the docstring or make it true. 

```
F-H9
```

#### Blocking database calls inside async coroutines stall live audio 

`WHERE: worker/tools.py:61` , `worker/tools.py:87` _What was checked:_ Compared against every other DB touch in the worker, all of which use `asyncio.to_thread` (e.g. `worker/main.py:214` , `:463` ) specifically to avoid this. _Why it matters:_ `end_conversation_summary` and `escalate_to_human` are `async def` and call synchronous `psycopg.connect(...)` directly. That blocks the worker's event loop for a full TCP+TLS handshake to Supabase during a live call — audio processing, VAD and TTS streaming all stop. It happens at exactly the two moments the caller is most likely to notice: hang-up and escalation. _Fix:_ Wrap both in `asyncio.to_thread` , matching the pattern the rest of the worker already follows, or use a pooled async connection. 

```
F-H10
```

#### Urdu has zero provider redundancy and the pipeline has no fallback 

`WHERE: worker/providers/capabilities.py:102–122` ; `worker/providers/registry.py:45,57,86` ; `worker/providers/llm/groq.py:70` ; `worker/providers/tts/uplift.py:63` _What was checked:_ Read the capability matrix and every registry branch. _Why it matters:_ `ur` — the product's namesake language — lists exactly one provider per layer: Gladia STT, Gemini LLM, Uplift TTS. The registry raises `UnsupportedProviderError` rather than substituting (correct as a design principle) but there is no retry, no failover, no round-robin, and no circuit breaker anywhere, and two adapters explicitly set `max_retry=0` . Any one of those three vendors having an outage or rate-limiting the account takes 100% of Urdu traffic offline with no degraded mode. Gladia's 429 ceiling is documented at roughly 5 concurrent sessions; Uplift's ceiling has never been measured ( `docs/42-RESEARCH-QUEUE.md` RQ-001, still open). _Fix:_ Add at least one alternate provider per layer for `ur` and an explicit, logged failover policy — with the substitution surfaced to the tenant rather than silent (contrast F-M15). Measure the Uplift ceiling and publish it. Add a circuit breaker so a provider outage degrades instead of dead-airing. 

```
F-H11
```

#### No production migration path; the only runner destroys all data 

`WHERE scripts/db reset py:1 55` ; `supabase/migrations/0001 schema sql:6 11` _What was checked:_ https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

26/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

`WHERE: scripts/db_reset.py:1–55` ; `supabase/migrations/0001_schema.sql:6–11` _What was checked:_ 

Searched the whole repository for a migration-version table or forward-only runner; found neither. _Why it matters:_ There is no `schema_migrations` table, so no environment records which migrations it has received. The only automation is `db_reset.py` , whose own docstring says "DEV only — never prod," and which applies `0001_schema.sql` — a file that opens with `drop table if exists usage_events, quota_state, sessions, agents, voices, tenants cascade` . Production schema changes are therefore applied by hand with no record and no verification, and a single mistaken invocation of the project's own `make db-reset` against a production connection string destroys every tenant, agent, session and usage record. Its docstring also documents two existing footguns (preview URLs wiped, admin account wiped on every reset), which shows the pattern has already caused damage in development. _Fix:_ Adopt a real migration tool (Alembic, sqitch, or Supabase's own CLI) with a version table and forward-only application. Split `0001` so the destructive `drop` block lives in a clearly-named dev-seed file that production can never reach. Write down migrations for anything reversible. 

```
F-H12
```

#### A single failed token refresh terminates the call 

`WHERE: sdk/src/index.ts:411–441` _What was checked:_ Traced `scheduleTokenRefresh` — it is called at `:235` (connect) and `:437` (successful refresh) and nowhere else. _Why it matters:_ On refresh failure the SDK emits one `error` event and returns. The timer is not rescheduled and no retry is attempted. The LiveKit token expires 60 seconds later and the call dies. One transient network blip at the wrong moment ends a customer conversation, and the host application's only signal is a generic `session_failed` . _Fix:_ Retry with exponential backoff until the token's actual expiry, and only then emit a terminal error. Emit a distinct, documented error code. 

```
F-H13
```

#### Service JWT signing keys are auto-generated into a file at import time 

`WHERE: admin/app.py:46–68` ; `tenant_portal_api/app.py:53–70` _What was checked:_ Read both functions; read `docker/admin.Dockerfile:20–26` , which documents why this is wrong. _Why it matters:_ When the env var is absent, both services generate a random secret and append it to .env.local at module import. In a container this either crashes (read-only filesystem) or silently succeeds and evaporates on the next deploy — minting a fresh signing key each time, invalidating every session, and making token lifetime non-deterministic. The Dockerfile spends seven lines explaining this exact failure; the code still does it, and nothing fails fast. `docs/62` covers `ADMIN_JWT_SECRET` but says nothing about 

`TENANT_PORTAL_JWT_SECRET` (see F-C1). _Fix:_ Replace both with a hard requirement plus fail-fast at startup, matching `control_plane/app.py:68–87` . Document both variables in `docs/62` and `.env.example` . 

```
F-H14
```

#### No brute-force protection, TOTP replay guard, or failed-login audit on either login endpoint 

`WHERE: admin/app.py:114–126` ; `tenant_portal_api/app.py:287–298` ; `admin/security.py:440–456` _What was checked:_ Read both login paths and the TOTP verifier. _Why it matters:_ Neither endpoint is ratelimited, throttled, or locked out after repeated failures — unlike `/v1/session` , which is. `totp_verify` accepts the ±1-step window with no record of consumed codes, so a valid code is reusable for up to 90 seconds contrary to RFC 6238 §5 2 And because `record admin action` is only called on success 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

27/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

seconds, contrary to RFC 6238 §5.2. And because `record_admin_action` is only called on success, 

`admin_audit_log` contains no trace of a failed attempt, so a brute-force campaign is invisible. The admin portal has full cross-tenant read access and can rotate any tenant's secret. _Fix:_ Add per-account and per-IP throttling with exponential lockout on both endpoints; record every failure to the audit log; store consumed TOTP counters and reject reuse. 

###### `F-H15` 

#### aiohttp==3.14.1 carries three advisories, one HIGH 

`WHERE: requirements.txt:2` _What was checked:_ OSV.dev scan (Appendix A.1). _Why it matters:_ GHSAcq5v-8q36-5273 (HIGH) — out-of-bounds heap read in the C HTTP response parser on a malformed chunked response; plus HTTP request smuggling via WebSocket upgrade and an unnegotiatedcompression issue. `aiohttp` is in the request path of the worker and, via the monolithic requirements file, of the tenant portal too. _Fix:_ Upgrade to a patched release; re-scan; add a blocking Python dependency-audit job in CI (F-M20). 

###### `F-H16` 

#### No .dockerignore; the worker image copies the entire build context 

`WHERE:` absent `.dockerignore` ; `docker/worker.Dockerfile:34` ( `COPY . .` ); `docker/tenant-portalapi.Dockerfile:7` ( `COPY scripts/ scripts/` ) _What was checked:_ Confirmed no `.dockerignore` exists at the repo root or under `docker/` . _Why it matters:_ `COPY . .` with no ignore file places `.git/` — the complete 278-commit history — inside the runtime image, along with `tests/` , `scratch/` , `docs/` , and any .env.local present in the build context. On Render the build is a clean checkout so `.env.local` is unlikely, but any local or CI-side image build bakes in real credentials. The portal image separately ships every provisioning and admin script into the runtime container. _Fix:_ Add a `.dockerignore` covering `.git` , `.env*` , `tests` , `scratch` , `docs` , `graphify-out` , `node_modules` , `__pycache__` . Copy only the packages each service imports. 

###### `F-H17` 

#### Outbound PSTN calls ignore the monthly minutes cap and fail open on unknown tenants 

`WHERE: tenant_portal_api/telephony_queries.py:308–338` ; compare `control_plane/mint.py:121–130` _What was checked:_ Read `reserve_call_quota` in full and compared against the mint's quota gate. _Why it matters:_ `reserve_call_quota` reads only `tenants.max_concurrent` . It never touches `max_minutes_month` or `minutes_this_month` . A tenant blocked from browser sessions by the monthly cap can place unlimited outbound PSTN calls — the most expensive path in the product. And `if not tenant_row: return True` ( `:314–315` ) grants quota to a tenant ID that does not exist, which is a fail-open decision in the same function that authorises spend. There is also no rate limit on `POST /portal/telephony/outbound-calls` and no spend circuit breaker anywhere. _Fix:_ Enforce both caps in one shared function used by the mint and the telephony path. Change the unknown-tenant branch to `return False` . Add a per-tenant outbound call rate limit and a platform-wide spend guard. 

```
F-H18
```

Billing and quota release happen only on clean shutdown 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

28/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

g 

`WHERE: worker/main.py:730–835` , `:832–834` ; `scripts/reconcile_sessions.py` _What was checked:_ Traced the only code paths that close a session row, decrement concurrency, and write `usage_events` . _Why it matters:_ All three happen exclusively in LiveKit shutdown callbacks. A crash, OOM kill, or container eviction leaves the session row open forever, the concurrency slot consumed (reducing the tenant's capacity until someone notices), and the call unbilled. `queries.py:264–276` documents that this already produced a tenant showing 13 "live" calls whose oldest was 96 hours old. 

`scripts/reconcile_sessions.py` exists to repair it — and nothing in the repository schedules it: no cron, no workflow, no runbook step. On top of that, the whole callback body is wrapped in `except Exception` → `logger.warning` ( `:826–828` ), so a silent billing failure produces one log line and no alert. _Fix:_ Schedule both reconcile scripts (GitHub Actions cron, Render cron job, or a supervisor loop) and alert on divergence. Emit usage incrementally during the call rather than only at the end. Escalate a failed usage write beyond a warning. 

`M E D I U M` — works, but with real technical debt, missing tests, or a maintainability risk that is not urgent. 

|`ID`|`FINDING`|`WHERE`|`WHY IT MATTERS`|`FIX`|
|---|---|---|---|---|
|F-<br>M1|28 exception handlers<br>swallow errors silently<br>(14 in production<br>service code)|Full list in Appendix A.3;<br>worst:<br>`control_plane/app.py:20`<br>`4`,<br>`telephony_webhooks.py:3`<br>`07`,<br>`telephony_credentials.p`<br>`y:118`,<br>`worker/session_recordin`<br>`g.py:82`|Guideline §2 names this pattern explicitly. A DB outage<br>returns a fake voice catalogue; a failed credential re-<br>encryption is invisible; a failed recording delete is<br>invisible.|Log with context at<br>WARNING or higher in<br>every case; re-raise where<br>the caller can act.|
|F-<br>M2|`agents.prompt` has no<br>length limit|`tenant_portal_api/app.p`<br>`y:107`;<br>`0001_schema.sql:40`|Every LLM turn pays for the full persona. This is the<br>mechanism behind the observed Groq ITPM exhaustion.<br>`worker/prompt_compact.py` mitigates only for Groq, only at<br>session build.|Enforce a server-side<br>character cap at write time<br>with a clear 422; surface<br>effective token cost in the<br>dashboard.|
|F-<br>M3|Unbounded `limit`<br>query parameters|`tenant_portal_api/app.p`<br>`y:416`;<br>`telephony_routes.py:551`;<br>`queries.py:279`|`?limit=1000000` returns every session with full transcripts<br>— memory pressure and a data-exfiltration amplifier.|Clamp server-side (e.g.<br>`min(limit, 200)`) and<br>paginate with a cursor.|
|F-<br>M4|No body-size limit on<br>the public Telnyx<br>webhook|`telephony_webhooks.py:3`<br>`39–341` (`await`<br>`request.body()`)|Unauthenticated endpoint reads an arbitrarily large body<br>into memory before signature verification.|Reject above a sane byte<br>ceiling before reading.|
|F-<br>M5|Raw exception text<br>returned to clients|`telephony_routes.py:541`<br>(`f"Outbound call setup`<br>`failed: {e}"`);<br>`control_plane/app.py:14`<br>`8` (`f"failed: {e}"` in<br>`/healthz/deep`)|Leaks internal hostnames, driver messages, and stack<br>context. `/healthz/deep` is unauthenticated.|Return a stable error code;<br>log the detail server-side<br>only.|
|F-<br>M6|`/docs` and `/redoc`<br>enabled<br>unauthenticated in<br>production|`control_plane/app.py:11`<br>`2–113`|Publishes the full API schema, including `dev-mint` (F-C2),<br>to anyone.|Disable in production or<br>gate behind auth.|



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

29/50 

9/13/26, 5:49 PM 

|3/26|, 5:49 PM||AwaazLabs UVA Audit||
|---|---|---|---|---|
|F-<br>M7|Hand-rolled cipher for<br>telephony credentials<br>while `cryptography` is<br>already a dependency|`tenant_portal_api/telep`<br>`hony_credentials.py:26–`<br>`43`, `:125–151`|HMAC-keystream + HMAC tag is a defensible encrypt-<br>then-MAC construction, but it is unreviewed custom<br>crypto in a codebase that already imports<br>`cryptography==50.0.0` (used for Ed25519 at<br>`telephony_webhooks.py:18`). `_master_key` is plain<br>`sha256(env_value)` with no KDF or salt, so a low-entropy<br>key is directly brute-forceable.<br>`decrypt_provider_secret:87–88` silently returns<br>ciphertext-as-plaintext in mock mode.|Replace with `AESGCM` or<br>`Fernet`; derive the key with<br>a proper KDF; remove the<br>mock-mode plaintext<br>passthrough.|
|F-<br>M8|`agents.tools_auth_secr`<br>`et` stored in plaintext|`supabase/migrations/0026`<br>`:8`; read at<br>`worker/config.py:110`|A third secret-handling standard in one schema: tenant<br>HMAC plaintext, telephony credentials custom-<br>encrypted, tool secret plaintext.|Encrypt at rest using the<br>same mechanism chosen<br>for F-C6 and F-M7.|
|F-<br>M9|All Docker images run<br>as root, use floating<br>base tags, and define<br>no healthcheck|`docker/*.Dockerfile`|No `USER` directive anywhere; `FROM python:3.12-slim`<br>without a digest means builds are not reproducible and<br>a compromised upstream tag is inherited silently.|Add a non-root `USER`; pin by<br>digest; add `HEALTHCHECK`.|
|F-<br>M10|No security headers on<br>any service|All FastAPI apps;<br>`dashboard/next.config.js`|No CSP (the main mitigation for F-C6's XSS chain), no<br>HSTS, no X-Frame-Options, no X-Content-Type-Options.|Add a headers middleware<br>to each service and a<br>`headers()` block to<br>`next.config.js`.|
|F-<br>M11|`used_nonces` grows<br>without bound|`supabase/migrations/0004`<br>; written at `mint.py:98–`<br>`101`,<br>`machine_auth.py:234–237`|One row per successful mint, forever. No purge job exists<br>anywhere. The `used_at` index implies cleanup was<br>planned and never written.|Add a scheduled `delete`<br>`from used_nonces where`<br>`used_at < now() - interval`<br>`'10 minutes'`.|
|F-<br>M12|`escalations` is write-<br>only — no API, no UI,<br>no query|Written at<br>`worker/tools.py:93–97`;<br>grep for `escalations`<br>across<br>`tenant_portal_api/`,<br>`admin/`, `dashboard/src/`,<br>`sdk-server/src/` returns<br>nothing|A shipped, LLM-callable feature produces records that<br>no one can read through the product. Caller phone<br>numbers accumulate in a table with no reader and no<br>retention.|Add a tenant-scoped read<br>endpoint and a dashboard<br>view, or remove the tool.|
|F-<br>M13|No deletion path for<br>agents or tenants|No `DELETE` route in<br>`tenant_portal_api/app.p`<br>`y` or `admin/app.py`|Agents accumulate permanently; tenant offboarding is<br>impossible, which also blocks GDPR erasure (F-C4).|Add soft-delete for agents<br>and a documented tenant-<br>offboarding procedure.|
|F-<br>M14|Browser SDK `fetch`<br>calls have no timeout|`sdk/src/index.ts:121`,<br>`:181`, `:415`|A hung host backend leaves `connect()` pending forever<br>with no error and no hook — the client-side shape of the<br>">20s silence" symptom.|Add `AbortController` with a<br>configurable timeout; emit<br>a distinct timeout error<br>code.|
|F-<br>M15|Silent provider and<br>model substitution|`worker/providers/llm/gr`<br>`oq.py:42–51`;<br>`worker/telephony_tts.py`<br>via `main.py:236,248`|Eight advertised Groq model IDs collapse to one;<br>telephony silently swaps both TTS and LLM. The<br>capabilities API keeps advertising the tenant's choice. A<br>sub-processor disclosure that names the wrong vendor<br>is a compliance problem, not just a surprise.|Surface the effective<br>provider/model in the<br>session response and the<br>dashboard; deprecate<br>retired IDs in the<br>capabilities API instead of<br>aliasing them.|
|F-<br>M16|Only three SDK error<br>codes; all 429s<br>collapse to one|`sdk/src/index.ts:46`,<br>`:189–190`|A host cannot distinguish plan cap from rate limit from<br>upstream provider 429 — so it cannot back off correctly<br>or tell the user anything useful.|Add codes for rate limit,<br>worker-not-ready, provider-<br>limit, and timeout; map<br>them from distinct control-<br>plane responses.|



F- Missing index on 

`0001:76` , `0010` ; joined at The `/portal/agents` query joins on an unindexed column `create index` 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

30/50 

|M17<br>9/13/26|`usage_events.session_i`<br>`d`<br>, 5:49 PM|`queries.py:61–67`|for every tenant on the most-visited page. Degrades as<br>`usage_events` grows.<br>AwaazLabs UVA Audit|`usage_events_session_idx`<br>`on usage_events`<br>`(session_id);`|
|---|---|---|---|---|
|F-<br>M18|Test-only<br>authentication<br>backdoors in<br>production telephony<br>code|`telephony_routes.py:73–`<br>`74`, `:145–150`|`TELEPHONY_ALLOW_MOCK_PORTAL_AUTH=1` returns a hardcoded<br>tenant with no token;<br>`TELEPHONY_ALLOW_MOCK_MACHINE_AUTH=1` accepts the literal<br>`"valid_mock_signature"`. Default off and documented as<br>dev-only, but they live in the module that spends money,<br>and nothing asserts at startup that they are off.|Assert at startup that<br>neither is set unless<br>`ENVIRONMENT ==`<br>`"development"`; better, move<br>them behind a test-only<br>dependency override.|
|F-<br>M19|Mock-mode switches<br>disable webhook<br>signature verification<br>and credential<br>decryption|`telephony_webhooks.py:1`<br>`21`;<br>`telephony_credentials.p`<br>`y:52,59,87`|`TELEPHONY_PROVIDER_MODE` correctly defaults to `"real"`<br>(`telephony_config.py:14`), so this is not live today. But a<br>single env typo (`test`, `local`) silently turns off Telnyx<br>signature checking and credential encryption at once,<br>with no startup warning.|Assert at startup that<br>production is not in mock<br>mode; log loudly at boot<br>when it is.|
|F-<br>M20|No dependency audit,<br>secret scan, bundle<br>check, or SBOM in CI|`.github/workflows/ci.ym`<br>`l` (four jobs, none of<br>these); `Makefile:8,15`<br>(gitleaks and bundle-<br>check exist only in `make`<br>`gate`)|The vulnerability findings in this report (F-C5, F-H15)<br>would have been caught automatically. The repo already<br>_has_ the gitleaks and bundle-check commands — they<br>simply are not wired into CI.|Add `npm audit --audit-`<br>`level=high`, `pip-audit`,<br>`gitleaks detect`, and `make`<br>`bundle-check` as blocking CI<br>jobs; generate an SBOM on<br>release.|
|F-<br>M21|npm publishing has no<br>provenance, no<br>changelog, and covers<br>only one of three<br>packages|`release-sdk.yml:11–41`;<br>no `CHANGELOG*` in any<br>package; all three at<br>`version: 0.1.0` while the<br>handover documents<br>1.0.1|Consumers cannot verify build provenance or see what<br>changed between versions, and two of three packages<br>have no release path at all.|Add `id-token: write` + `npm`<br>`publish --provenance`; add<br>changelogs; extend the<br>workflow to all three<br>packages; align versions.|
|F-<br>M22|`make secrets` silently<br>depends on an<br>uninstalled tool|`Makefile:15`|`gitleaks` is not installed on this machine, so `make gate`<br>cannot pass locally. The gate correctly _fails_ rather than<br>passing vacuously — good — but it means nobody is<br>running it.|Pin gitleaks as a CI action<br>(F-M20) so the scan runs<br>regardless of local tooling.|
|F-<br>M23|npm package<br>metadata points at a<br>personal repository|`sdk/package.json:6–8`;<br>`sdk-server/package.json`;<br>`telephony/package.json`;<br>`README.md:4`|Published packages direct customers to<br>`github.com/habiba-imran/urdu-agent-SDK` while origin is<br>`Finova-Solutions/urdu-voice-agent-SDK`. Supply-chain<br>and bus-factor risk: who can push to that repo?|Point all metadata at the<br>organisation repository and<br>re-publish.|
|F-<br>M24|Full prompts and<br>transcripts written to<br>logs and to a file on<br>disk by default|`worker/main.py:602,608`;<br>`worker/prompt_dump.py`;<br>`.env.example:44`<br>(`UVA_DUMP_PROMPTS=1`<br>documented as "default<br>on")|Caller PII reaches application logs and<br>`docs/last_session_prompt.txt` — neither covered by any<br>retention or redaction rule (F-C4).|Default the dump off;<br>redact or truncate turn text<br>at INFO level; bring logs<br>under the retention policy.|
|F-<br>M25|No worker health or<br>readiness endpoint|`worker/main.py` — the<br>LiveKit agent process<br>exposes no HTTP<br>surface|The control plane has `/healthz`, `/healthz/deep`,<br>`/healthz/warm`; the component that actually serves audio<br>has nothing. A wedged worker is undetectable except by<br>a failing call.|Expose a minimal health<br>endpoint reporting plugin<br>registration, VAD load, and<br>active job count.|
|F-<br>M26|No cap on agents per<br>tenant|`tenant_portal_api/app.p`<br>`y:308`|Unbounded resource creation on an authenticated but<br>unmetered endpoint.|Enforce a per-plan agent<br>limit.|
|F-<br>M27|Duplicate migration<br>version and two<br>incompatible naming<br>schemes|`0014_telephony_data_gov`<br>`ernance_audit.sql` /<br>`0014_telephony_idempote`<br>`ncy_webhook_tenant_scope`<br>`.sql`; `20260801185628_…`|Ordering happens to resolve, but the discipline is broken<br>and a third contributor will break it properly. Compounds<br>F-H11.|Renumber; standardise on<br>one scheme; enforce<br>uniqueness in CI.|



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

31/50 

|9/13/26|, 5:49 PM||AwaazLabs UVA Audit||
|---|---|---|---|---|
|F-<br>M28|No `CODEOWNERS`, no PR<br>template; branch<br>protection unverifiable|`.github/` contains only<br>`workflows/` and<br>`ISSUE_TEMPLATE/`|Combined with F-H3 (push to `main` deploys), the absence<br>of an enforced review requirement would mean a single<br>unreviewed commit reaches production.|Add `CODEOWNERS` and a PR<br>template; confirm and<br>document branch<br>protection (see Section 6).|
|F-<br>M29|`DbSecretProvider`<br>caches secrets for 60<br>s, delaying rotation|`control_plane/secrets_d`<br>`b.py:35`, `:99–128`; also<br>`except Exception: pass`<br>at `:118–119` hides DB<br>failures and silently falls<br>back to the env provider|A rotated secret keeps working for up to a minute after<br>rotation, and a DB outage silently reverts authentication<br>to a stale env-based map.|Invalidate on rotation; log<br>the fallback rather than<br>swallowing it.|
|F-<br>M30|Monolithic<br>`requirements.txt`<br>shipped to the tenant<br>portal image|`docker/tenant-portal-`<br>`api.Dockerfile:6`|Installs `livekit-agents`, `numpy`, `openai`, `python-socketio`<br>into a service that imports none of them — larger image,<br>larger attack surface, and it inherits the vulnerable<br>`aiohttp` (F-H15). The control-plane and admin images<br>correctly use slim files.|Create<br>`docker/requirements-`<br>`tenant-portal.txt` from the<br>portal's real imports.|



#### `L O W` — cosmetic, nice-to-have, or a future consideration with no current impact. 

|`ID`|`FINDING`|`WHERE`|
|---|---|---|
|F-L1|README's "Run Database Migrations" step runs `scripts/reconcile_sessions.py --dry-`<br>`run`, which applies no migrations|`README.md:60–63`|
|F-L2|README links to two files that do not exist (`VAAS_GODTIER_MASTER_PLAN_V2.md`,<br>`VAAS_COLLABORATION_GUIDE.md`)|`README.md:45–46`|
|F-L3|"Enterprise-grade" and "Enterprise Production Infrastructure" claims outrun the product<br>— no SSO, no RBAC, no audit export, no data residency, no DPA|`README.md:2,6`|
|F-L4|"publishable key" is literally the tenant UUID, not a separate credential, and is never<br>validated server-side|`tenant_portal_api/queries.py:238`;<br>`admin/queries.py:262`; `control_plane/app.py:265`|
|F-L5|Dashboard route gating is client-side only (mitigated — the backend enforces auth on<br>every route)|`dashboard/src/components/AppShell.tsx:41–56`|
|F-L6|Per-turn internal latency and stage breakdown are broadcast into the room, where the<br>end user's browser receives them|`worker/latency.py:496–528,625–633`;<br>`sdk/src/index.ts:345–348`|
|F-L7|SDK attaches audio elements to `document.body` with no SSR guard — throws if imported at<br>module scope in Next.js|`sdk/src/index.ts:366`|
|F-L8|A throwing event listener silently prevents later listeners from firing|`sdk/src/index.ts:274–278`|
|F-L9|Dead code: `mint.py` selects `hmac_secret_hash` and never uses it|`control_plane/mint.py:70,77`|
|F-<br>L10|`_cartesia_agent_session_extra` is a pure alias kept only for old test imports|`worker/main.py:433–437`|
|F-<br>L11|Generated artefacts committed to the repo root (`graphify-out/` with two dated snapshots,<br>`scratch/` with 5 files)|repo root|
|F-<br>L12|`docs/63-GUIDE-WORKER-DEPLOYMENT-DEFERRAL.md` still states there is no worker Dockerfile|`docs/63`, contradicted by<br>`docker/worker.Dockerfile`|
|F-|Stale `pythonpath = . pipecat_stubs` referencing a directory that never existed in this|`pytest.ini:5`|



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

32/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

|L13|checkout (documented as such)||
|---|---|---|
|F-|`release-sdk.yml` uses `if: ${{ secrets.NPM_TOKEN != '' }}` where the sibling workflows|`.github/workflows/release-sdk.yml:34`|
|L14|use the documented `env:`-mapping workaround — verify against an actual run||
|F-|`_ensure_bucket` calls `list_buckets`/`create_bucket` on every single session end rather than|`worker/session_recording.py:33–41,65`|
|L15|once at startup||



Totals: 7 Critical · 18 High · 30 Medium · 15 Low. 

## 10. Appendix — supporting evidence 

### A.1 Python dependency scan (OSV.dev, 2026-09-13) 

Scanned 34 pinned packages in `requirements.txt` ; 6 pinned packages in each of `docker/requirements-admin.txt` and `docker/requirements-control-plane.txt` . 

```
requirements.txt — 6 advisories, all in aiohttp==3.14.1:
  GHSA-cq5v-8q36-5273  [HIGH]      Out-of-bounds heap read in C HTTP response parser
                                    error path (malformed chunked response)
  GHSA-mfx4-hv73-q22v  [MODERATE]  HTTP request smuggling via WebSocket upgrade
  GHSA-mq44-7p77-q5h7  [MODERATE]  WebSocket client accepts compressed frames without
                                    negotiated permessage-deflate
  PYSEC-2026-3545 / -3546 / -3547   (same three issues, PyPI advisory IDs)
docker/requirements-admin.txt          — 0 advisories
docker/requirements-control-plane.txt  — 0 advisories
```

_Reproduce:_ `pip-audit -r requirements.txt` on a Python ≥3.12 interpreter, or POST the pinned `(name, version)` pairs to `https://api.osv.dev/v1/querybatch` with `ecosystem: "PyPI"` . 

### A.2 npm dependency scan (OSV.dev, 2026-09-13) 

```
sdk/package-lock.json         15 resolved packages   — 0 advisories
sdk-server/package-lock.json   3 resolved packages   — 0 advisories
telephony/package-lock.json    1 resolved package    — 0 advisories
dashboard/package-lock.json                          — 29 advisories
  next@14.2.35
    GHSA-p293-qw3h-jr36  [CRITICAL]  Unauthenticated Remote Code Execution on
                                      windows-hosted servers
    GHSA-89xv-2m56-2m9x  [HIGH]      SSRF in Server Actions on custom servers
    GHSA-c4j6-fc7j-m34r  [HIGH]      SSRF in applications using WebSocket upgrades
    GHSA-p9j2-gv94-2wf4  [HIGH]      SSRF in rewrites via attacker-controlled
                                      destination hostname
    GHSA-8h8q-6873-q5fj  [HIGH]      DoS with Server Components
GHSAq4gf8mx6v5v3[HIGH]DoSwithServerComponents
```

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

33/50 

9/13/26, 5:49 PM AwaazLabs UVA Audit `GHSA-q4gf-8mx6-v5v3  [HIGH]      DoS with Server Components GHSA-m99w-x7hq-7vfj  [HIGH]      DoS in App Router using Server Actions GHSA-h25m-26qc-wcjf  [HIGH]      HTTP request deserialization DoS + 11 MODERATE (cache confusion/poisoning ×4, XSS ×2, request smuggling, unauthenticated disclosure of internal Server Function endpoints, Image Optimizer DoS ×2, unbounded Server Action payload) + 1 LOW postcss@8.4.31 GHSA-6g55-p6wh-862q  [HIGH]      Arbitrary file read via attacker-controlled sourceMappingURL in CSS comments GHSA-r28c-9q8g-f849  [HIGH]      Path traversal in source-map auto-loading GHSA-fxqj-rqcc-2cmp  [MODERATE]  Incomplete fix of GHSA-6g55-p6wh-862q GHSA-qx2v-qp2m-jg93  [MODERATE]  XSS via unescaped </style> in stringify output postcss@8.5.22 GHSA-fxqj-rqcc-2cmp  [MODERATE]` 

_Reproduce:_ `cd dashboard && npm audit --audit-level=moderate` . 

### A.3 Silent exception handlers (catch **→** pass / bare return) 

28 total; 14 in production service code. 

```
control_plane/app.py:104                       except Exception: -> pass   (Sentry init)
control_plane/app.py:204                       except Exception: -> pass   (/v1/voices → fake catalogue)
worker/latency.py:146                          except Exception: -> return None
worker/latency.py:164                          except Exception: -> return None
worker/latency.py:256                          except RuntimeError: -> pass
worker/latency.py:282                          except Exception: -> pass
worker/main.py:913                             except (TimeoutError, RuntimeError): -> return
worker/main.py:927                             except (TimeoutError, RuntimeError): -> return
worker/main.py:1069                            except Exception: -> pass   (VAD preload)
worker/session_recording.py:82                 except Exception: -> pass   (storage object delete)
worker/tools.py:139                            except Exception: -> pass   (http client close)
worker/providers/llm/gemini.py:57              except Exception: -> pass
tenant_portal_api/telephony_credentials.py:118 except Exception: -> pass   (credential re-encryption)
tenant_portal_api/telephony_webhooks.py:307    except Exception: -> pass   (event insert)
tenant_portal_api/telnyx_client.py:975         except Exception: -> pass
admin/audit.py:37                              except (ValueError, ...): -> return None
+ 12 in scripts/ (operator tooling — lower severity)
```

### A.4 Test-collection evidence (F-H1) 

```
$ python -m pytest --collect-only -q | grep -c telephony
0
```

```
Modules pytest attempts to collect (all whitelisted in pytest.ini:8):
  tests/test_host_backend_contract.py   tests/test_machine_agent_api.py
  tests/test_phase0.py                  tests/test_phase2.py
  tests/test_phase4_portal_api.py       tests/test_phase4_voice_picker.py
  tests/test_sdk_parity.py              (+ test_isolation.py, test_mint.py, …)
```

```
tests/ contains 75 test_*.py files. pytest.ini whitelists 22.
53 files / 269 test functions are never collected, including:
  test_telephony_machine_routes_full.py    31 tests
```

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

34/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

```
  test_telephony_db_sync_and_rotation.py   14
  test_telephony_real_provider_wiring.py   13
  test_telephony_telnyx_client.py          11
  test_telephony_schema.py                  8
  test_telephony_outbound_trunk_numbers.py  8
  test_telephony_runtime_and_reconcile.py   8
  test_telephony_livekit_sip.py             7
  test_telephony_queries.py                 7
  test_telephony_routes.py                  7
  test_telephony_tts.py                     7
  test_telephony_client_calling_simulation.py 6
  test_telephony_data_governance_schema.py  5
  test_telephony_rls_schema.py              5
  test_telephony_scaffold.py                4
  test_telephony_purchase_flow.py           1
  test_telephony_outbound_conflicts.py      1
  test_telephony_outbound_destinations.py   1
── telephony subtotal: 18 files, ~170 tests, zero of them ever run ──
  test_latency_phase1/2/3/4.py             42
  test_stale_jobs.py                        7
  test_harness.py                           7
  test_session_opening.py                   6
  test_tools_webhook.py                     5  (the SSRF validation tests — F-H8)
  test_greeting_fields.py                   5
  test_session_recording.py                 3  (F-C4 surface)
  test_prompt_compact.py                    2
  test_interruption.py                      1
```

```
  + test_injection_live.py, test_e2e.py, test_cross_tenant_read_live.py,
    test_admin_boundary_live.py, test_token_widen_live.py (live/manual)
```

### A.5 Git-history scan (clean result) 

278 commits scanned for provider-key shapes ( `sk-` , `AIza` , `gsk_` , `xoxb-` ), PEM private-key headers, and JWTs; plus an addedfiles scan for `.env*` , `*.pem` , `*.key` , `*.p12` . 

```
Real secrets found: NONE
Only matches: .env.example templates (6 historic paths, all *.example)
              elided placeholder JWTs in docs/api-reference.md:46,87,94
Build artefacts tracked: none (node_modules/, .next/, dist/ all absent from
              git ls-files except 4 intentionally-vendored
              client-submission_v2/**/dist/ files)
```

This is a good result and should be stated as such. `.gitignore` correctly covers `.env` , `.env.*` with an `!.env.example` exception. 

### A.6 Reproduction notes for the security findings 

F-C1 — Read `tenant_portal_api/telephony_routes.py:59–61` . Then, on the deployed portal service, check whether `TENANT_PORTAL_JWT_SECRET` is set as a real process environment variable. If it is not, mint a token with the literal secret and call any `/portal/telephony/*` route: 

```
import jwt, datetime
tok = jwt.encode({"sub": "<victim-tenant-uuid>", "aud": "tenant-portal",
                  "iss": "uva-tenant-portal",
                  "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)},
```

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

35/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 

```
                 "mock_jwt_secret_for_tests", algorithm="HS256")
```

Test against a throwaway tenant on staging only. Do not run this against production or another tenant's data. 

F-C2 — `curl -X POST <control-plane>/v1/session/dev-mint -H 'Content-Type: application/json' -d '{"agentId":"<any agent uuid>"}'` . Expect a valid LiveKit token with no credential supplied. Confirm the side effect by reading `quota_state.concurrent_now` before and after hitting the concurrency cap. 

F-C3 — `curl -i -X OPTIONS <control-plane>/v1/session -H 'Origin: https://evil.example' -H 'Access-Control-RequestMethod: POST'` with `CP_ALLOWED_ORIGINS` unset. Inspect `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` . 

F-H4 — Send 121 requests/minute to `/v1/session` with a victim's `X-Tenant-Id` and a garbage signature. All are rejected as bad signatures, but the counter still increments; the victim's legitimate 122nd request receives 429. 

F-H8 — Set an agent's `tools_base_url` to `http://127.0.0.1:8000` via `PATCH /portal/agents/{id}` and confirm it is accepted (422 expected, 200 actual). Do not point it at a live metadata endpoint outside a controlled test environment. 

## 11. Recommended remediation order 

Not a project plan — a dependency ordering. Each gate is a stop condition. 

Gate 1 — Stop the bleeding (before any further traffic, hours not weeks). F-C1 (delete the fallback secret, set the env var, rotate) · F-C2 (remove or gate `dev-mint` ) · F-C3 (fail fast on missing CORS allowlist) · F-M18/F-M19 (assert mock switches off at startup). These are small, local code changes with immediate effect. 

Gate 2 — Restore the ability to know whether anything works. F-H1 (remove the pytest whitelist and triage the 269 tests that surface) · F-H2 (fix or delete the broken CI job) · F-H3 (gate deploys on CI) · F-M20 (add dependency, secret and bundle scans to CI). Until Gate 2 closes, every other fix ships unverified. 

Gate 3 — Close the legal exposure (before any further recorded call). F-C4 in full: opt-in recording, spoken disclosure, retention columns on the tables that hold personal data, a scheduled purge, and a documented erasure procedure. Obtain a legal opinion on the biometric and two-party-consent questions in Section 8 Part B. Secure sub-processor DPAs, including for the free-tier vendors. 

Gate 4 — Close the credential and tool-authorisation holes. F-C6 (encrypt at rest, remove the browser reveal, ship rotation) · F-C7 (confirmation gate, caller-identity binding, idempotency keys, schema validation) · F-C5 and F-H15 (dependency upgrades) · F-H8 (real SSRF controls) · F-H13/F-H14 (fail-fast secrets, login throttling). 

Gate 5 — Make it operable. F-H11 (a real migration tool) · F-H18 (scheduled reconciliation and alerting) · F-H5 (durable rate limits and replay state) · F-H6 (webhook durability) · F-M25 (worker health) · a kill switch and a rehearsed rollback. 

Gate 6 — Only then, commercial claims. Provider redundancy for Urdu (F-H10), a measured and published capacity sheet, a legal and trust pack, billing, and a status page. Until then, remove "enterprise-grade" from the README (F-L3) and do not sell telephony or enterprise tiers. 

Document control 

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

36/50 

9/13/26, 5:49 PM ocu e t co t o 

AwaazLabs UVA Audit 

|Audited<br>commit|`94e7000` (`main`)|
|---|---|
|Audit date|2026-09-13|
|Findings|7 Critical · 18 High · 30 Medium · 15 Low (70 total)|
|Scans<br>executed|OSV.dev dependency scan (4 npm lockfiles, 3 Python requirement files) · git-history secret and artefact scan (278 commits) ·<br>`pytest --collect-only` · configuration review of CI/CD, Dockerfiles, and migrations|
|Explicitly<br>not covered|Live penetration/load/soak testing · running production or staging environment · third-party account ownership, MFA, and billing<br>state · GitHub repository settings and branch protection · backup restore verification · live prompt-injection testing · full line-by-<br>line review of `telephony_service.py` and `telnyx_client.py` · frontend usability, performance, and accessibility on a running instance|
|Previous<br>report|`AWAAZLABS_AUDIT_REPORT.previous.md`|



```
AwaazLabs UVA — Product Audit Report · Finova Solutions Engineering ·
Confidential, internal use only
Audited main @ 94e7000 on 2026-09-13 against the QualiCall Product Audit
Guidelines. 7 Critical · 18 High · 30 Medium · 15 Low. Scope limitations
are stated in full in §0 — no live penetration, load, or soak testing
was performed, and third-party account ownership could not be verified.
```

https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

37/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

38/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

39/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

40/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

41/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

42/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

43/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

44/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

45/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

46/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

47/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

48/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

49/50 

9/13/26, 5:49 PM 

AwaazLabs UVA Audit 



https://claude.ai/code/artifact/d5bdc8ae-190d-4a35-bfe3-af5403cf5431?via=auto_preview 

50/50 

