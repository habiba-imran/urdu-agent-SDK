# Humanization — Codebase Context for Research

**Audience:** Claude (or any researcher) designing per-provider / per-combination humanization settings and prompts.  
**Repo:** AwaazLabs UVA (`sdk-agent`), branch context as of Habiba Wave 1 work.  
**Goal of this doc:** Describe **exactly how the worker behaves today** — not a desired design. Use this as ground truth when researching how to extend humanization across LLM × STT × TTS combinations.

**Related existing docs (read these too):**
- `docs/CTO_CONTEXT_LLM_LATENCY_AND_CARTESIA_HUMANIZATION.md` — leadership brief (latency + Cartesia token tax). **Note:** some model defaults in that brief may lag code (see §4.2 below).
- `docs/cartesia_humanization.md` — vendor guide that drove Cartesia Phase A–D.
- `docs/rime-labs-humanization.md` — vendor guide that drove Rime Phase A–D.
- `docs/UVA-PRIORITY-LIST.md` — Wave 1 Humanization + TTFT ticket (Habiba).
- `docs/AwaazLabs UVA Audit.md` §3.2 / F-M2 / F-M15 — unbounded prompt, silent provider remap.

---

## 0. What “humanization” means in this codebase

Humanization is **not** one flag. It is a stack of layers that only partially exist today:

| Layer | What it is | Implemented for |
|-------|------------|-----------------|
| **A — LLM spoken-output rules** | Trusted system-instruction block that teaches the model *how to write for the ear* (and optionally emit TTS markup) | **Cartesia** (full SSML emotion path), **Rime** (punctuation/fillers only), **everyone else** = generic latency/tool rules only |
| **B — TTS constructor defaults** | Model, speed, emotion, websocket, sample rate merged from `agents.tts_options` + platform defaults | **Cartesia**, **Rime** only |
| **C — Audio channel profiles** | WebRTC vs telephony encoding / sample rate | **Cartesia**, **Rime** |
| **D — Pre-TTS text sanitizer** | Strip markdown/emoji; keep or strip SSML depending on TTS | **Cartesia**, **Rime** only |
| **E — Streaming tokenizer** | Sentence splitter that must not stall first audio; Cartesia needs `xml_aware=True` so tags aren’t broken | **Cartesia** only |
| **F — Turn / preemptive / telephony policy** | Whether LLM/TTS start before end-of-utterance; Groq TPM protection | Channel + **LLM provider** (Groq disables preemptive) |
| **G — Runtime remaps** | Force TTS/LLM on PSTN regardless of agent config | Telephony → Cartesia TTS; EN Gemini → Groq |

**Critical design rule already in code:** spoken-output rules live in **platform system instructions**, never in tenant `agents.prompt`. Tenant prompt is framed as untrusted DATA in a separate `chat_ctx` message (`worker/main.py` `build_agent`). See `31-GUIDE-SECURITY.md` §4 references in source comments.

---

## 1. Architecture (cascaded voice loop)

```
Caller audio
  → LiveKit (WebRTC browser OR Telnyx SIP telephony)
  → Worker: VAD → STT → (EOU) → LLM (± tools) → sanitize → TTS → audio back
```

**One worker path** serves all provider combinations. Provider choice is per-agent config loaded at session start (`worker/config.py` → `build_session` in `worker/main.py` → `worker/providers/registry.py`).

### 1.1 Capability matrix (what tenants may select)

Source of truth: `worker/providers/capabilities.py` (`CAPABILITIES`).

| Language | STT | LLM | TTS |
|----------|-----|-----|-----|
| **ur** | Gladia only | Gemini only | Uplift only |
| **en** | Gladia, Deepgram | Gemini, Groq | ElevenLabs, Fish Audio (`testing`), Cartesia, Rime |

**Structural rules:**
- Groq is **absent** from `ur` (not merely disabled).
- Fish Audio is `testing` (tenant create routes treat testing ≈ blocked today).
- TTS voices live in DB `voices` table; capabilities only list TTS **providers**.

### 1.2 What goes into every LLM turn

