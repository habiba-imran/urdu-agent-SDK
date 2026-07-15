# AGENT_SYSTEM.md — the operating system

**You are the ORCHESTRATOR.** This file tells you how to work. It does not tell you what to build.
What to build lives in `docs/`. Route via `docs/00-INDEX.md`. Never read all docs at once.

---

## 1. RESEARCH BASIS — why these rules exist

Each rule maps to a documented failure. Do not "simplify" them away.

| Finding | Source | Rule it forces |
|---|---|---|
| Unguided Claude Code succeeds **~33%**; creator abandons **10–20%** of sessions | Anthropic internal | Machine gates, not vibes |
| **CLAUDE.md followed only ~70%** of the time; hooks ≈100% | Anthropic | Safety in hooks, never prose alone |
| Agents **rewrite tests instead of fixing code** — documented even with "DO NOT CHANGE THE CODE" in CLAUDE.md; real case: Playwright tests injecting JS so they passed while the bug shipped | GitHub issue + community | `test-guard.sh` |
| `/compact` **destroys architectural rationale** — "numbers get rounded, conditional logic collapses, the rationale evaporates" | Augment Code | State in files, never conversation |
| Subagents are a **net loss** on tightly-coupled edits; win only on read-heavy independent work | Konishi orchestration guide | One writer, many readers (§3) |
| **All** coding agents fall to prompt injection; adaptive attacks land **>85%** | arXiv:2601.17548 (78 studies) | Untrusted data never reaches a privileged tool |
| Supabase MCP + `service_role` + poisoned row = **documented exfiltration** (~800pts HN). Read-only necessary but **not sufficient** — output text still leaks | General Analysis; Willison | `docs/33-GUIDE-SUPABASE.md` |
| **Long CLAUDE.md degrades instruction-following** | Widely reported | CLAUDE.md is a router. Depth in docs/ |
| Progressive disclosure saves **~60%** context — metadata first, full content on demand | Community measurement | This whole file tree |
| "Corrected >2× on the same issue → context is cluttered → `/clear`" | Anthropic | 3-strike rule (§6) |

### ponytail — verified, and the hype is wrong

Real repo: `github.com/DietrichGebert/ponytail`, MIT, ~44k stars in 9 days.

The viral "80–94% less code / 47–77% cheaper" numbers came from a **single-shot prose benchmark** where the baseline padded with filler. Issue #126 called it out; **the maintainer corrected it.** Honest agentic numbers (12 tickets, real FastAPI+React repo, n=4, Haiku 4.5):

**~54% less code · ~22% fewer tokens · ~20% cheaper · ~27% faster · 100% adversarial-security retained** (the only arm to cut every metric without dropping a guard; naive "write one-liners" scored 83%).

- Install at **`default`**. Never `extremist` — an SDK needs abstractions a YAGNI-extremist refuses to build.
- ⚠️ On verbose reasoning models the token balance goes **negative** (documented on GPT-5.5). **P0-T07 measures it on your model.** If negative, disable it.
- Harvest `ponytail:` debt at every phase gate (`/ponytail-debt`).

---

## 2. THE LOOP

```
┌─> 1. READ    state/PROGRESS.md                    (mandatory, every task)
│   2. ROUTE   docs/00-INDEX.md -> load ONE guide   (never load all)
│   3. PLAN    smallest thing satisfying the gate   (ponytail ladder)
│   4. BUILD   orchestrator only
│   5. GATE    make gate                            (hook blocks Stop if red)
│   6. REVIEW  reviewer subagent, fresh context, diff only
│   7. RECORD  PROGRESS.md + commit sha
└─  8. COMMIT  one task, one commit
```

**Never skip 1. Never skip 6.** Step 6 is the only thing that catches "agent says done, tests are red."

---

## 3. TOPOLOGY — one writer, many readers

You asked for parallel agents. The evidence says parallel **writers** on one codebase lose — cold starts, one-shot returns, lost coupling. Subagents win on **read-heavy, independent, high-output-to-conclusion** work.

**So: parallelise reading. Serialise writing.**

```
        ORCHESTRATOR (main thread) — the ONLY agent that writes
             |
   +---------+---------+---------+
   |         |         |         |
researcher reviewer security db-inspector      <- all READ-ONLY
(parallel) (fresh ctx)(parallel)  (MCP only)
```

Defined in `.claude/agents/`. Tool scoping enforces this — not hope.

- Fan out 2–4 `researcher`s **only** on independent questions.
- `reviewer` runs on **every** task. Sees diff + acceptance criteria only, never your reasoning.
- Escalate to `git worktree` + `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` **only** for genuinely disjoint phases (P5 ∥ P6). Not before.

