# Humanization Implementation Plan

**Status:** Implementation **closed** (Phases 0–7 + critical/high/medium audit fixes landed). Remaining work is Habiba listening A/Bs only — not more code pathways.  
**Owner:** Habiba (`worker/**`, demo-app smoke as needed)  
**Out of scope:** `control_plane/` dispatch, npm publish, humanization-as-marketing copy, Ehsan CI/npm work  
**Principle:** Layered humanization — not 16 combo prompts.

```text
effective providers (after telephony remaps)
        ↓
TurnProfile        (STT + VAD + EOU + interruption)
        ↓
SpokenOutputProfile (universal + LLM overlay + language)
        ↓
TTSHumanizationProfile (delivery, sanitizer, tokenizer, options)
        ↓
audio
```

**Do-not-do (from research):** 16 prompts; markup in universal rules; resolve humanization before remaps; blind model upgrades; Groq prompt bloat; Gladia Urdu code-switching on without evidence; full Fish non-verbal vocab; TurnDetector without cold-start recheck.

---

## How to use this plan

| Rule | Meaning |
|---|---|
| Phase exit | Do not start the next phase until the verification checklist for this phase is green |
| Flags | Prefer env / `tts_options` / `stt_options` flags for A/B; keep current behavior as default until listening passes |
| Measure | Use existing worker logs: `turn_latency`, `prewarm_wait_ms`, `start_ms`, `opening_mode`, Groq dump (`docs/last_session_prompt.txt`) |
| Listening | Use scenarios A–J from `humanization.md` §27 and rubric §29 |

---

# Phase 0 — Inventory freeze & resolver skeleton

**Goal:** One place that builds humanization **after** telephony remaps, without changing live behavior yet.

### Work
1. Add `worker/humanization/` (or equivalent) package:
   - `resolve_effective_providers(cfg, channel)` — wraps existing `force_cartesia_for_telephony` / `force_groq_for_telephony` outputs
   - Dataclass stubs: `SpokenOutputProfile`, `TTSHumanizationProfile`, `TurnProfile`
2. Wire `build_session` to call the resolver **after** remaps, but keep outputs identical to today (thin wrappers around current code).
3. Document call order in module docstring (config → remaps → effective → profiles).

### Files (expected)
- New: `worker/humanization/*.py`
- Touch: `worker/main.py` (`build_session`), maybe `worker/telephony_tts.py` (import only)

### Verification
- [x] Unit: remapped telephony agent still resolves TTS=`cartesia`, LLM=`groq` when keys present
- [x] Unit: WebRTC path unchanged (no forced remaps)
- [x] Existing tests still pass: greeting / session_opening / cartesia options / rime options / telephony remap tests
- [ ] Manual: one demo call on current Cartesia+Groq stack — confirm wording still acceptable (Phase 1 adds universal+LLM overlays; expect mild prompt change)

**Exit criteria:** Resolver exists; remaps unchanged; Phase 1 may intentionally change spoken prompts.

---

# Phase 1 — Universal spoken policy + LLM humanization overlays

**Goal:** Make the **LLM** sound human across providers without growing Groq ITPM. Extract shared “write for the ear” rules; add tiny Groq/Gemini modifiers.

### Work

#### 1A — Universal spoken block
1. Extract shared rules from Cartesia/Rime blocks into `UNIVERSAL_SPOKEN_RULES` (research §4):
   - ear not page, short sentences, contractions, no corporate filler, no markdown/emoji, light fillers, restrained emotion wording, concise turns
2. **Do not** put `<emotion>`, `<break>`, Fish `[laugh]`, Eleven audio tags in this block.
3. Refactor `build_system_instructions`:
   ```text
   SYSTEM_INSTRUCTIONS_BASE
   + CLIENT_TOOLS (if any)
   + UNIVERSAL_SPOKEN_RULES
   + llm_overlay(effective.llm)
   + tts_overlay(effective.tts)   # existing Cartesia/Rime content, trimmed of duplicates
   + language_directive
   ```