| Piece | Every turn? | Notes |
|-------|-------------|-------|
| Platform system instructions | Yes | From `build_system_instructions(cfg)` — includes Cartesia/Rime spoken rules when TTS matches |
| Language directive | If non-Urdu | Appended in `build_agent` |
| Tenant persona | Yes | Groq: may be compacted (`worker/prompt_compact.py`) |
| Full conversation history | Yes | **No sliding window** today (Wave 1 TTFT ticket) |
| Tool schemas | If tools gateway configured | Fixed token tax |
| Completion budget | Yes | Groq ~96 (`GROQ_MAX_COMPLETION_TOKENS`); Gemini max_output_tokens 256 |

---

## 2. Prompt / instruction assembly (the humanization switch today)

### 2.1 Entry point

```
worker/main.py::build_agent(cfg)
  → build_system_instructions(cfg)   # worker/cartesia_spoken_output.py
  → + _language_directive
  → Agent(instructions=..., chat_ctx=persona framed as DATA, tools=...)
```

### 2.2 `build_system_instructions` branching (exact)

File: `worker/cartesia_spoken_output.py`

```
base = SYSTEM_INSTRUCTIONS_BASE          # voice receptionist + tool discipline + response latency
+ CLIENT_TOOLS_DISCIPLINE                # only if tools_base_url / env gateway present
+ if tts_provider == "cartesia":
      CARTESIA_SPOKEN_OUTPUT_RULES       # OR EXPRESSIVE variant if expressive actually enabled
  elif tts_provider == "rime":
      RIME_SPOKEN_OUTPUT_RULES
  else:
      (nothing — ElevenLabs / Fish / Uplift get NO spoken-output humanization block)
```

**Implication for research:** Today humanization prompts are keyed **primarily on TTS provider**, not on LLM or STT. Gemini+Cartesia and Groq+Cartesia get the **same** Cartesia SSML teaching block. ElevenLabs + Groq gets **zero** TTS-specific speaking rules.

### 2.3 What the Cartesia rules teach the LLM (manual SSML — default)

File: `CARTESIA_SPOKEN_OUTPUT_RULES` in `worker/cartesia_spoken_output.py`

