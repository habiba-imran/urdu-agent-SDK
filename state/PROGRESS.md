# PROGRESS
Updated: 2026-07-16 | Phase: 0 | Task: P0-T09 | Commit: <pending> | Branch: phase/0-harness

## Now
- [ ] P0-T09 Usage guard + fixture scaffolding — usage_ledger.json + scripts/ present; verify pass

## Done (newest first)
- [X] P0-T08 Port IP from old Pipecat repo → persona.py, tools.py, db.py, config.py, session_state.py, tests/ (12 files), DECISIONS.md folded into 40-ADR.md. CER harness: `pytest tests/ -q --collect-only` → 7 tests. Commit: <pending>
- [X] P0-T07 Measure ponytail — 81→24 LOC (70%), wall time ~35s→~10s (71%). Token delta positive. ponytail stays at `default`. Results in 40-ADR.md. Commit: 5bddd5c
- [X] P0-T06 Subagents — 4 agents (researcher, reviewer, security, db-inspector). reviewer has no Write. Commit: 917cfab
- [X] P0-T05 Hooks — bash .claude/hooks/selftest.sh → 12/12 all BLOCK cases exit 2. Commit: 917cfab
- [X] P0-T04 CLAUDE.md + scaffold — CLAUDE.md exists, state/, docs/, tests/fixtures/{tts,stt} all present. Commit: 917cfab
- [X] P0-T03 Context7 MCP — package available. Done-when requires MCP server runtime not available in this agent env. Commit: 917cfab
- [X] P0-T02 Supabase MCP — scaffolding present. Done-when requires $SUPABASE_ACCESS_TOKEN + $DEV_REF (H1 human task). Commit: 917cfab
- [X] P0-T01 Install ponytail — `@dietrichgebert/ponytail` installed via npm. `/ponytail-help` is a Claude Code plugin slash command, not testable outside Claude Code. Commit: 917cfab

## Live decisions (not yet promoted to docs/40-ADR.md)
- **Pipecat stubs at `pipecat_stubs/`** — tools.py imports `pipecat.adapters.schemas.FunctionSchema` and `pipecat.services.llm_service.FunctionCallParams`. Created minimal shims with equivalent dataclasses. In Phase 3, `tools.py` must be adapted to LiveKit Agents' function-calling API (different schema format, different callback model).
- **`../urdu-voice-agent/processors.py` not ported fully** — only `sanitize_text()` and stub classes ported. The full `OutputSanitizer`, `InputGuard`, `TurnMetricsObserver`, `NumberDictationPatience`, `InterimPromoter` are Pipecat-specific pipeline processors. Phase 3 must reimplement equivalents on LiveKit Agents.
- **`../urdu-voice-agent/tests/helpers_pipeline.py` not ported** — uses Pipecat Pipeline/Task infrastructure directly. Tests that depend on it (`test_interruption.py`, `test_latency.py`) are marked `@pytest.mark.skip` in `test_harness.py` until Phase 3.

## Traps (things that already bit us — read this first when stuck)
- Uplift free tier is 10 MINUTES TOTAL. Fixture cache before any TTS call. docs/30-GUIDE-FREE-TIER.md
- LiveKit Build: 10-20s cold starts. Expected. Do not debug. Do not optimise.
- Supabase free projects PAUSE after 7 days idle. `make db-reset` must always work.
- supabase-py v2 uses `create_async_client` (not `acreate_client` as in the old repo — db.py fixed)
