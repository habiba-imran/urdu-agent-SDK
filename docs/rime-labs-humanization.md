Got everything. Rime's docs are actually more linguistically rich than most TTS providers — they have a proper filler words research post, an official prompting guide, and a super detailed model feature matrix. Let me break this all down properly.

---

## Complete Guide: Humanizing Rime TTS in LiveKit + Telephony

Rime has a fundamentally different philosophy from Cartesia. Rime's bet is data, not architecture — their models are trained on a proprietary dataset of real conversations with everyday speakers rather than audiobook narrators or podcast hosts, which produces the laughs, sighs, and filler prosody of an actual phone call. That foundation is already working in your favor. But you still have to drive it correctly.

---

### Layer 0 — Understand the Model Landscape First (Critical)

Rime is the one provider where your model choice determines which humanization levers you even have access to. Get this wrong and you'll be trying to use features that silently don't apply.

| Model | When to use | Custom pauses | Inline phonemes | SSML tags | Speed |
|---|---|---|---|---|---|
| `coda` | Default for all new apps — highest quality, sub-100ms | ❌ | ❌ | ❌ | `timeScaleFactor` or `speedAlpha` |
| `mistv3` | Fastest TTFA (~37ms), custom pauses needed | ✅ `<750>` | ❌ | ❌ | `timeScaleFactor` or `speedAlpha` |
| `mistv2` | Need inline phoneme overrides for brand names | ✅ `<750>` | ✅ `{r1Ym}` | ❌ | `speedAlpha` (inverted direction!) |

Requests that omit `modelId`, or send a value the API does not recognize, are served by Mist v3. Set `modelId` explicitly on every request — Coda is never served by default.

**The most important Coda gotcha:** When `model="coda"`, it ignores Rime parameters such as `reduce_latency`, `pause_between_brackets`, `phonemize_between_brackets`, `temperature`, `top_p`, and `repetition_penalty`. Coda has no bracket-based pause syntax. Its humanization comes entirely from the text you give it and the voice you pick.

---

### Layer 1 — Model Upgrade to Coda

Coda pairs an LLM backbone with a dedicated speech inference engine trained on full-duplex conversational data. It preserves pitch contour, breath, hesitation — all the things that make a voice human — and additionally models the very particular duration characteristics of real conversation with much higher fidelity than a single-decoder design. Conversation has a rhythm that monologue doesn't, and Coda is built to capture it.

```python
from livekit.plugins import rime

tts = rime.TTS(
    model="coda",
    speaker="celeste",   # or any Coda voice
    use_websocket=True,  # lower latency + word-level timestamps
    segment="bySentence",
)
```

```python
# Or via LiveKit Inference (no separate Rime API key):
session = AgentSession(
    tts="rime/coda:celeste",
    ...
)
```

---

### Layer 2 — Voice Selection (IVR/Conversational over Narration)

Rime explicitly tags voices by use-case category. IVR-tagged voices are perfect for interactive voice agents, call centers, and food ordering — humanlike performance with the natural cadence of a seasoned call center agent, works great with filler words, and captures appropriate emotions based on callflow-specific text.

Good starting voices for Coda (all English):

| Voice | Description | Use case |
|---|---|---|
| `celeste` | Chill Gen-Z American female | Conversational, casual agents |
| `astra` | Chipper, upbeat American female | Receptionist, outbound |
| `luna` | Chill but excitable American female | Customer support |
| `lyra` | Default Coda voice | General purpose |
| `orion` | — | Male agent voices |

Browse the full catalog at `play.rime.ai` — filter by "IVR" tag to see all conversational-optimized voices. Use the built-in playback to compare before committing.

**For Hindi/Urdu adjacent context** — Coda supports Hindi (`hi`), Arabic (`ar`), and Indian English with dedicated accent voices, which is relevant for your Layla/Vera context. Coda has 2 Hindi voices currently; check `docs.rime.ai/docs/voices-coda` for the live list.

---

### Layer 3 — Speed Control (Direction varies by model — easy to get wrong)

This is the most error-prone part of Rime's API because the direction of `speedAlpha` **inverts between models**.

The right parameters by scope and model:

```python
# Coda and Mist v3 — use timeScaleFactor
# timeScaleFactor > 1.0 = SLOWER; < 1.0 = FASTER
tts = rime.TTS(
    model="coda",
    speaker="celeste",
    time_scale_factor=1.1   # slightly slower = more natural, thoughtful
)

# Mist v2 — use speedAlpha (INVERTED direction)
# speedAlpha > 1.0 = SLOWER; < 1.0 = FASTER (opposite of Coda/Mist v3!)
tts = rime.TTS(
    model="mistv2",
    speaker="quinn",
    speed_alpha=1.1   # same effect as above — slightly slower
)
```

`speed_alpha` works over both HTTP and WebSocket. `time_scale_factor` is HTTP only — over WebSocket, use `speed_alpha` regardless of model.

For natural conversation, a slight slowdown (`timeScaleFactor=1.05–1.15`) tends to feel more deliberate and warm rather than rushed. Start at 1.0 and evaluate — large changes reduce naturalness.

---

### Layer 4 — Custom Pauses (Mist v2/v3 only)

Rime's pause syntax uses angle brackets with milliseconds. To insert a pause within a sentence, insert the length of the desired pause in milliseconds inside angle brackets, like `<750>`.

This is Mist v2/v3 only — Coda ignores it. If you're on Coda, use punctuation and ellipses instead.

```python
# Mist v3 or Mist v2 only — enable pauseBetweenBrackets
tts = rime.TTS(
    model="mistv3",
    speaker="quinn",
    pause_between_brackets=True
)

# In your LLM system prompt, insert pauses in text:
"Yeah, let me just check on that. <500> Okay so... <300> I'm seeing your record here."

# After filler words:
"Hmm <400> okay so let me look at that for you."

# After lookup narration:
"One moment here. <800> Alright, so I've got it pulled up."
```

For Coda, the equivalent is punctuation-based:
```
"Hmm... okay so, let me look at that for you."
"One moment. Alright, so I've got it pulled up."
```

---

### Layer 5 — Phoneme Control for Brand Names / Proper Nouns (Mist v2 only)

If you need deterministic pronunciation of brand names, clinic names, medications, or doctor names — this is Mist v2's killer feature that Coda doesn't have yet.

```python
tts = rime.TTS(
    model="mistv2",
    speaker="quinn",
    phonemize_between_brackets=True
)

# In LLM output text, wrap hard words in curly brackets with Rime phonetic alphabet:
"Welcome to {kAr.d1.ol.o.dZi} Associates."
"Your doctor is {sm1T} and your appointment is at {sev.@n} thirty."
```

You can check out the Rime phonetic alphabet for the full symbol reference, and Pronunciation control for an overview of all the ways to control pronunciation.

If you're on Coda or Mist v3 and need a specific word fixed, the path is: submit the word to `support@rime.ai` for the shared pronunciation dictionary, or respell it phonetically in plain English as a fallback.

---

### Layer 6 — The `spell()` Function for IDs / Codes

Rime has a native function for reading identifiers character-by-character — works on both Coda and Mist models.

```python
# In your LLM text output:
"Your appointment reference is spell(TKT4829)."
"Your account number is spell(rf543dc2)."
"Call us back at 1-800-spell(FLOWERS)."
"Your email is spell(help@awaazlabs.ai)."
```

Do not use `spell()` for standard phone numbers (digit grouping sounds more natural without it) or for real words that happen to be uppercase. Avoid dashes inside numbers, phone numbers, or IDs — they cause unnatural pauses. Use spaces or `spell()` instead.

---

### Layer 7 — The LLM System Prompt (Where Most Humanization Happens)

Rime publishes an official prompting guide with a drop-in system prompt. The key difference from Cartesia's approach: **Coda does not support SSML tags at all.** You humanize entirely through the text content — filler words, punctuation, sentence structure.

Coda does not accept SSML. Do not use `<break>`, `<emotion>`, or other inline tags. The only supported inline function is `spell()`. Rime deliberately keeps the interface small. Coda uses the meaning of the text to shape emotional delivery, while punctuation controls pacing and emphasis.

