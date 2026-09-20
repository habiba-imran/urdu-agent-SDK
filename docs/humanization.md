# AwaazLabs UVA — Humanization Research Handoff

**Research status:** Research-only; not an implementation specification  
**Research cutoff:** 17 September 2026  
**Primary codebase source:** `HUMANIZATION_CODEBASE_CONTEXT_FOR_RESEARCH.md` supplied for this research  
**Objective:** Capture the research findings for making the cascaded `STT → LLM → TTS` voice agent feel natural across supported provider combinations while preserving latency, interruption behavior, safety, and maintainability.

---

## 1. Evidence labels used in this handoff

This document separates:

1. **Current codebase fact** — behavior stated in the supplied codebase context.
2. **Current vendor/framework fact** — behavior verified against provider or LiveKit docs current at the research cutoff.
3. **Research recommendation** — a proposed direction based on those facts.
4. **Needs A/B / repo verification** — do not treat as production truth until tested against the exact pinned SDK, voice, model, account tier and deployment.

This distinction matters because the worker was built around older provider behavior while Cartesia, Rime, ElevenLabs, Fish, Gemini, Deepgram and LiveKit have changed substantially.

---

# 2. Current UVA humanization architecture

The current loop is:

```text
Caller audio
    ↓
LiveKit
    ↓
VAD
    ↓
STT
    ↓
end-of-utterance / turn handling
    ↓
LLM
    ↓
spoken-output sanitizer
    ↓
TTS
    ↓
audio
```

One worker serves multiple combinations.

## 2.1 Current provider matrix

### English

```text
STT: Gladia / Deepgram
LLM: Gemini / Groq
TTS: Cartesia / Rime / ElevenLabs / Fish Audio
```

This produces up to:

```text
2 × 2 × 4 = 16
```

theoretical English combinations before channel remaps.

### Urdu

Current codebase context:

```text
Gladia → Gemini → Uplift
```

## 2.2 Humanization layers currently present

| Layer | Current responsibility |
|---|---|
| LLM spoken-output rules | Teach spoken style and sometimes TTS markup |
| TTS defaults | Model, voice, speed, emotion, transport and provider options |
| Audio profile | WebRTC vs telephony sample-rate / encoding decisions |
| Sanitizer | Remove unwanted text; retain only provider-valid markup |
| Streaming tokenizer | Split text without delaying audio or breaking markup |
| Turn policy | EOU, preemptive generation, interruptions |
| Runtime remaps | PSTN can change configured providers |

## 2.3 Current provider asymmetry

### Cartesia
Current custom stack includes spoken rules, emotion markup, sanitizer, XML-aware tokenizer, defaults and channel profiles.

### Rime
Has a partial stack: plain-text spoken rules, punctuation/filler guidance, sanitizer and options.

### ElevenLabs
Current UVA context exposes almost none of the available humanization controls: basically voice + language, without a dedicated options/profile layer.

### Fish
Likewise lacks a full humanization profile in UVA and is currently marked testing.

### Uplift
Urdu-only path with no English-style provider humanization layer.

## 2.4 Effective providers matter

English PSTN may change runtime providers:

```text
non-Cartesia TTS → Cartesia
Gemini → Groq when GROQ_API_KEY is available
```

Therefore humanization must be resolved **after runtime remapping**.

---

# 3. Main architecture conclusion

Do **not** create 16 full prompts.

Avoid:

```python
if deepgram_groq_cartesia:
    ...
elif gladia_groq_cartesia:
    ...
# many more...
```

Recommended decomposition:

```text
                  HUMANIZATION PROFILE
                          │
       ┌──────────────────┼───────────────────┐
       │                  │                   │
       ▼                  ▼                   ▼
LLM speech policy     TTS delivery       turn-taking
       │                  │                   │
Groq / Gemini       Cartesia / Rime     Deepgram / Gladia
                    Eleven / Fish
                    Uplift
       │                  │                   │
       └──────────────────┼───────────────────┘
                          │
                     channel profile
                    WebRTC / PSTN
```

Use this mental model:

```text
LLM:
"What would a person naturally say?"

TTS:
"How should it be delivered?"

STT + VAD + EOU:
"When should the agent respond?"

Channel:
"What latency/interruption behavior is appropriate?"
```

This layered architecture is the strongest overall research result.

---

# 4. Universal spoken-output policy

Across current provider guidance, the same basics repeat:

- write for the ear, not the page
- use short spoken sentences
- use contractions naturally
- avoid corporate boilerplate
- do not restate everything the caller said
- use punctuation for rhythm
- avoid markdown, headings, bullets and emoji
- use fillers/disfluencies lightly
- do not force emotion into every turn
- keep most voice turns concise

A conceptual shared platform block could be:

```text
VOICE OUTPUT

Write for the ear, not the page.

Use short, natural spoken sentences and ordinary conversational wording.
Use contractions naturally.
Respond directly instead of repeating what the caller already said.
Avoid repetitive acknowledgements and canned phrases.
Do not use markdown, headings, bullets, emoji, or document-style formatting.
Use punctuation naturally to shape rhythm.
Occasional brief hesitation or filler is fine when it genuinely fits,
but never force one into every response.
Match the caller's emotional register without exaggerating it.
Keep most replies concise and let the caller lead the depth.
```