#### 1B — Groq overlay (compact)
Append a **short** Groq-specific block only when `llm_provider == groq`:
- concise voice turns
- direct answers
- minimal explanation
- minimal markup burden (defer delivery to TTS layer)
- strong tool discipline (already partly in base — do not duplicate paragraphs)

Keep total added chars small; re-check `GROQ_PROMPT_SOFT_CHARS` compaction still owns persona only.

#### 1C — Gemini overlay
When `llm_provider == gemini`:
- direct, concise instructions (research: over-complicated prompts → over-analysis)
- avoid restating caller
- prefer short spoken clauses for streaming TTS

Do **not** upgrade to Gemini 3.8 in this phase.

#### 1D — Prompt compaction alignment
Confirm `prompt_compact.py` still assumes platform owns voice rules; update comments/tests if section stubs mention old ownership.

### Verification
- [x] Unit: Cartesia agent instructions contain universal + Cartesia overlay; no duplicated “no markdown” paragraphs thrice
- [x] Unit: Rime agent gets universal + Rime (no SSML) overlay; zero Cartesia tags in Rime prompt
- [x] Unit: ElevenLabs/Fish/Uplift agents get universal + LLM overlay (even if TTS overlay still empty)
- [x] Unit: Groq path instruction length ≤ modest ceiling (`< 5000` chars for Cartesia+Groq compose; overlay `< 400`)
- [x] Unit: `compact_prompt_for_groq` still drops redundant voice sections (prompt_compact tests)
- [ ] Listening (same TTS): Groq vs Gemini on scenarios A, C, E — score natural wording + concision (rubric) — **needs Habiba live call**
- [ ] Log check: no Groq 429 regression on a 5–10 turn demo call — **needs Habiba live call**

**Exit criteria:** All LLM paths share universal spoken policy; Groq/Gemini have tiny overlays; prompts are not larger than necessary. Live listening/429 checks remain human-gated.

---

# Phase 2 — STT / turn-taking humanization (TurnProfile)

**Goal:** Make **STT + turn timing** feel human (patient EOU, good barge-in) without baking STT into spoken prompts.

### Work

#### 2A — `TurnProfile` object
Compose from research §15–16 / §26:
```text
TurnProfile
├── detector          # "stt" today; later flux / livekit
├── endpointing       # LiveKit min/max + provider-specific
├── preemptive_llm / preemptive_tts
├── interruption policy
├── false-interruption resume
└── channel overrides (webrtc vs telephony)
```
Move current `TURN_HANDLING_OPTIONS` / `TELEPHONY_TURN_HANDLING_OPTIONS` / Groq preemptive disable into this builder. Behavior default = today’s defaults.

#### 2B — Deepgram endpointing A/B (P0)
1. Keep default `endpointing_ms=10` for latency baseline.
2. Add env (or `stt_options.endpointing_ms`):
   - `UVA_DEEPGRAM_ENDPOINTING_MS=10|100|200|300|500`
3. Document that 10ms is latency-first, not automatically “most human.”

#### 2C — Gladia (no spoken prompt)
1. Keep `code_switching=False` for Urdu (do not flip).
2. Optionally surface `stt_options` passthrough only for safe keys already supported by plugin (`languages` already set) — no speculative new Gladia features without plugin verify.
3. Ensure TurnProfile does not add English-only assumptions when `agent_language=ur`.

#### 2D — Metrics hooks for turn feel
Reuse / extend turn latency logs to count or log:
- false interruption events (already partly wired)
- time EOU → LLM request (if not already)
Document which log fields listeners should capture during A/B.

### Out of this phase (parked → Phase 6)
- Deepgram Flux
- LiveKit audio TurnDetector (`v1` / `v1-mini`)

### Verification
- [x] Unit: telephony Groq still has preemptive generation off
- [x] Unit: WebRTC Deepgram default still `endpointing_ms=10`
- [x] Unit: env override changes Deepgram constructor arg only
- [x] Unit: Gladia still `code_switching=False`
- [ ] A/B listening (same LLM+TTS): Deepgram 10 vs 200 vs 300 on scenarios B, I, F
  - Track: false EOU, user repeats, “feels impatient,” barge-in recovery
  - **Habiba live call** — set `UVA_DEEPGRAM_ENDPOINTING_MS` per run; watch `deepgram STT build ... endpointing_ms=` and `turn_latency.turnMs`
