# Handoff to Habiba — Ehsan → backend services & database

**Filled by:** Ehsan, 2026-10-11, after the first audit pass over the Ehsan half of
`AUDIT_SPLIT_PLAN_v3.pdf` (FINAL, 2026-10-07).
**Mirrors:** `audit-context/HANDOFF_TO_EHSAN.md`.
**Rule (same as yours):** I never wait on these. You own verification and fixes in your trees.
Full detail for every ID below is in `FINDINGS_EHSAN.md`.

---

## Status

| Field | Value |
|---|---|
| Commit audited | `7a3c382` (origin/main == origin/staging == finova/main) |
| Code changed by this pass | **none** — audit first, per plan §9 working rule 1 |
| Findings filed | 32 (1 Critical, 6 High, 15 Medium, 8 Low, 1 Info) |
| Open Critical on Ehsan side | 1 — M10-F01 (CI gate), mine to fix |
| Items needing *your* tree | 4 (M1-F02, M12-F01a, M4 question, M6-F03 suggestion) |

---

## Contracts (plan §5) — my side of your table

Nothing in this pass touched shared code. `git diff --stat HEAD` is empty; the only new files
are `FINDINGS_EHSAN.md` and this handoff. Concretely:

| # | Contract | State after my pass |
|---|---|---|
| 1 | HMAC mint + machine shapes / `used_nonces` | **Unchanged.** Verified both signers against your server live — see below. |
| 2 | `worker.providers` public interface | **Unchanged.** `registry.build_components` / `_build_stt|llm|tts` untouched. |
| 3 | `sanitize_transcript_turns` | **Unchanged.** Not edited, not renamed. |
| 4 | `is_hosted` / `decrypt_tool_secret` / `is_mock_provider_mode` | **Unchanged by me**, but see M6-F01/M6-F03: `is_hosted()` returning False on the local worker is the single biggest finding on my side. |
| 5 | Quota lifecycle | Clean-path worker release verified (below). Unchanged. |
| 6 | Tools URL/secret | Your save-time rules are correct; the worker's request-time guard is the gap (M6-F01). Unchanged. |
| 7 | Recordings | Unchanged. One inconsistency in the worker's hosted check (M6-F03). |
| 8 | Dashboard read-only | **UI side is closed** — see M11 below. Unchanged. |

---

## Things that need a decision or a change in YOUR tree

### 1. M1-F02 — the machine API verifies a Pydantic re-serialisation, not the request bytes

`tenant_portal_api/app.py:1155` and `:1253` pass `body=body.model_dump(exclude_none=True)` to
`verify_machine_request`, and `CreateAgentBody`/`UpdateAgentBody` (`app.py:175`, `:203`) have no
`model_config`, so Pydantic's default `extra='ignore'` drops unknown fields **before** the hash
is computed. Proven against a live portal with hand-signed requests:

```
known fields only                        -> 200
same body + one unknown `future_field`   -> 401 {"detail":"bad signature"}
same body + `greeting: null`             -> 401 {"detail":"bad signature"}
```

Why it matters to you: a newer SDK against an older portal reports `bad signature` for every
call — the most misleading error in the set. The comment you already have at `app.py:1148-1154`
documents an earlier instance of exactly this class of break.

What I suggest: hash the **raw request body bytes** server-side. The telephony SDK already
sends exactly the bytes it signed (`telephony/src/transport.ts:39` sends `canonicalJson(body)`),
so for telephony that is a drop-in. The agents SDK signs `canonicalJson(body)` but sends
`JSON.stringify(body)` (`sdk-server/src/index.ts:248` vs `:265`) — that is a one-line change on
my side and I will make it whenever you want to move. Doing this also makes M1-F01 (below)
disappear instead of needing a client-side fix.

**Needs both of us** (plan §5 item 1). Tell me if you want it and I'll land the SDK side in the
same window.

### 2. M12-F01(a) — 15 portal test failures nobody's CI shows

With a database configured, the full suite is red in your tree. One root cause, 15 failures:
`POST /portal/login` returns

```
403 {"detail":"CSRF check failed: send Origin/Referer matching TENANT_PORTAL_ORIGINS, or header X-UVA-Portal: 1"}
```

after which every dependent test raises `KeyError: 'token'`. Files:
`tests/test_phase4_portal_api.py` (9), `tests/test_portal_wave2_credentials.py` (5),
`tests/test_portal_members_invite.py` (1). Offline there are also 6 collection errors in
`tests/test_portal_supabase_auth.py`.

