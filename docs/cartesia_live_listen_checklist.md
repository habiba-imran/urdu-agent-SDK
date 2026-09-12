# Cartesia English live-listen checklist (Phase D)

Nothing in this doc has been executed. It exists so the next Cartesia EN listening session
starts on listening, not on rediscovering what to check. Commands are copy-paste-ready but
**not run** here — a live Cartesia call is a paid TTS path and needs explicit sign-off.

Manual SSML prompt (Phases A–C) is the default. Expressive mode is an **opt-in A/B**, not
the production default.

## 1. Staged commands

```bash
# 1a. Seed a Cartesia EN test agent (manual SSML / default path).
python scripts/provision_cartesia_test_agent.py --commit

# 1b. Optional A/B: a second agent with LiveKit expressive mode.
python scripts/provision_cartesia_test_agent.py --commit --expressive

# 1c. Worker (separate terminal).
python -m worker.main dev

# 1d. Mint a join token with the tenant/agent/secret printed by 1a or 1b, then join
#     via the LiveKit Agents Playground: https://agents-playground.livekit.io
```

Worker logs to confirm Phase C/D wiring:

- `cartesia audio profile channel=webrtc encoding=pcm_s16le sample_rate=16000`
  (or `telephony` / `pcm_mulaw` / `8000` on a PSTN call)
- `cartesia session extras sanitizer=True expressive=False` (default)
- `cartesia session extras sanitizer=True expressive=True` (A/B agent)

If `--expressive` was set but the log says `expressive=False` plus a warning, the installed
`livekit-agents` has no `AgentSession(expressive=...)` parameter — stay on the manual SSML path.

## 2. Listening dimensions

Score each per turn, not one overall “sounded fine.”

| Dimension | What to listen for | Where it is controlled |
|---|---|---|
| Greeting | Two short clauses with a pause, not one compressed line | `CARTESIA_GREETING_INSTRUCTIONS` |
| Disfluency timing | `um` followed by a pause then `so` — not `um` at full speed | Phase A spoken-output rules |
| Disfluency bound | At most one filler per reply; none on a firm factual answer | ADR-010 bound in the prompt |
| Emotion stability | Calm baseline; no ping-pong inside one turn | Prompt emotion guardrails + TTS `emotion=["calm","content"]` |
| Banned phrases | No “Certainly!”, “I'd be happy to”, “Absolutely!” | Spoken-output rules |
| Codes / IDs | Confirmation codes and phones spelled, not slurred | `<spell>` rules + sanitizer keeps the tags |
| Markdown leakage | Sonic must not read “asterisk asterisk” or emoji names | `sanitize_spoken_text` + `tts_text_transforms` |
| Tool-turn air | Before escalate, a spoken “let me get someone…” — no silent hang | Prompt TOOL TURNS + `escalate_to_human` docstring |
| Telephony muddiness | PSTN should not sound extra-compressed vs WebRTC | Phase C mulaw 8 kHz vs pcm 16 kHz |
| Interruption resume | Talk-over then silence should not leave 2s of dead air | `false_interruption_timeout=0.7` |

## 3. Expressive A/B (same script, `--expressive`)

LiveKit documents expressive mode against `inference.TTS`, not `livekit.plugins.cartesia.TTS`
(the adapter this worker uses). Treat a successful A/B as a bonus, not a requirement.

Compare default vs `--expressive` on the same prompts:

1. Greeting
2. Empathy (“that must have been frustrating”)
3. Good news (“you're all set”)
4. A code: “your reference is TKT4829”
5. Ask to speak to a person (tool narration)

**Pass for default path:** pauses, fillers, and spell tags are audible; no markdown artifacts.

**Pass for expressive path (only if logs show `expressive=True`):** delivery shifts with the
moment without stacked SSML + expressive tags (robotic or “over-acted”). If it sounds worse,
leave `tts_options.expressive` unset.

## 4. Out of scope for this listen

- Cached filler audio on tool-call start (ADR-011 — still unbuilt)
- Switching the worker to LiveKit Inference `inference.TTS`
- Professional Voice Clone
- Urdu / Uplift agents