Do **not** put provider markup into the universal block:

```text
<emotion>
<break>
<speed>
<volume>
[laugh]
[sigh]
[whisper]
spell(...)
```

Those belong to provider/language delivery layers.

---

# 5. Groq findings

## Current model

Current Groq docs still expose:

```text
openai/gpt-oss-20b
```

with roughly:

```text
~1000 output tokens/sec
```

and low/medium/high reasoning effort.

For realtime voice, UVA's existing low-reasoning choice remains sensible.

## Rate-limit reality

The current public Groq rate-limit page displays `openai/gpt-oss-20b` around:

```text
30 RPM
1K RPD
8K TPM
200K TPD
```

for the shown developer limits.

Actual account headers/limits remain authoritative. UVA's historical ~7K-class pressure should therefore still be taken seriously.

## Prompt caching

Groq now automatically prompt-caches GPT-OSS prefixes.

Important rules:

- exact prefix matching
- static rules/tools/examples first
- dynamic/user/session material later
- cached input reduces processing cost/latency
- cached tokens do not count toward rate limits in the same way as uncached input

This strongly supports keeping platform voice rules static and tenant/session data later.

## Humanization implication

For Groq:

```text
small universal spoken block
+ tiny provider overlay only when necessary
+ TTS-side delivery
```

is preferable to a giant emotion/SSML teaching prompt.

Why:

- input-token count affects TTFT
- markup consumes the 96-token output budget
- prompt-cache reuse is improved
- cancellation waste remains a concern

The Groq profile should mainly enforce:

- concise voice turns
- direct answers
- minimal unnecessary explanation
- minimal markup burden
- strong tool discipline

Sources:

- https://console.groq.com/docs/model/openai/gpt-oss-20b
- https://console.groq.com/docs/reasoning
- https://console.groq.com/docs/prompt-caching
- https://console.groq.com/docs/rate-limits

---

# 6. Gemini findings

## Model drift

Current stable Flash:

```text
gemini-3.8-flash
```

Google still supports 3.7 and 3.6 as previous-generation Flash models.

## Thinking-level difference

UVA currently uses Gemini 3.6 with minimal thinking.

Current docs:

```text
Gemini 3.6 Flash:
minimal / low / medium / high

Gemini 3.8 Flash:
low / medium / high
```

`minimal` is not supported on 3.8.

Google explicitly positions `low` for latency-sensitive cases such as realtime chat.

## Required A/B

Do not blindly upgrade.

Test:

```text
3.6 Flash + minimal
vs
3.8 Flash + low
```

Measure:

- TTFT
- short spoken-response compliance
- tool behavior
- tendency to over-explain
- provider markup reliability
- interruption/cancellation behavior
- token usage

## Migration caveat

Google's 3.8 migration guidance says to remove older sampling parameters such as:

```text
temperature
top_p
top_k
```

So UVA's `temperature=0.4` should not simply be carried into 3.8 testing.

## Prompt style

Google's current Gemini 3 guidance favors direct, concise instructions and warns that over-complicated prompting can lead to over-analysis.

Therefore Gemini also benefits from:

```text
small shared spoken policy
+ small Gemini conversational modifier
+ TTS delivery layer
```

Sources:

- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash
- https://ai.google.dev/gemini-api/docs/latest-model
- https://ai.google.dev/gemini-api/docs/thinking
- https://ai.google.dev/gemini-api/docs/generate-content/gemini-3

---

# 7. Cartesia findings

## Sonic 3.6 is now current at Cartesia

UVA currently defaults to `sonic-3.5`.

Cartesia's own current docs say:

```text
Sonic 3.6 (`sonic-3.6`) is GA
```

with stable snapshot:

```text
sonic-3.6-2026-08-27
```

## Sonic 3.6 naturalness changes the prompt question

Cartesia says Sonic 3.6:

- is its fastest / most natural current model
- supports 44 languages
- varies pacing and intonation from transcript emotional context
- can do so without explicit SSML
- renders textual "uhm"/"hmm" naturally
- added Urdu
- is backwards compatible with 3.5

This means the current rule requiring emotion markup on nearly every reply needs A/B testing.

## Current SSML-like controls

Cartesia currently documents:

```text
<speed>
<volume>
<emotion>
<break>
<spell>
```

But:

- emotion is beta / experimental
- punctuation should be the first pause mechanism
- `<break>` splits generation context and can make speech less natural
- repeated break tags can be harmful
- `<spell>` is useful for strict character-by-character output

Therefore:

```text
"Um... let me check that."
```

may be better than mechanically inserting:

```text
um <break time="300ms"/>
```

## Voice selection

Cartesia recommends stable, pleasant, realistic voices for voice agents rather than maximal theatrical emotion.

The research conclusion is:

> Humanization should mean appropriate emotional delivery, not maximum emotional delivery.

## Urdu

Sonic 3.6 now supports Urdu.

This creates a future benchmark:

```text
Uplift Urdu
vs
Cartesia Sonic 3.6 Urdu
```

Do not change the UVA Urdu matrix without a real Pakistani-Urdu listening test.

## LiveKit mismatch

Cartesia vendor docs are already on Sonic 3.6.

Current LiveKit hosted-model docs still visibly expose Sonic 3 family IDs.

Therefore verify:

- pinned `livekit-plugins-cartesia`
- direct plugin vs LiveKit Inference
- exact model-string support
- sanitizer/tokenizer behavior

before switching models.

## Modern LiveKit expressive mode

Current LiveKit docs say Cartesia Sonic supports:

```python
AgentSession(..., expressive=True)
```

with framework delivery controls such as emotion, pace, volume and pauses.

This is newer than the limitation described in the supplied UVA context.

It deserves a direct A/B against the current manual Cartesia prompt.

Suggested experiment:

```text
A. Sonic 3.5 + current manual tags
B. Sonic 3.6 + current manual tags
C. Sonic 3.6 + lighter plain text
D. Sonic 3.6 + LiveKit expressive mode
```

Sources:

- https://docs.cartesia.ai/build-with-cartesia/tts-models/latest
- https://docs.cartesia.ai/build-with-cartesia/capability-guides/ssml-tags
- https://docs.livekit.io/agents/models/tts/cartesia/

---

# 8. Rime findings

## Current docs no longer center Arcana

UVA currently defaults to Arcana.

Current Rime model docs center:

```text
Coda
Mist v3
Mist v2
```

and say:

> Start with Coda for new applications.

Arcana does not appear as a current model in the present model overview, so UVA's Arcana default should be treated as code/provider drift until the actual account is checked.

## Coda

Rime describes Coda as:

- flagship
- released May 2026
- trained on full-duplex conversational data
- highest Rime human-evaluation quality for naturalness/prosody/artifact-free output
- sub-100ms model latency in Rime's self-hosted/on-prem figures
- word-level timestamps
- `spell()` support

Coda is the strongest default humanization baseline.

## Mist

Mist v3:
- lowest TTFA focus
- custom pauses

Mist v2:
- inline pronunciation control

Therefore:

```text
best conversational baseline → Coda
extreme TTFA priority         → Mist v3 experiment
load-bearing inline phonemes  → Mist v2 experiment
```

## Rime prompting philosophy

Current Rime guidance is clear:

- LLM prose is often too formal for speech
- Coda does not accept SSML
- use conversational words + punctuation
- use contractions
- use fillers/restarts lightly
- do not stack fillers
- keep sentences short
- keep baseline calm
- don't put excitement into every turn

So Rime should remain a plain-text provider.

Conceptual overlay:

```text
Express delivery through wording and punctuation.
Do not emit SSML or voice-control markup.
Use fillers only where a person would genuinely hesitate.
Keep sentences short.
```

## Speed warning

Do not carry Arcana-era speed settings blindly into Coda/Mist.

Speed semantics vary across Rime models; model migration needs a fresh listening/latency test.

Sources:

- https://docs.rime.ai/docs/models
- https://docs.rime.ai/docs/prompting

---

# 9. ElevenLabs findings

## UVA currently underuses the provider

Current UVA context only uses roughly voice + language.

Modern ElevenLabs and the current LiveKit plugin expose much more.

## Model choices

### Flash v2.5
Current ElevenLabs guidance:
- low-latency realtime model
- about 75ms model latency in published guide

### Eleven v3
- most expressive general TTS
- audio tags
- higher variability/latency
- not recommended as the standard realtime conversational model

### Eleven v3 Conversational
This is a separate realtime expressive model:
- about 280ms published model latency
- audio tags
- 70+ languages
- specifically positioned for expressive conversational agents

Do not confuse:

```text
eleven_v3
```

with:

```text
eleven_v3_conversational
```

## Voice settings

Current API exposes:

```text
stability
similarity_boost
style
use_speaker_boost
speed
```

Provider guidance:

- lower stability → more emotional variation
- higher stability → more consistent, potentially monotonous
- nonzero style may add compute/latency
- speaker boost adds computational load
- speed 1.0 is normal

Do not hard-code one global "human" preset; voice behavior varies.

## Current LiveKit plugin surface

Current LiveKit ElevenLabs TTS supports:

- `voice_settings`
- model selection
- `auto_mode`
- normalization
- language normalization
- tokenizer choice
- SSML parsing toggle
- chunk scheduling
- custom HTTP session
- aligned transcript
- pronunciation dictionaries

It also recognizes:

```text
eleven_v3
eleven_v3_conversational
```

and routes those through ElevenLabs' text-to-dialogue API.

## Operational change

Current LiveKit docs say ElevenLabs was retired from LiveKit Inference on **31 August 2026**.

The direct plugin still works with your own ElevenLabs account.

## Connection reuse

Current LiveKit plugin code keeps/reuses a valid current TTS connection.