- [ ] Cold-start: `session.start_ms` unchanged (±noise) when only endpointing changes — **Habiba live call**

**Exit criteria:** TurnProfile exists; Deepgram endpointing is tunable via env; listening notes recorded for default recommendation (may keep 10ms until product chooses). Live A/B remains human-gated.

**Note:** Portal still rejects nonempty `stt_options` (`invalid_stt_options`). Worker A/B is **env-only** until portal allowlists `endpointing_ms` for Deepgram.

---

# Phase 3 — Sanitizer + TTS delivery baselines (needed so LLM/STT humanization isn’t destroyed)

**Goal:** Stop cross-provider markup leakage; give ElevenLabs/Fish real delivery controls so LLM plain speech sounds human.

> LLM/STT humanization fails if Cartesia tags leak into Rime/Eleven/Fish or if Eleven/Fish stay “voice_id only.”

### Work

#### 3A — Sanitizer matrix
| TTS | Sanitizer behavior |
|---|---|
| Cartesia | Keep valid Cartesia markup (existing) |
| Rime | Strip Cartesia/Fish/Eleven syntax (existing + extend if needed) |
| ElevenLabs | Strip Cartesia XML + Fish brackets; optional allowlist later for audio tags |
| Fish | Allow restrained `[...]` cues only if prompt enables them; strip Cartesia XML |
| Uplift | Light cleanup (markdown/emoji); no English SSML |

API shape: `sanitizer_for(effective_tts, effective_model=None)` (research §19).

#### 3B — ElevenLabs options layer (P0/P1)
1. Add `elevenlabs_options.py` (mirror Cartesia/Rime pattern):
   - defaults: low-latency model (`eleven_turbo_v2_5` or Flash v2.5 if string verified on pinned plugin), conservative `voice_settings`
   - allow keys present on pinned `livekit-plugins-elevenlabs` signature: `model`, `voice_settings`, `auto_mode`, `apply_text_normalization`, `pronunciation_dictionary_locators`, etc.
2. Wire `build()` to merge defaults + `tts_options`.
3. Optional tiny TTS overlay: “plain text; delivery via voice settings” (no Cartesia tags).
4. Do **not** default to `eleven_v3_conversational` (separate experiment flag).

#### 3C — Fish options layer (P1)
1. Add `fish_audio_options.py`:
   - defaults aligned with plugin (`s2.1-pro` already plugin default), `latency_mode`, speed/volume if desired
2. Restrained expressive vocabulary later (Phase 5); this phase = constructor options + sanitizer only.
3. Keep capabilities `testing` until smoke passes.

#### 3D — Cartesia restraint flag (no model bump yet)
1. Add `tts_options.spoken_style = "manual_ssml" | "light"` (default `manual_ssml`).
2. `light` = use expressive-style plain-text Cartesia rules (existing `CARTESIA_SPOKEN_OUTPUT_RULES_EXPRESSIVE` content) **without** requiring LiveKit expressive.
3. Keep constructor emotion defaults; document possible fight with contextual prosody for later A/B.

### Verification
- [x] Unit: Cartesia tags stripped for Rime/Eleven/Fish sanitizer paths
- [x] Unit: ElevenLabs build receives model + voice_settings from defaults (via resolve kwargs)
- [x] Unit: Fish build receives latency_mode from defaults/options
- [x] Unit: unknown `tts_options` keys rejected (validation errors)
- [ ] Live smoke: ElevenLabs English agent — clear audio, no spoken “emotion value=” leakage — **Habiba**
- [ ] Live smoke: Fish (if account) — audio OK; still `testing` until approved — **Habiba**
- [ ] Cartesia `light` vs `manual_ssml` listening on A, C, J (flag only; no default flip) — **Habiba** (`tts_options.spoken_style=light`)

**Exit criteria:** Eleven/Fish are first-class optioned providers; sanitizers cover all English TTS; Cartesia light path available behind flag. Live smokes remain human-gated.

---

# Phase 4 — Language profile (Urdu) + Uplift pronunciation

