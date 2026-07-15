# Urdu Voice Agent SDK — agent-built

## Human, start here
1. `docs/41-HUMAN-TASKS.md` — do H1–H8. **Send H9 today** (blocks Phase 8).
2. Open Claude Code. Paste:
   > Read CLAUDE.md and AGENT_SYSTEM.md. Then read docs/20-PHASE-0-HARNESS.md and execute it.
   > Do not write product code. Run Gate 0 and show me the output.
3. Confirm Gate 0. Say "begin Phase 1".

## Map
| File | What |
|---|---|
| `CLAUDE.md` | auto-loaded router (~50 lines). Keep it short — long files degrade compliance. |
| `AGENT_SYSTEM.md` | the operating system: loop, topology, escalation, handoff |
| `docs/00-INDEX.md` | **routing table** — the agent loads ONE guide, not all |
| `docs/2x-PHASE-*.md` | one guide per phase, with machine-checkable gates |
| `docs/3x-GUIDE-*.md` | topic guides (free-tier, security, testing, supabase) |
| `docs/40-ADR.md` | decision log — read before deciding, append after |
| `state/` | live: PROGRESS (every task), HANDOFF, BLOCKERS |
| `.claude/hooks/` | **the enforcement layer.** CLAUDE.md ≈70% obeyed; hooks ≈100%. |
| `.claude/agents/` | one writer (you), four read-only reviewers |

## The three rules that matter
1. **Free tier**: Uplift is 10 minutes TOTAL. Fixtures, not account rotation. `docs/30-GUIDE-FREE-TIER.md`
2. **3 strikes**: same failure 3× → STOP → `state/BLOCKERS.md` → ask the human.
3. **The gate is truth**: red gate = not done, regardless of how good the reasoning was.

## Verify the harness
```bash
bash .claude/hooks/selftest.sh    # 12 blocking rules — must be 12/12
python3 scripts/usage_guard.py --report
```
