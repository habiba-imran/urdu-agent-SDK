# BLOCKERS — 3-strike escalations
> Same failure 3x -> STOP. Write it here. Ask the human. DO NOT try a 4th approach.
> Human takes it to Claude chat -> answer lands in docs/42-RESEARCH-QUEUE.md.

## Template
```
## BLOCK-nnn | P<n>-T<nn> | <ISO8601>
**Expected:**
**Actual:**
**Tried:** (1) ... -> result  (2) ... -> result  (3) ... -> result
**Hypothesis:**
**Need from human:**
**STATUS: BLOCKED — P<n>-T<nn+1> does not start**
```

## Open

## BLOCK-001 | P0-T08 | 2026-07-16T00:35Z
**Expected:** Old Pipecat repo with `persona.py`, `tools.py`, `db.py`, `tests/` CER harness, `DECISIONS.md` at a known path in this workspace.
**Actual:** Searched E:\Finova-Internal\Urdu-Voice-Agent-SDK and all parent directories. No Pipecat .py files found. The uva-agent-system.zip also does not contain them. Architecture doc (11-ARCHITECTURE.md line 52-53) references these files but provides no path or clone URL.
**Tried:** (1) `dir /s /b *.py` across workspace — no persona.py/tools.py/db.py (2) grep for pipecat path references in all .md files — no path or URL found (3) checked zip file contents — not included
**Hypothesis:** The old Pipecat repo lives outside this workspace (possibly on another machine or in a different directory not shared). The handoff notes say to "port from the old Pipecat repo" but the repo is not accessible to this agent.
**Need from human:** Path to the old Pipecat repo (absolute path or clone URL), OR confirmation that the old repo is unrecoverable and P0-T08 should be written from scratch.
**STATUS: BLOCKED — P0-T08 cannot proceed without the source files**
