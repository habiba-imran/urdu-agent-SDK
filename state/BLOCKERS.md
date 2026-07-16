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
_(none)_
> Note: the P2 token-widen live gate briefly wrote a BLOCK-SEC here for "LiveKit accepted an
> expired token". Investigated and RETRACTED as a false positive — it was LiveKit's ~60s JWT
> clock-skew leeway (tokens 60s+ past exp ARE rejected), not a vulnerability. The test's wait
> margin was too tight; fixed to wait past the leeway. See docs/40-ADR.md / HANDOFF.

## Resolved
## BLOCK-001 | P0-T08 | 2026-07-16T00:35Z   [RESOLVED 2026-07-16]
**Expected:** Old Pipecat repo with `persona.py`, `tools.py`, `db.py`, `tests/` CER harness, `DECISIONS.md` at a known path.
**Resolution:** Human provided path at `../urdu-voice-agent/`. All files verified present and ported. P0-T08 complete.