Either the new CSRF middleware (`tenant_portal_api/csrf.py`) needs those tests to send the
header, or the tests need updating — your call which is correct. The reason you have not seen
it is on my side of the fence (M10-F01/F02, below): the `pytest-integration` job `exit 0`s when
`SUPABASE_DB_URL` is absent, so the DB half of the suite has never gated.

Repro: local PostgreSQL, all 42 migrations applied, then `python -m pytest`. Result on
`7a3c382`: **1310 passed, 18 failed, 19 skipped**. I can hand you the exact local DB setup
(initdb flags + the Supabase `auth.jwt()`/`auth.uid()` + role shims) if you want it — it took
about ten minutes and all 42 migrations applied clean from empty, including 0034–0039.

### 3. M4 question — no per-tenant cap on number purchases

I reviewed all 28 frozen telephony SDK operations for spend bypass and found **none**:
`assert_outbound_destination_allowed` has exactly one call site
(`telephony_service.py:1111`, inside create-outbound-call), every SDK operation is a frozen
(method, path, action) triple, and `fillPath` refuses to leave the `/machine/` surface.

The one thing I could not find is a cap on `purchaseNumber` → `/machine/telephony/number-orders`.
Searched `max_numbers|MAX_NUMBERS|number_limit|numbers_per_tenant` across `tenant_portal_api/**`
and all 42 migrations: no hits. I am **not** filing it as a finding, because purchases bill the
tenant's own connected Telnyx account, not the platform. Confirm that reading and I will close
it; if any number is ever bought on a platform account, it becomes a real spend finding.

### 4. M6-F03 suggestion — one hosted check, not three

`worker/recording_policy.py:33-42` has its own `is_hosted_render()` that reads `RENDER` only,
while `control_plane/runtime_env.is_hosted()` reads `UVA_ENV`/`RENDER`/`ENVIRONMENT`. A worker
deployed anywhere other than Render is "not hosted" for recording purposes, so the env-only
force-on (`UVA_SESSION_RECORD_AUDIO=1`) stays available in a real deployment — a consent and
retention problem, not just hygiene.

The file is mine and I will fix it by calling your `runtime_env.is_hosted()` (the worker already
imports from that module in `ssrf_guard.py`, so no new coupling). Flagging it because it changes
behaviour you own the policy for: after the fix, a hosted worker can no longer be forced to
record by environment variable alone.

---

## What I verified about your side (no action needed — recorded so you can stop re-checking)

- **Mint-path signature compare is constant-time.** The plan recorded this as unverified:
  `control_plane/mint.py:111` and the rotation retry at `:126` both use `hmac.compare_digest`,
  as does `tenant_portal_api/machine_auth.py:160`.
- **Empty-body GET hashing agrees across all three implementations.** The SDKs sign `{}` and
  your GET routes pass `body={}` (`app.py:1211`, `:1231`). All hash `"{}"`.
- **Urdu round-trips through the machine API.** `ensure_ascii=False` in
  `machine_auth.payload_hash` matches `JSON.stringify` on both clients — verified by
  differential *and* live: `createAgent` with an Urdu prompt and `updateAgent` with an Urdu
  greeting both returned 200, and the prompt came back byte-intact from `listAgents`.
- **The raw tool-gateway secret never leaves over the API.** `queries.py:37-61` maps it to
  `tools_auth_secret_configured: boolean`; only `_agent_row_internal` (`:64-72`, worker path)
  decrypts it. The unauthenticated demo route in M8-F03 therefore leaks prompts, not secrets.
- **Your save-time tools URL validation is correct**, including the DNS-resolution check, and
  its docstring correctly identifies the worker as the owner of the rebinding gap. The gap is
  real and it is mine (M6-F01).
- **Outbound destination enforcement cannot be bypassed from the SDK** (M4-F01, closed).
- **`reconcile.yml` now applies by default on schedule** and the code matches the comment —
  I re-read it; my earlier note that it was dry-run-by-default was out of date.
- **All 42 migrations apply clean from empty** on PostgreSQL 18.4 with only
  `auth.jwt()`/`auth.uid()` and the three roles shimmed, re-apply as no-ops, and the checksum
  drift refusal works.
- **Dashboard read-only, UI side: closed, and wider than the decision required.** There is no
  create-agent path *and* no edit or delete path: `createAgent`, `updateAgent` and `deleteAgent`
  exist in `dashboard/src/lib/portalApi.ts:214/230/248` with **zero callers** anywhere in
  `dashboard/src/**` (the only other hits are inside documentation code samples). So whichever
  way the product decision lands on edits/reveal/telephony/Test Studio, the dashboard is not
  the thing exercising it today. Your server still allows PATCH/DELETE, which is consistent
  with "undecided". I filed M11-F01 (Low) to delete the three dead helpers so a future `onClick`
  cannot re-open it without a server change.

