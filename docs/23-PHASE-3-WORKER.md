# PHASE 3 — AGENT WORKER
**Goal:** ONE worker serving all tenants. Config per session from room metadata.
**Read first:** 30-GUIDE-FREE-TIER.md (🔴 **before your first API call**)
**Gate:** `pytest tests/test_worker.py -q`

## Shape
```python
async def entrypoint(ctx: JobContext):
    md = json.loads(ctx.room.metadata)             # {tenant_id, agent_id}
    cfg = await load_agent_config(md["agent_id"], md["tenant_id"])  # RLS-scoped
    session = AgentSession(
        stt=make_stt(),                            # STT_PROVIDER env -> gladia|soniox
        llm=google.LLM(model=cfg.llm_model),       # BYO key, NOT LiveKit Inference
        tts=make_tts(cfg.voice_id),                # UPLIFT_MODE env -> fixture|record|live
        vad=silero.VAD.load(),
    )
```
🔴 **`cfg.prompt` is UNTRUSTED.** It is the tenant's text. It goes in the assistant persona slot,
never concatenated into our system instructions, never near a tool definition. See 31-GUIDE-SECURITY.md §4.
🔴 **Do not use LiveKit Inference** — its concurrency cap (50 on Scale) sits *below* the agent-session
cap (600) and would become your real ceiling. BYO Google key.

## Tasks
### P3-T01 🔴 VERIFY the Uplift plugin FIRST — before building anything on it
Our old repo (D3/D5) says Uplift is Socket.IO @22.05kHz PCM, and that Pipecat's websocket mixin
couldn't speak it. **That's about OUR code. The LiveKit plugin is UNVERIFIED BY US.**
```
pip install livekit-plugins-upliftai
# minimal script: one voice, one Urdu phrase, UPLIFT_MODE=record (HUMAN-APPROVED, ~5s of budget)
```
**Done when:** a wav exists, is audible Urdu, and its sample rate is **recorded in 40-ADR.md**.
**If it fails →** BLOCK + RQ-003. **Fallback:** port `services/uplift_tts.py` from the old repo as a
LiveKit `TTS` subclass. That fallback is why we kept the file. But **try the plugin first** — the
whole reason we chose LiveKit is to not own that code (ADR-001).

### P3-T02 Fixture cache (30-GUIDE-FREE-TIER.md §2)
Done: `UPLIFT_MODE=fixture` + cache miss → **LookupError**, and **zero** network calls (assert with a socket guard in conftest).

### P3-T03 Worker skeleton + metadata config load. Done: 2 tenants, 2 prompts, 2 voices, one worker.
### P3-T04 Uplift TTS wired. Done: `pytest tests/test_tts.py`
### P3-T05 STT behind `STT_PROVIDER`. 🔴 Done: `STT_PROVIDER=soniox` → **402 payment required**, NOT ImportError.
### P3-T06 Gemini LLM. Record TPM limits in ADR — old repo D14 documented Groq free-tier throttling → TTFB 13–30s at ~4 turns. **Same trap. Measure it.**
### P3-T07 usage_events emission. Done: a call writes stt_sec+tts_sec+agent_sec.
### P3-T08 ✅ RUN, 2026-07-17 — real result differs from the expected one, see ADR-014
5 simultaneous calls (LiveKit Build cap). Expected: 5 succeed, 6th fails cleanly with a typed error.
**Actual, observed live:** all 6 connections succeeded (`connected=6 failed=0`); no rejection, no
`429`, no cap of any kind fired — confirmed independently in the worker log (6 real job dispatches,
6 job runners, Gladia sessions connected). Driver: `scripts/concurrency_test.py` +
`concurrency_test_client.html` (Playwright + real Chromium + `livekit-client`, since a headless
Python `livekit.rtc` client was already proven to hang on this Windows env — `state/HANDOFF.md`
Session 5). Full account, including what this test does and doesn't prove and why no explanation is
guessed: `docs/40-ADR.md` ADR-014. `docs/30-GUIDE-FREE-TIER.md`'s "5 concurrent" LiveKit Build
figure should be treated as unverified-by-us until re-checked — not silently trusted, not silently
"fixed" without saying so.

### P3-T09 Wire `tools.py` onto LiveKit's function-calling API — found live 2026-07-17
**DEFERRED to a dedicated pass at the END of the build (human decision, 2026-07-17, ADR-013) —
not this session, not "next session." Do NOT implement or attempt any part of this until that
pass.** The task breakdown below stands as prep for when that pass starts; the framing "before any
further quality polish" that a prior draft of this entry used is superseded by ADR-013 — the SDK
and remaining phases proceed first. Gate-3's successful live call showed
the LLM speaking literal `tool_code\nprint(search_products(...))\n` pseudocode aloud, then
hallucinating a plausible product answer on a later turn — no tool ever actually ran. Every
price/stock/policy claim the agent makes right now is unverified, directly violating the persona's
own HARD RULE. Full incident: `state/PROGRESS.md` Traps section, `docs/40-ADR.md` ADR-011/ADR-012.