**Punctuation as prosody (Rime's model reads these as acoustic cues):**

| Punctuation | Effect |
|---|---|
| `,` comma | Short internal pause, slight rise |
| `.` period | Sentence-end pause, falling pitch |
| `?` question mark | Rising intonation |
| `...` ellipsis | Hesitant or trailing pause — use sparingly |
| `;` semicolon | Between comma and period |

**The before/after examples from Rime's official prompting guide:**

| Default LLM output | Best practice for Rime |
|---|---|
| "I can certainly assist you with that inquiry." | "Yeah, I can help with that. One sec." |
| "Unfortunately, I am required to inform you that your request cannot be processed at this time." | "So... I'm not going to be able to do that today. Here's what I can do instead." |
| "I will now transfer you to the appropriate department for further assistance." | "Okay, one moment. I'm going to grab someone who can take this from here." |

**Full drop-in system prompt (official from `docs.rime.ai/docs/prompting`):**

```
VOICE OUTPUT GUIDELINES

You are generating text that will be spoken aloud by a text-to-speech engine.
Write for the ear, not the page. Follow these rules.

PART 1: SOUND LIKE A PERSON

1. Be conversational, not literary. Use contractions ("I'll", "we're"). Start
   sentences with "And", "But", or "So" when it sounds natural. Drop formal
   connectors ("furthermore", "additionally", "in conclusion").

2. Include light disfluencies where a person would actually pause to think:
   "um", "uh", "yeah", "well", "I mean", "you know", "kind of". Sprinkle, do
   not stack. Two "um"s in a row sounds like a bug.

3. Use punctuation as your only prosody tool:
   - Commas for short pauses inside a sentence.
   - Periods for sentence-ending pauses.
   - Question marks for rising intonation.
   - Ellipses (...) for a hesitant or trailing pause.
   Do NOT insert SSML tags, <break>, <emotion>, or any other markup.
   The only supported inline directive is spell(). See Part 3.

4. Keep sentences short. Under 25 words, ideally under 15. A long sentence
   without internal commas will sound breathless.

5. Maintain a calm, even baseline. Save exclamation marks for moments that
   truly warrant them.

6. Use audible personality patterns:
   "Yeah, no, I get it."
   "So... let me check that for you."
   "Okay, here's what I'm seeing."
   "Hmm, one sec."

PART 2: NORMALIZE CLEANLY

The engine handles most formats natively. Pass these through unchanged:
$124.50, 04/21/2026, 7:05 PM, (213) 555-9274, 5kg, 98°F, 95%

Only rewrite:
- Dates without a year: 04/21 → "April 21st"
- Bare hours: 3pm → "3:00pm"  
- Decade names: 1990s → "the nineteen nineties"
- Non-dollar currency shorthand: €900K → "900 thousand euros"

PART 3: USE spell() FOR IDS

Wrap alphanumeric identifiers so they're read letter-by-letter:
"Your confirmation is spell(ABC123XYZ)."
"Your account number is spell(rf543dc2)."

Use spell() for: order/confirmation/tracking numbers, account/SKU numbers,
booking codes, acronyms the engine doesn't pronounce naturally.

Do NOT use spell() for standard phone numbers or real words in uppercase.
Avoid dashes inside numbers/IDs — use spaces instead.

PART 4: INVARIANTS

- Never output bullet points, numbered lists, markdown, asterisks, or emojis.
- Never say "I'd be happy to", "Certainly!", or "As an AI".
- Always end with terminal punctuation: . ? !
- Apply these rules silently. Don't mention them in output.
```

---

### Layer 8 — Filler Words: Rime's Linguist-Level Guidance

Rime has actual PhD linguists on staff and they've published specific rules about where fillers go in real speech. This is the most unique thing in their entire body of documentation.

When creating text for conversational TTS, consider adding filler words: between repetitions of small functional words like "the", "a", "I"; before infrequent, long, or complex words or phrases; and before any word you want to have a particular rhetorical effect.

Filler words like "um" and "like", as well as backchannel affirmations like "mhmm" and "uh-huh", can be the difference between a synthetic voice seeming real or uncanny.

Practical examples for clinic/healthcare context:

```
# Instead of:
"I'll need to verify your insurance information before confirming the appointment."

# Write:
"Yeah, so, um, I'll just need to, uh, verify your insurance real quick before we lock that in."

# Instead of:
"Your appointment has been scheduled for Tuesday at 2 PM."

# Write:
"Alright... so you're all set. Tuesday at 2:00 PM. We'll see you then!"

# Instead of:
"I'm transferring you to our billing department."

# Write:
"Okay, so, yeah, I'm gonna go ahead and transfer you over to billing. One moment."
```

The Rime model is specifically trained to render these naturally — it's not slapped on top. The filler words trigger acoustic patterns the model learned from real conversations.

---

### Layer 9 — WebSocket Streaming (Enable in Production)

Set `use_websocket=True` to opt into WebSocket streaming, which lowers latency and emits word-level timestamps for TTS-aligned transcriptions. Streaming and aligned transcripts are enabled automatically when WebSocket mode is active.

```python
tts = rime.TTS(
    model="coda",
    speaker="celeste",
    use_websocket=True,
    segment="bySentence",  # synthesize at sentence boundaries
)
```

The `segment` parameter controls how aggressively Coda flushes audio chunks:
- `"bySentence"` — synthesize at sentence boundaries (default, most natural prosody)
- `"immediate"` — flush as soon as text arrives (lowest latency, less prosodic context)
- `"never"` — wait for explicit flush (manual control for advanced use)

For telephony voice agents, `bySentence` gives the best naturalness because sentences arrive complete and the model has full prosodic context.

---

### Layer 10 — Telephony Codec for Rime

For phone-based voice agents and IVR systems, Rime synthesizes G.711 μ-law natively so no transcoding step sits between synthesis and the caller. Set `Accept: audio/PCMU` (HTTP) or `audioFormat=mulaw` (WebSocket) for μ-law output, and set `samplingRate: 8000` to match the telephony stream and shrink payloads.

For your LiveKit + Telnyx stack:

```python
# LiveKit plugin picks PCM by default at 16kHz — correct for LiveKit WebRTC leg
tts = rime.TTS(
    model="coda",
    speaker="celeste",
    audio_format="pcm",     # PCM for LiveKit
    sample_rate=16000,      # 16kHz for LiveKit agents
    use_websocket=True,
)

# For direct Telnyx SIP/PSTN path via Rime HTTP API:
headers = {"Accept": "audio/PCMU"}
payload = {
    "speaker": "celeste",
    "modelId": "coda",
    "samplingRate": 8000,   # G.711 telephony standard
    ...
}
```

**Worker implementation (Phase C):** `session_audio_channel()` already classifies WebRTC vs telephony. The LiveKit Rime plugin (`livekit-plugins-rime==1.6.5`) hardcodes `audioFormat=pcm` on the WebSocket URL and has no `encoding` constructor arg, so this worker does **not** request native µ-law. It sets `sample_rate=16000` (WebRTC) or `8000` (telephony) so LiveKit/SIP does not resample from the plugin default 22050 Hz. Native PCMU remains a Rime HTTP/WS capability if you bypass the plugin.

---

### TL;DR — Rime Priority Order

| Priority | Action | Effort |
|---|---|---|
| 1 | Explicitly set `modelId: "coda"` (never omit it) | 1 line |
| 2 | Pick an IVR-tagged voice from the Rime voice catalog | Config |
| 3 | Add the official prompting system prompt to your LLM | Medium |
| 4 | Write filler words and disfluencies INTO the text (not tags) | Medium |
| 5 | Enable `use_websocket=True` + `segment="bySentence"` | 1 line |
| 6 | Set `timeScaleFactor=1.05–1.15` for slightly slower, deliberate pace | 1 line |
| 7 | Use `spell()` for all confirmation codes, IDs, phone letters | LLM prompt |
| 8 | Switch to Mist v3 + enable `pauseBetweenBrackets` if you need explicit `<750>` pause control | Model swap |
| 9 | Switch to Mist v2 if you need phoneme control for brand/medical names | Model swap |
| 10 | Native μ-law output at 8kHz for PSTN telephony leg | 1 line |

---

### Cartesia vs Rime — Key Differences at a Glance

| Feature | Cartesia | Rime |
|---|---|---|
| Pause control | `<break time="300ms"/>` SSML | `<750>` bracket syntax (Mist only) / ellipsis + punctuation (Coda) |
| Emotion control | `<emotion value="calm"/>` + `generation_config.emotion` | No explicit emotion tags — model reads text meaning |
| Filler words | In LLM text OR inferred | Always in LLM text — model is trained on them natively |
| Brand pronunciation | Custom pronunciation dictionaries | Phoneme overrides `{r1Ym}` (Mist v2 only) + dictionary submissions |
| Telephony codec | `pcm_mulaw` at 8000 | Native PCMU at 8000 — no transcoding |
| Codes/IDs | `<spell>AB12CD</spell>` | `spell(AB12CD)` function |
| Best for | More nuanced emotional control, Sonic 3.5 voice quality | Phone-first, trained on real conversational data, IVR naturalness |