---

## Things on my side you should know about, because they change what "green" means

- **M10-F01 (Critical): CI cannot fail a Python test.** `tests/conftest.py:191-197` converts any
  failure into a skip when no credential env vars are set — exactly how the `pytest-unit` job
  runs. A test containing `assert 1 == 2` reports "1 skipped", exit 0. This is my own F-H1
  follow-up code and mine to fix. Until it is fixed, treat "CI green" on any Python change as
  "no information".
- **M10-F02 (High): CI runs 43 of 139 test files** (`tests/ci_unit_manifest.txt`), and the
  integration job passes when the DB secret is missing. That is why item 2 above is invisible.
- **M6-F01 (High): the worker's SSRF guard is inert on the machine that runs it.** Verified with
  live DNS (`localtest.me` → 127.0.0.1): your hosted portal rejects it at save time, a hosted
  worker blocks it, the local worker allows it. Mine to fix; the fix will make the worker apply
  hosted rules unless a developer explicitly opts out.
- **M3-F01 (High): the production worker runs in LiveKit dev mode** (`scripts/dev_worker.py`
  runs `worker.main dev`), so `load_threshold` is `math.inf` — no load shedding at all, plus no
  per-job memory cap. Relevant to your M2-F01 capacity question: there is currently no
  admission control to plan against.
- **M3-F03 (Medium): the agents SDK's default `llmModel` is `gemini-2.5-flash`**, which
  `worker/providers/llm/gemini.py:30-39` says 404s and silently remaps. Both agents I created
  through the SDK stored that dead ID while your `getProviderCapabilities()` advertised only
  `gemini-3.6-flash`. Fix is mine (SDK default), but you may want the portal to reject an
  `llm_model` that is not in the capability list rather than storing it.
- **M9-F01 (High): `client-deliverables-final/` is gone** — all 14 files, deleted in `a351576`
  ("prior deletions as explicitly requested through `git add .`"). Nine live documents still
  point at it, including `docs/CLIENT_QUICKSTART.md`, `docs/CLIENT_HANDOFF_GUIDE.md` and the
  published `sdk/README.md`, and `tests/test_wave5_residuals.py:162` *asserts* that the client
  docs reference it. If that deletion was intentional, say so and I will retire the references;
  if not, I will restore it from `a351576^`.
- **M8-F03 (High if a client runs it): `client-integration-test/` has unauthenticated routes**
  that read and mutate real tenant data — `GET /api/agents` (every agent's full prompt, no
  auth) and `POST /api/agents/:agentId/pipeline` (rewrites any agent's providers using the
  server-held tenant secret, no auth), with CORS reflecting any `Origin` when the allowlist is
  empty. Mine to fix. Flagging it to you because `TESTING.md` tells an operator to run it
  against a real tenant.

---

## Open questions I need a human answer to (plan §8)

| # | Question | Blocks |
|---|---|---|
| Q1 | Which services run on Render, on which plan? | M8-F01 — the voice SDK's 15 s budget vs the real wake time |
| Q2 | Expected peak concurrent calls (per tenant / overall)? | M3-F01 — I cannot pick a `load_threshold` or a load-test target without a number |
| Q3 | Which machine runs the worker; always on; who restarts it? | M6-F01, M3-F01, M7 all assume "a laptop" |
| Q4 | Is the nonce purge actually scheduled in production? | yours; `reconcile.yml` calls it every 15 min and now applies by default — confirm the schedule is live on the repo that holds the default branch |
| Q7 | Will the repo stay private? | M10-F03 (delete the provenance claims vs make the repo public) and M9-F05 (every GitHub link in the published npm READMEs 404s anonymously — `curl` confirmed) |
| Q8 | Does any client receive `client-integration-test/` or the deleted pack? | M8-F03's severity, and whether M9-F01 must be restored |

---

## What I have running, if you want to reuse it

A local PostgreSQL 18.4 (SSL on, port 55432) with all 42 migrations applied and the Supabase
objects shimmed, plus the tenant portal on `127.0.0.1:8099` driven by the SDKs installed from
`npm pack` tarballs. That setup is what produced the live evidence above, and it is how I would
suggest running the DB half of the suite in CI (a service-container Postgres) so item 2 stops
being invisible. Ask and I will write the setup down as a script.
