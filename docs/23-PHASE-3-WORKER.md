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
### P3-T08 🔴 CONCURRENCY TEST NOW — not Phase 8 (audit gap #16)
5 simultaneous calls (LiveKit Build cap). Done: 5 succeed, 6th fails **cleanly** with a typed error.
*Finding a concurrency flaw in week 8 is a rewrite. In week 3 it's an afternoon.*

### P3-T09 🔴 Wire `tools.py` onto LiveKit's function-calling API — found live 2026-07-17, TOP PRIORITY
**Not started. Do this before any further quality polish.** Gate-3's successful live call showed
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

**Bigger open question — NOT a coding detail, needs a human decision before implementation
starts:** `tools.py`'s handlers (`search_products`, `create_reservation`, etc.) query Supabase
tables (`products`, `customers`, `reservations`, `support_tickets`, `callbacks`, `shop_info`) that
**do not exist in this repo's actual schema** — `state/PROGRESS.md`'s own CER-harness note already
flags this: *"the ported tests query old Pipecat-era TechZone tables... that don't exist in this
repo's schema (`tenants`, `agents`, `sessions`, `quota_state`, `usage_events`, `voices`). The CER
harness was written against a completely different database."* So even a correctly-wired
function-calling layer would still hit a missing-table error the moment a tool actually tries to
query. **This raises a scoping question the next session should answer explicitly, not assume:**
is `tools.py`'s hardcoded TechZone-laptop-shop tool suite meant to be (a) a permanent demo/test
fixture for Gate-3-style human-listen calls only, needing its own small demo schema/seed data, or
(b) something that needs to become tenant-configurable (each tenant defines their own tools/catalog)
as part of the real multi-tenant product — a much larger design question, closer to Phase 4/5/6
territory than a Phase-3 bugfix. **Do not silently pick one; ask.**

**Done when (draft, to be refined by whoever picks this up):** `pytest` gate proving `search_products`
is invoked as a real LiveKit tool (not text) and returns real data from a schema that actually
exists; a live call where a price/stock claim is traceably grounded in a tool result, not
LLM-invented text.

## GATE 3
```
[ ] tests/test_worker.py green
[ ] one live Urdu call, e2e, human-listened          <- HUMAN GATE
[ ] latency recorded (will NOT hit 800ms on Gladia — expected, note it, move on)
[ ] CER harness runs against fixtures
[ ] 5 concurrent OK, 6th fails cleanly
[ ] STT_PROVIDER=soniox -> 402
[ ] make usage -> under budget
```
