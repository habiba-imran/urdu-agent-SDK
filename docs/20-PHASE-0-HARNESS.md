# PHASE 0 — HARNESS
**Goal:** the harness that makes every later phase safe. No product code.
**Gate:** `make gate0`

## Tasks
### P0-T01 Install ponytail (default intensity)
```
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```
**Done when:** `/ponytail-help` lists commands. **Free-tier:** none.
⚠️ `default`, NEVER `extremist`. See 40-ADR.md ADR-004.

### P0-T02 Supabase MCP — read-only, dev, minimal
```bash
claude mcp add supabase -e SUPABASE_ACCESS_TOKEN=$SUPABASE_ACCESS_TOKEN -- \
  npx -y @supabase/mcp-server-supabase@latest \
  --read-only --project-ref=$DEV_REF --features=database,docs
```
**Done when:** `list_tables` returns `[]` with no error.
🔴 Token in `-e`, **NEVER** in args (args land in git history). Full rationale: 33-GUIDE-SUPABASE.md.

### P0-T03 Context7 MCP — kills the #1 hallucination source
```bash
claude mcp add context7 -- npx -y @upstash/context7-mcp
```
**Done when:** `resolve-library-id "livekit agents"` returns a hit.
**Why:** inventing LiveKit/Uplift/Supabase API signatures is the most likely failure. Context7 serves live docs.

### P0-T04 Write CLAUDE.md + scaffold
`/init`, then **replace** with the CLAUDE.md in this repo. Create `docs/ state/ supabase/ scripts/ tests/fixtures/{tts,stt}`.
**Done when:** `test -f CLAUDE.md && test -d state && test -d tests/fixtures/tts`

### P0-T05 Hooks
Write `.claude/settings.json` + `hooks/{guard-bash,test-guard,gate,lint}.sh`, `chmod +x`.
**Done when:** `bash .claude/hooks/selftest.sh` → all BLOCK cases exit 2.
🔴 **The most important task in Phase 0.** CLAUDE.md is followed ~70%; hooks ~100%.

### P0-T06 Subagents
Write `.claude/agents/{researcher,reviewer,security,db-inspector}.md` with tool scoping.
**Done when:** `/agents` lists all four; `reviewer` has no Write tool.

### P0-T07 MEASURE PONYTAIL — do not skip
Pick one real task. Run it twice: `/ponytail-off` then `/ponytail-default`. Record tokens, wall time, LOC.
**Done when:** `docs/40-ADR.md` ADR-004 has REAL numbers from OUR model.
**If the token delta is negative → disable it and say so in the ADR.** Vendor claims are not evidence.

### P0-T08 Port IP from the old repo
`persona.py`, `tools.py`, `db.py`, **all of `tests/`**, `DECISIONS.md` → `40-ADR.md` D-numbers.
**Done when:** `pytest tests/ -q --collect-only` collects the CER harness.
❌ Do NOT port: `bot.py`, `services/uplift_tts.py`, `processors.py`, `static/`.

### P0-T09 Usage guard + fixture scaffolding
`scripts/usage_guard.py`, `scripts/fixture_stats.py`, `state/usage_ledger.json`, `services/tts_cache.py` (30-GUIDE-FREE-TIER.md §2).
**Done when:** `make usage` prints a ledger with 0 spend and the budget from 30-GUIDE §3.

## GATE 0
```bash
make gate0   # -> node -v; git clean; .env gitignored; hooks selftest; /agents=4;
             #    fixtures dirs; ADR-004 has real numbers; usage ledger exists
```
**Then STOP.** Post output. Human says "begin Phase 1".
