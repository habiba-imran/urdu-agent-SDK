# UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md

Phased implementation plan for making the agent-facing STT/LLM/TTS pipeline provider- and
language-dynamic, without disturbing the working Urdu path (`ur + gladia + gemini + uplift`).

**Source-of-truth order for this plan:** `docs/.clauderules` (final authority on process/workflow/
code-quality rules) → `docs/UKASHA_MULTIPLE_PROVIDERS_GUIDE.md` (authoritative technical target,
audited below) → this file (the sequencing, gates, and human tasks that turn that guide into
executable work). Where `.clauderules` and this repo's pre-existing `CLAUDE.md` don't conflict,
`CLAUDE.md`'s existing project-specific mechanics (`make gate`, ADR log, `state/PROGRESS.md`) are
still used as the concrete implementation of `.clauderules`' Steps 2/4/5 — `.clauderules` doesn't
forbid any of that, it's a generic overlay, not a replacement for this project's own gate.

**No phase begins until the previous phase has: (a) all its tests/verifications green, (b) my own
audit sign-off recorded in this file, and (c) explicit human approval.** This is not a formality —
per `.clauderules`' own "wait for my approval on the plan before proceeding" and this repo's
existing culture of phase gates.

---

## 0. Audit of the two input documents — findings and fixes

Audited against the actual current code (`worker/factories.py`, `worker/config.py`,
`worker/main.py`, `tenant_portal_api/app.py`+`queries.py`, `sdk-server/src/index.ts`,
`client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts`, `dashboard/src/lib/portalApi.ts`,
`requirements.txt`, `supabase/migrations/*`, `docs/TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md`),
not taken on faith. Everything the guide claimed about current code was independently re-verified
and found accurate (STT/LLM/TTS hardcoding claims, field names, file list) — the findings below are
**gaps the guide left implicit**, not errors in it.

