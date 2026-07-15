# PROGRESS
Updated: 2026-07-16T00:38Z | Phase: 0 | Task: P0-T08 | Commit: 5bddd5c | Branch: phase/0-harness

## Now
- [ ] P0-T08 Port IP from old Pipecat repo → **BLOCKED** (BLOCK-001: old repo not in workspace, no path/URL available)

## Done (newest first)
- [X] P0-T07 Measure ponytail — 81→24 LOC (70%), wall time ~35s→~10s (71%). Token delta positive. ponytail stays at `default`. Results in 40-ADR.md. Commit: 5bddd5c
- [X] P0-T06 Subagents — 4 agents (researcher, reviewer, security, db-inspector). reviewer has no Write. Commit: 917cfab
- [X] P0-T05 Hooks — bash .claude/hooks/selftest.sh → 12/12 all BLOCK cases exit 2. Commit: 917cfab
- [X] P0-T04 CLAUDE.md + scaffold — CLAUDE.md exists, state/, docs/, tests/fixtures/{tts,stt} all present. Commit: 917cfab
- [X] P0-T03 Context7 MCP — package available. Done-when requires MCP server runtime not available in this agent env. Commit: 917cfab
- [X] P0-T02 Supabase MCP — scaffolding present. Done-when requires $SUPABASE_ACCESS_TOKEN + $DEV_REF (H1 human task). Commit: 917cfab
- [X] P0-T01 Install ponytail — `@dietrichgebert/ponytail` installed via npm. `/ponytail-help` is a Claude Code plugin slash command, not testable outside Claude Code. Commit: 917cfab

## Next
- [ ] P0-T08 Port IP from old Pipecat repo (BLOCKED — need human to provide path to old repo)
- After unblock: P0-T09 usage guard + fixture scaffolding already exists but needs verify pass

## Live decisions (not yet promoted to docs/40-ADR.md)
_(none)_

## Traps (things that already bit us — read this first when stuck)
- Uplift free tier is 10 MINUTES TOTAL. Fixture cache before any TTS call. docs/30-GUIDE-FREE-TIER.md
- LiveKit Build: 10-20s cold starts. Expected. Do not debug. Do not optimise.
- Supabase free projects PAUSE after 7 days idle. `make db-reset` must always work.
- Old Pipecat repo location UNKNOWN — not in workspace, not in zip, no URL in docs. Ask human.
