# PROGRESS
Updated: <ISO8601> | Phase: 0 | Task: P0-T01 | Commit: <sha> | Branch: phase/0-harness

## Now
- [ ] P0-T01 Install ponytail
      guide:     docs/20-PHASE-0-HARNESS.md
      done when: /ponytail-help lists commands
      free-tier: none
      attempt:   1/3

## Done (newest first)
_(none)_

## Next
- [ ] P0-T02 Supabase MCP (read-only, dev, minimal features)

## Live decisions (not yet promoted to docs/40-ADR.md)
_(none)_

## Traps (things that already bit us — read this first when stuck)
- Uplift free tier is 10 MINUTES TOTAL. Fixture cache before any TTS call. docs/30-GUIDE-FREE-TIER.md
- LiveKit Build: 10-20s cold starts. Expected. Do not debug. Do not optimise.
- Supabase free projects PAUSE after 7 days idle. `make db-reset` must always work.
