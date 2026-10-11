# FINDINGS — Ehsan (worker, npm SDKs, dashboard, build & release)

Audit under `AUDIT_SPLIT_PLAN_v3.pdf` (FINAL, 2026-10-07). Ehsan leads **M3, M6, M9, M10**;
shares **M7** (worker/laptop), **M11** (UI/visibility), **M12** (npm + worker tests); reviews
**M1** (client signers), **M2** (worker release / SDK refresh), **M4** (telephony SDK),
**M8** (SDK/demo timeouts) for Habiba.

Working rules followed: every `file:line` below was opened in this audit, not copied from the
plan. "NOT FOUND" states what was searched. Findings are recorded before fixes.

## Environment these results came from

| Item | Value |
|---|---|
| Commit | `7a3c382` (origin/main == origin/staging == finova/main, pulled 2026-10-11) |
| Python | 3.12.15 venv, `requirements.txt` installed exactly |
| Database | local PostgreSQL 18.4, SSL on, all 42 migrations applied clean from empty (`scripts/migrate.py --allow-initial`), Supabase `auth.jwt()` / `auth.uid()` / `anon`+`authenticated`+`service_role` emulated |
| Node | v24.12.0, npm 11.6.2 |
| Full suite, DB configured | **1310 passed, 18 failed, 19 skipped, 3 deselected** |
| Full suite, offline (no DB) | 1169 passed, 172 skipped, **6 collection errors** |
| CI's own gating job (`scripts/run_ci_unit.py`) | 712 passed, 39 skipped — green |

---

## M10 — Supply chain, CI, release (P1, Ehsan leads)

### M10-F01
```
ID:            M10-F01
Module:        M10 (also M12)
Severity:      Critical
Where:         tests/conftest.py:165-199 (pytest_runtest_call wrapper, the `or not _HAS_CREDENTIALS` branch)
               .github/workflows/ci.yml:28-37 (the job that sets no credential env vars)
What:          The only Python job that can fail CI converts every test failure into a skip.
               The conftest wrapper turns a failed test into Skipped when `_HAS_CREDENTIALS`
               is false, and `_HAS_CREDENTIALS` is false in exactly the environment the
               `pytest-unit` job runs in (`SUPABASE_DB_URL: ""`, no SUPABASE_URL /
               SUPABASE_KEY / GROQ_API_KEY / GOOGLE_API_KEY / CEREBRAS_API_KEY /
               UPLIFTAI_API_KEY).
Impact:        No Python regression can turn CI red. Every merge to main/staging since this
               hook landed has been gated by a job that is structurally incapable of failing.
How verified:  ran test. Added tests/test_zz_gate_probe.py containing `assert 1 == 2` and ran
               it in the CI unit job's exact env:
                 CI_UNIT_FORCE_OFFLINE=1 SUPABASE_DB_URL="" ... pytest tests/test_zz_gate_probe.py
                 -> "1 skipped", exit 0, reason "conftest.py:197 ... no credentials configured"
               Same test with one credential var set -> "1 failed". Probe file deleted after.
Suggested fix: narrow the skip to its actual purpose. The guard exists for provider-key and
               live-backend absence, which are already covered by (a) the `tripped` branch
               (offline socket guard fired) and (b) the "API key is required" branch. Drop
               `or not _HAS_CREDENTIALS` entirely, or gate it on an explicit opt-in
               (`UVA_TEST_ALLOW_SKIP_ON_FAILURE=1`) that CI never sets. Then add a canary
               test to CI that asserts a deliberate failure is reported as a failure.
Status:        open
Note:          This is my own F-H1 follow-up code. Mine to fix.
```

### M10-F02
```
ID:            M10-F02
Module:        M10 (also M12)
Severity:      High
Where:         .github/workflows/ci.yml:38-70 (pytest-integration), scripts/run_ci_unit.py:30-40,
               tests/ci_unit_manifest.txt
What:          CI runs 43 of the repo's 139 test files. `pytest-unit` runs only the manifest
               whitelist; `pytest-integration` prints a ::warning:: and `exit 0` whenever the
               SUPABASE_DB_URL secret is absent, so the DB-backed half has never been gating.
               F-H1 removed a 63-name whitelist from pytest.ini; an equivalent whitelist now
               lives in tests/ci_unit_manifest.txt, so a new test file still does not run in
               CI unless someone edits that list.
Impact:        18 real failures and 6 collection errors exist on main right now and no CI run
               shows them (see M12-F01). "CI green" means "43 files passed".
How verified:  ran both. `python scripts/run_ci_unit.py` -> 712 passed / 39 skipped, green.
               Default discovery with the same env -> 1169 passed + 6 errors. Default
               discovery with a database -> 18 failed. `wc`: 43 manifest entries vs 139
               `tests/test_*.py`.
Suggested fix: make `pytest-unit` run default discovery (`python -m pytest`) and keep the
               manifest only as a fast subset; make `pytest-integration` fail, not pass, when
               the secret is missing on main/staging (a service-container Postgres in CI
               removes the excuse — it worked locally in minutes).
Status:        open
```

### M10-F03
```
ID:            M10-F03
Module:        M10 (also M9)
Severity:      Medium
Where:         telephony/README.md:23; telephony/CHANGELOG.md:31-32;
               .github/ISSUE_TEMPLATE/release-checklist.md:30;
               .github/workflows/release-sdk.yml:14-15, 153-156
What:          Three shipped documents state that releases publish with npm provenance. The
               publish step deliberately omits `--provenance` (npm rejects it from a private
               repo) and the registry confirms nothing is attested.
Impact:        A consumer who checks the provenance claim finds none; the claim is in the
               README that ships inside the npm tarball.
How verified:  ran. `curl https://registry.npmjs.org/@awaazlabs-uva%2fvoice/1.1.0` ->
               `dist` has keys [fileCount, integrity, shasum, signatures, tarball,
               unpackedSize]; **no `attestations`**. Published 2026-09-18T10:30:10Z by
               npm user `habibaimran`.
Suggested fix: either delete the three claims, or make the canonical repo public and add
               `--provenance` + npm >= 11.5.1 (Node 20 ships npm 10, so provenance/OIDC would
               also need the Node bump). Decide with the repo-visibility question (plan §8 Q7).
Status:        open
```

### M10-F04
```
ID:            M10-F04
Module:        M10
Severity:      Medium
Where:         sdk/package.json, sdk-server/package.json, telephony/package.json (no `license`);
               repo root (no LICENSE file)
What:          None of the three published packages declares a license, and there is no
               LICENSE file to inherit. npm shows them as unlicensed.
Impact:        A corporate integrator's dependency review blocks on "no license". It also
               makes the legal status of the client-facing SDK ambiguous.
How verified:  read all three package.json files; `curl` the registry — `license: None` on
               the published `@awaazlabs-uva/voice@1.1.0`.
Suggested fix: add a `license` field (and the matching LICENSE file) to all three before the
               next publish.
Status:        open
```

### M10-F05
```
ID:            M10-F05
Module:        M10
Severity:      Low
Where:         .github/workflows/ci.yml:172-196
What:          pip-audit and npm audit are suppressed twice: `continue-on-error: true` and a
               trailing `|| echo "::warning::..."`. The warning is the only trace, and nothing
               makes anyone read it.