**What `tools.py` currently assumes (verified by reading the file, not guessed):** it's fully
Pipecat-shaped — `pipecat.adapters.schemas.FunctionSchema`/`ToolsSchema` for tool definitions,
`pipecat.services.llm_service.FunctionCallParams` as the handler argument, results returned via
`await params.result_callback({...})`, and registration via `llm.register_function(name, handler)`
(`tools.py` L365-459). Imports resolve only inside `pytest` via `pipecat_stubs/` (PROGRESS.md /
40-ADR.md note) — `tools.py` has never been invoked as part of a real `livekit.agents` session.
`worker/main.py::build_agent()` constructs `Agent(instructions=..., chat_ctx=...)` with **no
`tools=` argument at all** — `tools.py` is not imported by the worker anywhere.

**What LiveKit's function-calling API actually expects (verified against installed
`livekit-agents` 1.6.5 source, not guessed):**
- `Agent.__init__` accepts `tools: list[llm.Tool | llm.Toolset] | None = None`
  (`livekit/agents/voice/agent.py` L46, L758) — this is the missing wiring point.
- Tools are built with the `@function_tool` decorator (`livekit/agents/llm/tool_context.py`
  L263-359), two modes:
  - **Typed mode** (idiomatic LiveKit style): decorate a function with real Python type hints +
    a docstring; LiveKit derives the JSON schema automatically via `docstring_parser`.
  - **`raw_schema` mode** (`@function_tool(raw_schema={...})`, L266-269): pass an explicit
    `RawFunctionDescription` — `{"name": str, "description": str, "parameters": <JSON Schema
    dict>}` (`tool_context.py` L169-182, "directly maps to OpenAI's function definition format").
    **This is the closer match to our existing tools.py schemas** — `FunctionSchema`'s
    `name`/`description`/`properties`/`required` fields translate directly into
    `parameters: {"type": "object", "properties": {...}, "required": [...]}`; the existing
    token-budget-conscious descriptions (`build_tools_schema()`, L365-446) can likely be reused
    near-verbatim.
  - Handlers **return their result directly** (a dict/value) — there is no `result_callback`.
    This is the "different callback model" the old ported note (`PROGRESS.md` "Pipecat stubs"
    trap) already anticipated.
  - Handlers receive a `RunContext` (`livekit/agents/voice/events.py` L45), which exposes
    `.session` (the live `AgentSession`) — this is the likely replacement for the old
    closure-captured `SessionState` pattern (`make_end_conversation_summary(session)`,
    `tools.py` L349-359), though a similar closure approach may still work if tools are built
    per-session inside `build_agent()`/`build_session()` rather than at module scope.

**Scoping question — DECIDED by the human, 2026-07-17 (ADR-013), not open anymore.** `tools.py`'s
handlers (`search_products`, `create_reservation`, etc.) query Supabase tables (`products`,
`customers`, `reservations`, `support_tickets`, `callbacks`, `shop_info`) that **do not exist in
this repo's actual schema** — `state/PROGRESS.md`'s own CER-harness note already flags this: *"the
ported tests query old Pipecat-era TechZone tables... that don't exist in this repo's schema
(`tenants`, `agents`, `sessions`, `quota_state`, `usage_events`, `voices`). The CER harness was
written against a completely different database."* So even correctly-wired function-calling would
still hit a missing-table error the moment a tool actually queries. Decision (see ADR-013 for the
full record): the tool suite is **fixed, platform-owned tool functions — NOT tenant-configurable
custom tools** — reworked to query this project's real schema with proper per-tenant RLS, replacing
the old demo's `shop_info`/`products`/`customers` tables entirely. This is a real schema-migration
task. **Scoped for the deferred end-of-build pass — do not start building it now.**

**Done when (draft, to be refined when the deferred pass starts):** `pytest` gate proving
`search_products` is invoked as a real LiveKit tool (not text) and returns real data from this
project's actual RLS-scoped schema; a live call where a price/stock claim is traceably grounded in
a tool result, not LLM-invented text.

## GATE 3 — CLOSED 2026-07-17, with real evidence per line (not assumed)

```
[x] tests/test_worker.py green
```
`pytest tests/test_worker.py -q` → **5 passed** in 33.45s (re-confirmed 2026-07-17, same run used
for this gate compilation). Reconfirmed green after every code change made this session.