Before adding more custom connection caching, inspect whether UVA's provider-client lifecycle already preserves that plugin instance long enough to benefit.

## Recommended starting paths

### Low-latency baseline

```text
universal spoken policy
    ↓
plain text
    ↓
Flash v2.5
    ↓
voice settings + pronunciation + normalization
```

### Expressive experiment

```text
universal spoken policy
+ small Eleven audio-tag guidance
    ↓
eleven_v3_conversational
```

But verify which options are ignored by the text-to-dialogue path.

## LiveKit expressive-mode caveat

This research found explicit current generic LiveKit expressive support for Cartesia and Fish, but not equivalent documentation for ElevenLabs.

Do not assume:

```python
expressive=True
```

automatically teaches ElevenLabs audio tags.

Sources:

- https://elevenlabs.io/docs/eleven-api/choosing-the-right-model
- https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech
- https://elevenlabs.io/docs/api-reference/voices/settings/update
- https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/what-is-eleven-v3-alpha
- https://docs.livekit.io/agents/models/tts/elevenlabs/
- https://docs.livekit.io/reference/python/livekit/plugins/elevenlabs/index.html

---

# 10. Fish Audio findings

## Current production model

Fish recommends:

```text
s2.1-pro
```

Provider docs describe:

- improved quality/latency/throughput over S2-Pro
- production TTFA/DPA option
- 83 provider-level languages
- natural-language bracket delivery control

## Delivery syntax

Fish S2.1 Pro understands natural-language square-bracket cues such as:

```text
[whispers sweetly]
[laughing nervously]
```

and common styles including:

```text
[whisper]
[laugh]
[emphasis]
[sigh]
[gasp]
[pause]
[angry]
[excited]
[sad]
[surprised]
[inhale]
[exhale]
```

This is a strong fit for LLM-driven expressive delivery.

## LiveKit expressive support

Current LiveKit explicitly says Fish `s2.1-pro` supports expressive mode.

The framework can drive:

- emotion
- emphasis
- pauses
- non-verbal events

## Useful TTS controls

Current LiveKit Fish path exposes controls such as:

```text
latency_mode
speed
volume
temperature
```

## Capability-path mismatch

Fish provider docs say S2.1 Pro supports 83 languages.

LiveKit's hosted model page may expose a smaller explicit language list.

Again:

```text
provider capability ≠ every LiveKit access path
```

Verify direct plugin/inference before expanding UVA capabilities.

## Recommended direction

```text
universal spoken policy
    ↓
Groq/Gemini concise response
    ↓
LiveKit expressive
    ↓
Fish S2.1 Pro
```

Avoid a large custom Fish prompt unless listening tests prove necessary.

## Restraint

Do not give a professional support agent the entire non-verbal vocabulary.

Reasonable early candidates:
- light laughter only when genuinely appropriate
- subtle emphasis
- calm/empathetic direction
- brief pauses

Likely disable initially:
- crying/sobbing
- panting/groaning
- random coughing
- frequent throat clearing
- dramatic gasps
- singing/vocalization

Sources:

- https://docs.fish.audio/developer-guide/models-pricing/models-overview
- https://docs.livekit.io/agents/models/tts/fishaudio/

---

# 11. Uplift / Urdu findings

## Urdu must be its own language profile

Do not translate English humanization rules word-for-word.

Natural Urdu depends on:

- Pakistani phrasing
- Urdu script
- gender grammar
- dates/numbers
- English business names
- code switching
- pronunciation
- sentence rhythm

## Uplift's own guidance

Its current LiveKit tutorial explicitly uses:

- Pakistani Urdu
- proper Urdu script
- no Roman Urdu
- simple conversational language
- concise spoken responses
- continuous oral narration, not bullets
- spoken dates rather than raw digits

This supports language-first humanization.

## Phrase replacements

Uplift exposes reusable pronunciation replacement configs for:

- brands
- technical terms
- LLM misspellings
- regional variants
- English spelling → Urdu phonetic output

This is highly relevant for business voice agents.

## Recommended Urdu architecture

```text
Gladia
    ↓
Gemini
    ↓
Urdu spoken-output profile
    ↓
phrase/pronunciation replacement
    ↓
Uplift
```

not:

```text
English emotion markup translated into Urdu
```

## Future branch

Because Sonic 3.6 now supports Urdu, later compare:

```text
Uplift
vs
Cartesia Sonic 3.6 Urdu
```

using real Pakistani speakers.

Sources:

- https://docs.upliftai.org/tutorials/livekit-voice-agent
- https://docs.upliftai.org/sdk/nodejs/phrase-replacements

---

# 12. Deepgram findings

## Current UVA setting is latency-first

UVA:

```text
Nova-3
endpointing=10ms
no_delay=True
interim_results=True
smart_format=False
```

Current Deepgram docs say:

```text
10ms:
fast chatbot / short utterance behavior

300–500ms:
better for conversations with mid-thought pauses
```

So 10ms should not automatically be considered the most human setting.

## Why it matters