Impact:        A new advisory in a pinned dependency can sit unnoticed indefinitely. (The
               design decision — "advisories must not block an unrelated hotfix" — is sound;
               the gap is that no path ever surfaces them.)
How verified:  read code.
Suggested fix: drop the redundant `|| echo` (continue-on-error already keeps the job green),
               and add a scheduled advisory-only workflow that opens/updates an issue so the
               finding lands somewhere a human sees.
Status:        open
```

Clean results in M10 (searched, nothing found):

- `release-sdk.yml` enforces tag/`package.json` version equality, a `## [version]` CHANGELOG
  section, `repository.url` == running repo, "already on npm" refusal, and fails (not skips)
  on a missing `NPM_TOKEN`. Verified by reading all 161 lines.
- Release tags `voice-v1.1.0`, `agents-v0.1.0`, `telephony-v0.1.0` exist on the canonical
  remote (`finova`, all at `d6b42a7`) and the registry versions match `package.json` exactly:
  voice 1.1.0, agents 0.1.0, telephony 0.1.0 (`curl` on all three). The "packages do not
  resolve on npm" problem from Wave 1 is gone.
- `docker-smoke` builds all four images; `dashboard` job typechecks and builds; the published
  browser bundle is grepped for secret-shaped strings and that check *does* gate.

---

## M3 — Worker capacity and provider failure (P1, Ehsan)

### M3-F01
```
ID:            M3-F01
Module:        M3 (links M2)
Severity:      High
Where:         scripts/dev_worker.py:3-5 and its Popen argv ("python -m worker.main dev");
               worker/main.py:1795-1813 (WorkerOptions — no load_threshold, no job memory cap)
What:          The production worker is started in LiveKit's dev mode, which disables load
               shedding. livekit-agents sets `load_threshold = ServerEnvOption(dev_default=
               math.inf, prod_default=0.7)`; the `dev` subcommand resolves the dev default, so
               the worker never stops accepting jobs however loaded the machine is. The repo
               also leaves `job_memory_limit_mb = 0` (no per-job cap; `job_memory_warn_mb`
               only logs).
Impact:        One machine, no admission control: concurrent calls are accepted until CPU
               thrashes and every live call degrades together. This is the direct answer to
               the plan's M3 question "Is it configured or left at LiveKit's default?" —
               the effective value is "disabled".
How verified:  read code, in the installed library:
                 venv/livekit/agents/worker.py:148  _default_load_threshold = ServerEnvOption(dev_default=math.inf, prod_default=0.7)
                 venv/livekit/agents/worker.py:141-145  getvalue() returns dev_default when devmode
                 venv/livekit/agents/worker.py:200  job_memory_limit_mb: float = 0
                 venv/livekit/agents/cli/_legacy.py:1615-1616  `dev`/`console` set LIVEKIT_DEV_MODE=1
               and `docker/worker.Dockerfile:48` uses `start` (prod, 0.7) while the documented
               local runner uses `dev`.
Suggested fix: run the production worker with `start`, or pass an explicit
               `load_threshold=` and `job_memory_limit_mb=` in WorkerOptions so the value no
               longer depends on which subcommand someone typed. Then measure the real
               ceiling on that machine (plan §8 Q2 needs a number).
Status:        open
```

### M3-F02
```
ID:            M3-F02
Module:        M3 (links M7)
Severity:      Low
Where:         venv/livekit/agents/cli/_legacy.py:1618-1619, 1647-1651 vs 1676-1682
What:          The same `dev` subcommand also selects the DEBUG log default (`start` selects
               INFO), so the production worker logs at DEBUG.
Impact:        Verbose per-turn logs on the machine that holds production secrets; more places
               for caller content to land (see M7).
How verified:  read code (installed library, as above).
Suggested fix: same as M3-F01, or set `LIVEKIT_LOG_LEVEL=INFO` on the worker machine.
Status:        open
```

Clean results in M3 (searched, nothing found):

- **Empty / log-only `except` blocks**: searched all 63 `worker/**.py` modules for
  `except Exception`, `except BaseException`, bare `except:` → 101 broad handlers, of which
  only 3 swallow silently, and all three are nested best-effort cleanup where swallowing is
  correct: `worker/main.py:1722` (health flag after a prewarm failure already logged),
  `worker/session_opening.py:101` (optional data packet to a browser that may be gone),
  `worker/telephony_call_status.py:306` (`_close_quietly`). No `contextlib.suppress` abuse.
  This check is clean.
- Provider connect retries are bounded (`worker/provider_retries.py`) and the registry raises
  `UnsupportedProviderError` rather than falling back silently.

---

## M6 — Tool gateway, SSRF, prompt injection, agent powers (P1, Ehsan leads)

### M6-F01
```
ID:            M6-F01
Module:        M6
Severity:      High
Where:         worker/ssrf_guard.py:70-137 (every early-return path when `hosted` is false);
               worker/tools.py:321 (`prepare_tools_post_url(url)` — called with no `hosted=`,
               so it uses `is_hosted()`); control_plane/runtime_env.py:33-40
What:          The worker's request-time SSRF guard is inert on the machine that actually runs
               it. With `UVA_ENV`/`RENDER`/`ENVIRONMENT` unset — the documented state of the
               production worker ("LiveKit worker runs locally for now") — `is_hosted()` is
               False and the guard: allows `http://` (gateway secret in cleartext), allows
               `localhost`/`.internal`/`metadata.google.internal`, allows literal private and
               loopback IPs, allows a public hostname that resolves to a private address, and
               performs no IP pinning. Every branch returns the URL unchanged.
               tenant_portal_api/tools_webhook.py:10-16 states in its own docstring that DNS
               rebinding is closed "by the worker [resolving], pinning and connecting to the
               same address" — that mitigation is exactly what switches off here.
Impact:        A tenant can save a tools_base_url that resolves publicly (so save-time
               validation passes), then re-point the DNS record at 127.0.0.1 or a LAN address.
               The worker POSTs there with `x-tool-gateway-secret`, and the response is fed
               back to the LLM as a tool result — SSRF into the operator's own machine and
               home/office LAN, plus secret disclosure, from a tenant-controlled DNS record.
How verified:  ran, against live DNS, using `localtest.me` (a real public name whose A record
               is 127.0.0.1):
                 DNS localtest.me -> ['127.0.0.1']
                 worker guard hosted=False: ALLOWED -> https://localtest.me/tools {}
                 worker guard hosted=True : blocked (resolves to a private/link-local address)
                 portal save-time (hosted): rejected - resolves to an internal address
               and `is_hosted()` printed False for a bare worker process. Also ran the full
               matrix (169.254.169.254, metadata.google.internal, 127.0.0.1, 192.168.1.10,
               [::1], localhost, *.svc.cluster.local): all ALLOWED with hosted=False.
Suggested fix: invert the default — apply the hosted rules unless a developer explicitly opts
               out (`UVA_ALLOW_PRIVATE_TOOL_TARGETS=1`), which keeps local tool development
               working while making the deployed worker safe by default. Pin and re-resolve
               regardless of environment.