**Goal:** Urdu humanization is language-first, not translated English emotion markup.

### Work
1. Add `URDU_SPOKEN_OUTPUT_RULES` (research §11):
   - Pakistani Urdu, proper script, no Roman Urdu
   - simple conversational language, continuous oral narration
   - spoken dates/numbers; careful English brand handling
2. Attach when `agent_language=ur` (with Uplift TTS).
3. Improve phrase-replacement wiring:
   - keep env `UPLIFT_PHRASE_CONFIG_ID`
   - document tenant/dictionary sync as follow-up (may need portal later — note as dependency)
4. Ensure Gladia Urdu TurnProfile stays `code_switching=False`.

### Verification
- [x] Unit: `ur` agent instructions include Urdu profile; no Cartesia emotion teaching
- [x] Unit: `en` agent does not get Urdu block
- [x] Fixture/live Uplift: phrase config id still applied when env set
- [ ] Listening (Urdu speaker): scenarios A, G, H — pronunciation + natural phrasing

**Exit criteria:** Urdu has its own spoken profile; English paths unchanged.

---

# Phase 5 — Provider delivery experiments (gated model / expressive A/Bs)

**Goal:** Run the research’s key experiments **behind flags**; promote winners only after listening + latency pass.

### Workstreams (parallelizable)

#### 5A — Cartesia Sonic 3.6 + styles
Flags:
- `tts_options.model=sonic-3.6` (or env default override for demo agents only)
- styles: `manual_ssml` / `light` / (later) LiveKit expressive if SDK supports

Experiments (research §30):
```text
A. Sonic 3.5 + current tags   (control)
B. Sonic 3.6 + current tags
C. Sonic 3.6 + light/plain
D. Sonic 3.6 + LiveKit expressive  # only if cartesia_expressive_available()
```

#### 5B — Rime Coda / Mist
- Opt-in `tts_options.model=coda` with Coda-compatible voice (`rime-coda-*`)
- Do not carry Arcana `speed_alpha` blindly — retune
- Mist v3 only if TTFA critical

#### 5C — ElevenLabs expressive path
- Flag for `eleven_v3_conversational` + small audio-tag overlay
- Verify which options the dialogue API ignores on pinned plugin

#### 5D — Fish restrained expressive
- Optional small prompt allowlist: light emphasis / calm / rare laugh
- Prefer LiveKit expressive **only** if available for Fish on pinned agents version
- Disable crying/gasps/etc.

#### 5E — LLM model A/B (separate from overlays)
- Keep Groq low-reasoning control
- Optional demo-only: `GEMINI_LLM_MODEL=gemini-3.8-flash` with `thinking_level=low` and **without** copying `temperature` blindly
- Measure TTFT + spoken compliance

### Verification (per experiment)
- [x] Flag infrastructure: Cartesia model/style env+options; Rime coda/mist without Arcana speed; Fish restrained; Gemini thinking_level env
- [x] Unit: eleven_v3* / audio_tags **refused** on pinned livekit-plugins-elevenlabs==1.6.5 (no text-to-dialogue)
- [x] Unit: LiveKit expressive still gated off (`cartesia_expressive_available()` False on 1.6.5 AgentSession)
- [ ] Same listening set A–J; rubric scores recorded
- [ ] Latency: EOU→first audio, LLM TTFT, TTS TTFB — no multi-second regression
- [ ] Groq: cancelled/preemptive token pressure not worse
- [ ] Cold start: `start_ms` for expressive/TurnDetector trials
- [ ] Written decision: keep control / promote flag / abandon

**Blocked pending human decision (do not auto-promote):**
1. **ElevenLabs 5C full path** — needs deliberate upgrade to livekit-plugins-elevenlabs ≥≈1.7.1 (dialogue streaming). **Deferred** (keep blocked on 1.6.5).
2. **Cartesia/Fish LiveKit expressive** — needs public `AgentSession(expressive=...)` + inference TTS path; unavailable on plugin TTS in 1.6.5.
3. **Default model changes** (sonic-3.6, gemini-3.8-flash, mistv3) — listening + latency only. Env knobs ready; production defaults unchanged.
4. **Listening A–J** — deferred to end of humanization rollout (Habiba).

