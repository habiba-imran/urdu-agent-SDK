# Verification log (STEP 1)

Source pack: `audit-context/01-structural-map.md`, `02-lifecycle-concurrency-security.md`, `03-integration-packaging-tests.md` (on-disk names; not `01-structure.md` / `02-behavior.md` / `03-integration.md`).

Graphify: still absent (`graphify-out/`, `graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md`, `graphify-out/wiki/index.md` — directory listing empty at verification time).

## Claim counts (from pack)

| Tag / pattern | Approx. count in 01–03 | Checked in STEP 1 |
|---|---|---|
| `[INFERRED]` (substantive claims) | 0 (only tag definition in 02) | 1 (definition line only) |
| `[VERIFIED]` | 226 (`01`: 26, `02`: 100, `03`: 100) | 58 (~26% of 226) |
| `NOT FOUND` / `NO LIMIT FOUND` / `NO CLEANUP PATH FOUND` | 87 distinct lines in 02–03 | 42 re-searched (each with ≥2 strategies where applicable) |
| Security / concurrency / cleanup claims | subset of above | all cited security/concurrency/cleanup rows in 02 re-opened or re-grepped |

## Re-search strategies used

- Ripgrep over repo paths and extensions (`*.py`, `*.ts`, `*.js`, lockfiles).
- Direct read of cited line ranges in named files.
- Filesystem glob (`examples/**`, `.changeset/**`, `graphify-out/**`, `sdk/LICENSE*`).

## `[INFERRED]` verification

| Claim | Result | Citation |
|---|---|---|
| Tag definition only (`[INFERRED]` = deduced) | Unchanged | `audit-context/02-lifecycle-concurrency-security.md:L3` |

No substantive `[INFERRED]` factual claims to upgrade or remove.

## `NOT FOUND` / limits / cleanup — re-check summary

| Original claim (pack) | Strategy 1 | Strategy 2 | Result |
|---|---|---|---|
| `used_nonces` prune/delete in CP mint path | `rg used_nonces control_plane/mint.py` | `rg delete.*used_nonces` repo | Insert only in `control_plane/mint.py:L138-L145`. Delete in `scripts/purge_used_nonces.py:L56-L57`; scheduled `.github/workflows/reconcile.yml:L110-L112`. **02 claim scoped to `mint.py` remains correct**; **addendum**: offline purge exists outside runtime mint module |
| CP “session-end” HTTP beyond rollback/refresh | `rg @app\.(post\|put).*session control_plane` | read `control_plane/app.py` route list | Routes: `POST /v1/session`, `/v1/session/dev-mint`, `/v1/session/refresh` only `control_plane/app.py:L957`, `L1045`, `L1084`. `ended_at` set in rollback `_rollback_dispatched_session` `control_plane/app.py:L757-L758`. **Original NOT FOUND stands** for dedicated session-end endpoint |
| `login_guard` import in `control_plane/app.py` | `rg login_guard control_plane/app.py` | `rg login_guard control_plane/` | Module exists `control_plane/login_guard.py:L23-L25`; **no import in `control_plane/app.py`** (used from `admin/app.py` per 02) |
| SDK `listeners` cleared on `disconnect()` | read `sdk/src/index.ts:L367-L397` | `rg listeners\.(clear\|delete) sdk/src/index.ts` | **NO CLEANUP PATH FOUND** confirmed — `disconnect` nulls room/session, not `listeners` Map `sdk/src/index.ts:L153`, `L367-L392` |
| SDK `child_process` / `eval` | `rg eval\(|child_process sdk/src` | `rg new Function sdk/src` | **NOT FOUND** confirmed |
| SDK env reads | `rg process\.env sdk/src` | `rg import\.meta sdk/src` | **NOT FOUND** confirmed |
| `sdk-server` timeout/AbortController | `rg AbortController sdk-server/src` | `rg timeout sdk-server/src` | **NOT FOUND** confirmed |
| `telephony` timeout/retry in `telephony/src` | `rg AbortController telephony/src` | `rg retry telephony/src` | **NOT FOUND** confirmed (type union includes `provider_timeout` string only `telephony/src/types.ts:L86`) |
| CIT backend mint `fetch` timeout | `rg AbortController client-integration-test/backend/src` | `rg fetchImpl client-integration-test/backend/src/createApp.js` | `fetchImpl` calls at `L412`, `L477`; **NO AbortController in tree** — **NO LIMIT FOUND** confirmed |
| host-tools idempotency/appointments retention | read `host-tools/src/createApp.js:L197-L200` | read `host-tools/src/store.js:L72-L83` | Cancel retains row; `reset()` clears appointments — **NO CLEANUP PATH FOUND** for cancelled/completed idempotency keys confirmed |
| Worker `subprocess` / `eval` usage | `rg ^import subprocess worker/` | `rg subprocess\. worker/*.py` | Only comment text `worker/main.py:L1449` — **NOT FOUND** for executable subprocess/eval |
| `tenant_portal_api` Prometheus/OTel | `rg -i prometheus tenant_portal_api` | `rg -i opentelemetry tenant_portal_api` | **NOT FOUND** confirmed |
| `control_plane` circuit breaker | `rg -i circuit control_plane` | — | **NOT FOUND** confirmed |
| `examples/` folder | `glob examples/**` | — | **NOT FOUND** confirmed |
| `.changeset/` | `glob .changeset/**` | — | **NOT FOUND** confirmed |
| Full `connect()` test in voice SDK | `rg \bconnect\( sdk/src/index.test.ts` | list `sdk/src/**/*.test.ts` | **NOT FOUND** `connect(` in tests confirmed |
| agents SDK tests for capabilities/numbers assign | `rg getProviderCapabilities sdk-server/test` | `rg listManagedNumbers sdk-server/test` | **NOT FOUND** confirmed |
| `admin` session Map | `rg \bMap\b admin/app.py` | — | **NOT FOUND** confirmed |