User:

```text
"So I ordered it yesterday... um... and then the wrong size came."
```

Too-aggressive endpointing may:

- commit too early
- cause interruptions
- send incomplete turns
- sound impatient

## Required A/B

Test:

```text
10ms
100ms
200ms
300ms
500ms
```

Track:
- false EOU
- actual EOU latency
- interruption count
- user repeats
- subjective conversation flow

## Flux

Deepgram now positions Flux for voice agents.

It provides:

```text
StartOfTurn
EndOfTurn
EagerEndOfTurn
TurnResumed
```

and integrated turn detection.

Deepgram itself recommends starting with **EndOfTurn only**.

### Groq + Flux
Start with final EOT only due cancelled speculative request/token pressure.

### Gemini + Flux
Eager EOT can be A/B tested if its additional speculative calls are acceptable.

Sources:

- https://developers.deepgram.com/docs/understand-endpointing-interim-results
- https://developers.deepgram.com/docs/flux/agent

---

# 13. Gladia findings

Current LiveKit Gladia plugin publicly exposes:

```text
languages
code_switching
translation
runtime option updates
```

STT should not have a "humanization prompt."

Gladia affects the experience through:

- transcript accuracy
- language behavior
- code switching
- timing

The current UVA Urdu decision to keep code switching off was evidence-driven; do not reverse it just because code switching sounds more natural in theory.

Source:

- https://docs.livekit.io/agents/models/stt/gladia/

---

# 14. LiveKit turn detector findings

Current LiveKit Agents includes an audio turn detector.

It offers:

```text
v1      → full model through LiveKit Inference
v1-mini → local CPU model
```

It requires VAD and requires `min_silence_duration >= 0.25s`.

Current docs list 14 supported languages:

```text
English, Arabic, German, Spanish, French, Hindi,
Indonesian, Italian, Japanese, Korean, Dutch,
Portuguese, Turkish, Chinese
```

Urdu is not listed.

This could make English turn handling more provider-independent:

```text
audio
 ├─ STT → transcript
 └─ TurnDetector → EOU signal
          ↓
         LLM
```

But UVA's previous cold-start work found heavier turn/interruption initialization could add startup cost.

Any turn-detector test must measure:

```text
session.start_ms
job → first audio
false EOU
EOU latency
```

Source:

- https://docs.livekit.io/agents/logic/turns/turn-detector/

---

# 15. STT belongs in turn policy, not spoken policy

Avoid:

```python
if stt == "deepgram":
    spoken_prompt += ...
```

Prefer:

```python
turn_profile = turn_profile_for(
    stt=effective_stt,
    llm=effective_llm,
    language=language,
    channel=channel,
)
```

Turn-profile concerns include:

- endpointing
- turn detector
- preemptive LLM
- preemptive TTS
- interruption sensitivity
- false-interruption resume
- barge-in behavior

---

# 16. Channel policy

## WebRTC

Usually allows:

- better audio conditions
- more reliable echo cancellation
- more aggressive interruption recovery
- optional speculation where quotas permit

## Telephony

Current UVA context:

- forces Cartesia TTS
- may force Groq for English
- disables preemptive generation
- uses different interruption behavior
- uses telephony-specific audio settings

Resolve humanization **after** these remaps.

Correct:

```text
config
 ↓
runtime remaps
 ↓
effective providers
 ↓
humanization profile
```

---

# 17. Proposed provider-combination matrix

| LLM | TTS | Spoken policy | Delivery |
|---|---|---|---|
| Groq | Cartesia | Compact universal + Groq modifier | Sonic 3.6 native prosody and/or LiveKit expressive |
| Gemini | Cartesia | Universal + Gemini conversational modifier | Sonic 3.6 native prosody and/or expressive |
| Groq | Rime | Compact universal + tiny Rime overlay | Coda plain-text prosody |
| Gemini | Rime | Universal + tiny Rime overlay | Coda plain-text prosody |
| Groq | ElevenLabs | Compact universal | Flash + TTS settings first |
| Gemini | ElevenLabs | Universal | Flash + TTS settings first |
| Groq | Fish | Compact universal | S2.1 Pro + LiveKit expressive |
| Gemini | Fish | Universal | S2.1 Pro + LiveKit expressive |
| Gemini | Uplift | Urdu-specific profile | Uplift + phrase replacements |

STT/turn profile is composed separately.

---

# 18. Humanization should be restrained

"More expressive" is not automatically "more human."

Failure modes:

```text
"um" on every turn
emotion tags on every sentence
constant fake empathy
unnecessary laughter
random sighs
constant enthusiasm
repetitive "yeah/so/well"
slow theatrical delivery
random non-verbal noises
```

A strong business-agent baseline should be mostly normal speech with contextually earned variation.

Humanization means natural conversational behavior, not pretending to be a human.

---

# 19. Sanitizer requirements

Use:

```text
sanitizer_for(effective_tts, effective_model)
```

not only the originally configured provider.

### Cartesia
Allow only its valid markup when using manual markup.