**Exit criteria:** At least Cartesia and Deepgram recommendations documented; defaults changed only with explicit decision note.

---

# Phase 6 — Advanced turn detection (optional / higher risk)

**Goal:** Improve EOU human feel with Flux or LiveKit TurnDetector — only after Phase 2 baseline exists.

### Work
1. Deepgram Flux adapter path (if pinned `livekit-plugins-deepgram` supports it):
   - Start **EndOfTurn only**
   - Groq: no Eager EOT initially (token cost)
   - Gemini: Eager EOT optional A/B
2. LiveKit TurnDetector:
   - Try `v1-mini` first (local)
   - English only (Urdu not in detector language list)
   - Must re-measure `session.start_ms` and job→first audio
3. Keep detector choice inside `TurnProfile`.

### Verification
- [x] Feature flagged; default remains STT endpointing (Nova + `turn_detection=stt`)
- [x] Flux via pinned `deepgram.STTv2` / `flux-general-en`; Eager EOT off by default; Groq never gets Eager
- [x] TurnDetector via `livekit.agents.inference.TurnDetector` (`UVA_TURN_DETECTOR=v1-mini|v1`); Urdu refused
- [ ] Listening B/I/F vs Phase 2 winner
- [ ] Cold-start budget: no unacceptable `start_ms` regression
- [ ] Groq TPM: no 429 spike with Flux eager disabled

**Exit criteria:** Ship only if turn quality ↑ and cold-start/TPM acceptable; else keep Phase 2 profile.

---

# Phase 7 — History / cache hygiene (LLM humanization durability)

**Goal:** Prevent old markup and huge history from undoing Phase 1 gains (research §21–22).

### Work
1. Investigate LiveKit `AgentSession` history APIs for windowing / truncating.
2. Prefer storing **plain** assistant text in history when delivery markup was TTS-only.
3. Keep static platform rules first for Groq prompt-cache friendliness.
4. Do not put tenant delivery markup into system instructions.

### Verification
- [x] Documented history policy (`worker/humanization/history.py`) using only verified APIs
- [x] Assistant history plain-text: strip TTS markup on `conversation_item_added`
- [x] Optional `ChatContext.truncate` via `UVA_CHAT_HISTORY_MAX_ITEMS` (default **48**; `0` disables)
- [x] DB transcript uses `plain_text_for_history`
- [x] Unit: static system prefix stable; tenant persona not in system instructions
- [ ] Spot-check Groq dump on a live long call (listening / Habiba)

**Exit criteria:** Documented history policy; implementation only if API-safe.

---

## Phase dependency graph

```text
Phase 0  resolver skeleton
   │
   ├──────────────┬──────────────────┐
   ▼              ▼                  ▼
Phase 1         Phase 2            Phase 3
LLM spoken      STT / TurnProfile  Sanitizers + Eleven/Fish options
   │              │                  │
   └──────┬───────┴────────┬─────────┘
          ▼                ▼
       Phase 4          Phase 5
       Urdu/Uplift      Gated model A/Bs
                          │
                          ▼
                       Phase 6  Flux / TurnDetector
                          │
                          ▼
                       Phase 7  History hygiene
```

Phases 1–3 can overlap after Phase 0 if staffing allows; **do not** change defaults in Phase 5 until 1–3 verification is green.

---

## Suggested scheduling (efficient order)

| Week-ish chunk | Focus | Why this order |
|---|---|---|
| 1 | Phase 0 + Phase 1 | Unlocks every provider combo with one spoken policy; biggest LLM win |
| 1–2 | Phase 2 | STT humanization without touching prompts |
| 2 | Phase 3 | Makes Eleven/Fish usable; protects sanitizer boundaries |
| 2–3 | Phase 4 | Urdu track in parallel once overlays exist |
| 3+ | Phase 5 | Experiments only — don’t block earlier shippable gains |
| Later | Phase 6–7 | Higher risk / needs more evidence |

---

## Cross-cutting verification checklist (every phase)