Status:        open
```

### M6-F02
```
ID:            M6-F02
Module:        M6 (links M7)
Severity:      Medium
Where:         docker/worker.Dockerfile (no `ENV UVA_ENV=...`) vs docker/admin.Dockerfile:35,
               docker/control-plane.Dockerfile:30, docker/tenant-portal-api.Dockerfile:24
What:          Three of the four service images set `ENV UVA_ENV=production`. The worker image
               does not, so even a containerised worker reports "not hosted" and inherits
               every relaxation in M6-F01.
Impact:        Deploying the worker to a container does not fix M6-F01; the gap is silent.
How verified:  read code (grep for UVA_ENV across docker/*.Dockerfile: 3 hits, worker absent).
Suggested fix: add `ENV UVA_ENV=production` to docker/worker.Dockerfile and document that a
               bare-metal production worker must export it too.
Status:        open
```

### M6-F03
```
ID:            M6-F03
Module:        M6 / M7
Severity:      Medium
Where:         worker/recording_policy.py:33-42 (`is_hosted_render()` reads only `RENDER`)
What:          A third hosted-detection scheme. `control_plane/runtime_env.is_hosted()` reads
               UVA_ENV/RENDER/ENVIRONMENT; recording policy reads `RENDER` alone. A worker
               deployed anywhere other than Render (including the current laptop, a VM or
               Docker) is "not hosted" for recording purposes, so the env-only force-on
               (`UVA_SESSION_RECORD_AUDIO=1`) stays available.
Impact:        Recording can be forced on in a real deployment that the code believes is a
               developer machine — a consent/retention problem, not just hygiene.
How verified:  read code; grep for `RENDER` in worker/**.
Suggested fix: have recording_policy call `control_plane.runtime_env.is_hosted()` (the worker
               already imports from that module in ssrf_guard.py, so no new coupling).
Status:        open
```

### M6-F04
```
ID:            M6-F04
Module:        M6
Severity:      Medium
Where:         host-tools/src/createApp.js:26 (`headerSecret !== secret`), :81/:133/:177/:225
               (tenant_id from the request body), :215-217 (`/_debug/appointments`),
               :250 (`err.message` to the client); host-tools/src/store.js:7-10, 20-22, 80-83
What:          The demo tool gateway has five issues that matter because its README tells the
               reader to adopt it ("Replace the in-memory store with Finova's real calendar...
               Keep the same route paths and idempotency behaviour"):
               (a) the shared secret is compared with `!==`, not a timing-safe compare;
               (b) `tenant_id` comes from the request body, so one gateway secret can act as
                   any tenant, and the store is keyed by that value;
               (c) `GET /api/tools/_debug/appointments` returns `store.listAppointments()` with
                   no tenant filter — every tenant's customer names and phone numbers;
               (d) write failures return `err.message` to the caller;
               (e) `appointments` and `idempotency` Maps have no expiry (only `reset()`), so a
                   long-running gateway grows without bound.
Impact:        As a demo, contained. If adopted as the gateway template — which the README
                invites — (b) and (c) are cross-tenant PII exposure.
How verified:  read code (all of createApp.js auth/route/write paths and all of store.js).
Suggested fix: derive tenant_id from the credential rather than the body; tenant-scope or
               remove the debug route; `crypto.timingSafeEqual`; return a generic error; add a
               TTL sweep. Or state plainly in the README that this is not a template.
Status:        open
```

---

## M1 — Client signers (P0, Habiba leads; Ehsan reviews the signers)

### M1-F01
```
ID:            M1-F01
Module:        M1
Severity:      Medium
Where:         sdk-server/src/index.ts:165-177 (canonicalJson); telephony/src/signing.ts:35-38,
               78-95 (canonicalJson/normalizeJson); tenant_portal_api/machine_auth.py:59-69
               (payload_hash)
What:          The JS canonicalisers and the Python one disagree on two inputs, so the request
               is rejected with "bad signature":
               (a) **key order** — JS `Object.keys().sort()` sorts by UTF-16 code unit, Python
                   `sort_keys=True` sorts by code point. Any key containing an astral
                   character (emoji, non-BMP script) sorts differently.
               (b) **float format** — JS emits `1e-7`, Python re-serialises the parsed value as
                   `1e-07`. Any number whose magnitude puts JS into exponential notation
                   (|x| < 1e-6) mismatches.
Impact:        Fails closed (401), so it is a correctness/DX bug, not an auth bypass. It is
               reachable because `sttOptions`/`llmOptions`/`ttsOptions` are free-form
               pass-through JSON: a provider option like `{"epsilon": 1e-7}` or an emoji key
               makes agent.create/update unexplainably return "bad signature".
How verified:  ran test, then reproduced live against a running portal through the published
               SDK (see "Live end-to-end verification" below: both classes return
               401 bad signature). Built a 15-case corpus and compared the client's own wire bytes
               (verbatim copies of both canonicalisers run under Node 24) against
               `machine_auth.payload_hash(json.loads(wire))` — the faithful model of what the
               server does. 30 client/case pairs, 4 mismatches, all of them the two classes
               above:
                 {"😀":2,"Ａ":1}   (client)  vs  {"Ａ":1,"😀":2}   (server)
                 {"x":1e-7}        (client)  vs  {"x":1e-07}       (server)
               Everything else matched, including `{}`, Urdu text, nested objects/arrays,
               quotes/backslashes/control characters, an empty-string key, `true/false/null`,
               integers, 2.5, and 1e21.
Suggested fix: sort by code point in both JS implementations (compare with
               `[...a].map(c=>c.codePointAt(0))`, or `Intl.Collator` is *not* right here), and
               document the numeric domain as "no exponential-notation numbers" — or stop
               re-serialising on the server (see M1-F02), which removes both classes at once.
Status:        open
```

### M1-F02
```
ID:            M1-F02
Module:        M1
Severity:      Medium
Where:         tenant_portal_api/app.py:1155 and :1253 (`body=body.model_dump(exclude_none=True)`);
               CreateAgentBody/UpdateAgentBody at app.py:175, :203 (no `model_config`, so
               Pydantic's default `extra='ignore'`)
What:          The server does not verify the signature over the bytes it received. It parses
               the body into a Pydantic model and hashes a re-serialisation of that model, so
               the signature binds a normalised projection of the request, not the request.
               Any field the client signed but the model does not know is dropped before
               hashing.
Impact:        Version skew between SDK and server surfaces as `401 bad signature` — the
               single most misleading error available — instead of "unknown field". A newer
               SDK against an older portal fails this way across the board. The flip side:
               two different wire bodies that normalise to the same dict have the same valid
               signature (an in-flight actor could add fields the model ignores), which the
               nonce burn limits but does not conceptually fix.
How verified:  read code (both call sites, both models, `payload_hash`, and the comment at
               app.py:1148-1154 which documents an earlier instance of exactly this class of
               break), then proved it against the running portal with hand-signed requests:
               known fields only -> 200; the same body plus one unknown `future_field` ->
               401 bad signature; the same body plus `greeting: null` -> 401 bad signature.
Suggested fix: hash the raw request body bytes on the server and have clients sign those same
               bytes (the client already computes `canonicalBody` — telephony even returns it).
               Keep the canonical-JSON rule only as the client's byte-generation recipe.
Status:        open
Owner:         server change — Habiba's file; raised here because it is a shared contract
               (plan §5 item 1).
```

Clean results in M1 (searched, nothing found):

- **Mint-path signature compare is constant-time.** The plan recorded this as unverified:
  `control_plane/mint.py:111` and the rotation-retry at `:126` both use
  `hmac.compare_digest`, as does `tenant_portal_api/machine_auth.py:160`.
- **Empty-body hashing agrees.** sdk-server passes `{}` for every GET (`index.ts:215`, `:286`,
  `:292`), telephony's `canonicalJson(undefined)` returns `{}`, and the GET routes pass
  `body={}` (`app.py:1211`, `:1231`). All three hash `"{}"`.
- **Urdu text agrees.** `ensure_ascii=False` on the server matches `JSON.stringify`'s
  non-escaping on both clients — verified in the differential above.
- **Both JS signers agree with each other** on all 15 cases, so there is no client-vs-client
  drift of the kind that broke canonicalisation before.
- **Header names agree**: `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature` in
  telephony/src/signing.ts:7-12, sdk-server/src/index.ts:255-258,
  client-integration-test/backend/src/signing.js:26-31.
- **The mint signer matches the server shape**: `${tenantId}.${timestamp}.${nonce}.${agentId}`
  (client-integration-test/backend/src/signing.js:10) == `control_plane/mint.py:40-44`.

---

## M9 — SDK developer integration (P1, Ehsan)

### M9-F01
```
ID:            M9-F01
Module:        M9
Severity:      High
Where:         deleted in commit a351576 ("Finalize P0 humanization and independent client
               testing"); still referenced by tests/test_sdk_parity.py:8-12,
               audit-context/AUDIT_CONTEXT.md and the split plan's M1/M9 scope
What:          The entire client-facing deliverable pack is gone from the repo — 14 files,
               1,241 lines: 01-INTEGRATION_GUIDE.md, 02-HOST_BACKEND_CONTRACT.md,
               03-ERROR_HANDLING.md, 04-TELEPHONY_AND_PROVIDER_KEYS.md,
               05-CREDENTIALS_TEMPLATE.md, 06-SECURITY_RULES.md, README.md and the whole
               runnable `host-backend-starter/` (config.js, createApp.js, server.js,
               signing.js, .env.example, package.json, README.md). The commit message says
               the deletions came in via `git add .` ("prior deletions as explicitly requested
               through git add ."), i.e. swept in rather than decided.
Impact:        There is no integration guide, no host-backend contract document and no runnable
               reference host backend to give a client. `client-integration-test/` (added in
               the same commit) is a test harness, not a deliverable: no integration guide, no
               security rules, no credentials template. Two of the four signers the plan asks
               me to verify no longer exist to verify.
How verified:  read git history — `git show --stat a351576 -- client-deliverables-final`
               (14 files, 1,241 deletions), `git ls-tree -r HEAD | grep -c client-deliverables-final`
               -> 0, and `find . -name "*starter*"` -> nothing.
Suggested fix: decide whether the pack is retired or restored. If retired, remove the dangling
               references (test_sdk_parity.py docstring, audit-context) and say what clients
               get instead. If not, restore from a351576^ and keep it in CI (a build of the
               starter would have caught the deletion).
Status:        open
```

### M9-F02
```
ID:            M9-F02
Module:        M9
Severity:      Medium
Where:         client-integration-test/packages/awaazlabs-uva-voice-1.1.1-humanization.0.tgz,
               packages/voice-manifest.json, frontend/package.json:14, sdk/package.json:3
What:          A 1.1.1-humanization.0 prerelease of the voice SDK is committed to the repo as
               a binary tarball and consumed by the client test harness via a `file:` dep,
               while sdk/package.json says 1.1.0 and npm's latest is 1.1.0. The manifest is
               honest about it ("unpublished test snapshot; not an npm registry release") and
               hash-pins it, but nothing reconciles the three versions.
Impact:        Whatever the client harness proves, it proves about a build no client can
               install. It also makes `tests/test_sdk_docs_contract.py` fail (see M12-F01).
How verified:  read all three files; `curl` the registry (voice: only 1.1.0);
               ran `scripts/check-packages.mjs` logic by reading it (sha256 + independence
               assertions are real).
Suggested fix: publish 1.1.1 (or bump package.json to the prerelease and publish it under a
               `next` tag) and point the harness at the registry, so "independently installed"
               means from npm.
Status:        open
```

### M9-F03
```
ID:            M9-F03
Module:        M9 (links M8)
Severity:      Medium
Where:         sdk-server/src/index.ts:267 (`const parsed = text ? JSON.parse(text) : null`),
               :260-266 (fetch with no AbortController), :183-186 (plain `Error` from the
               constructor)
What:          The agents SDK has no request timeout and no retry, and parses the response
               body with an unguarded `JSON.parse`. A Render cold start or proxy error page
               (HTML, not JSON) throws `SyntaxError: Unexpected token '<'` out of the SDK
               rather than a typed `AwaazLabsUvaAgentsError`. The constructor throws plain
               `Error`, so callers cannot discriminate configuration errors either.
Impact:        A first call after idle fails with a parse error the integrator cannot act on;
               with no timeout, a hung portal hangs the caller's request indefinitely.
               Telephony already does this correctly (`telephony/src/errors.ts:42-47` maps
               invalid JSON to an error code), so the two backend SDKs differ.
How verified:  read code (both SDKs).
Suggested fix: wrap the parse, add an `AbortController` timeout with a documented default, and
               throw `AwaazLabsUvaAgentsError` from the constructor. Mirror telephony.
Status:        open
```

### M9-F04
```
ID:            M9-F04
Module:        M9
Severity:      Low
Where:         sdk/package.json:25-45, sdk-server/package.json (no `engines`);
               telephony/package.json:49-51 (has `engines`)
What:          voice and agents declare no `engines`; telephony declares `node >= 20`. The
               agents SDK uses `crypto.subtle` and `node:crypto`, so it does have a floor.
Impact:        An integrator on an older Node gets a runtime error instead of an install
               warning.
How verified:  read all three package.json files; confirmed `license`/`engines` absence on the
               published package via the registry.
Suggested fix: add `engines.node` to voice and agents.
Status:        open
```

---

## M12 — Tests and observability (P2, Ehsan for npm and worker)

### M12-F01
```
ID:            M12-F01
Module:        M12
Severity:      High
Where:         the 18 failures listed below, on commit 7a3c382
What:          With a database configured, the suite is red in three independent places:
               (a) 15 portal failures, all one root cause: `POST /portal/login` returns
                   403 "CSRF check failed: send Origin/Referer matching TENANT_PORTAL_ORIGINS,
                   or header X-UVA-Portal: 1", after which every test raises
                   `KeyError: 'token'`. Files: tests/test_phase4_portal_api.py (9),
                   tests/test_portal_wave2_credentials.py (5),
                   tests/test_portal_members_invite.py (1). (Habiba's code + tests.)
               (b) tests/test_worker.py — `test_end_conversation_summary_writes_to_the_real_
                   session_row` and `test_escalate_to_human_writes_a_real_row_linked_to_the_
                   session` assert exact dict equality (`== {'status': 'saved'}`) against tool
                   results that now also carry `outcome`, `businessEffect`, `retrySafe` from
                   the humanization orchestrator. Mine (worker tests).
               (c) tests/test_sdk_docs_contract.py::test_package_json_versions_match_docs_pins
                   — `docs/LIVE_CALL_REGRESSION_2026_10_10.md` pins
                   `@awaazlabs-uva/voice@1.1.1-humanization.0`; the test's regex
                   `@(...)@(\d+\.\d+\.\d+)` captures `1.1.1` and compares it to 1.1.0. Mine.
               Offline (no DB) there are also 6 collection errors in
               tests/test_portal_supabase_auth.py.
Impact:        The suite cannot be used as a signal, which is how M10-F01/F02 stayed invisible.
How verified:  ran. Full run with the local DB: `18 failed, 1310 passed, 19 skipped,
               3 deselected`. Full run offline: `1169 passed, 172 skipped, 6 errors`.
               Individually re-ran test_sdk_docs_contract.py to confirm (c) is not an
               environment artefact: 1 failed, 3 passed.
Suggested fix: (a) is Habiba's — the new CSRF middleware needs the test client to send the
               header, or the tests need updating; (b) assert on the subset the test cares
               about, or freeze the tool-result contract deliberately; (c) allow a prerelease
               suffix in the regex and decide whether a doc may pin an unpublished build.
Status:        open
```

---

### M9-F05
```
ID:            M9-F05
Module:        M9
Severity:      High
Where:         sdk/README.md:21, :29, :123 (and 5 github.com links in total);
               sdk-server/README.md (2 links); telephony/README.md (1 link);
               docs/HOST_BACKEND_CONTRACT.md:1-12
What:          Every documentation link in the published npm READMEs points into a private
               GitHub repository, so none of them resolves for a client. The chain a client
               actually follows is: npm README -> "session contract" link -> 404; or npm
               README -> docs/HOST_BACKEND_CONTRACT.md (marked "Superseded", which redirects
               to `client-deliverables-final/...`) -> a directory that no longer exists
               (M9-F01). The "Optional starter" link points straight at the deleted starter.
Impact:        A paying integrator installing from npm has no reachable documentation at all
               except the authenticated in-dashboard /docs. The READMEs are shipped inside the
               published tarballs, so this is what clients see first.
How verified:  ran. Anonymous `curl -o /dev/null -w %{http_code}`:
                 https://github.com/Finova-Solutions/urdu-voice-agent-SDK                -> 404
                 https://raw.githubusercontent.com/.../docs/HOST_BACKEND_CONTRACT.md     -> 404
                 https://api.github.com/repos/Finova-Solutions/urdu-voice-agent-SDK      -> 404
               plus read of all three READMEs and of the superseded contract doc.
Suggested fix: point the npm READMEs at public URLs only (the dashboard /docs host, or inline
               the quickstart), or make the repo public. Either way remove the starter link
               until M9-F01 is decided.
Status:        open
```

### M9-F06
```
ID:            M9-F06
Module:        M9
Severity:      Medium
Where:         sdk/README.md (0 occurrences of sessionHeaders / sessionCredentials /
               connectTiming); sdk/src/index.ts:54 (`voiceId?: string` — the only occurrence
               in the file); docs/CLIENT_QUICKSTART.md:10-12, docs/CLIENT_HANDOFF_GUIDE.md,
               docs/CLIENT_ONBOARDING_EMAIL_TEMPLATE.md (all three point at the deleted pack);
               tests/test_wave5_residuals.py:159-172
What:          Documented-vs-real mismatches, re-verified on this commit:
               (a) `sessionHeaders`, `sessionCredentials` and `connectTiming` are public API
                   and appear nowhere in sdk/README.md (0 hits each).
               (b) `ConnectOptions.voiceId` is declared and never read — one occurrence in the
                   whole file. A developer who sets it gets silence, not an error.
               (c) The three CLIENT_* guides still route readers to `client-deliverables-final/`.
               (d) `tests/test_wave5_residuals.py::test_client_docs_no_longer_point_at_deleted_
                   trees` **asserts that they do**: `required = "client-deliverables-final"`.
                   The guard that was supposed to stop docs pointing at deleted trees now
                   enforces a pointer to a deleted tree, and passes while doing it.
Impact:        (b) is a silent no-op in the public API. (c)+(d) mean the docs guard cannot
               catch this class of rot any more.
How verified:  read code + grep counts, and read the test body.
Suggested fix: document the three options or mark them internal; either send `voiceId` or
               delete it from `ConnectOptions`; update the CLIENT_* guides and invert the test
               so it asserts every referenced path exists on disk.
Status:        open
```

### M9-F07
```
ID:            M9-F07
Module:        M9 / M12
Severity:      Low
Where:         sdk/src/*.test.ts (21 tests, none covering connect()/disconnect()/getters);
               sdk-server/test/client.test.mjs (12 tests)
What:          The plan's recorded test gaps are real. Voice covers error mapping, refresh
               backoff, listener isolation, playback readiness, metrics and LiveKit token
               injection — there is no connect() happy path, no disconnect(), no getter test.
               Agents covers the constructor, signing (POST / GET-empty-body / extraHeaders),
               create/update field mapping, unassign and error mapping — nothing for
               `getProviderCapabilities`, `listManagedNumbers`, `assignAgentToNumber`, and
               nothing for a non-JSON response (the M9-F03 path).
Impact:        The two most common integration failures (a bad connect, a cold-start HTML
               error page) are the two least covered.
How verified:  ran all three suites on this commit — voice 33 passed (6 files), agents 12
               passed, telephony phase8 smoke + phase9 contract passed — and listed every
               test name.
Suggested fix: add a mocked connect()/disconnect() path for voice and a non-JSON-response
               test for agents; both are cheap and would have caught M9-F03.
Status:        open
```

Clean results in M9 (searched, nothing found):

- **CommonJS loadability is NOT broken.** The plan's check was "load the agents/telephony
  packages from a CommonJS backend and see whether it works. ESM-only may block common
  setups." Ran it: `npm pack` both packages, installed the tarballs into a
  `"type": "commonjs"` project, then `require('@awaazlabs-uva/agents')` and
  `require('@awaazlabs-uva/telephony')` — both succeeded (4 and 9 exports) on Node v24.12.0,
  because `require(esm)` resolves the `default` condition. The residual risk is only old
  Node, and no `engines` field warns about it (M9-F04). A TypeScript CJS consumer still needs
  `moduleResolution: node16`/`bundler` to see the `exports` map.
- **Published tarball contents are correct**: `package/dist/index.js`, `index.d.ts`,
  `package.json`, `README.md`, `CHANGELOG.md` — nothing stray, `files` is accurate.
- **Registry versions match source**: voice 1.1.0, agents 0.1.0, telephony 0.1.0; release
  tags for all three exist on the canonical remote at `d6b42a7`.
- **`express.json()` with no limit** (plan item, demo backend `createApp.js:262`) is not a
  real gap: body-parser's default limit is 100kb. host-tools sets 64kb explicitly.

---

## M11 — Dashboard read-only requirement (P1, Ehsan for UI and visibility)

### M11-F01
```
ID:            M11-F01
Module:        M11
Severity:      Low
Where:         dashboard/src/lib/portalApi.ts:214 (createAgent), :230 (updateAgent),
               :248 (deleteAgent)
What:          The dashboard has no create-agent UI path — but it still ships three exported
               mutation helpers for agents, and none of them has a single caller anywhere in
               `dashboard/src/**`. They are a loaded gun for the read-only requirement: one
               `onClick={() => createAgent(...)}` re-opens it with no server change.
Impact:        Hygiene now; a regression risk for the product decision the plan is waiting on.
How verified:  ran. Ripgrep for `\b(createAgent|updateAgent|deleteAgent)\s*\(` across
               dashboard/src/**/*.{ts,tsx}: the only hits are the three definitions in
               portalApi.ts plus two occurrences inside documentation *code samples*
               (content/docs/pages/sdk-reference.ts:49, backend-setup.ts:226, which correctly
               teach the SDK/HMAC path). Zero call sites under dashboard/src/app/**.
Suggested fix: delete the three helpers (the SDK is the supported create path), or mark them
               `@internal` with a comment naming the M11 decision.
Status:        open
```

Clean results in M11 (searched, nothing found):

- **No create-agent (or edit/delete) UI path**, as above — stronger than the interim decision
  required, which only forbids creation.
- **No XSS sink**: zero `dangerouslySetInnerHTML` in `dashboard/src/**`.
- **Client env hygiene is clean**: every `process.env` read in client code is `NEXT_PUBLIC_*`
  (11 variables). The only non-prefixed reads are inside documentation code samples
  (`content/docs/pages/backend-setup.ts`), i.e. strings shown to the reader, not executed.
- **Staleness is not 15 minutes.** The plan suspected a 15-minute hidden window. The
  sessionStorage overview snapshot (`lib/overviewCache.ts`, MAX_AGE_MS = 15 min) is used only
  as `fallbackData` alongside `revalidateOnMount: true` and `keepPreviousData: true`
  (`app/page.tsx:116-129`), so it is a first-paint placeholder that revalidates immediately.
  SWR's `dedupingInterval` is 5 s, not 15 min (`components/SwrProvider.tsx:11-19`). An agent
  created through the SDK is therefore visible on the next fetch, not after 15 minutes.
- The revealed HMAC secret is held in React state only and never written to storage
  (`app/credentials/page.tsx:24-28, 55-60`). The cached overview contains credential
  *metadata* (`secret_provisioned`, `hmac_secret_hash`, `allowed_origins`), not the secret.

---

## M7 — Secrets, PII, logging (P1, Ehsan for the worker and laptop)

### M7-F01
```
ID:            M7-F01
Module:        M7
Severity:      Medium
Where:         worker/prompt_dump.py:14 (`_DEFAULT_DUMP = _ROOT / "docs" / "last_session_prompt.txt"`),
               :51; docs/last_session_prompt.txt (present, 5,336 bytes, tracked in HEAD);
               .gitignore (does not cover it)
What:          The prompt-dump default path is inside the repository working tree, the file is
               not gitignored, and it has been committed four times (62b2eb3, 38a3b61,
               4de5707, b8e104a). The module's own docstring says "never on shared prod disks
               (PII / persona in plaintext)" — the default location makes the repo exactly
               that. The current committed copy holds a real `agent_id`, the full
               `system_instructions` and the effective persona for a live agent.
Impact:        Agent prompt/persona (the client's IP) and agent identifiers are in git history
               and will be re-committed by any `git add .` after a debug session — which is
               how a351576 was made (M9-F01).
How verified:  ran: `git check-ignore -v docs/last_session_prompt.txt` -> not ignored;
               `git ls-files --error-unmatch` -> tracked; `git log --all --` -> 4 commits;
               read the file's header block.
Suggested fix: default the dump to a path outside the repo (or `state/`/temp) and add
               `docs/last_session_prompt.txt` to .gitignore; decide separately whether to
               purge the existing copies from history.
Status:        open
```

Clean results in M7 (searched, nothing found):

- **`.env.local` is not committed and cannot be**: `.gitignore:1-3` is `.env`, `.env.*`,
  `!.env.example`; `git log --all -- .env.local` is empty.
- **Transcript logging is off by default and bounded**: `worker/transcript_logging.py:17-32`
  requires an explicit truthy `UVA_LOG_TRANSCRIPTS` and caps text at 200 chars.
  `UVA_DUMP_PROMPTS` is likewise explicit-opt-in (`worker/prompt_dump.py:20-26`).
- **The raw tool-gateway secret is never returned over the API**:
  `tenant_portal_api/queries.py:37-61` maps it to `tools_auth_secret_configured: boolean`;
  only `_agent_row_internal` (worker path, line 64-72) decrypts it. Verified by reading both
  mappers and the `list_agents` SELECT.
- **The telephony SDK redacts sensitive response keys** (`telephony/src/transport.ts:15-29`
  — 13 keys including `api_key`, `sip_secret`, `tenant_secret`, `x_signature`).

---

## M8 — Resilience on Render free (P1, Ehsan for SDK and demo timeouts)

### M8-F01
```
ID:            M8-F01
Module:        M8
Severity:      Medium
Where:         sdk/src/internal/http.ts:9 (`DEFAULT_FETCH_TIMEOUT_MS = 15_000`);
               sdk/src/index.ts:218-219, 307, 331-332
What:          The voice SDK's one and only budget for the first call is 15 s, and the initial
               session mint has no retry (only the *refresh* loop has backoff). The plan
               records a Render free-plan cold start of roughly a minute. The browser's 15 s
               has to cover the host backend's own cold start plus the host's call to the
               control plane, so the first visitor after an idle period gets a `timeout` /
               `session_failed` error and no retry, with nothing marking the error retryable.
               LiveKit's join timeouts are deliberately pinned to the same value
               (`peerConnectionTimeout`, `websocketTimeout`).
Impact:        After every idle window the first caller fails. It looks like a product fault,
               not a cold start.
How verified:  read code (all four call sites + the timeout helper). The cold-start duration
               itself is the plan's vendor claim and still needs plan §8 Q1 confirmed from the
               Render dashboard — the arithmetic (15 s budget vs ~60 s wake) is what I am
               recording.
Suggested fix: raise the default for the mint path specifically, or retry the mint once on
               timeout, and emit a distinct retryable error code (`backend_waking`) so hosts
               can show "starting up" instead of a failure.
Status:        open
```

### M8-F02
```
ID:            M8-F02
Module:        M8 / M9
Severity:      Medium
Where:         sdk-server/src/index.ts:260-266; telephony/src/transport.ts (no AbortController,
               no timeout anywhere in the file)
What:          Neither backend SDK sets a request timeout. Against a sleeping Render service
               the integrator's own request hangs for as long as their platform allows. The
               telephony client does at least accept an injectable `TelephonyFetch`, so an
               integrator *can* supply a timeout; the agents SDK offers no such seam.
Impact:        A cold portal turns into a hung request in the client's backend, with no SDK
               option to bound it (agents) or any documentation that you must (telephony).
How verified:  read code; grepped both files for `timeout|AbortController|signal` — the
               agents SDK has none, telephony's transport has none.
Suggested fix: add a `timeoutMs` option with a sane default to both, defaulting the agents SDK
               the same way the voice SDK already does.
Status:        open
```

### M8-F03
```
ID:            M8-F03
Module:        M8 / M9
Severity:      High (as shipped to a client to run); Medium if it stays an internal harness
Where:         client-integration-test/backend/src/createApp.js:314-326 (GET /api/agents),
               :329-348 (POST /api/agents/:agentId/pipeline), :352-372 (POST /api/voice/session),
               :54-60 (addCorsHeaders)
What:          The harness that replaced the client deliverable pack exposes the tenant's real
               credentials through unauthenticated routes:
               - `GET /api/agents` has no auth and returns `listAgents()` — every agent's name,
                 **full prompt**, provider configuration and `tools_base_url`.
               - `POST /api/agents/:agentId/pipeline` has no auth and rewrites any agent's
                 language/STT/LLM/TTS/voice through the server-held tenant secret.
               - `POST /api/voice/session` is gated only by `publishableKey`, which is by
                 definition public (it is embedded in the browser), and it can *also* apply a
                 pipeline change before minting.
               - `addCorsHeaders` reflects any `Origin` when the allowlist is empty, so all of
                 the above are reachable from any web page a tenant user visits.
Impact:        Anyone who can reach the port — or any website, via the reflected Origin — can
               read the client's prompts and silently reconfigure their agents' providers, and
               mint sessions against their quota. `TESTING.md` / `PLATFORM_TESTING.md` tell the
               operator to run this against a real tenant.
How verified:  read code (every route handler, the CORS helper and the config loader); checked
               `listAgents()`'s payload against `tenant_portal_api/queries.py:75-102` to
               confirm what it discloses (prompts yes, raw tool secret no).
Suggested fix: require a shared secret header on every `/api/*` route except `/healthz`,
               default the Origin allowlist to closed, and split the pipeline mutation out of
               the session route. Then decide (plan §8 Q8) whether this harness is a
               deliverable; if it is, it needs M9's product treatment.
Status:        open
```

---

## M1 / M2 / M4 — review items for Habiba's modules

### M2-F01 (Ehsan side)
```
ID:            M2-F01
Module:        M2 / M9
Severity:      Low
Where:         sdk/src/index.ts:762-783 (`resolveRefreshEndpoint`), :679-692 (the refresh POST)
What:          This is the plan's open M9 question — "is the refresh URL from the host response
               validated before the session token is sent to it?" Answer: **no**. The SDK takes
               `session.refreshUrl` from the host's session response and resolves it with
               `new URL(refreshUrl, sessionEndpoint)`; an absolute URL passes through
               unchanged (the code comment says so). It then POSTs to it with
               `Authorization: Bearer <LiveKit session token>` plus any `sessionHeaders` the
               host configured.
Impact:        Bounded today: the value comes from the host backend, which already holds these
               tokens, and the control plane only ever returns the relative
               `/v1/session/refresh`. It becomes real if a host ever reflects client input
               into `refreshUrl`, or proxies a third party's response — then the session token
               and any custom auth headers leave for an attacker-named origin.
               `credentials: 'same-origin'` keeps cookies from following, but headers go.
How verified:  read code (both functions, and the control plane's refresh response shape).
Suggested fix: require the resolved refresh endpoint to be same-origin with `sessionEndpoint`
               (or relative to it) and throw `AwaazLabsUvaVoiceError('session_failed', ...)`
               otherwise. Two lines, no API change.
Status:        open
```

### M2-F02 (Ehsan side)
```
ID:            M2-F02
Module:        M2
Severity:      Low
Where:         sdk/src/index.ts:174 (`listeners = new Map<Event, Set<Listener>>`), :383
What:          No cap or warning on listener registration. A `Set` dedupes identical function
               references, but a React component that passes an inline closure registers a new
               listener on every render, and nothing bounds or warns (Node's EventEmitter
               warns at 11).
Impact:        A host-side leak that looks like an SDK leak: duplicate transcript handling and
               growing memory in a long-lived page.
How verified:  read code.
Suggested fix: warn once past a threshold per event name, and document `off()` in the README's
               event section.
Status:        open
```

### M4-F01 (Ehsan side) — telephony SDK and spend
```
ID:            M4-F01
Module:        M4
Severity:      Info
Where:         telephony/src/routes.ts:3-32 (28 operations); telephony/src/transport.ts:31-40;
               tenant_portal_api/telephony_service.py:1111
What:          Reviewed all 28 frozen operations against the question "can any bypass server
               spend controls". Only two cost money: `createOutboundCall`
               (`telephony.outbound_calls.create`) and `purchaseNumber`
               (`telephony.number_orders.create`). Outbound destinations are enforced
               server-side on exactly the call path — `assert_outbound_destination_allowed`
               has one call site, inside create-outbound-call — and the SDK has no alternate
               route to it: every operation is a frozen (method, path, action) triple and
               `fillPath` refuses to leave the `/machine/` surface. Number purchase has **no**
               per-tenant cap (searched `max_numbers|MAX_NUMBERS|number_limit|
               numbers_per_tenant` across `tenant_portal_api/**` and all 42 migrations: no
               hits), but it bills the tenant's own connected Telnyx account, so it is the
               tenant's spend, not the platform's.
Impact:        No bypass found. Recording the number-purchase cap as a question for Habiba
               rather than a finding, because the money is the tenant's.
How verified:  read code (all 28 routes, the transport, `fillPath`, the enforcement call site)
               plus the grep above.
Status:        closed — no bypass found; one question forwarded to Habiba (number-order cap).
```

Also for M1: the agents SDK signs `canonicalJson(body)` but sends `JSON.stringify(body)`
(`sdk-server/src/index.ts:248` vs `:265`), so its wire bytes are not the bytes it signed.
Telephony sends `canonicalJson(body)` as the body (`transport.ts:39`), so its wire bytes *are*
the signed bytes. That asymmetry matters for the M1-F02 fix: moving the server to raw-bytes
verification is a drop-in for telephony and needs a one-line change in the agents SDK.

---

## Open questions I need answers to (plan §8)

| # | Question | Why it blocks me |
|---|---|---|
| Q1 | Which services are on Render, on which plan? | M8-F01's severity is arithmetic against the real wake time. |
| Q2 | Expected peak concurrent calls? | M3-F01 needs a target before I can set `load_threshold` and measure the machine. |
| Q3 | Which machine runs the worker; always on; who restarts it? | M6-F01/M3-F01/M7 all hinge on "the worker is a laptop". |
| Q7 | Will the repo stay private? | Decides M10-F03 (delete the provenance claims vs make the repo public) and M9-F05 (the dead README links). |
| Q8 | Does a client receive `client-integration-test/` (or anything) as a deliverable? | Decides whether M8-F03 is High or Medium, and whether M9-F01 must be restored. |
| — | Is `docs/last_session_prompt.txt`'s history worth purging? | M7-F01. |

---

## Live end-to-end verification (added after the first pass)

I ran the tenant portal locally (`uvicorn tenant_portal_api.app:app`, port 8099) against the
migrated PostgreSQL above, seeded a tenant with a known signing secret, and drove it with the
**built SDKs installed from `npm pack` tarballs** — not with test doubles. Results:

| Call (through the published SDK) | Result |
|---|---|
| `agents.listAgents()` (GET, empty body) | 200 `[]` |
| `agents.getProviderCapabilities()` (GET) | 200, advertises `gemini` models `["gemini-3.6-flash"]` |
| `agents.createAgent({prompt: "آپ ایک مددگار اسسٹنٹ ہیں۔", voiceId: "jinn"})` | **200** — created, Urdu round-trips |
| `agents.listAgents()` after create | 200, prompt returned intact |
| `agents.updateAgent(id, {greeting: "السلام علیکم"})` | **200** |
| `telephony.getConnectionStatus()` (GET) | 200 `platform_status: not_connected` |
| `telephony.listManagedPhoneNumbers({})` (POST) | 200 `[]` |
| `agents.createAgent({..., llmOptions: {epsilon: 1e-7}})` | **401 bad signature** |
| `agents.createAgent({..., llmOptions: {"Ａ":1,"😀":2}})` | **401 bad signature** |
| hand-signed `agent.create` with one unknown field (`future_field`) | **401 bad signature** |
| hand-signed `agent.create` with `greeting: null` | **401 bad signature** |
| hand-signed `agent.create`, known fields only | 200 |

So M1-F01 and M1-F02 are not theoretical: they reproduce through the published client against
a running server. The happy path (create / list / update, including Urdu) works.

### M3-F03
```
ID:            M3-F03
Module:        M3 / M9
Severity:      Medium
Where:         sdk-server/src/index.ts:199 (`llm_model: params.llmModel ?? 'gemini-2.5-flash'`);
               worker/providers/llm/gemini.py:30-39 (`_DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"`,
               `_DEPRECATED_GEMINI_MODELS` remaps `gemini-2.5-flash`)
What:          The agents SDK defaults `llmModel` to `gemini-2.5-flash`. The worker's own
               comment records that this ID "returned 404 for new keys (2026-09)" and remaps
               it at runtime. The portal accepts and stores the dead ID without validating it
               against the capability list, and `getProviderCapabilities()` advertises only
               `gemini-3.6-flash`. So the SDK's default contradicts the platform's own
               capability response, and every agent created with the default carries a dead
               model ID in the database that only works because the worker rewrites it.
Impact:        Silent dependence on a compatibility shim. Remove an entry from
               `_DEPRECATED_GEMINI_MODELS` and every agent created with the SDK default stops
               working. Integrators reading `getProviderCapabilities()` and the SDK default
               see two different answers.
How verified:  ran. Created two agents through the SDK and queried the database:
                 audit-happy | gemini | gemini-2.5-flash
                 probe-known | gemini | gemini-2.5-flash
               while the same server's capabilities response listed only `gemini-3.6-flash`.
Suggested fix: drop the SDK-side default (let the server choose) or set it to the current
               model, and have the portal reject an `llm_model` that is not in the capability
               list rather than storing it.
Status:        open
```

### M3-F04
```
ID:            M3-F04
Module:        M3
Severity:      Low
Where:         worker/providers/stt/soniox.py, worker/providers/tts/fish_audio.py (+
               fish_audio_options.py); worker/providers/registry.py:32-83; worker/factories.py
What:          Answering the plan's "legacy paths: reachable or dead?" — both are dead.
               `registry._build_stt` knows only gladia and deepgram; `_build_tts` knows only
               uplift, cartesia, elevenlabs and rime. Neither `soniox` nor `fishaudio` appears
               in the registry, in `worker/main.py` or in
               `tenant_portal_api/provider_validation.py`. The Soniox adapter is reachable only
               through the legacy `worker/factories.py`, which nothing in the runtime imports —
               its only importers are `scripts/probe_soniox_402.py` and two test modules (one
               of which, `tests/test_tts.py`, is in `collect_ignore`).
Impact:        Dead code that still looks live, and an unsupported provider value would raise
               `UnsupportedProviderError` mid-session rather than being rejected at save time.
How verified:  read code + grep for `soniox` / `fishaudio|fish_audio` across worker/, scripts/
               and tenant_portal_api/ (hits only in the adapter files, factories.py and the
               probe script).
Suggested fix: delete the two adapters (git history keeps them) or wire them into the registry
               behind their `rollout_state`. Keep `factories.py` only if the probe script is
               still wanted.
Status:        open
```

### M6-F05
```
ID:            M6-F05
Module:        M6
Severity:      Medium
Where:         worker/write_tool_gate.py:29-35 (`_AFFIRM_RE`), :299-309 (`note_user_turn`),
               :411 (the `heard_affirmative` gate); worker/humanization/understanding.py:20
               (`CORRECTION`)
What:          The last gate before a destructive write (book / reschedule / cancel) accepts a
               contracted refusal as consent. `CORRECTION` invalidates a pending proposal on
               `\bnot\b`, which matches "do not" but **not** "don't" or "dont" (the token after
               the apostrophe is "t"). `_AFFIRM_RE` meanwhile matches "book it" / "do it"
               inside the refusal, so `heard_affirmative` is set and the confirm POST fires.
Impact:        A caller who says "don't book it" gets the appointment booked.
How verified:  ran. Drove the real gate (a pending proposal, then `note_user_turn`) and read
               the resulting state:
                 WOULD CONFIRM     "don't book it"
                 WOULD CONFIRM     'dont book it'
                 WOULD CONFIRM     "please don't book it"
                 WOULD CONFIRM     "don't do it"
                 WOULD CONFIRM     "never mind, don't book it"
                 WOULD CONFIRM     "hold on, don't book it yet"
                 invalidated       'do not book it'
               and, to be fair to the design, the invalidation path does catch 9 of the 10
               other refusals I tried ("no", "no, cancel it", "no thanks, I want to reschedule
               instead", "not okay", "that's not ok", "I'd rather not", "nahi karo", …), while
               "skip it" / "forget it" / "wait" / "hmm" are correctly *held* rather than
               confirmed. The residual gap is specifically the apostrophe contraction.
               `tests/test_injection_write_gate.py` (5 tests) and `tests/test_write_tool_gate.py`
               pass (44 passed, 1 skipped) and contain no case of this shape.
Suggested fix: add `don'?t|dont|doesn'?t|won'?t|can'?t|never` to `CORRECTION`, and make
               `is_affirmative_utterance` return False when a negation token precedes the
               affirmation in the same utterance. Add the six phrases above as test cases.
Status:        open
```

---

## Still to do

- M3: measure the real concurrency ceiling on the worker machine with live providers, and
  laptop-sleep / Wi-Fi-drop / SIGTERM behaviour (needs the machine and Q2/Q3).
- M3: per-vendor failure behaviour (timeout / 429 / mid-call disconnect) and what the caller
  hears — needs live provider keys.
- M9: run the voice README quickstart in a browser end to end (the agents and telephony
  quickstarts are now verified above against a live portal).
- M12: the smallest useful concurrency and failure tests once M3's measurements exist.