### Rime
Strip Cartesia/Fish/Eleven syntax.

### ElevenLabs
Do not allow Cartesia markup simply because SSML parsing exists.

### Fish
Prevent Fish bracket cues from leaking to other TTS providers.

### Uplift
Prefer Urdu text cleanup / phrase replacement.

Cross-provider markup leakage remains a serious design risk.

---

# 20. Tokenizer requirements

Goals:

- low first-token-to-TTS delay
- preserve enough sentence context for prosody
- never split markup in a way that makes TTS read it aloud

Provider notes:

### Cartesia manual path
XML-aware splitting remains important.

### Cartesia framework expressive
Verify whether the custom XML-aware tokenizer is still needed.

### Rime
Short, natural sentence chunks.

### ElevenLabs
Current plugin already has `auto_mode`, sentence tokenization and chunk scheduling.

### Fish
Use streaming/latency controls without destroying delivery quality.

### Uplift
Stream short Urdu chunks while preserving grammatical context.

---

# 21. Conversation-history coupling

Current UVA context says full conversation history is sent every turn.

That compounds:

- TTFT
- Groq token pressure
- accumulated markup
- stale spoken-style influence

Humanization should avoid putting provider delivery markup into persistent history where possible.

A future history/window strategy should preserve:

```text
static platform rules
tenant persona as data
recent meaningful turns
tool outcomes
```

without indefinitely accumulating old expressive syntax.

---

# 22. Prompt-compaction implication

Groq persona compaction already assumes platform rules own voice behavior.

Keep that ownership.

If new Eleven/Fish/Uplift spoken rules are added:

- keep them platform-owned
- do not duplicate them in tenant persona
- keep static prefixes stable for Groq caching
- only change compaction logic when ownership truly changes

---

# 23. Conceptual resolver

Research direction:

```python
effective = resolve_effective_providers(cfg, channel)

speech_rules = universal_spoken_rules(language=effective.language)
speech_rules += llm_profile(effective.llm)

tts_profile = tts_humanization_profile(
    provider=effective.tts,
    model=effective.tts_model,
    language=effective.language,
    channel=effective.channel,
)

turn_profile = turn_profile_for(
    stt=effective.stt,
    llm=effective.llm,
    language=effective.language,
    channel=effective.channel,
)
```

Provider profile decides:

```text
prompt overlay
constructor defaults
expressive mode
sanitizer
tokenizer
pronunciation mechanism
```

---

# 24. Conceptual data model

```text
SpokenOutputProfile
├── base_rules
├── llm_overlay
├── provider_overlay
├── language_overlay
└── max spoken-turn guidance

TTSHumanizationProfile
├── model
├── defaults
├── expressive_mode
├── expressive_options
├── sanitizer
├── tokenizer
├── pronunciation strategy
└── audio profile

TurnProfile
├── detector
├── endpointing
├── preemptive_llm
├── preemptive_tts
├── interruption policy
├── false-interruption resume
└── channel overrides
```

---

# 25. Provider priorities

## P0 — Cartesia

Investigate:
1. Sonic 3.5 → 3.6 compatibility through actual plugin path.
2. Native 3.6 prosody without mandatory tags.
3. Modern LiveKit expressive mode.
4. Manual markup vs framework expressive vs plain text.
5. Whether constructor default emotions fight contextual delivery.
6. Urdu only as a later benchmark.

## P0 — Rime

Investigate:
1. Arcana status/account availability.
2. Coda migration.
3. Coda voices.
4. speed semantics.
5. pronunciation requirements.
6. Coda vs Mist v3 latency.

## P0/P1 — ElevenLabs

Investigate:
1. options schema.
2. Flash v2.5 baseline.
3. stability/similarity/style/speaker boost/speed.
4. pronunciation dictionaries.
5. `auto_mode`.
6. v3 Conversational separately.
7. own ElevenLabs account after LiveKit Inference retirement.
8. whether UVA lifecycle preserves plugin connection reuse.

## P1 — Fish

Investigate:
1. account enablement.
2. S2.1 Pro.
3. LiveKit expressive mode.
4. restrained non-verbal vocabulary.
5. latency modes.
6. direct-provider vs LiveKit capability differences.

## Separate Urdu track

Investigate:
1. Pakistani Urdu spoken profile.
2. phrase replacement.
3. dates/numbers.
4. English brand/name pronunciation.
5. Gladia code-switching only through real A/B.
6. Cartesia Urdu later.

---

# 26. Turn-taking priorities

## P0
Deepgram Nova endpoint A/B:

```text
10 / 100 / 200 / 300 / 500ms
```

## P1
Deepgram Flux:
- EndOfTurn first
- eager EOT later
- stay conservative with Groq

## P1
LiveKit TurnDetector:
- v1
- v1-mini
- measure cold-start impact

## Urdu
Keep separate because current LiveKit audio TurnDetector language list does not include Urdu.

---

# 27. Listening-test scenarios

Use the same test set for every combination.

### A — Simple factual
"What time do you close?"