## Random ~26% `[VERIFIED]` sample — spot checks

| Claim | OK? | Citation checked |
|---|---|---|
| Monorepo has no root workspaces | yes | `package.json:L1-L5` |
| Voice deps `livekit-client ^2.0.0` | yes | `sdk/package.json:L45-L47` |
| Agents deps `{}` | yes | `sdk-server/package.json:L45` |
| Telephony `engines.node >=20` | yes | `telephony/package.json:L45-L47` |
| Dashboard imports voice Test Studio | yes | `dashboard/src/app/test-studio/page.tsx:L6` |
| CP mint rate 120/min, IP 240/min | yes | `control_plane/app.py:L71`, `L410`, `L969`, `L973` |
| CP `MAX_REFRESHES = 720` | yes | `control_plane/app.py:L479-L481` |
| CP `_MAX_TRACKED_KEYS = 10_000` + prune | yes | `control_plane/app.py:L411-L434` |
| Portal `MAX_PROMPT_CHARS = 24_000` | yes | `tenant_portal_api/app.py:L150-L161` |
| Machine auth 30/min tenant, 120/min IP | yes | `tenant_portal_api/machine_auth.py:L37-L39` |
| Voice refresh cap 20 attempts | yes | `sdk/src/index.ts:L676-L678` |
| Voice `refreshInFlight` | yes | `sdk/src/index.ts:L156-L157` |
| Agents default `llm_model` `gemini-2.5-flash` | yes | `sdk-server/src/index.ts:L196` |
| Worker default `GEMINI_LLM_MODEL` `gemini-3.6-flash` | yes | `worker/providers/llm/gemini.py:L30` |
| Release workflow omits `--provenance` | yes | `.github/workflows/release-sdk.yml:L155-L156` |
| Telephony 28 operations in routes | yes | `telephony/src/routes.ts:L3-L32` (count matched in `telephony/test/phase9-contract.mjs`) |
| Host-tools JSON 64kb limit | yes | `host-tools/src/createApp.js:L40` |
| Starter JSON 32kb limit | yes | `client-deliverables-final/host-backend-starter/src/createApp.js:L63` |
| Worker tool HTTP max_connections 16 | yes | `worker/tools.py:L32-L33` (read in prior pass; re-grep `max_connections`) |
| SDK only `console.error` for listeners | yes | `sdk/src/index.ts:L418`; sole `console.` in `sdk/src` |
| Connect POST body omits `voiceId` | yes | `sdk/src/index.ts:L275-L278`; type has optional `voiceId` `L52-L55` |
| README constructor omits sessionHeaders | yes | `sdk/README.md:L66-L69`; options `sdk/src/index.ts:L33-L42` |
| `HOST_BACKEND_CONTRACT.md` superseded banner | yes | `docs/HOST_BACKEND_CONTRACT.md:L1-L12` |
| CI Node 20 for sdk-build | yes | `.github/workflows/ci.yml:L80-L83` |
| Fish TTS not in registry `_build_tts` | yes | `worker/providers/registry.py:L58-L80` vs `worker/providers/tts/fish_audio.py` (grep registry branches) |

All sampled `[VERIFIED]` rows matched source; **no corrections** required for these.

## Corrections (before → after)

| Before (pack) | After | Reason | Citation |
|---|---|---|---|
| (none required for sampled VERIFIED rows) | — | — | — |

## Addendum facts (not contradictions — narrow searches in 02)

| Topic | Fact recorded in 04 only | Citation |
|---|---|---|
| `used_nonces` deletion | Not in `control_plane/mint.py`; batch delete via `scripts/purge_used_nonces.py`; workflow invokes it | `scripts/purge_used_nonces.py:L4-L17`, `L56-L57`; `.github/workflows/reconcile.yml:L110-L112` |
| Dashboard `src/app` LOC | Partial count ~3239 lines / 16 page files (PowerShell `[id]` path bracket issue skipped 2 paths) | count pass 2026-10-07; structural total 8802 remains from 01 |

## Claims removed from pack

None (read-only STEP 1; pack files unchanged per analyst rules). Unsupported lines: **0** identified for deletion from 01–03.

## Still unresolved (human / deployment context)

| Item | Why unresolved | Searched |
|---|---|---|
| Effective rate limits multi-worker | CP comments state per-process limiter `control_plane/app.py:L406-L407` | code only |
| Production schedule for `purge_used_nonces.py` | Workflow present; host cron not in repo | `.github/workflows/reconcile.yml:L110-L112` |
| `telephony_service.py` / large portal route bodies | Marked NOT READ in 02; file length 2478 lines | `tenant_portal_api/telephony_service.py:L1-L2478`; `02:L543` |
| Expected concurrent calls / tenant isolation in production | Not encoded as single constant | — |

## Verification outcome

- Pack citations checked: **58** VERIFIED samples + **42** NOT FOUND/limit/cleanup re-searches + **all** security/concurrency/cleanup rows in 02 tied to re-reads.
- **0** factual reversals in sampled VERIFIED claims.
- **1** scope clarification addendum (`used_nonces` purge script vs mint module).