- Plain spoken prose; no markdown/bullets/emoji
- Ban corporate fillers (“I'd be happy to”, “Certainly!”, …)
- **Required:** start nearly every reply with `<emotion value="…"/>` (sympathetic / content / curious / calm / apologetic)
- Bounded disfluency: at most one `um <break time="300ms"/>` style filler per reply
- `<spell>CODE</spell>` for IDs/phones; optional `[laughter]`
- Speak a brief line before tools / escalate (no dead air)

**Expressive variant** (`CARTESIA_SPOKEN_OUTPUT_RULES_EXPRESSIVE`): tells the LLM **not** to emit emotion/break tags (LiveKit would inject). **Currently unused in practice** — see §3.1.

### 2.4 What the Rime rules teach the LLM

File: `worker/rime_spoken_output.py`

- **No SSML** — never emit Cartesia tags (Coda/Arcana would read them aloud)
- Punctuation = prosody; `spell(ID)` for codes
- Bounded fillers (um/so/well); short sentences; no corporate filler

### 2.5 Greeting instructions (when no static `agents.greeting`)

`greeting_instructions(cfg)` in same module:
- Cartesia manual: includes an example with `<break time="300ms"/>`
- Cartesia expressive: plain text example
- Rime: punctuation pauses, no SSML
- Default (all other TTS): one short sentence, no markup

Opening modes: `worker/session_opening.py` — `wait` | `say` (static greeting) | `generate_reply` (uses greeting_instructions).

Static greetings are also run through the provider sanitizer before speak (`_spoken_greeting`).

---

## 3. TTS layer — per provider (current code)

### 3.1 Cartesia — **fully humanized path**

| Concern | File | Current behavior |
|---------|------|------------------|
| Adapter | `worker/providers/tts/cartesia.py` | `cartesia.TTS(**resolve_cartesia_tts_kwargs(...), tokenizer=low_latency...)` |
| Options schema | `worker/providers/tts/cartesia_options.py` | Keys: `model`, `speed`, `volume`, `emotion`, `expressive` |
| Defaults | `CARTESIA_TTS_DEFAULTS` | `sonic-3.5`, `speed=0.95`, `emotion=["calm","content"]`, `expressive=False` |
| Audio profiles | same file | webrtc + telephony both **pcm_s16le @ 16 kHz** (µ-law direct = garbled; LiveKit SIP resamples) |
| Tokenizer | `low_latency_cartesia_tokenizer()` | blingfire with `xml_aware=True`, `stream_context_len=1` (critical for SSML + first audio) |
| Sanitizer | `worker/cartesia_spoken_sanitize.py` | Strip markdown/emoji; **keep** `<emotion>`, `<break>`, `<spell>`, `<speed>`, `<volume>`, `[laughter]` |
| Wiring | `worker/main.py` `_tts_agent_session_extra` + `_sanitizing_agent_class` | `tts_text_transforms` + Agent `tts_node` override |
| Telephony force | `worker/telephony_tts.py::force_cartesia_for_telephony` | Non-Cartesia agents on PSTN remapped to Cartesia Katie; **tts_options wiped to `{}`** so platform defaults apply |

**Expressive flag gotcha (must research around this):**
- LiveKit Agents 1.6.x hardcodes session expressive off; expressive injection only for `inference.TTS`, **not** `livekit.plugins.cartesia.TTS`.
- Defaulting `expressive=True` previously selected the “don’t emit tags” prompt while nothing injected tags → **flat calm voice**.
- `cartesia_expressive_enabled()` requires stored `expressive=True` **and** `AgentSession.__init__` exposing public `expressive` — today that returns false → always manual SSML path.

### 3.2 Rime — **partially humanized path**

| Concern | File | Current behavior |
|---------|------|------------------|
| Adapter | `worker/providers/tts/rime.py` | Uses `speaker` + `lang` (3-letter: `en`→`eng`) |
| Options | `worker/providers/tts/rime_options.py` | Keys: `model`, `speed_alpha`, `time_scale_factor` |
| Defaults | `RIME_TTS_DEFAULTS` | `model=arcana`, `speed_alpha=1.1`, `use_websocket=True`, `segment=immediate` |
| Audio | same | webrtc 16 kHz; telephony **8 kHz** |
| Sanitizer | `worker/rime_spoken_sanitize.py` | Strip markdown/emoji/**Cartesia SSML**/Mist `<750>` pauses; keep `spell()`; rewrite `<spell>X</spell>` → `spell(X)` |
| Spoken rules | `worker/rime_spoken_output.py` | Yes |
| Telephony | Forced **off** Rime → Cartesia (Rime under-ran realtime on PSTN) |

Research docs recommend Coda; code defaults **Arcana** to match seeded catalog speakers. Coda is opt-in via `tts_options.model="coda"` + a Coda voice.

### 3.3 ElevenLabs — **no humanization stack**

| Concern | Current behavior |
|---------|------------------|
| Adapter | `worker/providers/tts/elevenlabs.py` — `elevenlabs.TTS(voice_id=..., language=...)` only |
| `tts_options` | **No** schema / defaults / validation module |
| Spoken-output rules | **None** (falls through to base system instructions only) |
| Sanitizer | `sanitizer_for_provider("elevenlabs")` → **None** |
| Tokenizer | Plugin default |
| State | `enabled` for `en` |

**Research question:** What ElevenLabs controls exist (stability, style, speaker boost, SSML, pronunciation dictionaries) and should the LLM emit anything special, or should humanization be **TTS-side only** (no tag tax on Groq)?

### 3.4 Fish Audio — **no humanization stack**

| Concern | Current behavior |
|---------|------------------|
| Adapter | `worker/providers/tts/fish_audio.py` — `fishaudio.TTS(voice_id=...)` **no language kwarg** |
| Options / rules / sanitizer | **None** |
| State | `testing` (payment / funding historically blocked — audit §6) |

### 3.5 Uplift (Urdu) — **no English-style humanization**

| Concern | Current behavior |
|---------|------------------|
| Adapter | `worker/providers/tts/uplift.py` — fixture/live modes; optional phrase-config |
| Spoken rules / sanitizer | **None** |
| Language | Urdu-only path with Gladia + Gemini |

**Research question:** Does Uplift support any prosody / emotion / SSML? Urdu humanization is a separate track from EN Cartesia SSML.

### 3.6 Sanitizer dispatch

File: `worker/spoken_sanitize.py`

```
cartesia → cartesia_spoken_sanitize
rime     → rime_spoken_sanitize
else     → None
```

Cross-applying sanitizers is explicitly forbidden in comments (Cartesia keeps SSML; Rime strips it).

---

## 4. LLM layer — latency / token behavior (affects humanization)

Humanization markup is an **LLM output** problem and a **fixed system-prompt input tax**. LLM choice changes whether that tax is affordable.

### 4.1 Gemini — `worker/providers/llm/gemini.py`

| Setting | Value |
|---------|-------|
| Default remap target | `GEMINI_LLM_MODEL` or `gemini-3.6-flash` |
| Deprecated IDs remapped | 2.0/2.5/3.1 flash variants → default |
| Timeout | 30s HTTP |
| Temperature | 0.4 |
| max_output_tokens | 256 |
| Thinking | Gemini 3: `thinking_level="minimal"`; older: `thinking_budget=0` |
| max_retry | (plugin default; not forced to 0 here) |

**Measured:** EN telephony TTFT often **1.5–3s+** even with minimal thinking → product silence.  
**Policy:** `force_groq_for_telephony` remaps EN Gemini → Groq when `GROQ_API_KEY` present.

**Urdu:** Gemini stays (only LLM in `ur` capabilities).

### 4.2 Groq — `worker/providers/llm/groq.py` (**code truth**)

| Setting | Value |
|---------|-------|
| Live default | `GROQ_LLM_MODEL` or **`openai/gpt-oss-20b`** |
| Dead IDs remapped | Llama 3.1/3.3, Qwen 3.6/3.8/32b, Scout, Kimi, etc. → default |
| max_completion_tokens | `GROQ_MAX_COMPLETION_TOKENS` default **96** |
| max_retries | **0** (avoid burning TPM; LiveKit session may still retry 429s → dead air) |
| Timeout | 30s |
| Reasoning | `gpt-oss*`: `reasoning_effort=low`; `qwen/*`: `reasoning_effort=none` |

**Doc drift warning:** `CTO_CONTEXT_…` still discusses Qwen 3.6 27B as the selected default. **Current adapter default is gpt-oss-20b** because Qwen IDs 404 on many free/developer keys. Research should verify both.

**Persona compaction:** only when `cfg.llm_provider == "groq"` (`build_agent`). Hard ceiling `GROQ_PROMPT_SOFT_CHARS` (default 3000). Drops sections that duplicate platform rules — **including** assuming platform owns voice/spoken rules. If you add spoken rules for ElevenLabs, compact logic may need to stay aligned so Groq doesn’t keep duplicate tenant voice sections.

**Preemptive generation:** **disabled** whenever LLM is Groq (web and phone) — `turn_handling_for_channel` in `worker/latency.py`. Cancelled preemptives were burning free-tier ITPM (~7k ITPM measured).

### 4.3 LLM × TTS interaction (the research core)

| Combo | Spoken rules today | Sanitizer | Tag tax on LLM | Notes |
|-------|-------------------|-----------|----------------|-------|
| Groq + Cartesia | Full SSML teaching block | Keep SSML | **High** every turn | Primary EN demo / telephony path |
| Gemini + Cartesia | Same SSML block | Keep SSML | High + slow TTFT | Web if agent left on Gemini; phone forced off EN |
| Groq + Rime | Rime no-SSML rules | Strip SSML | Medium (style only) | Web only; phone remaps TTS→Cartesia |
| Gemini + Rime | Rime rules | Strip SSML | Medium | Same |
| Groq/Gemini + ElevenLabs | **Base only** | None | Low | Flat “chatbot” risk |
| Groq/Gemini + Fish | **Base only** | None | Low | testing |
| Gemini + Uplift (ur) | **Base only** | None | Low | Only Urdu stack |
| Any + Cartesia after telephony force | Cartesia rules after remap | Cartesia | High | `tts_options` cleared on force |

---

## 5. STT layer — what exists (usually not “humanization,” but combination-relevant)

### 5.1 Gladia — `worker/providers/stt/gladia.py`

- `gladia.STT(languages=[language], code_switching=False)`
- Explicit `code_switching=False` — historical CER 0.14 ur-only vs 0.43 with ur+en switching (ADR-009 / comments)
- Used for **ur** and available for **en**

### 5.2 Deepgram — `worker/providers/stt/deepgram.py`

- Nova-3, `en-US` for English, `no_delay=True`, `endpointing_ms=10`, `interim_results=True`, `smart_format=False`
- Interims feed LiveKit **preemptive generation** when enabled (non-Groq web)
- Optimized for **latency**, not transcript prettiness (smart_format off)

### 5.3 STT × humanization research angles

STT does not emit emotion tags. Combinations still matter because:
- Bad finals → LLM apologizes / hedges → different emotion tags
- Interim quality affects preemptive (when on)
- Urdu Gladia path has **no** Cartesia-style humanization on Uplift
- Code-switching policy is language-critical for Urdu

There is **no** STT-specific prompt profile in code today.

---

## 6. Turn handling / channel policy (not TTS, but changes feel)

File: `worker/latency.py`

| Mode | Preemptive LLM/TTS | Interruption notes |
|------|--------------------|--------------------|
| WebRTC + non-Groq | ON (`preemptive_tts=True`) | False-interruption resume ON |
| WebRTC + Groq | **OFF** | Same interruption base |
| Telephony (any) | **OFF** | False-interruption resume OFF (no browser AEC) |
| Interruption detector | Default `UVA_INTERRUPTION_MODE=vad` (local Silero; skips Cloud adaptive init) | |

Endpointing: `min_delay=0.15`, `max_delay=1.5`.

---

## 7. Telephony remaps (silently change the combination)

File: `worker/telephony_tts.py`

1. **`force_cartesia_for_telephony`** — if channel is telephony and TTS ≠ cartesia → Cartesia Katie + empty `tts_options`.
2. **`force_groq_for_telephony`** — if telephony + EN + Gemini + `GROQ_API_KEY` → Groq + `TELEPHONY_GROQ_MODEL` (same default as groq adapter).

**F-M15 audit note:** capabilities API may still advertise the tenant’s original providers; runtime substitution is silent. Humanization research must treat **effective** providers after remap as the real combo.

---

## 8. Files to open (checklist for code search)

### Prompt / humanization
- `worker/cartesia_spoken_output.py` — **central switch** for system + greeting instructions
- `worker/rime_spoken_output.py`
- `worker/spoken_sanitize.py`
- `worker/cartesia_spoken_sanitize.py`
- `worker/rime_spoken_sanitize.py`
- `worker/main.py` — `build_agent`, `_sanitizing_agent_class`, `_tts_agent_session_extra`, `build_session`
- `worker/session_opening.py` — opening modes + greeting sanitize
- `worker/prompt_compact.py` — Groq-only persona shrink (interacts with token tax)
- `worker/prompt_dump.py` — debug dump of what was actually sent

### TTS adapters / options
- `worker/providers/tts/cartesia.py`, `cartesia_options.py`
- `worker/providers/tts/rime.py`, `rime_options.py`
- `worker/providers/tts/elevenlabs.py`
- `worker/providers/tts/fish_audio.py`
- `worker/providers/tts/uplift.py`
- `worker/telephony_tts.py`

### LLM / STT
- `worker/providers/llm/groq.py`, `gemini.py`
- `worker/providers/stt/gladia.py`, `deepgram.py`
- `worker/providers/capabilities.py`, `registry.py`
- `worker/latency.py` — turn_handling / preemptive / prewarm

### External research already on disk
- `docs/cartesia_humanization.md`
- `docs/rime-labs-humanization.md`
- `docs/CTO_CONTEXT_LLM_LATENCY_AND_CARTESIA_HUMANIZATION.md`

---

## 9. What is **missing** today (honest gaps for research)

1. **No spoken-output profiles for ElevenLabs, Fish Audio, Uplift, or Gladia/Deepgram.**
2. **No matrix of (LLM × TTS) prompt variants** — only TTS-keyed Cartesia/Rime blocks + shared base.
3. **No LLM-keyed humanization** (e.g. shorter Cartesia rules on Groq free tier vs fuller rules on Gemini/paid).
4. **No chat-history sliding window** — history compounds humanization token tax.
5. **No ElevenLabs/Fish `tts_options` schema** analogous to Cartesia/Rime Phase B.
6. **LiveKit expressive path not usable** with plugin Cartesia on current agents version.
7. **Telephony forces** collapse many combinations to Groq+Cartesia on EN phone — web demos exercise more combos than PSTN.
8. **Fish Audio account** historically payment-failing; treat as research + enablement, not assumed live.
9. **Urdu** humanization path (Gladia + Gemini + Uplift) is essentially unimproved relative to EN Cartesia work.

---

## 10. Suggested research questions for Claude

Use the codebase facts above; please **search vendor docs + LiveKit plugin sources** and return a design, not generic advice.

### A. Combination matrix
For each **enabled** combo of `{gladia, deepgram} × {gemini, groq} × {cartesia, rime, elevenlabs, fish_audio}` (and separately `ur: gladia × gemini × uplift`):

1. Which humanization levers belong on **TTS constructor** vs **LLM prompt** vs **post-LLM sanitizer**?
2. What should the LLM be taught to emit (SSML / plain text / provider-specific markup / nothing)?
3. What is the **token cost** of that teaching block vs benefit (especially Groq ~7k ITPM)?
4. After telephony remaps, which combos actually need first-class support vs “web-only”?

### B. Architecture for settings
Propose a maintainable structure in this repo, e.g.:
- `spoken_output_for(tts_provider, llm_provider, channel) -> rules`
- vs TTS-only profiles + separate LLM “brevity” profiles
- How to avoid cross-contaminating Cartesia tags into Rime/ElevenLabs (sanitizer already shows this failure mode)
- How `prompt_compact` should treat new spoken-rule ownership

### C. Provider-specific unknowns to look up
- **ElevenLabs:** stability/similarity/style/speaker_boost; SSML support in LiveKit plugin; streaming; telephony.
- **Fish Audio:** any emotion/prosody API; language handling without `language` kwarg; LiveKit plugin kwargs.
- **Cartesia:** confirm Sonic 3.5 emotion tag list vs our prompt list; whether baseline `emotion=["calm","content"]` fights mid-turn `<emotion>` tags.
- **Rime:** Arcana vs Coda for agent IVR; whether our Arcana default is correct; fillers without SSML.
- **Uplift:** Urdu prosody / phrase config as humanization.
- **Gladia / Deepgram:** any settings that improve “natural” agent turns (endpointing, formatting) without hurting latency.
- **Gemini vs Groq:** does the same Cartesia SSML prompt compliance differ by model? Should Groq get a **shorter** emotion vocabulary to save completion tokens (cap 96)?

### D. Latency coupling (must not ignore)
From CTO brief: humanization and TTFT/ITPM are coupled. Any proposal that adds system tokens on Groq must include a **mitigation** (paid tier, shorter rules, history window, fewer tools, TTS-side-only humanization, or framework expressive injection).

### E. Deliverable shape requested from research
1. Decision table: combo → prompt profile ID + TTS options defaults + sanitizer + notes.
2. Recommended **implementation order** (e.g. ElevenLabs TTS-side first, then thin LLM style rules, then Urdu).
3. Explicit “do not do” list (e.g. never put Cartesia tags in base instructions for all TTS).
4. Open questions that need a live A/B call, not more docs.

---

## 11. Paste-ready one-liner for Claude

> You are researching humanization for AwaazLabs UVA, a LiveKit cascaded STT→LLM→TTS worker. Read `docs/HUMANIZATION_CODEBASE_CONTEXT_FOR_RESEARCH.md` as ground truth for current behavior. Today only Cartesia (SSML emotion tags + sanitizer + sonic-3.5 defaults) and Rime (no-SSML spoken rules + sanitizer + Arcana defaults) are humanized; ElevenLabs, Fish Audio, and Uplift have no spoken-output profiles; prompts key off TTS provider only; EN telephony silently forces Cartesia+Groq; Groq free-tier ITPM conflicts with large Cartesia teaching prompts. Design per-combination settings and prompts for Gladia/Deepgram × Gemini/Groq × Cartesia/Rime/ElevenLabs/Fish (and Urdu Gladia×Gemini×Uplift), with token/latency tradeoffs and an implementation plan that fits the existing `build_system_instructions` / `tts_options` / sanitizer architecture.

---

*Generated as a research handoff from the live worker codebase. Prefer code over older narrative docs when they disagree (especially Groq default model).*