### B — Mid-thought pause
"So I ordered yesterday... [pause] ...and the wrong size came."

### C — Emotional caller
"I'm pretty frustrated. This is the third time I've called."

### D — Correction
"No, that's not what I meant."

### E — Tool wait
"Can you check my order?"

### F — Immediate barge-in
Interrupt within the first 300–500ms.

### G — Codes
"My confirmation code is AB19X7."

### H — Difficult names/brands
Use actual production terms.

### I — Long multi-part request
Test false EOU.

### J — Appropriate humor
Test whether laughter is contextually restrained.

---

# 28. Metrics

## Latency

```text
EOU → LLM request
LLM request → first token
TTS input → first audio
EOU → first audible agent response
```

## Turn behavior

```text
false interruptions
late replies
barge-in recovery
user repeat rate
```

## LLM speech quality

```text
corporate/formal wording
repetition
over-acknowledgment
sentence length
filler frequency
markup leakage
```

## TTS quality

```text
naturalness
prosody
emotional fit
pronunciation
voice stability
artifacts
```

## Resource use

```text
input tokens
output tokens
cancelled speculative calls
Groq cached tokens
TTS cost
```

---

# 29. Human listening rubric

Rate each 1–5:

| Metric | Question |
|---|---|
| Natural wording | Would someone actually phrase it this way aloud? |
| Pace/rhythm | Are pauses and cadence natural? |
| Emotional fit | Is emotion appropriate and restrained? |
| Concision | Is the response right-sized for speech? |
| Interruption | Does the agent stop/listen correctly? |
| Turn timing | Does it wait for true EOU? |
| Voice stability | Is the voice consistent? |
| Pronunciation | Are names, codes and numbers correct? |
| Repetition | Does it avoid repeating fillers/acknowledgments? |
| Overall comfort | Does the conversation feel fluid and competent? |

---

# 30. Key experiments

## Cartesia

```text
A. Sonic 3.5 + current tags
B. Sonic 3.6 + current tags
C. Sonic 3.6 + light/plain text
D. Sonic 3.6 + LiveKit expressive
```

## Rime

```text
A. current Arcana
B. Coda
C. Mist v3 if TTFA is critical
```

## ElevenLabs

```text
A. current minimal adapter
B. Flash v2.5 + tuned voice settings
C. v3 Conversational
```

## Turn handling

```text
A. Nova-3 endpoint=10ms
B. Nova-3 200–300ms
C. Flux EndOfTurn
D. LiveKit audio TurnDetector
```

## LLM

```text
Groq GPT-OSS 20B low
vs
Gemini 3.6 Flash minimal
vs
Gemini 3.8 Flash low
```

using the same TTS and same spoken policy.

---

# 31. Do-not-do list

1. Do not create 16 duplicated humanization prompts.
2. Do not put Cartesia tags in universal rules.
3. Do not send provider markup to the wrong TTS.
4. Do not resolve humanization before telephony remaps.
5. Do not assume a newer model is automatically faster.
6. Do not move Gemini 3.6 minimal → 3.8 low without TTFT tests.
7. Do not carry old Gemini sampling settings blindly into 3.8.
8. Do not grow the Groq system prompt casually.
9. Do not force emotion markup into every Groq reply.
10. Do not overuse Cartesia `<break>`.
11. Do not send Cartesia SSML to Rime.
12. Do not treat Rime as an SSML provider.
13. Do not carry Arcana speed settings to Coda blindly.
14. Do not confuse `eleven_v3` with `eleven_v3_conversational`.
15. Do not assume generic LiveKit expressive support for ElevenLabs.
16. Do not expose all Fish non-verbal sounds by default.
17. Do not turn Urdu Gladia code switching on without real evidence.
18. Do not translate English voice rules word-for-word into Urdu.
19. Do not keep 10ms endpointing only because it benchmarks faster.
20. Do not enable Flux eager EOT on Groq without token-cost analysis.
21. Do not adopt a heavier turn detector without rechecking cold start.
22. Do not judge humanization only by TTS voice quality.
23. Do not accumulate provider markup forever in conversation history.
24. Do not use one provider preset for all voices.
25. Do not make the agent cough/laugh/sigh constantly.
26. Do not trade several seconds of TTFT for marginal naturalness.
27. Do not assume provider language coverage equals LiveKit-path coverage.
28. Do not assume a vendor API feature exists in the pinned plugin.
29. Do not duplicate caching/connection behavior already done by LiveKit.
30. Do not use filler audio to hide engineering latency.

---

# 32. Suggested repo-review order after this research

For every finding, mark:

```text
ALREADY PRESENT
APPLICABLE NOW
REQUIRES SDK UPGRADE
REQUIRES PROVIDER MODEL CHANGE
REQUIRES PROVIDER ACCOUNT CHANGE
REQUIRES A/B CALL
NOT APPLICABLE
```

Suggested review sequence:

1. universal spoken policy
2. effective-provider resolution after remaps
3. Rime model drift
4. ElevenLabs options/plugin support
5. Cartesia Sonic 3.6 + expressive support
6. Fish account/model readiness
7. Deepgram endpointing/Flux
8. LiveKit TurnDetector startup impact
9. Urdu/Uplift phrase replacements
10. history/prompt-compaction implications