- [ ] Telephony remaps still run **before** profile resolve
- [ ] No new secrets in repo; env knobs documented in `.env.example`
- [ ] Unit tests for new options validation + instruction composition
- [ ] No Groq system-prompt balloon (compare `docs/last_session_prompt.txt` sizes)
- [ ] One WebRTC + one telephony smoke when turn/TTS defaults change
- [ ] Update this plan’s “Decision log” when a flag becomes the new default

---

## Decision log (fill during implementation)

| Date | Phase | Decision | Evidence |
|---|---|---|---|
| 2026-09-17 | Audit critical | Urdu PSTN keeps Uplift (no Cartesia remap) | `test_urdu_pstn_uplift_e2e` + telephony remap |
| 2026-09-17 | High | Buffered stream sanitizer across chunks | `spoken_sanitize.make_stream_sanitizer` |
| 2026-09-17 | High | Groq compact preserves §4/§5/FINAL AUTHORITY | `prompt_compact` + gap e2e |
| 2026-09-17 | High | Greeting cache fingerprints `tts_options` | 6-tuple key in `greeting_cache` |
| 2026-09-17 | Medium | Deepgram endpointing default 200ms | more-human STT default |
| 2026-09-17 | Medium | Cartesia emotion via overrides / SSML tags only | no constructor emotion on light |
| 2026-09-17 | Medium | Cartesia bracket + plain URL sanitizer gaps | spoken sanitizers |
| 2026-09-17 | Medium | Drop dead sanitizing agent; narrow telephony remap | registry / telephony_tts |
| 2026-09-17 | Wave 1 close | History window default 48 items | `history.resolve_chat_history_max_items` |
| 2026-09-17 | Wave 1 close | Session LLM/TTS/STT `max_retry=0` | `build_session_connect_options` |
| 2026-09-17 | Wave 1 close | Cartesia default `spoken_style=light` | `CARTESIA_TTS_DEFAULTS` |
| 2026-09-17 | Wave 1 close | English WebRTC Gemini→Groq when key set | `force_groq_for_english_webrtc` |
| 2026-09-17 | Close | Code pathway + pytest gate (humanization phase tests whitelisted) | gate + related tests green |

---

## Explicitly deferred (not “forgotten”)

| Item | Why deferred |
|---|---|
| Default LiveKit `expressive=True` for Cartesia | Pinned 1.6.x plugin path does not inject tags |
| Gemini 3.8 as default | Needs TTFT A/B; sampling param migration |
| Rime Coda as default | Voice catalog + account + speed retune |
| Gladia code-switching on | Prior CER evidence against |
| Cartesia Urdu replacing Uplift | Needs Pakistani listening benchmark |
| npm / CP / billing key checks | Not Habiba humanization scope |
| Scenarios A–J live listening | Habiba-owned; not a code pathway |

---

## Pathway closed (2026-09-17)

**Code work for humanization is done for Wave 1.** Phases 0–7 + audit gap fixes are landed; humanization phase tests are on the pytest whitelist (`pytest.ini`).

Wave 1 defaults (2026-09-17 closeout):
- Chat history window **48** items (disable with `UVA_CHAT_HISTORY_MAX_ITEMS=0`)
- Provider session retries **off** (`max_retry=0` on LLM/TTS/STT connect options)
- Cartesia **light** spoken style by default (manual SSML via `tts_options.spoken_style`)
- English browser **Groq** when `GROQ_API_KEY` is set (`UVA_FORCE_GROQ_ENGLISH=0` to keep Gemini)

Next (outside this pathway): live listening A/Bs against `humanization.md` §27/§29. No further implementation unless listening finds a concrete defect.

---

## Success definition (Wave humanization)

A host-configured English agent (any allowed STT×LLM×TTS combo) and the Urdu Gladia→Gemini→Uplift path should:

1. Speak concise, natural wording (LLM overlays + universal policy)
2. Wait for true end-of-utterance more patiently when configured (STT/TurnProfile)
3. Deliver audio without markup leakage (sanitizers + TTS profiles)
4. Preserve barge-in and cold-start budgets (no multi-second regressions)
5. Avoid constant fake empathy / fillers / non-verbal noise

Reference: `docs/humanization.md` §35 bottom line.