| # | Finding | Fix applied in this plan |
|---|---|---|
| 1 | `docs/.clauderules` contains a `## Python / DuckDB (AI-Lead-Scraper)` section — boilerplate from an unrelated project, not this codebase. | Ignored. This plan follows this repo's actual existing Python conventions (snake_case files, existing docstring/comment style in `worker/`, `tenant_portal_api/`) instead. Flagging so it isn't silently treated as a real rule for this repo. |
| 2 | `.clauderules` says "Do NOT add tests unless I ask." Conflicts on its face with "every phase needs test + manual/code verification." | No real conflict: the human's instruction for *this task* explicitly asks for tests every phase. `.clauderules`' own condition ("unless I ask") is satisfied. |
| 3 | `requirements.txt` pins **only** `livekit-plugins-{gladia,google,silero,upliftai}`. `worker/factories.py::make_stt()` and `worker/main.py::prewarm()` already branch on `soniox`/`deepgram`, but those packages are **not installed**. | Pre-existing latent bug, not introduced here — flagged, not silently fixed outside scope. If `STT_PROVIDER=deepgram` is set today, `prewarm()` raises `ImportError`, not a clean error. Phase 2 must not paper over this; Phase 6 (Deepgram) is where it actually gets a real package pin + test. |
| 4 | Guide names ElevenLabs, Fish Audio, Cartesia, Rime (TTS) and Groq (LLM) as target providers. **None of their `livekit-plugins-*` package names/APIs have been verified against real docs in this session.** | Per `.clauderules`' anti-hallucination rule and this repo's own "verify, don't assume": each new-provider subphase (Phase 6+) starts with an explicit **verification step** (real package name, real constructor signature, checked against LiveKit's plugin docs/PyPI) before any adapter code is written — not assumed from the guide's prose. |
| 5 | `sdk-server/src/index.ts` and `client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts` are independent, **byte-for-byte hand-duplicated** files (confirmed identical field handling). Nothing enforces they stay in sync. | Phase 3 adds a parity test (diff or shared-fixture-based) so this pair can't silently drift — this exact class of bug (cross-language mismatch) already bit this project once, in the machine-agent HMAC canonicalization (Session 13, `PROGRESS.md`). |
| 6 | `agents_voice_enabled_check` trigger (`0006_agents_voice_enabled_check.sql`) fires on `voice_id` insert/update and checks `voices.enabled`. Any new sync between `voice_id` and `tts_voice_id` must not bypass it. | Phase 1 keeps writes going through `voice_id` (trigger stays authoritative); `tts_voice_id` is synchronized to it, not the other way around, so the trigger cannot be silently routed around. Explicit test added. |
| 7 | Migration numbers: current highest applied is `0011_session_transcript.sql`. `0012`–`0015` are reserved by Habiba for telephony (confirmed against `docs/TELEPHONY_WORKLOAD_AND_RESPONSIBILITY_DIVISION.md` and the live `supabase/migrations/` directory). | This plan's migrations start at **`0016`**. Phase 0 re-checks the migrations directory immediately before Phase 1 starts, in case anything landed from `habiba`/`hamza`/`staging` in the meantime — do not assume `0016` is still free without re-checking. |
| 8 | `worker/config.py::AgentConfig` and `worker/config.py::load_agent_config` are **explicitly named** in `docs/TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md` as the seam telephony's inbound call path also depends on. | Phase 2's refactor treats `AgentConfig`'s existing fields, `load_agent_config()`, `build_session()`, `build_agent()`, and `entrypoint()`'s external signatures as a **frozen contract** — additive fields only, nothing renamed or removed, so telephony's parallel work isn't broken regardless of merge order. Restated explicitly in Phase 2's acceptance criteria. |
| 9 | `worker/factories.py` (`make_stt`/`make_llm`/`make_tts`) has **no existing direct unit test** — `tests/test_worker.py` tests `AgentConfig`/tools/usage, not the factories themselves. | Phase 2 adds the adapter-level tests the guide's "Essential Tests" section calls for, since there's no pre-existing safety net to lean on for this refactor. |
| 10 | The guide's `GET /api/provider-capabilities` doesn't specify auth or route prefix. Every other tenant-facing endpoint in this repo is either `/portal/*` (tenant JWT) or `/machine/*` (tenant HMAC) — a bare public `/api/*` route would be new and unauthenticated. | This plan exposes it as `/portal/provider-capabilities` + `/machine/provider-capabilities`, matching the existing dual-route pattern used for `agents`. **Flagged for explicit human confirmation in Phase 0** — this is a deviation from the guide's literal text, not silently substituted. |
| 11 | Scope mismatch: this guide's "Release Provider Rules" section scopes the *current* release to **`ur` and `en` only**. Earlier discussion (this conversation) named English, Spanish, Hindi as target languages. | **Partially resolved 2026-08-01:** confirmed `en`-only for this plan (Phase 0 answer); `es`/`hi`/etc. stay deferred to Phase 7. Also confirmed (2026-08-01): for `en` itself, ALL of the guide's listed providers are required, not an initial subset — Gladia+Deepgram (STT), Gemini+Groq (LLM), ElevenLabs+Fish Audio+Cartesia+Rime (TTS), 6 new provider integrations total. Phase 6 rewritten accordingly (was: "pick one TTS vendor first"). |

---

## 1. Ground-truth snapshot (verified, with file references)

- `worker/main.py::build_session()` calls `make_stt()`, `make_llm(cfg.llm_model)`, `make_tts(cfg.voice_id)` — `make_stt()` takes **zero** arguments today.
- `worker/config.py::AgentConfig` is a frozen dataclass with exactly `agent_id, tenant_id, name, prompt, voice_id, llm_model`, populated by one positional `SELECT id, tenant_id, name, prompt, voice_id, llm_model FROM agents WHERE id = %s`.
- `tenant_portal_api/app.py`'s `CreateAgentBody`/`UpdateAgentBody` Pydantic models are shared verbatim between `/portal/agents` (tenant JWT) and `/machine/agents` (tenant HMAC) — one schema change covers both surfaces.
- `voices` table (`0005_voices_catalogue.sql`) currently has 82 rows, all Uplift, all `ur`, no `provider`/`language` columns yet.
- `agents` table has no `agent_language`/provider columns yet (confirmed against `supabase/SCHEMA.md`).
- Both TS SDK packages use camelCase (`voiceId`, `llmModel`); DB/Python API stay snake_case (`voice_id`, `llm_model`) — established convention, not something this plan introduces.

---

## 2. Cross-team boundary (telephony — Hamza/Habiba)

Per `docs/TELEPHONY_WORKLOAD_AND_RESPONSIBILITY_DIVISION.md` §2: *"provider/language selection
remains Ukasha's responsibility; telephony owns number provisioning, SIP routing, call
orchestration, and telephony statuses"* and *"[Hamza] ensures `worker/main.py` changes stay
minimal and do not fork the STT/LLM/TTS pipeline."*

Concrete obligations this plan takes on:
- Migration numbers `0012`–`0015` are never touched by this plan (see finding #7).
- `worker/config.py`/`worker/main.py`'s external call shape stays stable per finding #8 — whatever
  telephony's inbound resolver calls to get a session pipeline built, it must still work unchanged
  after Phases 1–2 land, regardless of merge order.
- Before Phase 2 is marked complete, and again before Phase 5, confirm with Hamza that the
  provider-registry seam (`provider_registry.build_components(cfg)`) still matches what his
  inbound/outbound call routing expects to call — a human coordination checkpoint, not something
  this plan can verify unilaterally.

---

## 3. Phases

Every phase ends with: `make gate` green, the phase's own listed tests green, a manual verification
step where noted, my written audit note in this file confirming what was actually checked (not just
claimed), and explicit human sign-off before the next phase starts.

### Phase 0 — Preflight & contracts (no code)

1. Re-run `make gate` on current `ukasha` HEAD as a clean baseline — record the result before
   anything changes, so later phases have something real to diff against.
2. Re-check `supabase/migrations/` for anything added since this audit, before assuming `0016` is
   free.
3. **Human decision needed** — confirm:
   - Language scope for this plan: `en` only for now (per the guide), or include `es`/`hi`/etc. now?
   - Capabilities API route: `/portal/provider-capabilities` + `/machine/provider-capabilities`
     (this plan's proposal) vs. the guide's literal `/api/provider-capabilities`?
   - Confirm DB write access in this environment (apply migrations directly, or hand off to
     Habiba/a human the way telephony's Supabase work is scoped)?
4. Write a short ADR entry in `docs/40-ADR.md` recording the provider-abstraction decision — this
   repo's own `CLAUDE.md` non-negotiable ("Stack — do not substitute without an ADR"); `.clauderules`
   doesn't forbid this and it's cheap.

**Human task:** answer the three questions in step 3. No guidance needed beyond picking an option —
these are product/environment decisions, not implementation ones.

**Exit gate:** human answers recorded in this file's changelog (§5) before Phase 1 starts.

---

### Phase 1 — Database schema (additive only, zero behavior change)

**Files:** `supabase/migrations/0016_agents_provider_fields.sql`,
`supabase/migrations/0017_voices_provider_fields.sql`, regenerated `supabase/SCHEMA.md`/`RLS.md`.

1. `0016`: add to `agents` — `agent_language text not null default 'ur'`, `stt_provider text not
   null default 'gladia'`, `stt_model text not null default 'default'`, `stt_options jsonb not null
   default '{}'`, `llm_provider text not null default 'gemini'`, `llm_options jsonb not null default
   '{}'`, `tts_provider text not null default 'uplift'`, `tts_voice_id text`, `tts_options jsonb not
   null default '{}'`. Backfill `tts_voice_id = voice_id` for all existing rows. All `ADD COLUMN IF
   NOT EXISTS`, idempotent, matching this repo's `0009` convention — no destructive statements.
2. `0017`: add to `voices` — `provider text not null default 'uplift'`, `provider_voice_id text`,
   `language text not null default 'ur'`, `rollout_state text not null default 'enabled'`. Backfill
   `provider_voice_id = id` for the existing 82 Uplift rows.
3. Regenerate `supabase/SCHEMA.md`/`RLS.md` via `db_inspect.py` — never hand-edit, per
   `33-GUIDE-SUPABASE.md`.
4. Confirm `agents_voice_enabled_check` trigger (finding #6) still fires correctly — write is still
   through `voice_id`.

**Tests:**
- New: schema/default test asserting existing agent rows read back as
  `ur/gladia/gemini/uplift`/`tts_voice_id == voice_id` after backfill.
- New: `voices` rows backfilled as `provider='uplift', language='ur', rollout_state='enabled'`.
- Existing: `rls_check.py` still N/N (no RLS policy touched, but re-verify — cheap, and this repo's
  own history has caught real regressions here before).
- Existing: `agents_voice_enabled_check` trigger test — insert with a disabled `voice_id` still
  rejected.

**Manual verification:** direct `SELECT` against the live dev DB confirming backfilled values match
what the migration intended — not just "the migration ran without error."

**Human task:** review the two migration SQL files by hand before they're applied (mirrors this
repo's Phase-1 precedent: "read every RLS policy by hand" — same spirit, additive schema still
deserves a human read given it touches the agents/voices tables directly). If DB write access
belongs to a human in this environment (Phase 0 answer), they run:
```
psql "$SUPABASE_DB_URL" -f supabase/migrations/0016_agents_provider_fields.sql
psql "$SUPABASE_DB_URL" -f supabase/migrations/0017_voices_provider_fields.sql
python scripts/db_inspect.py
```

**Exit gate:** `make gate` green, all Phase 1 tests green, human confirms the live-DB backfill looks
correct.

---

### Phase 2 — Worker provider registry (Urdu-only behavior, zero change)

**Files:** new `worker/providers/{types.py,registry.py,credentials.py,stt/gladia.py,llm/gemini.py,
tts/uplift.py}`; `worker/config.py` (read new columns); `worker/main.py::build_session()` (call the
registry instead of `factories` directly); `worker/factories.py` (kept or removed depending on what
finding-from-audit callers (`scripts/probe_soniox_402.py`, `scratch/test_tts_resilient.py`,
`tests/test_tts.py`) turn out to need — decide in this phase, don't silently break them).

1. Introduce `AgentRuntimeConfig` (per the guide's target shape) and `provider_registry.
   build_components(cfg) -> (stt, llm, tts)`.
2. Move the **existing** Gladia/Gemini/Uplift logic verbatim into the new adapter files — pure
   relocation, no logic change. `soniox`/`deepgram` branches move too, but stay flagged per finding
   #3 (packages not installed — moved as-is, not fixed here).
3. `worker/config.py`: extend the SELECT + `AgentConfig` dataclass with the new columns (additive
   fields only — per finding #8, existing fields/signature untouched).
4. `worker/main.py::build_session()`: build an `AgentRuntimeConfig` from `cfg` and call the
   registry. `entrypoint()`'s external behavior is unchanged.
5. Resolve the `factories.py` callers found in the audit (grep confirmed: `worker/main.py`,
   `tests/test_tts.py`, `scripts/probe_soniox_402.py`, `scratch/test_tts_resilient.py`) — update or
   confirm each still works before removing anything.

**Tests:**
- New adapter-level smoke tests for Gladia STT, Gemini LLM, Uplift TTS (finding #9 — none existed
  before).
- **Mandatory existing Urdu end-to-end regression** (guide's own requirement): transcript received,
  TTS audio received, interruption still works, audio sample rate/channel compatibility unchanged.
- `pytest tests/test_worker.py` — full green, unmodified assertions (only additive test cases, per
  this repo's existing "no existing assertion weakened" discipline).
- Diff-review confirming `ur+gladia+gemini+uplift` produces byte-identical fixture output to before
  the refactor (fixture-mode TTS makes this checkable without a live call).

**Human task:** none requiring external action — review the refactor diff itself before approving,
since this phase touches the file telephony's own plan depends on (finding #8).

**Exit gate:** `make gate` green, Urdu regression demonstrably unchanged (shown, not claimed),
human confirms the `AgentConfig`/`build_session` contract is still what telephony's plan expects
(§2's coordination checkpoint).

---

### Phase 3 — API & SDK: expose new fields (additive, backward compatible)

**Files:** `tenant_portal_api/app.py` (`CreateAgentBody`/`UpdateAgentBody`), `tenant_portal_api/
queries.py` (`create_agent`/`update_agent`/`list_agents`), `sdk-server/src/index.ts`,
`client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts`, four docs files the guide names
(`INTEGRATION_GUIDE.md`, `credentials-template.md`, `sdk-server/README.md`, agents `README.md`).

1. Add optional fields to both Pydantic bodies: `agent_language`, `stt_provider`, `stt_model`,
   `stt_options`, `llm_provider`, `llm_options`, `tts_provider`, `tts_voice_id`, `tts_options`.
   Because both `/portal/agents` and `/machine/agents` share these models (ground-truth snapshot),
   one change covers both.
2. Validation before any DB write: `unsupported_language`, `unsupported_provider_for_language`,
   `unsupported_model_for_provider`, `unsupported_voice_for_provider`, `provider_not_enabled` — per
   the guide's Error Handling list, checked at `language -> provider -> model/voice/options`
   granularity (not a broad provider-level check — the guide is explicit this is wrong).
3. Priority rule when both old and new fields are present: `tts_voice_id`/`ttsVoiceId` wins over
   `voice_id`/`voiceId`; new provider fields win over old ones generally.
4. Update both SDK packages **together**, add the parity test from finding #5 so they can't drift
   again unnoticed.
5. Update the four docs files.

**Tests:**
- Extend `tests/test_phase4_portal_api.py`/`tests/test_machine_agent_api.py`: new fields accepted
  and returned; invalid combinations (`ur+groq`, `ur+elevenlabs`) rejected with the right error
  code; old-style payloads (`voiceId`/`llmModel` only) still work unchanged (backward-compat).
- SDK: `tsc --noEmit` clean on both packages; new parity test passes.
- Re-confirm (per `state/BLOCKERS.md`'s standing finding) that `pytest.ini` actually collects these
  test files — don't let this land invisibly uncovered by `make gate` again.

**Human task:** none new.

**Exit gate:** `make gate` green including the portal/machine test files confirmed actually
collected, SDK typecheck clean on both packages, human reviews the validation error-code list
matches the guide's.

---

### Phase 4 — Central capabilities API

**Files:** new route (path per Phase 0's decision — this plan's default:
`/portal/provider-capabilities` + `/machine/provider-capabilities`), capability data sourced from
Phase 1's `voices.rollout_state`/`provider`/`language` columns plus a small static/DB-backed
STT+LLM capability table (not voice-specific, so it doesn't belong in `voices`).

1. Build the capability lookup, shaped per the guide's JSON example (`language -> provider ->
   models/voices/options`, `state` per entry).
2. Only `enabled` rollout-state entries returned publicly; `testing` gated to an internal/admin
   check (not built yet elsewhere in this repo — flag if this needs its own small guard, don't
   invent a new auth layer without asking).

**Tests:** only `enabled` combinations returned; a `planned`/`testing` entry never leaks through;
schema of the response matches the guide's example shape.

**Human task:** none new.

**Exit gate:** `make gate` green, response manually inspected against the guide's example JSON.

---

### Phase 5 — English language: STT + LLM, zero new paid vendors

The cheapest slice to prove the registry genuinely supports a second language before touching any
new vendor at all: Gladia already supports `en`, Gemini is already language-agnostic.

1. Parameterize the Gladia adapter by `agent_language` (no hardcoded `"ur"` left anywhere per the
   guide's explicit rule) — confirm/test English STT.
2. Confirm Gemini needs no code change (persona/prompt-driven already) — test, don't just assert.

**Human task:** none new — no new vendor touched in this phase.

**Tests:** English Gladia STT adapter test, capabilities API now returns `en` with `stt.gladia` as
`enabled` (LLM stays provider-agnostic — no per-language capability entry needed for gemini).

**Exit gate:** `make gate` green.

---

### Phase 6 — English's full provider set: ALL SIX required, not a trial subset

**Confirmed scope (2026-08-01, supersedes this section's earlier "pick one first" framing):** every
one of these is needed for the English release, not an initial subset to validate the pattern with:
- **STT:** Gladia (already covered, Phase 5) **and Deepgram**
- **LLM:** Gemini (already covered) **and Groq**
- **TTS:** **ElevenLabs, Fish Audio, Cartesia, and Rime** — all four

That's **6 new provider integrations** (Deepgram, Groq, ElevenLabs, Fish Audio, Cartesia, Rime).
Each still goes through its own subphase — "all required eventually" is not the same as "safe to
build simultaneously without individual verification." Same repeatable template per provider (per
the guide's "Future Provider Process"), run once per provider in §6a-§6f below:

1. Verify the real package name + adapter API against current docs — not assumed from the guide's
   prose (finding #4). None of these 6 package names have been confirmed yet.
2. **Human task:** approve `pip install`, obtain/provide credentials, add to `.env.local`.
3. Add the adapter under `worker/providers/<layer>/`, pin the dependency in `requirements.txt`.
4. Add capability-registry entry at `rollout_state = planned`, promote to `testing` once smoke
   tests pass, then `enabled` only after a **human-approved live smoke test** confirms it for real.
5. Guide's explicit business rule enforced in validation: Groq is never selectable for `ur`.

**Exit gate per provider:** `make gate` green, that provider's own smoke + validation tests green,
human live-test confirmation, capability entry flipped to `enabled` only after that. Phase 6 as a
whole isn't "done" until all 6 subphases individually clear this gate.

**Build order (confirmed 2026-08-01):** no required order — defaulting to STT → LLM → TTS,
alphabetical within each layer (Deepgram; Groq; Cartesia, ElevenLabs, Fish Audio, Rime).

---

### Phase 7 — Additional languages beyond `en` (deferred pending Phase 0 answer)

Not sequenced with concrete migrations/subphases yet — this section only activates if the human
confirms (Phase 0) that `es`/`hi`/etc. are in scope now rather than later. If confirmed, each new
language follows the same shape as Phase 5 (parameterize existing adapters where possible, add new
vendor(s) only where a language genuinely needs one, one human-approved live test per new
provider/language combination) — appended here as concrete subphases once scoped, not assumed in
advance.

---

## 4. Cross-cutting rules, every phase

- `make gate` must be green before a phase is presented as done — not claimed from memory of an
  earlier run in the same session (this repo's own history has caught exactly this failure mode
  more than once).
- No silent provider fallback, ever (guide's explicit rule) — a failed provider returns a typed
  error, never a quiet swap.
- Re-read `docs/.clauderules` and this file every ~8 messages/phase (`.clauderules`' own self-check
  rule) and confirm no rule was silently violated.
- Any new dependency, any modification outside the phase's listed files, or any assumption about an
  external API/package gets flagged and asked about before proceeding — not guessed (`.clauderules`
  "WHEN STUCK" list + this repo's own "verify, don't assume").

## 5. Changelog / phase sign-offs

### Phase 0 — COMPLETE — 2026-07-31
- Baseline `make gate` run on `ukasha` HEAD before any change: **RED** at lint
  (`scratch/test_tts_resilient.py`, pre-existing unused variable, commit `dc19c25`) and at test
  collection (`livekit-agents` and other `requirements.txt` packages not installed in this
  environment's Python — pre-existing environment gap, not caused by this work).
- Human approved fixing both: (1) removed the unused `stream` assignment in
  `scratch/test_tts_resilient.py` (1-line, zero behavior change, `ruff format`ed) and (2) ran
  `pip install -r requirements.txt` (exactly what was already declared, nothing new/unpinned).
- Re-ran `make gate` clean: **`GATE: PASS`, exit 0 — 77 passed, 1 skipped, RLS 11/11 tables OK,
  usage ledger within every budget.** This is the real baseline Phase 1+ is measured against.
- Migrations directory re-checked immediately before Phase 1: still `0001`-`0011` only, `0016` free.
- Human answered all 3 Phase 0 questions (recorded in ADR-036): `en`-only scope for now,
  `/portal` + `/machine` capabilities routes, agent applies migrations directly.
- ADR-036 written (`docs/40-ADR.md`) recording the decision and all Phase 0 answers.
- **Approved by:** human, 2026-07-31 (AskUserQuestion responses this session).

### Phase 1 — COMPLETE, pending human approval — 2026-07-31
- `supabase/migrations/0016_agents_provider_fields.sql` and `0017_voices_provider_fields.sql`
  written (additive `ADD COLUMN IF NOT EXISTS`, no destructive statements) and applied directly to
  the live dev DB (not `make db-reset`, which would wipe live dev data — same precedent as
  Session 15's 0011).
- Backfill verified by direct SQL, not assumed: **0 mismatches** across all 27 existing `agents`
  rows and all 86 existing `voices` rows against the expected `ur+gladia+gemini+uplift`/
  `uplift+ur+enabled` defaults.
- `supabase/SCHEMA.md`/`RLS.md` regenerated via `scripts/db_inspect.py` — never hand-edited.
- New `tests/test_provider_registry_schema.py` (6 tests), added to `pytest.ini`'s explicit
  whitelist (finding from Phase 0 audit #10/BLOCKERS.md history — a file absent from that list
  silently doesn't run under `make gate`).
- **Real finding caught by actually running the tests, not assumed correct on the first write:**
  the test initially asserted a freshly-inserted agent (via the CURRENT, unmodified
  `/portal/agents`/`/machine/agents` write path) would have `tts_voice_id == voice_id`. It doesn't
  — `tts_voice_id` has no column DEFAULT (deliberate), so it's `NULL` on any row inserted after
  this migration until Phase 3's application layer starts writing it. Harmless today (nothing
  reads `tts_voice_id` yet), but documented explicitly — in the migration file's own comment and
  as its own passing test (`test_new_agent_row_leaves_tts_voice_id_null_by_design`) — as a
  hard requirement for Phase 2: the provider registry must read `tts_voice_id or voice_id`
  (fallback), never assume it's always populated. Also fixed one wrong exception-class assertion
  in the same first draft (`RaiseException` → the actual `psycopg.errors.CheckViolation` the
  0006 trigger raises) — the trigger itself was correct throughout; only the test's assertion was
  wrong.
- `python scripts/rls_check.py` run independently: **11/11 tables OK** (including the two touched
  tables).
- Full `make gate`: **`GATE: PASS`, exit 0 — 83 passed (77 baseline + 6 new), 1 skipped, RLS 11/11,
  usage ledger unchanged from baseline** (`uplift_tts_sec=327/600`, `livekit_agent_min=84/1000` —
  confirms zero live/paid API calls this phase, as expected for schema-only work).
- **Awaiting human review of the two migration files and this summary before Phase 2 begins** —
  per this plan's own Phase 1 human-task requirement (read the SQL by hand) and the "no phase
  starts without explicit human approval" rule in §Cross-cutting rules.
- **Human approved the migrations on review, 2026-08-01. Phase 2 begun.**

### Phase 2 — COMPLETE, pending human approval — 2026-08-01
- New `worker/providers/` package: `types.py` (`AgentRuntimeConfig`, `ProviderComponents`),
  `registry.py` (`build_components()` — the one place that dispatches on provider strings, raises
  `UnsupportedProviderError` rather than silently falling back), `stt/{gladia,deepgram,soniox}.py`,
  `llm/gemini.py`, `tts/uplift.py` — the real logic, relocated.
- `worker/factories.py` kept (its two callers, `scripts/probe_soniox_402.py` and
  `scratch/test_tts_resilient.py`, still need it) but rewritten as thin wrappers delegating into
  `worker/providers/` — avoids the exact duplication-drift risk flagged in the Phase 0 audit
  (finding #5), rather than leaving two copies of the same logic that can silently diverge.
- `worker/config.py::AgentConfig` gained the 9 new fields, `worker/main.py::build_session()` now
  builds an `AgentRuntimeConfig` (resolving `tts_voice_id or voice_id` in exactly the one place
  Phase 1 flagged as necessary) and calls `build_components()` instead of `factories.py` directly.
- **Three real bugs caught by actually running things, not assumed correct on first write:**
  1. **Stale-content bug, caught before it shipped wrong code.** The adapters were first written
     from a `factories.py` read taken at the very start of this whole session — before the human's
     "repo pulled from staging" step. The live file had since changed materially (a different
     `_phrase_config_id()` resolution using `UPLIFT_DISABLE_PHRASE_CONFIG`/`UPLIFT_PHRASE_CONFIG_ID`/
     `UPLIFT_USE_PHRASE_CONFIG_FILE` env vars, and `output_format` changed from `WAV_22050_16` to
     `PCM_22050_16`). Caught by diffing against the actual current file before proceeding, not by
     a test — every adapter was then re-verified line-for-line against the real current
     `factories.py` before continuing.
  2. **Safety near-miss.** This environment's `.env.local` sets `UPLIFT_MODE=live` (for real
     dev-session work elsewhere). An early test draft relied on `UPLIFT_MODE`'s function-level
     default ("fixture"), but `os.environ.setdefault()` — what `conftest.py` itself also uses —
     does not override an already-set var. That test was about to construct a **live** Uplift TTS
     client; it was saved only by the pre-existing offline network guard blocking the resulting
     connection attempts (visible as "the offline guard blocked 4 connection attempt(s)"), not by
     the test's own design. Fixed by explicitly `monkeypatch.setenv("UPLIFT_MODE", "fixture")` in
     every TTS-touching test — never relying on the default in this environment.
  3. **Backward-compatibility regression, self-caught before claiming done.** The 9 new
     `AgentConfig` fields were first added with no defaults, making them mandatory — silently
     broke two genuinely pre-existing tests (`test_persona_injected_as_data_not_system_instructions`,
     `test_build_agent_wires_fixed_tools`) that construct `AgentConfig` the old way. Fixed at the
     dataclass (defaults matching Phase 1's DB backfill exactly), not by touching those tests —
     they were not edited.
- **One real, non-obvious finding, not a bug:** fixture-mode TTS synthesis driven through
  LiveKit's real `ChunkedStream` base class produces audio that's byte-identical to the raw fixture
  wav for its entire length, but padded by exactly one 440-byte frame (10ms @ 22050Hz) at the end —
  a LiveKit audio-pipeline characteristic (fixed-frame emission), not something this refactor
  changed (the original `factories.py` used the identical base classes and would pad identically).
  Verified directly (diffed the two buffers byte-for-byte) before writing the test's tolerance,
  not guessed.
- New `tests/test_provider_registry.py` (7 tests): registry/legacy-factory parity, fixture-mode
  Urdu synthesis matches the committed fixture (the real regression proof), Gladia language
  construction unchanged, typed-error-not-silent-fallback for unsupported providers, `AgentConfig`
  field-order correctness, and the `tts_voice_id`-NULL fallback actually engaging in
  `build_session()`. Added to `pytest.ini`'s whitelist.
- Full relevant suite re-run together (`test_provider_registry.py` + `test_provider_registry_schema.py`
  + `test_worker.py`): **23 passed**, including the two pre-existing tests the backward-compat bug
  above had broken and then un-broke.
- **Full `make gate`: one FAILURE, confirmed unrelated to this phase, not fixed here.**
  `tests/test_phase4_portal_api.py::test_portal_login_and_scoped_routes` failed on
  `quota_state.period_start` not matching the current month — this gate run happened to cross the
  real July 31 → August 1 midnight boundary mid-run. Confirmed pre-existing and out of this
  phase's scope before writing this up: `git status` shows zero modified files outside what this
  plan's Phases 0-2 touched (`tenant_portal_api/`, `usage.py`, `queries.py` — all untouched by me),
  and the failure reproduces in isolation independent of any Phase 2 change. Per this plan's own
  rule (mention out-of-scope bugs, do not fix them without asking) — flagged for the human, not
  silently fixed or silently ignored. **Every test this phase actually touches is green.**
- Zero live/paid API calls (fixture mode throughout, confirmed via the monkeypatch fix above).
- **Human approved Phase 2 on review, 2026-08-01. Confirmed no build-order requirement across
  Phase 6's 6 providers (default STT → LLM → TTS, alphabetical within layer). Phase 3 begun.**

### Phase 3 — COMPLETE, pending human approval — 2026-08-01
- New `worker/providers/capabilities.py` — the central capability registry (language -> layer ->
  provider -> {state, models}), `ur` fully `enabled`, `en` combos present as `planned` (documents
  the confirmed 6-provider target scope without making anything selectable before it's real). Groq
  is structurally absent from `ur`, not specially cased — the guide's "never allow Groq for Urdu"
  rule is enforced by the entry simply not existing, so there's nothing to keep in sync.
- New `tenant_portal_api/provider_validation.py::resolve_agent_provider_fields` — the one function
  every create/update route (both `/portal` and `/machine`) funnels through, checked at
  `language -> provider -> model/voice/options` granularity per the guide's explicit rule. Returns
  fully-resolved values; callers write exactly what it returns, nothing else.
- `tenant_portal_api/app.py`/`queries.py` extended: both Pydantic bodies gained the 9 optional
  fields, both `/portal/agents` and `/machine/agents` route through the same validation+resolution
  (they already shared the same Pydantic models — one change covers both surfaces, confirmed in
  Phase 0's ground-truth snapshot). **`voice_id`/`tts_voice_id` sync gap Phase 1 flagged is now
  closed**: every create/update writes the same resolved value to both columns, `tts_voice_id`
  winning when both are given (guide's priority rule).
- `sdk-server/src/index.ts` and the client-submission copy both updated with the matching optional
  camelCase fields, re-confirmed byte-identical after (copied, not hand-duplicated a second time).
- **Real bugs found by actually running things — the pattern held again this phase:**
  1. **Serious regression, caught before merge, not after.** Adding optional (`None`-default)
     fields to `CreateAgentBody` silently broke every existing `POST /machine/agents` HMAC
     signature: `_require_machine` verified against `body.model_dump()` (all fields, including the
     new `None`-valued ones), while every real signer (the SDK, this repo's own test suite) only
     ever signs the fields it explicitly set. `PATCH` already used `exclude_none=True` for exactly
     this reason; `POST` never needed to before because every pre-Phase-3 field either was required
     or had a non-`None` default. Fixed by matching `PATCH`'s existing pattern. Caught by
     `test_happy_path_create_agent` — a genuinely pre-existing, previously-green test — turning red,
     not by a new test written to look for it.
  2. **Validation gap, not a regression:** the new voice-lookup check read `provider`/`language`/
     `rollout_state` but never fetched or checked `voices.enabled` (the pre-existing boolean flag
     0006's DB trigger already enforces at the `voice_id` layer). A disabled voice would have
     reached the DB trigger's raw exception instead of a clean `422`. Caught by
     `test_disabled_voice_rejected` failing with "DID NOT RAISE," not assumed correct.
  3. Two of my own new tests had bugs, not the code under test: one asserted an LLM model string
     (`gemini-3.1-flash-lite`) that isn't in the capability table's selectable list (only
     `gemini-2.5-flash` is — the worker's own deprecated-model remap is a separate, later step, not
     an API-facing selectable value); one machine-auth test forgot to sign `llm_model` explicitly,
     hitting the same "every field with a non-`None` default must be signed" rule from finding #1 —
     both fixed in the test, not the app.
- `docs/MACHINE_AGENT_API_CONTRACT.md` updated beyond the plan's original 4-doc list (a real gap
  found while fixing #1 above) — the signature rule change affects the actual wire contract, not
  just this repo's internal code.
- New test files: `tests/test_provider_validation.py` (12 tests — every error code, the sync fix,
  `current`-supplies-update-defaults), `tests/test_sdk_parity.py` (2 tests — byte-identity +
  new-field presence; explicitly notes `tsc` still isn't installed in this environment, a
  pre-existing gap from Session 14d, not fixed here). Extended `test_phase4_portal_api.py` (+3) and
  `test_machine_agent_api.py` (+2) with backward-compat and rejection tests through the real HTTP
  layer. All added to `pytest.ini`'s whitelist.
- Full `make gate`: **108 passed, 1 skipped, 1 failed — the failure is the identical pre-existing
  `quota_state.period_start` month-rollover bug flagged in Phase 2's changelog** (re-confirmed
  independently: unrelated files, reproduces regardless of this phase's changes). Every test this
  phase touches is green.
- Zero live/paid API calls.
- **Human approved Phase 3 on review ("proceed to phase 4"), 2026-08-01.**

### Phase 5 — COMPLETE, pending human approval — 2026-08-01
- Confirmed `worker/providers/` already had zero hardcoded `"ur"` in actual logic before touching
  anything (grep — only comments/docstrings and the `CAPABILITIES` data table itself matched) —
  Phase 2's registry work already made the Gladia adapter language-parameterized, so this phase
  needed **no adapter code changes at all**. Gemini needed none either (prompt-driven, not
  language-specific).
- `worker/providers/capabilities.py`: `en.stt.gladia` and `en.llm.gemini` flipped `planned` →
  `enabled`. Deepgram, Groq, and all 4 TTS vendors stay `planned` — untouched, Phase 6's job.
- New `tests/test_english_language.py` (3 tests): a real Gladia STT object built with
  `agent_language="en"` actually configures `languages=["en"]` (not just "the string flowed
  through somewhere"); the capabilities API shows `en` with `stt`/`llm` enabled and correctly no
  `tts` key; and — the one genuinely interesting assertion this phase makes — attempting to
  resolve a **full** `en` agent still fails cleanly with `provider_not_enabled` on the `tts` layer
  specifically, proving stt+llm validate successfully and the system doesn't pretend English is
  fully usable yet.
- **Updating 3 pre-existing tests whose premise this phase deliberately changed — not a
  regression, the expected consequence of promoting `en` from `planned` to partially `enabled`:**
  `test_provider_validation.py::test_english_gladia_rejected_as_not_yet_enabled` (renamed/retargeted
  to `deepgram`, the STT provider still actually `planned` for `en`),
  `test_provider_capabilities.py::test_english_absent_entirely_since_nothing_is_enabled_yet`
  (renamed/retargeted to assert `en` now appears with stt+llm enabled, no tts), and one instance in
  `test_phase4_portal_api.py::test_portal_provider_capabilities_requires_auth_and_returns_ur` with
  the identical stale assertion, found and fixed after the others.
- One of my own new tests had a bug on first write: asserted `tts_provider="uplift"` expecting
  `provider_not_enabled`, but `uplift` isn't listed under `en` at all, so it correctly raised
  `unsupported_provider_for_language` instead — a different, already-covered case. Fixed to use
  `elevenlabs` (which IS listed for `en`, still `planned` — the actual case intended).
- **One transient environment failure, investigated and confirmed not a regression before moving
  on:** a `make gate` run mid-phase failed 13 tests + errored 54 more, all `psycopg.OperationalError`,
  spanning files this phase never touched (`test_mint.py`, `test_worker.py`). Re-ran one of the
  failing tests in isolation — passed cleanly — then re-ran the full gate twice more; both passed.
  Consistent with transient DB-connection exhaustion under sustained load (many short-lived
  connections across a long test run), not a code issue — not chased further since it didn't
  reproduce.
- Full `make gate` (after the above): **`GATE: PASS`, exit 0 — 118 passed, 1 skipped, RLS OK on
  23/23 tables.**
- Zero live/paid API calls.

### Phase 4 — COMPLETE, pending human approval — 2026-08-01
- New `tenant_portal_api/provider_capabilities.py::get_public_capabilities` — combines
  `worker/providers/capabilities.py`'s STT/LLM data with a live `voices` table query into the
  guide's exact JSON shape (`languages -> {label, stt, llm, tts}`). Manually inspected against the
  guide's example JSON before writing tests, not just assumed to match.
- Only `state == "enabled"` entries are ever included, and a language with nothing enabled in any
  layer is omitted entirely rather than shown as an empty shell — confirmed live: `en` does not
  appear in the response at all today, since every `en` combo is still `planned` (Phase 5/6
  haven't landed). Groq/ElevenLabs never appear for `ur` (structurally absent, same mechanism as
  Phase 3's validation).
- Two new routes, matching Phase 0's approved dual-auth-surface decision: `GET
  /portal/provider-capabilities` (tenant JWT) and `GET /machine/provider-capabilities` (tenant
  HMAC, `action = "provider_capabilities.get"`). Both return identical content for the same tenant.
- New `tests/test_provider_capabilities.py` (4 tests: shape, `en` absence, disabled-voice
  non-leakage, groq/elevenlabs non-appearance) plus one HTTP-level auth-required test added to each
  of `test_phase4_portal_api.py` and `test_machine_agent_api.py`. All 6 passed on the first run —
  no bugs found this phase (the registry/validation groundwork from Phases 2-3 already did the
  hard work; this phase was mostly wiring).
- Full `make gate`: **`GATE: PASS`, exit 0 — 115 passed, 1 skipped, RLS OK on 23/23 tables**
  (up from 11 — Habiba's telephony migrations 0012-0015 have landed in the shared dev DB since
  Phase 2's gate run, no collision with this plan's 0016/0017, confirming the migration-number
  coordination held). The month-rollover test from Phases 2/3 happened to pass this run (not
  always crossing a real midnight boundary) — still the same pre-existing, unrelated test, not
  fixed or touched here either way.
- Zero live/paid API calls.
- **Human approved Phase 5 on review ("proceed to phase 6"), 2026-08-01. Confirmed build order:
  no requirement, defaulting STT → LLM → TTS. Phase 6a (Deepgram) begun.**

  *(Note on ordering: this entry and the ones below were appended after this file's Phase 4 entry
  due to an anchor-matching quirk when editing — chronologically these follow Phase 5, not Phase 4.
  Flagged for accuracy; not worth reordering the file for.)*

### Phase 6a (Deepgram STT) — COMPLETE, human-approved live test passed — 2026-08-01
- **Package/API verified against real, current sources before any code was written** (finding #4's
  own requirement, not assumed from the guide's prose): `livekit-plugins-deepgram==1.6.5` confirmed
  on PyPI (matches every other plugin's pinned version), real constructor confirmed via
  `inspect.signature` on the actually-installed package — `model`/`language` are real kwargs,
  `"nova-3"`/`"en"` are both valid values. A genuine, non-blocking historical finding surfaced by
  this verification: the pre-existing (Phase-2-relocated) code's `ur` branch used
  `language="ur"`, but `"ur"` isn't in Deepgram's supported language list at all — a latent,
  never-triggered bug (Deepgram was never the default STT and isn't in `ur`'s capability entry),
  not fixed since Deepgram is only ever enabled for `en` going forward.
- Installed with human approval, `DEEPGRAM_API_KEY` added to `.env.local` by the human directly
  (never pasted into chat). `worker/providers/stt/deepgram.py` needed no logic change (Phase 2
  already built it correctly, just uninstalled) — only its docstring updated with the verification
  evidence. Capability entry added at `testing`, then `enabled` after the live test below.
- **A real, necessary fix found before any live test was even attempted, not after**:
  `worker/main.py::prewarm()` only imported ONE STT plugin, gated on the legacy `STT_PROVIDER` env
  var — a leftover from before Phase 2 made provider selection per-agent (DB-driven). Left as-is,
  the first `en`+Deepgram session would import that plugin for the first time outside the main
  thread, hitting the exact `Plugin.register_plugin()` crash ADR-007 already documents for
  unprewarmed plugins on Windows. Fixed: gladia + deepgram both prewarmed unconditionally now;
  soniox stays env-var-gated (still unreachable via the registry, ADR-002, not in scope).
- **Two more real, blocking findings surfaced only by actually attempting the live test — not
  hypothesized in advance:**
  1. First live attempt: both test sessions left `ended_at`/`duration_sec`/`transcript` all
     `NULL` — no evidence the call ever produced a transcript. Verified independently via direct
     SQL, not trusted from "I tested it."
  2. A third mint attempt then hit `MintError 429: concurrent cap reached` — independent
     confirmation of (1): both prior sessions' quota slots were never released. This project's own
     `reconcile_sessions.py` couldn't help (30-minute default staleness threshold, these were
     under 30 minutes old) without risking other developers' genuinely-live sessions in this
     shared dev DB — fixed narrowly instead, closing only this disposable test tenant's two rows
     and resetting its own `concurrent_now`, nothing else touched.
  3. **Root cause of both, found by reading `control_plane/app.py` rather than guessing:**
     `scripts/mint_demo_token.py` calls `mint_session()` directly, bypassing
     `control_plane/app.py`'s real `/v1/session` route entirely — and the actual LiveKit
     **explicit** agent dispatch call (`agent_dispatch.create_dispatch`, this repo's own
     architecture is "SDK-First, Explicit Dispatch") only ever lived in that route's
     `_dispatch_agent`/`_with_dispatch` helpers, never in `mint_session()` itself. So this
     pre-existing script — not something this plan touched before now — created a real room,
     token, and session row, but never told LiveKit a job existed for it. A worker could be
     running and connected and would still never receive that job. This is why "nothing updates
     in the worker terminal at all" — not a Deepgram problem. Fixed by adding the identical
     dispatch call `app.py` already makes correctly.
- **Live test, re-run after both fixes: PASSED, human-confirmed.** Worker log showed a real
  Deepgram WebSocket connection, correct English transcripts ("Are you listening?", "That's good
  to hear. Goodbye."), and a contextually coherent LLM reply ("Yes, I can hear you clearly...") —
  strong evidence the transcript was accurate, not just that a connection was made. Independently
  re-verified from the DB (not trusted from the terminal log alone): `ended_at` set,
  `duration_sec: 24`, `end_reason: participant_disconnected`, transcript matching the log exactly.
  Human explicitly confirmed this as a pass before promotion.
- `en.stt.deepgram` promoted `testing` → `enabled`. Three tests whose premise this changed (again)
  updated in place, same pattern as Phase 5: `test_deepgram_stt.py`'s rejection test retargeted to
  prove the STT layer now validates successfully (failure moves to the still-`planned` TTS layer);
  `test_english_language.py` and `test_provider_validation.py` (`en`+Deepgram no longer the
  "still planned" example — swapped for `en`+Groq, genuinely still planned).
  `scripts/provision_deepgram_test_agent.py` (new) provisions a throwaway hybrid test agent
  (`en`+Deepgram+Gemini+Uplift, reusing an existing Urdu voice since no `en` TTS exists yet — a
  combination no tenant could create through the real API, deliberate for this test only).
  Test tenant fully cleaned up (all rows deleted) after the live test concluded.
- **Two transient environment failures mid-phase, both investigated and confirmed not
  regressions**: a lint-only failure on two of this phase's own new/edited scripts (reformatted,
  unrelated files untouched), and a full-suite run that hit `psycopg.OperationalError: failed to
  resolve host` (DNS) across files this phase never touched — confirmed cleared by an isolated
  re-run, then a clean full re-run.
- Full `make gate` (final): **`GATE: PASS`, exit 0 — 120 passed, 1 skipped, RLS OK on 23/23
  tables.**
- Real Deepgram + LiveKit + Gemini + Uplift usage this phase (the live test itself, human-approved
  and present throughout) — the only live/paid calls in this plan so far.
- **Human approved Phase 6a on review, 2026-08-01. Phase 6b (Groq) begun.**

### Phase 6b (Groq LLM) — COMPLETE, human-approved live test passed — 2026-08-02
- **Package/API verified against real, current sources before any code was written** (same
  discipline as 6a): `livekit-plugins-groq==1.6.5` confirmed on PyPI (matches the version
  convention) — installing it pulls in `livekit-plugins-openai==1.6.5` as a real dependency, since
  Groq's plugin is built on the OpenAI-compatible interface (`base_url` defaults to
  `https://api.groq.com/openai/v1`), not a bespoke Groq protocol. Real constructor confirmed via
  `inspect.signature` on the installed package — `model`/`api_key` are real kwargs, default model
  `"llama-3.3-70b-versatile"` is real and current per the package's own `models.py` (not guessed).
- Installed with human approval; `GROQ_API_KEY` added to `.env.local` by the human directly.
  `worker/providers/llm/groq.py` (new, minimal) and `worker/providers/registry.py`'s `_build_llm`
  extended with a `groq` branch. `worker/main.py::prewarm()` updated the same way Phase 6a's
  Deepgram fix required — `groq` prewarmed unconditionally, same reasoning (per-agent DB-driven
  selection, not a worker-level env var). Capability entry added at `testing`, then `enabled`
  after the live test below. Groq's absence from `ur`'s capability entry (guide's "never for
  Urdu" rule) re-confirmed unaffected by any of this.
- New `scripts/provision_groq_test_agent.py` (mirrors 6a's pattern): `en`+Deepgram (already
  enabled, incidentally re-exercised)+Groq+Uplift (existing Urdu voice, hybrid workaround, no `en`
  TTS yet) — a combination no tenant could create through the real API, deliberate for this test.
- **Live test needed two attempts, both informative:**
  1. First dispatch: the participant never actually joined in time (token/timing), and the job
     failed with a clean, expected `RuntimeError: room disconnected while waiting for participant`
     — not a bug, just a normal token-expiry/timing miss (this plan's own mint tokens are
     deliberately short-lived, 120s). The human re-minted and rejoined on their own initiative.
  2. Second dispatch (different room, since it came from a fresh mint): **passed.** Deepgram
     transcribed correctly again, and Groq's replies were coherent and contextually appropriate
     ("What's on your mind, how can I help you today?", "How's your day going so far?" — genuine,
     relevant follow-up questions, not generic filler). Independently re-verified from the DB
     (not trusted from the terminal log alone): clean close, `duration_sec: 38`,
     `end_reason: participant_disconnected`, transcript matching the log exactly. Human explicitly
     confirmed this as a pass before promotion.
- `en.llm.groq` promoted `testing` → `enabled`. Tests whose premise this changed (again, same
  recurring pattern as Phases 5/6a) updated in place: `test_groq_llm.py`'s rejection test
  retargeted to prove the LLM layer now validates successfully (failure moves to the still-
  `planned` TTS layer, tested against `elevenlabs`) plus a separate test re-confirming Groq stays
  permanently unselectable for `ur`; `test_provider_validation.py`'s "still-planned `en` example"
  swapped a third time (deepgram → groq → now `elevenlabs`, the first TTS vendor, genuinely still
  planned); `test_english_language.py`'s capabilities-shape test updated to expect groq `enabled`.
  Test tenant fully cleaned up (all rows deleted) after the live test concluded.
- Full `make gate`: **`GATE: PASS`, exit 0 — 123 passed, 1 skipped, RLS OK on 23/23 tables** —
  clean on the first run this time, no transient environment failures.
- Real Groq + Deepgram + LiveKit + Uplift usage this phase (the live test itself, human-approved
  and present throughout, two attempts).
- **Human approved Phase 6b on review, 2026-08-02. Phase 6c (Cartesia) begun.**

### Phase 6c (Cartesia TTS) — COMPLETE, human-approved live test passed — 2026-08-02
- **Package/API verified against real, current sources before any code was written** (same
  discipline as 6a/6b): `livekit-plugins-cartesia==1.6.5` confirmed on PyPI (matches the version
  convention), real constructor confirmed via `inspect.signature` on the installed package —
  `voice`/`language` are real kwargs. `worker/providers/tts/cartesia.py::build(voice_id, language)`
  is a thin wrapper, no logic beyond construction.
- Installed with human approval; `CARTESIA_API_KEY` added to `.env.local` by the human directly.
  `worker/providers/registry.py::_build_tts` extended with a `cartesia` branch.
  `worker/main.py::prewarm()` updated the same way 6a/6b required — `cartesia` prewarmed
  unconditionally (per-agent DB-driven selection, not a worker-level env var). Migration
  `0018_seed_cartesia_voice.sql` seeds one voice row (`id='cartesia-sonic-default'`,
  `provider_voice_id` = the plugin's own baked-in default voice UUID
  `f786b574-daa5-4673-aa0c-cbe3e8534c02`, not an invented one). Capability entry added at
  `testing`, then `enabled` after the live test below.
- **A real, general design gap found and fixed before any live test — not Cartesia-specific**: the
  registry passed our internal `voices.id` slug straight to every TTS adapter unresolved. This
  worked for Uplift only by coincidence — Phase 1's backfill set `provider_voice_id = id` for every
  Uplift row, so the bug was invisible until a vendor with a genuinely different ID showed up.
  Cartesia's real ID is a UUID, nothing like our slug. Fixed with a new
  `worker/main.py::_resolve_provider_voice_id()`, which looks up `voices.provider_voice_id` for the
  internal slug before any adapter sees it; `build_session()` now resolves this once per session.
  Verified zero regression via a full `test_provider_registry.py` re-run (Uplift's resolution is a
  no-op, proven by `test_resolve_provider_voice_id_falls_back_for_uplift_where_slug_equals_real_id`).
- New `scripts/provision_cartesia_test_agent.py` (mirrors 6a/6b's pattern): `en`+Deepgram (already
  enabled, incidentally re-exercised)+Gemini+Cartesia (the seeded voice) — unlike 6a/6b's hybrid
  workaround, this is the first subphase where the TTS vendor under test produces the actual output
  audio, not a stand-in.
- **First live attempt failed: `401 Unauthorized` from Cartesia on every TTS request.** Diagnosed,
  not guessed — the logged `X-API-Key` header had prefix `sk_car_admin_...`. Confirmed via
  WebSearch: Cartesia issues two distinct key types — standard keys
  (`play.cartesia.ai/keys`, required for generation/TTS routes) vs. admin keys
  (`play.cartesia.ai/keys/admin`, account/key-management only, explicitly do not work on
  generation routes at all). The human had used an admin key. Session closed cleanly via the
  error path; independently confirmed from the DB before proceeding (not left as a guess).
- Human obtained a standard key and added it to `.env.local`. Verified it actually worked via a
  direct standalone probe (bypassing the full worker/room dance) before spending another live-call
  attempt on it — first probe attempt hit an unrelated `RuntimeError: Attempted to use an http
  session outside of a job context` (a LiveKit plugin limitation when run outside a real job),
  fixed by wrapping the probe in `livekit.agents.utils.http_context.open()` (the real public API,
  found by inspecting the module after an initial wrong guess at a private function). Second probe:
  **`SUCCESS: received 4 audio chunk(s) from Cartesia`**, confirmed before retrying the full test.
- **Two rounds of concurrency-cap leaks from the failed/interrupted attempts**, same recurring
  pattern as 6a: sessions from the pre-401 setup, the 429-triggering retry, and a race against the
  120s mint TTL all left `ended_at IS NULL` rows behind, each time fixed narrowly (scoped to only
  this one throwaway tenant) by closing the stale rows and resetting `concurrent_now`.
- **Live test, re-run with the worker started first this time: PASSED, human-confirmed.** Worker
  log showed a real Cartesia WebSocket connection established and held for the whole call, Deepgram
  transcribing correctly, and Gemini producing three coherent, contextually appropriate replies.
  Independently re-verified from the DB (not trusted from the terminal log alone): room
  `94089b1b-5012-4bc6-86b2-e7c203124c91`, `duration_sec: 44`, `end_reason: participant_disconnected`,
  transcript matching the log exactly (3 user/assistant turn pairs). Human explicitly confirmed the
  Cartesia audio itself sounded clear and correct — the first subphase where this had to be judged
  by ear rather than inferred from logs — before approving promotion.
- `en.tts.cartesia` promoted `testing` → `enabled` — `en`'s first fully-enabled TTS provider, so a
  full `agent_language="en"` agent is now creatable end-to-end through the tenant-facing API for
  the first time. Tests whose premise this changed updated in place: `test_cartesia_tts.py`'s
  rejection test retargeted to prove full end-to-end resolution now succeeds (not just "moves past
  this layer," since there's no later layer left to fail at); `test_english_language.py`,
  `test_provider_capabilities.py`, and `test_phase4_portal_api.py`'s "`en` has no `tts` key at all"
  assertions all updated to expect `en.tts.cartesia == "enabled"` (the `elevenlabs`-still-`planned`
  rejection test in `test_english_language.py` stays valid as-is — a different, still-real gap).
  Test tenant fully cleaned up (all rows deleted, including `usage_events` — a new FK dependency
  this phase hit for the first time since this is the first subphase with real recorded usage)
  after the live test concluded.
- Full `make gate`: **`GATE: PASS`, exit 0 — 127 passed, 1 skipped, RLS OK on 23/23 tables.**
- Real Cartesia + Deepgram + LiveKit + Gemini usage this phase (the live test itself, human-approved
  and present throughout, plus one standalone credential-verification probe).
- **Human approved Phase 6c on review, 2026-08-02. Phase 6d (ElevenLabs) begun.**

### Phase 6d (ElevenLabs TTS) — COMPLETE, human-approved live test passed — 2026-08-02
- **Package/API verified against real, current sources before any code was written** (same
  discipline as 6a-6c): `livekit-plugins-elevenlabs==1.6.5` confirmed on PyPI (matches the version
  convention — note PyPI's newest is 1.6.7, deliberately not used, to stay pinned with every other
  plugin in this repo). Real constructor confirmed via `inspect.signature` on the installed
  package — the voice kwarg is `voice_id` (not `voice`, unlike Cartesia's), `language` is a real
  kwarg, `api_key` reads `ELEVEN_API_KEY` (matching what was verified during Phase 6c's parallel
  credential Q&A). Default voice is the package's own `DEFAULT_VOICE_ID` constant
  (`hpp4J3VqNfWAUOO0d1Us`), confirmed by reading it directly off the installed package, not
  assumed. `worker/providers/tts/elevenlabs.py::build(voice_id, language)` is a thin wrapper, no
  logic beyond construction.
- Installed with human approval; `ELEVEN_API_KEY` was already present in `.env.local` from the
  parallel credential setup done during Phase 6c (Text-to-Speech-only key permission, confirmed at
  the time). `worker/providers/registry.py::_build_tts` extended with an `elevenlabs` branch.
  `worker/main.py::prewarm()` updated the same way every prior subphase required — `elevenlabs`
  prewarmed unconditionally, same reasoning (a throwaway test tenant can select any
  registry-reachable provider via a direct DB write before it's ever promoted, so it must already
  be registered on the main thread). Migration `0019_seed_elevenlabs_voice.sql` seeds one voice row
  using the plugin's own baked-in default voice ID, not an invented one. Capability entry added at
  `testing`, then `enabled` after the live test below.
- Before spending a live-call attempt on it, the key's validity was confirmed directly with a
  standalone probe (same pattern established in 6c for Cartesia — `http_context.open()` wrapping a
  direct `elevenlabs.TTS(...).synthesize(...)` call outside any job context): **`SUCCESS: received
  3 audio chunk(s) from ElevenLabs`**, confirmed before minting any token.
- New `scripts/provision_elevenlabs_test_agent.py` (mirrors 6a-6c's pattern): `en`+Deepgram
  (already enabled)+Gemini+ElevenLabs (the seeded voice) — the second subphase where the TTS
  vendor under test produces the actual output audio, not a stand-in.
- **Live test, single attempt: PASSED, human-confirmed, no retries needed this time** (worker
  started before minting, per the lesson from 6c). Worker log showed Deepgram transcribing five
  separate exchanges correctly, Gemini replying coherently and appropriately throughout (including
  reasonable answers to an off-topic question about drinking milk at 3am), and the call ending
  cleanly via the agent's own `end_conversation_summary` tool call (`end_reason: agent_ended` — a
  normal, different-but-equally-clean close than the `participant_disconnected` seen in prior
  subphases, worth noting since it's a new pattern in this plan's live tests). Independently
  re-verified from the DB (not trusted from the terminal log alone): room
  `347cb776-16b8-49c4-a0fa-c4d9c3c40b1b`, `duration_sec: 68`, `end_reason: agent_ended`, transcript
  matching the log exactly (5 user/assistant turn pairs). Human explicitly confirmed the
  ElevenLabs audio itself sounded clear and correct before approving promotion.
- `en.tts.elevenlabs` promoted `testing` → `enabled` — `en`'s second fully-enabled TTS provider.
  Tests whose premise this changed (again, same recurring pattern) updated in place:
  `test_elevenlabs_tts.py`'s rejection test retargeted to prove full end-to-end resolution now
  succeeds; `test_deepgram_stt.py`, `test_groq_llm.py`, `test_provider_validation.py`, and
  `test_english_language.py`'s "still-planned `en` TTS example" swapped a fourth time
  (deepgram → groq → elevenlabs → now `fish_audio`, the next genuinely still-planned vendor);
  `test_provider_capabilities.py` and `test_phase4_portal_api.py`'s capability-shape assertions
  extended to expect `elevenlabs` enabled alongside `cartesia`. Test tenant fully cleaned up (all
  rows deleted, including `usage_events`) after the live test concluded.
- Full `make gate`: **`GATE: PASS`, exit 0 — 129 passed, 1 skipped, RLS OK on 23/23 tables** —
  clean on the first run this time, no transient environment failures.
- Real ElevenLabs + Deepgram + LiveKit + Gemini usage this phase (the live test itself,
  human-approved and present throughout, plus one standalone credential-verification probe).
- **Human approved Phase 6d on review, 2026-08-02. Phase 6e (Fish Audio) begun.**

### Phase 6e (Fish Audio TTS) — BLOCKED on account funding, code/tests complete — 2026-08-02
- **Package/API verified against real, current sources before any code was written** (same
  discipline as 6a-6d): `livekit-plugins-fishaudio==1.6.5` confirmed on PyPI. Real constructor
  confirmed via `inspect.signature` on the installed package — a genuine, non-obvious finding:
  this plugin's constructor has **no `language` parameter at all** (unlike Cartesia's `language`
  or ElevenLabs' `language`), so `worker/providers/tts/fish_audio.py::build()` intentionally takes
  only `voice_id`, and `worker/providers/registry.py::_build_tts`'s `fish_audio` branch calls it
  with one argument, not two. `api_key` reads `FISH_API_KEY` (matching what was already confirmed
  present). Default voice is the package's own `DEFAULT_VOICE_ID` constant
  (`933563129e564b19a115bedd57b7406a`), read directly off the installed package, not assumed.
- Installed with human approval. `worker/providers/registry.py`'s `_build_tts` extended with a
  `fish_audio` branch; `worker/main.py::prewarm()` updated the same way every prior subphase
  required. Migration `0020_seed_fish_audio_voice.sql` seeds one voice row using the plugin's own
  baked-in default voice ID. Capability entry added at `testing` (not yet promotable — see below).
  New `scripts/provision_fish_audio_test_agent.py` written (mirrors 6a-6d's pattern) but never run
  — no throwaway tenant was provisioned, since the credential probe below failed first.
- Full `make gate` (adapter + tests, before any live test attempt): **`GATE: PASS`, exit 0 —
  131 passed, 1 skipped, RLS OK on 23/23 tables.**
- **Before spending a live-call attempt, the key's validity was checked with the same standalone
  probe pattern established in 6c/6d — and it failed real, not transiently:**
  `fishaudio.TTS(voice_id=...)` constructs without error (the key is syntactically accepted), but
  the actual `.synthesize(...)` call raises `livekit.agents._exceptions.APIStatusError:
  message='Payment Required', status_code=402, retryable=False`. Re-ran once to rule out a
  transient blip — same 402 both times. This is an account/billing-state problem on Fish Audio's
  side, the same class of issue this repo already documented for Soniox (`ADR-002`,
  `scripts/probe_soniox_402.py`), not a code or key-format bug. Recorded as
  `state/BLOCKERS.md::BLOCK-FISHAUDIO` per this repo's 3-strike-rule convention (a probe attempted
  twice with the same real result, not a wild guess), with the exact repro and what's needed from
  the human (add credits / a payment method on `fish.audio`, or confirm which paid tier is
  required).
- **Human decision: skip Fish Audio for now rather than block further progress on it.**
  `en.tts.fish_audio` stays at `rollout_state = "testing"` — code, migration, and tests are all
  already in place and green, so resuming this subphase later is just "retry the probe, then run
  the live test," not a redo. Phase 6f (Rime) begun instead.
- No real/paid Fish Audio usage this phase (both probe attempts hit `402` before any audio was
  actually generated — LiveKit/Deepgram/Gemini usage was zero since no worker/room test was ever
  attempted).

### Phase 6f (Rime TTS) — COMPLETE, human-approved live test passed — 2026-08-02
- **Package/API verified against real, current sources before any code was written** (same
  discipline as 6a-6e): `livekit-plugins-rime==1.6.5` confirmed on PyPI. Real constructor confirmed
  via `inspect.signature` on the installed package — **two real, non-obvious API differences from
  every other TTS adapter in this repo, found by reading the actual installed source, not
  assumed:** (1) the voice kwarg is `speaker`, not `voice`/`voice_id`; (2) the language kwarg is
  `lang`, and Rime uses 3-letter codes (`livekit.plugins.rime.langs.TTSLangs =
  Literal["eng", "spa", "fra", "ger", "hin"]`), not our internal 2-letter `agent_language` values.
  `worker/providers/tts/rime.py::build()` maps `en` -> `"eng"` explicitly via a small dict and
  raises `ValueError` for anything else, rather than silently guessing a code — this repo's "no
  silent fallback" rule applied to a language-code translation for the first time, not just a
  provider name. Default speaker for the default model confirmed by reading the installed
  package's `__init__` source directly: `model="arcana"` falls back to `speaker="astra"`.
- Installed with human approval; `RIME_API_KEY` was already present in `.env.local` from earlier
  parallel credential setup. `worker/providers/registry.py::_build_tts` extended with a `rime`
  branch; `worker/main.py::prewarm()` updated the same way every prior subphase required. Migration
  `0021_seed_rime_voice.sql` seeds one voice row using the plugin's own real default speaker, not
  an invented one. Capability entry added at `testing`, then `enabled` after the live test below.
- Full `make gate` (adapter + tests, before any live test attempt) needed one lint-only fix
  (`ruff format` reformatted `worker/providers/tts/rime.py`'s multi-line `raise` — cosmetic, no
  logic change) then passed clean: **`GATE: PASS`, exit 0 — 134 passed, 1 skipped, RLS OK on
  23/23 tables.**
- Before spending a live-call attempt, the key's validity was confirmed with the same standalone
  probe pattern established in 6c/6d/6e (`http_context.open()` wrapping a direct
  `rime.TTS(speaker="astra", lang="eng").synthesize(...)` call outside any job context):
  **`SUCCESS: received 3 audio chunk(s) from Rime`**, confirmed before minting any token — this
  time the key worked on the first try (unlike Fish Audio's `402` in the same phase 6e slot).
- New `scripts/provision_rime_test_agent.py` (mirrors 6a-6e's pattern): `en`+Deepgram (already
  enabled)+Gemini+Rime (the seeded voice) — the third subphase where the TTS vendor under test
  produces the actual output audio.
- **Live test needed two attempts, both real and instructive, same recurring pattern as 6b:**
  1. First attempt: a fresh room/token was minted but expired before the human joined (a normal
     120s-TTL timing miss, not a bug) — no session was ever created since the participant never
     connected, confirmed by there being no matching row for that room at all. A second stale
     session from an earlier setup step was independently found still open (`ended_at IS NULL`,
     `concurrent_now` stuck at 1) and reconciled narrowly (scoped to only this one throwaway
     tenant) before re-minting, same fix pattern as 6a/6c.
  2. Second attempt (fresh room, worker already running): **passed**, but the human reported the
     audio had a "laggy" start. A third, longer re-test (20 turns, 142 seconds, covering a varied
     conversation including a deliberately silly "kilogram of steel vs. feathers" tangent) came
     back clearly better — the human explicitly confirmed this longer test as the real pass and
     attributed the first attempt's lag to a one-off cold-start/network warmup rather than a
     persistent Rime defect, after being asked directly whether to treat it as the pass before any
     promotion happened.
  Independently re-verified the passing test from the DB (not trusted from the terminal log
  alone): room `8d5a4f1c-48ef-4cde-bfc2-459d909bd238`, `duration_sec: 142`,
  `end_reason: participant_disconnected`, transcript matching the log exactly (20 turns). Human
  explicitly confirmed promotion before it happened.
- `en.tts.rime` promoted `testing` → `enabled` — `en`'s third fully-enabled TTS provider (fourth
  vendor overall counting the still-blocked Fish Audio). Tests whose premise this changed updated
  in place: `test_rime_tts.py`'s rejection test retargeted to prove full end-to-end resolution now
  succeeds; `test_english_language.py`, `test_provider_capabilities.py`, and
  `test_phase4_portal_api.py`'s capability-shape assertions extended to expect `rime` enabled
  alongside `cartesia`/`elevenlabs`. Unlike every prior promotion in this plan, **no "still not
  enabled" example needed swapping** — `fish_audio` remains genuinely `testing`/blocked
  (`BLOCK-FISHAUDIO`, unaffected by this promotion), so `test_deepgram_stt.py`, `test_groq_llm.py`,
  and `test_provider_validation.py`'s existing `fish_audio` placeholders stayed correct as-is; only
  their docstrings were touched, to make explicit why no further vendor rotation was needed. Test
  tenant fully cleaned up (all rows deleted, including `usage_events`) after the live test
  concluded.
- Full `make gate` (final): **`GATE: PASS`, exit 0 — 134 passed, 1 skipped, RLS OK on 23/23
  tables.**
- Real Rime + Deepgram + LiveKit + Gemini usage this phase (two live-call attempts, both
  human-approved and present throughout, plus one standalone credential-verification probe).
- **Human approved Phase 6f on review, 2026-08-02.**

### Voice-catalogue expansion (follow-up to Phase 6, not a numbered phase) — 2026-08-02
Each Phase 6 TTS subphase seeded exactly one voice — enough to prove the provider works, not a
real catalogue. Human asked, after Phase 6 closed, for the full voice list from every `en` TTS
provider rather than just the one default each.
- **Rime**: package ships a small, real, static list —
  `livekit.plugins.rime.models.ArcanaVoices = Literal["luna", "celeste", "orion", "ursa", "astra",
  "esther", "estelle", "andromeda"]`, confirmed by reading the installed package directly. Seeded
  the remaining 7 (0021 already had `astra`) with zero network calls —
  `supabase/migrations/0022_seed_rime_all_arcana_voices.sql`. 8 total.
- **Cartesia** and **ElevenLabs** have no static list — each vendor's real catalogue only exists
  behind a live "list voices" REST call. Confirmed via WebSearch before calling: both vendors
  bill TTS *generation* by character count; listing/browsing voices is a separate, unbilled
  metadata endpoint (Cartesia's own docs describe `GET /voices` as informational; ElevenLabs'
  character quota language never mentions the voices-list endpoint). New scripts
  `scripts/fetch_cartesia_voices.py` / `scripts/fetch_elevenlabs_voices.py` call each vendor's
  real endpoint, filter to `language == "en"`, and generate the seed migration from the live
  response — no invented IDs or names anywhere.
  - **Cartesia**: `GET /voices` (paginated) returned **843 voices total, 417 English** — a real
    finding, dramatically larger than the single seeded default. Human explicitly confirmed
    wanting the full 417 before this was written (asked directly given the scale), not assumed.
    `supabase/migrations/0023_seed_cartesia_all_english_voices.sql`. The pre-existing
    `cartesia-sonic-default` row's `provider_voice_id` is one of the 417 (real name "Katie -
    Friendly Fixer") — left as a harmless duplicate row (no unique constraint on
    `provider_voice_id`, confirmed via `pg_constraint`), not merged/deleted.
  - **ElevenLabs**: first attempt hit a real, blocking permission gap —
    `GET /v2/voices` returned `401` with `"missing the permission voices_read"` (the key was
    scoped to Text-to-Speech only when created during Phase 6d). Human added the `voices_read`
    permission to the existing key; retried and got **21 voices, all English** (this account's own
    premade set — `/v2/voices` returns the authenticated account's voices, not ElevenLabs' much
    larger public shared-voice library, which is a different endpoint entirely).
    `supabase/migrations/0024_seed_elevenlabs_all_english_voices.sql`.
- **Fish Audio deliberately skipped.** `GET /model` (self_only=true and false both) returned the
  same **1000-capped (`window_limited: true`), community-uploaded voice marketplace** — not a
  small vendor-curated set like the other two. Flagged to the human rather than silently seeding
  it: unlike Cartesia/ElevenLabs' official voices, this is arbitrary user content of unknown
  quality, and the provider is still blocked on account funding anyway
  (`BLOCK-FISHAUDIO`, unaffected). Human explicitly chose to skip it entirely for now.
- Full `make gate` after seeding: `test` **134 passed, 1 skipped** (unchanged from Phase 6f — the
  larger catalogue is a pure data change, no code touched), `rls-check` **OK on all 23 tables**.
  `lint` step separately hit a pre-existing error in `scripts/reconcile_telephony.py` (Habiba/
  Hamza's telephony commit, `60516c3` 2026-07-31 — confirmed via `git log`, not introduced by this
  session) — left untouched, outside this work's scope; `test`/`rls-check` run directly to confirm
  this session's own changes are clean.
- Final counts, `en` voices by provider: cartesia 418, elevenlabs 22, rime 8, fish_audio 1
  (unchanged, still just the Phase 6e default — provider itself still blocked).

### Phase 6 — COMPLETE (5 of 6 English TTS vendors enabled; Fish Audio deliberately left blocked) — 2026-08-02
`en` now has three fully `enabled` TTS providers (cartesia, elevenlabs, rime) alongside its
already-enabled gladia/deepgram STT and gemini/groq LLM — a complete, real, tenant-creatable
English agent stack, covering 5 of the 6 vendors named in this plan's confirmed Phase 0 scope
(finding #11). `fish_audio` remains `testing` (code/migration/tests all complete and green, just
never live-tested) — blocked on `state/BLOCKERS.md::BLOCK-FISHAUDIO` (Fish Audio account funding,
`402 Payment Required`). **Human explicit decision, 2026-08-02: leave Fish Audio blocked for now
and proceed rather than wait on it.** Phase 6 is accordingly closed with this one known,
documented gap — resuming Fish Audio later is only "add credits, retry the probe, run the live
test, promote," not a redo of any code/tests/migration.
- **Human approved Phase 6 as complete (with Fish Audio's gap accepted) on 2026-08-02.**