---

# 33. Open questions requiring repo inspection or listening tests

## Cartesia
- Does the pinned plugin accept `sonic-3.6`?
- Does plain Sonic 3.6 beat mandatory emotion tags?
- Does constructor emotion fight native contextual prosody?
- Does modern LiveKit expressive work in UVA?
- Is XML-aware tokenization still required in that path?
- How good is Sonic 3.6 Urdu for Pakistani speech?

## Rime
- Is Arcana still enabled on the account?
- Which seeded voices are Coda-compatible?
- Does Coda now meet PSTN realtime requirements?
- What speed settings sound best?

## ElevenLabs
- What model is actually used today if UVA omits model?
- Does the pinned plugin include `eleven_v3_conversational`?
- Which dialogue options are ignored?
- Flash tuned vs v3 Conversational: which is better at acceptable TTFA?
- Does `auto_mode` improve UVA TTFA?
- Is the plugin connection reused across jobs in UVA's cache lifecycle?

## Fish
- Is the account now production-ready?
- Which languages are really available through UVA's access path?
- Which expressive vocabulary is appropriate?
- Which latency mode is best?

## Uplift
- Is phrase replacement exposed in UVA's Python path?
- How should dictionaries sync with tenant config?
- How should mixed Urdu/English names be written?
- How does it behave under interruption?

## LLM
- Does Groq follow expressive markup under 96 output tokens?
- What is real Groq prompt-cache hit rate?
- 3.6 minimal vs 3.8 low: which has better TTFT?
- Which model repeats acknowledgments less?

## Turn taking
- What is the actual false-EOU rate at Deepgram 10ms?
- Does 200–300ms improve conversation enough?
- Does Flux work correctly through the pinned LiveKit version?
- Does LiveKit TurnDetector reintroduce startup delay?

---

# 34. Source index

## Codebase context
- `HUMANIZATION_CODEBASE_CONTEXT_FOR_RESEARCH.md`

## Cartesia
- https://docs.cartesia.ai/build-with-cartesia/tts-models/latest
- https://docs.cartesia.ai/build-with-cartesia/capability-guides/ssml-tags
- https://docs.livekit.io/agents/models/tts/cartesia/

## Rime
- https://docs.rime.ai/docs/models
- https://docs.rime.ai/docs/prompting

## ElevenLabs
- https://elevenlabs.io/docs/eleven-api/choosing-the-right-model
- https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech
- https://elevenlabs.io/docs/api-reference/voices/settings/update
- https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/what-is-eleven-v3-alpha
- https://docs.livekit.io/agents/models/tts/elevenlabs/
- https://docs.livekit.io/reference/python/livekit/plugins/elevenlabs/index.html

## Fish Audio
- https://docs.fish.audio/developer-guide/models-pricing/models-overview
- https://docs.livekit.io/agents/models/tts/fishaudio/

## Uplift
- https://docs.upliftai.org/tutorials/livekit-voice-agent
- https://docs.upliftai.org/sdk/nodejs/phrase-replacements

## Groq
- https://console.groq.com/docs/model/openai/gpt-oss-20b
- https://console.groq.com/docs/reasoning
- https://console.groq.com/docs/prompt-caching
- https://console.groq.com/docs/rate-limits

## Gemini
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash
- https://ai.google.dev/gemini-api/docs/latest-model
- https://ai.google.dev/gemini-api/docs/thinking
- https://ai.google.dev/gemini-api/docs/generate-content/gemini-3

## Deepgram
- https://developers.deepgram.com/docs/understand-endpointing-interim-results
- https://developers.deepgram.com/docs/flux/agent

## Gladia
- https://docs.livekit.io/agents/models/stt/gladia/

## LiveKit turn handling
- https://docs.livekit.io/agents/logic/turns/turn-detector/

---

# 35. Bottom line

The current UVA architecture largely thinks of humanization as:

```text
TTS-specific prompt rules
```

The current provider ecosystem points toward a cleaner model:

```text
natural spoken language
        +
provider-native/framework delivery
        +
natural turn timing
```

The likely target is:

```text
Caller
  ↓
STT
  ↓
Turn Detector / EOU
  ↓
LLM
  ↓
Universal Spoken Policy
  ↓
Small LLM Modifier
  ↓
TTS Delivery Profile
  ├─ Cartesia/Fish: native/framework expressive
  ├─ Rime: natural plain text
  ├─ ElevenLabs: model/voice settings or provider audio tags
  └─ Uplift: Urdu language + pronunciation profile
  ↓
Natural audio
```

The product goal is **not** "make every voice maximally emotional."

The goal is:

> Every supported provider combination should produce concise, context-appropriate spoken language, natural delivery, correct pronunciation, good interruption behavior and human-like turn timing, while avoiding markup leakage, artificial fillers, overacting, unnecessary LLM token cost and latency regressions.