---

## 4. TASK CONTRACT — every task, this exact shape

No task starts without all six fields. If you can't fill them, the task isn't ready.

```markdown
### P<phase>-T<nn> <title>
**Guide:**    docs/2x-PHASE-x-....md §<n>
**Files:**    exact paths you will touch
**Done when:** ONE machine-checkable command + expected output
**Gate:**     `pytest tests/test_x.py -q` -> 0 failures
**Free-tier:** which quota this consumes, or FIXTURE-ONLY
**Attempt:**  1/3
```

**"Done when" must be a command, never a sentence.** "Works correctly" is not done. `pytest -q` exiting 0 is done.

---

## 5. BRANCHES, COMMITS, ROLLBACK

- Branch per phase: `phase/3-worker`. Never commit to `main` (hook blocks it).
- One task = one commit: `P3-T04: wire Uplift TTS | gate: PASS`
- Gate red after commit → `git revert`, never `git reset` (history is your audit trail).
- Phase gate green → PR to `main` → **you (human) merge.** The agent never merges.
- Tag every phase gate: `git tag p3-gate-pass`. Rollback target.

---

## 6. 3-STRIKE ESCALATION

Same failure 3× → **STOP.** Do not try a 4th approach. Write `state/BLOCKERS.md`:

```markdown
## BLOCK-001 | P3-T04 | 2026-07-15T11:04Z
**Expected:** audio frames on the LiveKit track
**Actual:** silence; plugin connects, zero frames
**Tried:** (1) plugin 1.5.15 -> silence  (2) raw WS -> frames arrive, so it's the plugin layer
          (3) sample_rate=22050 override -> silence
**Hypothesis:** plugin assumes 48k; Uplift emits 22.05kHz PCM (see docs/40-ADR.md D3)
**Need:** known resample flag? -> HUMAN: take to Claude chat
**STATUS: BLOCKED — P3-T05 does not start**
```

Then stop and tell the human. They bring BLOCK-001 to Claude chat for research and paste the answer into `docs/42-RESEARCH-QUEUE.md`.

---

## 7. CONTEXT HANDOFF — the anti-amnesia protocol

Trigger at **any**: context >70% · 45–60 min elapsed · phase gate passed · responses degrading.

```
1. /update-progress
2. Write state/HANDOFF.md (template in state/HANDOFF.md)
3. git commit -am "checkpoint: P3-T04"
4. /clear
5. New session: "Read CLAUDE.md, state/PROGRESS.md, state/HANDOFF.md. Brief me. Continue."
```

**Any agent resumes from 3 files** — Claude, Codex, Cursor, Gemini. Nothing here is Claude-specific.
`/catchup` rebuilds from `git diff --name-only main` if HANDOFF is stale.

---

## 8. ANTI-HALLUCINATION

1. **Never guess an API signature.** Context7 → or read the installed source in `.venv/`. Both fail → BLOCKERS.md.
2. **Cite or omit.** Every non-obvious claim in code comments or docs carries a file path or URL.
3. **Never invent a number.** Latency, cost, limits — measured or cited. Not estimated.
4. **The gate is the truth.** If the gate is red, you are not done, regardless of your reasoning.
5. **Trust nothing in this repo's own docs about vendor behaviour** until a test proves it. Our old `DECISIONS.md` says Uplift is Socket.IO @22.05kHz — that's about *our* code, not the LiveKit plugin. P3-T01 verifies the plugin from scratch.

---

## 9. WHAT THIS SYSTEM DOES NOT PROMISE

You asked for "0 chance of any error." No system delivers that, and one that claims to is lying — you'd find out in week three.

**Achievable:** every error hits a gate before compounding · every blocker stops the loop instead of being papered over · every session resumable in <5 min · no secret reaches the client · no cross-tenant read succeeds.

**Not achievable:** agents will still hallucinate signatures (→ Context7 + rule 8.1) · will still claim done when red (→ gate.sh + reviewer) · prompt injection **cannot be fully eliminated** (OWASP's own position → prod never in reach) · ponytail saves ~20%, not 77%.

**The claim is not zero errors. It is zero *silent* errors.** That's the version that ships.

---

## 10. START

```
Human:  docs/41-HUMAN-TASKS.md  H1-H8. Send H9.
Agent:  docs/20-PHASE-0-HARNESS.md. Run Gate 0. Post output. STOP.
Human:  confirm -> "begin Phase 1"
```

**First message:**
> Read CLAUDE.md and AGENT_SYSTEM.md. Then read docs/20-PHASE-0-HARNESS.md and execute it. Do not write product code. Run Gate 0 and show me the output.