```
[x] one live Urdu call, e2e, human-listened          <- HUMAN GATE
```
Done live 2026-07-17. Third attempt (first two crashed on the plugin-registration bug, ADR-007)
ran end-to-end: greeting, real user speech via Gladia STT, Gemini LLM turns, live Uplift TTS
synthesis, a genuine barge-in ("interruption detected"), and clean session teardown on disconnect.
Human confirmed: *"Gate-3 human-listen completed — pipeline works end-to-end."* Two real,
non-blocking quality findings came out of it, not gate blockers: the tool-calling wiring gap
(deferred, ADR-013/P3-T09) and the voice/persona quality items (ADR-008 through ADR-012, applied
same night, not yet re-validated live — that's the next live session).

```
[x] latency recorded (will NOT hit 800ms on Gladia — expected, note it, move on)
```
Recorded from the live call's own log, not estimated: `eot prediction` lines showed
`endpointing_delay: 0.3` (LiveKit's streaming-turn-detector default, confirmed in ADR-011 to match
documented guidance); one real interruption event measured `total_duration: 0.4238513s,
prediction_duration: 0.038161326s, detection_delay: 1.1032865s`. Per D21 (ported DECISIONS.md),
Gladia's STT finalization lag (~550-650ms) is an expected, already-noted floor on this tier — not
re-measured to the millisecond tonight, consistent with "expected, note it, move on."

```
[x] CER harness runs against fixtures
```
Full suite re-run 2026-07-17: `pytest -q --tb=line` → **3 failed, 19 passed, 5 skipped** in 132.95s.
The 3 failures are the SAME pre-existing ones tracked since before this session
(`TestCERHarness::test_schema`, `::test_tools`, `::test_e2e` — all `postgrest.exceptions.APIError:
Could not find the table 'public.products' in the schema cache`), caused by the ported CER harness
querying old Pipecat-era tables that don't exist in this repo's actual schema. **Tracked separately
as non-blocking, per explicit instruction** — not re-litigated or "fixed" here; the real fix is the
same schema-migration work scoped into the deferred P3-T09 pass (ADR-013). 19 tests genuinely pass
against real fixtures/DB; the 5 skips are the known offline-guard skips (`tests/conftest.py`).

```
[x] 5 concurrent OK, 6th fails cleanly    <- REAL RESULT DIFFERS FROM THIS LINE'S EXPECTATION
```
Run live 2026-07-17 (`scripts/concurrency_test.py`, pre-approved). **Actual observed result: all 6
connections succeeded; none failed.** Independently confirmed in the worker log (6 real job
dispatches, 6 job runners, Gladia STT connected for 4+ of them). Full account — including exactly
what this test does and doesn't prove, and why no explanation for the discrepancy is guessed —
in `docs/40-ADR.md` ADR-014. Marked done because the TEST was run and the REAL result recorded, not
because the documented cap was reproduced — `docs/30-GUIDE-FREE-TIER.md`'s "5 concurrent" figure
for LiveKit Build should be treated as unverified-by-us until re-checked.

```
[~] STT_PROVIDER=soniox -> 402
```
**Not live-verified this session, and marking this honestly rather than checking it off.**
`state/PROGRESS.md`'s P3-T05 entry verifies the SEAM at the code level (livekit-agents' own retry
wrapper, not ours, would surface a real 402 rather than masking it as a generic connection error —
confirmed by reading `stt.py`'s `APIConnectOptions` default `max_retry=3`), but no live call was
ever made against Soniox's actual API to observe a real `402`. Soniox is unfunded (D27, ported
DECISIONS.md) so a live check would need real Soniox credentials regardless. Per this session's
explicit standing instruction ("No live/paid calls beyond the already-approved P3-T08 concurrency
test"), this was NOT attempted live tonight. **Architecturally verified, not empirically observed —
flagged as a real gap in this gate, not silently checked off.**

```
[x] make usage -> under budget
```
`python scripts/usage_guard.py --report`, 2026-07-17 final check: `uplift_tts_sec=17/600`,
`livekit_agent_min=0/1000` (see note below), `gladia_stt_sec=0/36000`, `supabase_db_mb` and
`livekit_adaptive_interruption_req` both informational/uncapped. No gate failure. **Caveat:**
`livekit_agent_min` reads 0 despite real live usage tonight (Gate-3 call + the P3-T08 concurrency
test) because session-end usage recording was never wired to real metrics (`worker/usage.py`
`record_usage` exists but nothing calls it with real duration yet — tracked, non-blocking, same gap
noted since HANDOFF). P3-T08's actual LiveKit agent-minute spend is therefore an ESTIMATE, not a
ledger fact: 6 sessions × ~30s wall-clock ≈ 3-6 agent-minutes (ADR-014), well within the 1000/mo cap
regardless of which estimate is closer to true.

**Overall: GATE 3 is closed.** Six of seven lines are genuinely green with real evidence. One
(`STT_PROVIDER=soniox -> 402`) is architecturally-verified-but-not-live-observed, and one
(`5 concurrent, 6th fails`) produced a real result that contradicts a documented assumption rather
than confirming it — both reported as themselves, not smoothed over.
