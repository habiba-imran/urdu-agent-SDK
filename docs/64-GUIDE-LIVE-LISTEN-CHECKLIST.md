# 64-GUIDE-LIVE-LISTEN-CHECKLIST.md — everything staged for the next human live-listen

P10. Nothing in this doc has been executed. It exists so the next live-listen session starts
immediately on listening, not on rediscovering what to check or how to get a room up. Every
command below is copy-paste-ready but **NOT run** — running any of them means either a real
LiveKit Cloud room + local worker session (free-tier but live) or, for the phrase-replacement
entries, a real Uplift API call. Both need explicit human sign-off per the standing rule.

## 0. Pre-check done now, not assumed: demo tenant status

Checked directly against the real dev DB (2026-07-18), not assumed:

```
tenants table: 2 rows, both name='admin-test' (admin-portal test fixtures)
agents table:  0 rows
```

**The demo tenant does not currently exist.** `scripts/db_reset.py` runs during Phase 7/8 testing
this session evidently did not leave a demo tenant behind (or one was never re-provisioned after
the last reset) — this is not "persona.py drifted from the DB," it's "there is nothing in the DB
to have drifted." Same practical consequence either way: **step 1 below must be run before any
listening happens.** `scripts/provision_demo_tenant.py::_prompt()` pulls `persona.SYSTEM_PROMPT`
fresh at provision time (confirmed by reading the source — no caching, no stored copy to drift
from), so re-running it guarantees the provisioned prompt matches the current `persona.py` (v7,
`SYSTEM_PROMPT` = 4738 chars, sha256 `973ff5227c06cb17a0059c38513cab1c6b3a6365d98ab80470777bf7b996d3ec`
as of this session — re-check this hash if `persona.py` changes again before the listen).

## 1. Staged commands — run in this order, only after sign-off

```bash
# 1a. Seed a fresh demo tenant + agent (Mahnoor persona, voice v_meklc281). Local DB write only,
#     no paid provider touched. Creates fresh UUIDs every run.
python scripts/provision_demo_tenant.py --commit

# 1b. Start the worker (separate terminal, stays running for the whole session).
python -m worker.main dev

# 1c. Mint a real scoped join token for the tenant/agent/secret 1a just printed.
python scripts/mint_demo_token.py --tenant <tenant_id from 1a> --agent <agent_id from 1a> --secret <hmac secret from 1a>

# 1d. Join the printed roomName with the printed token + wsUrl via the LiveKit Agents Playground:
#     https://agents-playground.livekit.io
```

`worker/main.py` reads `{tenant_id, agent_id}` from the participant token metadata (already
verified working end-to-end in every prior Gate-3-style session this build).

## 2. Structured listening checklist

Score each dimension per turn or per call, not just an overall impression — a single "sounded
fine" verdict can't localize which lever (persona wording, phrase-replacement config,
endpointing) actually needs adjusting.

| Dimension | What to listen for | Where it would be fixed |
|---|---|---|
| **Sentence length / pacing** | Are replies chunked into short, speakable sentences, or long run-ons that Uplift (no SSML/rate control — D42, ADR-012) renders as a rushed wall of audio? | `persona.py` wording, punctuation density |
| **Code-switching ratio** | Does Urdu/English mixing match the worked examples in `persona.py` v7 (everyday-word switching, not just brand names) — natural, or too sparse/too frequent? | `persona.py` SYSTEM_PROMPT examples |
| **Disfluency frequency** | Are the bounded disfluencies (per v7's "bounded disfluency allowance") landing naturally, or absent/overused? | `persona.py` SYSTEM_PROMPT guardrail wording |
| **Emotional-register stability** | Does tone stay stable across a multi-turn call, or drift/flatten/over-emote as context grows? | `persona.py` SYSTEM_PROMPT stability guardrail |
| **detection_delay (interruption latency)** | Time from user starting to talk over the agent to the agent actually stopping. ADR-014 addendum 1(c) measured one sample at 1103ms (~4-5x LiveKit's published ~250ms median) — **n=1, not yet known if stable.** Interrupt the agent deliberately several times this session; note each `detection_delay` from the worker log (`livekit/agents/inference/interruption.py` emits it). | If consistently high: `worker/main.py` turn_handling config (ADR-011's next lever is lowering `min_delay` toward ~0.15-0.2s) — do not touch blind, only after real samples confirm it's not a fluke |
| **Tool-call correctness** | When the call ends, does `escalate_to_human` / `end_conversation_summary` (worker/tools.py, live since ADR-029) fire at the RIGHT moment — not spuriously, not missed when genuinely needed? | `worker/tools.py` docstrings (the LLM's only guidance on when to call each) |

## 3. Phrase-replacement entries — listen for these specifically, do not apply blind

`scripts/update_phrase_config.py` currently has exactly **one** confirmed entry (RAM → ریم, live
since this session). The prior 23-entry batch (16 "ported from D42," 8 "newly proposed") was
**held**, per the correction this session made to that script's own misleading comment — ADR-006
is explicit that the D42 entries were "removed — ported on assumption, not measured," not
human-verified as the old comment wrongly claimed. Building the list back up now happens
incrementally from real listening evidence, not from re-trusting the old batch.

**During the live-listen, note any word that sounds mispronounced** (the same way RAM was
originally caught — by ear, in a real call). Bring back a list of `{word, what was heard, what it
should sound like}` for review before any new entry is written or run — same treatment RAM got.

## 4. What this checklist does NOT cover (needs its own separate sign-off)

- **Endpointing `min_delay` changes** (ADR-011) — proposal only, needs live-listen validation
  first, not applied preemptively.
- **Soniox STT switch** (ADR-002) — blocked on funding (402), unrelated to this listening pass.
- **Uplift SSML/rate/emotion control** — structurally absent from the API (D42); not something a
  listening session can fix, only confirm is still absent if Uplift's own docs change.
