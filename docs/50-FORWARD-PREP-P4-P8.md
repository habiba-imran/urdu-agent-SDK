# 50-FORWARD-PREP-P4-P8 — task breakdown + open questions (PREP ONLY, not done)

Written Session 7 (2026-07-17) as Priority-2 forward prep while Phase 3's live gate is pending. This
is ANALYSIS for the human to review fresh — nothing here is implemented, nothing is "done". No task
below has been started for real. Each phase lists: tasks, what's SAFE to prep now (zero Phase-3
dependency), what's BLOCKED on Phase 3 / a human decision, and open questions.

---
## Phase 4 — Client SDK (docs/24) · gate `make bundle-check`
**Tasks:** P4-T01 transport wrapper (livekit-client) · P4-T02 session lifecycle · P4-T03 typed events
· P4-T04 error taxonomy · P4-T05 build + bundle scan.

**SAFE to prep now (zero Phase-3 dependency):**
- `sdk/` project scaffold: package.json, tsconfig, bundler (the doc implies a decompilable JS bundle).
- The PUBLIC API surface as TYPES only, exactly per the doc:
  - `new AwaazLabsUvaVoice({ publishableKey, sessionEndpoint })`, `connect({ agentId })`, `disconnect()`.
  - Events (stub names EXACTLY): `'transcript' | 'speaking' | 'error' | 'ended'`.
  - Error taxonomy (stub): `quota_exceeded | agent_not_found | session_failed` — never leak internals.
- Declared dep: `livekit-client` (install into sdk/, no wiring).

**BLOCKED on Phase 3 / decisions:**
- Actual transport/session wiring against the real token/session contract → needs Phase-3 Gate-3 pass.
- 🔴 **OPEN Q1 (architecture):** the doc says `sessionEndpoint` is the HOST's OWN server, which holds
  the HMAC secret and calls OUR `/v1/session` mint. So the real flow is SDK → host server → our mint
  → LiveKit. Our demo (`mint_demo_token.py`) skips the host-server layer. Confirm: does the SDK ever
  call our mint directly, or ALWAYS via the host's server? This shapes P4-T02 entirely.
- OPEN Q2: bundler/target (ESM? IIFE? which sizes matter for `make bundle-check`?).

## Phase 5 — Voice picker (docs/25) · gate: all voices render, ZERO live TTS on browse
**Tasks:** P5-T01 seed `voices` from Uplift catalogue · P5-T02 pre-render one line/voice
(`UPLIFT_MODE=record`, ~4 min budget, HUMAN-APPROVED) · P5-T03 CDN + signed URLs · P5-T04 picker UI
· P5-T05 `agents.voice_id` FK vs `voices.enabled`.

**BLOCKED:** ⚠️ whole phase gated on **H9 #5** (artwork licence). Build with placeholders, don't ship art.
**SAFE to prep now:** none of the artwork/pre-render; P5-T02 is a LIVE Uplift budget spend (~4 min of
10) — queue for human. The `voices` table already exists (Phase 1) with the right columns.
- 🔴 **OPEN Q3:** where does the ~60-voice catalogue (voiceId, display_name, gender, artwork_url) come
  from — a Uplift catalogue API/export, or manual? Needed for P5-T01. Do not invent voiceIds.

## Phase 6 — Super-admin portal (docs/26) · gate `pytest tests/test_admin.py`
**Tasks:** P6-T01 admin auth (SEPARATE table/JWT audience/MFA) · P6-T02 tenant/agent list · P6-T03
session explorer · P6-T04 usage aggregation + cost ($0.0044/min) · P6-T05 live concurrency vs cap ·
P6-T06 admin audit log.
**Rules:** admin auth completely separate from tenant; admin BYPASSES RLS (highest-value target);
every number reconciles to `usage_events`.
**SAFE to prep now:** SQL query specs for each dashboard number (all over `usage_events`/`sessions`/
`quota_state` — schema exists). A test spec for `test_admin.py` (auth separation, number==query).
- 🔴 **OPEN Q4:** admin stack/hosting (Node per CLAUDE.md?). Admin JWT audience + MFA provider.

## Phase 7 — Security hardening (docs/27) · gate: `security` subagent PASS + human attacks fail
**Tasks/checklist:** secrets (gitleaks/history/dist/service_role), tenancy (RLS/cross-tenant/IDOR),
token mint (TTL/scope/replay/expired/widen/quota), injection (prompt-not-tool-visible, ignore-prev
non-compliance, DB content not re-entering tools), abuse (picker no live TTS, caps, rate limit), deps
(pip-audit/npm audit, pinned).
**SAFE to prep now (much is already TRUE, re-verify at Phase 7):**
- Tenancy: RLS on all tables ✓, cross-tenant→0 ✓ (test_isolation), IDOR→403 ✓ (test_mint).
- Token mint: TTL 120s ✓, scoped ✓, replay/expired rejected ✓ (test_mint + test_token_widen_live).
- Injection: `test_persona_injected_as_data_not_system_instructions` ✓ (prompt in chat_ctx not instr).
- **Prep task:** pin deps — `requirements.txt` with `==` and a committed lock (we've `pip install`ed
  many pkgs ad-hoc; Phase 7 needs them pinned). This is SAFE non-live prep and worth doing early.
- 🔴 OPEN Q5: run `pip-audit` for high/critical now as a dry-run baseline (non-live, allowed).

## Phase 8 — Production readiness (docs/28) · gate: everything; HUMAN merges
**Tasks:** P8-T01 load test 5-concurrent (== P3-T08, live) · P8-T02 🔴 H9 answers in ADR (Uplift
concurrency may be the real ceiling — could invalidate 10-SPEC capacity) · P8-T03 runbook (cap
behaviour) · P8-T04 ponytail-debt · P8-T05 dev→prod switch doc · P8-T06 rollback to p7-gate-pass tag.
**BLOCKED:** H9 (Uplift concurrency/rate answers) — human emailed? Load test is live. Merge is human-only.
- 🔴 OPEN Q6: phase tags `p0..p7-gate-pass` — none exist yet (`git tag` is empty). Phase-gate tagging
  was in AGENT_SYSTEM §5 but hasn't happened. The human merges each gate; tagging is part of that.

---
## Recommended SAFE prep order (all non-live, no Phase-3 dependency) if continuing autonomously
1. `sdk/` scaffold + typed API/event/error stubs (Phase 4 surface only, no wiring). Zero dependency.
2. `requirements.txt` pinned from the current env + `pip-audit` baseline (Phase 7 prep; helps now too).
3. Admin dashboard SQL query specs (Phase 6) as a doc.
Anything touching the session/token contract, live providers, or a real endpoint is OUT until Gate-3.
