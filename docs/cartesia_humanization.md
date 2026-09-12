Okay, got everything I need — Cartesia docs, LiveKit's own blog, SSML reference, audio codec guides, the Sonic 3.5 migration notes, all of it. This is going to be a proper full breakdown.

---

## Complete Guide: Humanizing Cartesia TTS in LiveKit + Telephony

This is a multi-layer problem. The "robotic" quality comes from several compounding issues — wrong model, wrong voice, unguided LLM output, missing prosody signals, and sometimes audio codec mismatch in the telephony path. Here's every lever you can pull, ranked by impact.

---

### Layer 1 — Model Upgrade (Highest impact, zero code changes)

Sonic 3.5 brings meaningfully more natural speech, pacing, and emotional expression — especially noticeable on expressive, conversational, and support-style transcripts, plus cleaner audio quality across all languages. If you're still on `sonic-3` or anything older, that's your first fix.

In your LiveKit plugin config:
```python
from livekit.plugins import cartesia

tts = cartesia.TTS(
    model="sonic-3.5",        # was sonic-3 or sonic-2
    voice="<voice-id>",
    language="en",
)
```

The `sonic-3.5` alias always points to the most recent stable snapshot, so you stay current automatically.

---

### Layer 2 — Voice Selection

This is huge and underrated. Stable, pleasant, yet also realistic voices work better for voice agents. Cartesia explicitly recommends these for agent use cases:

| Voice | ID | Locale |
|---|---|---|
| Katie | `f786b574-daa5-4673-aa0c-cbe3e8534c02` | en-US Female |
| Skylar | `db6b0ed5-d5d3-463d-ae85-518a07d3c2b4` | en-US Female |
| Jameson | `a5136bf9-224c-4d76-b823-52bd5efcffcc` | en-US Male |
| Gemma | `62ae83ad-4f6a-430b-af41-a9bede9286ca` | en-GB Female |
| Archie | `ef191366-f52f-447a-a398-ed8c0f2943a1` | en-GB Male |

For **emotion controls specifically**, the voices with the best emotional response are Leo, Jace, Kyle, Gavin, Maya, Tessa, Dana, and Marian. Use voices tagged "Emotive" on `play.cartesia.ai/voices` if you want emotion tags to actually land.

---

### Layer 3 — Emotion, Speed & Volume Controls

Sonic provides controls for the speed, volume, and emotion of generated speech — available via the `generation_config` parameter on each request, or via SSML tags within the transcript. It interprets these as *guidance* rather than strict adjustments, to ensure natural speech.

```python
tts = cartesia.TTS(
    model="sonic-3.5",
    voice="<voice-id>",
    speed=0.95,              # 0.6–1.5, default 1.0. Slightly slower = more natural
    volume=1.0,              # 0.5–2.0
    emotion=["calm", "content"],  # list of emotion strings
)
```

Full emotion list: The primary emotions — those with the most data and best results — are `neutral`, `calm`, `angry`, `content`, `sad`, and `scared`. Extended emotions include `happy`, `curious`, `sympathetic`, `enthusiastic`, `apologetic`, `hesitant`, `contemplative`, `determined`, and many more.

**Key gotcha:** Emotion controls are purely additive — they cannot reduce or remove emotions. `anger:low` adds a small amount of anger, it doesn't make the voice less angry. Emotion tags push the model to be more emotive, but only work when the emotion is consistent with the transcript. So don't put `<emotion value="excited"/>` before a sentence expressing sadness.

For telephony/clinic agents, start here:
```python
emotion=["calm", "content"]
# or
emotion=["calm", "sympathetic"]  # for Vera/insurance contexts
```

---

### Layer 4 — SSML Tags in the Transcript (Fine-grained control)

Sonic supports SSML-like tags to control generated speech. Supported tags are `speed`, `volume`, `emotion`, `break`, and `spell`.

**Pauses** — Most natural lever:
```xml
Hello, let me just pull that up.<break time="500ms"/> Okay, so I can see your record here.
```

Punctuation is the first tool for pausing — a comma or period usually produces a natural, well-paced pause. Reserve `<break>` tags for when you need an explicit silence of a specific duration.

**Emotion shifts mid-response:**
```xml
<emotion value="sympathetic"/> I understand that must have been frustrating.
<emotion value="calm"/> Let me see what I can do to help.
```

**Laughter / Nonverbalisms:**
Insert `[laughter]` in your transcript to make the model laugh.
```
Oh, well that's a new one! [laughter] Let me check on that for you.
```

**Speed inline:**
```xml
<speed ratio="0.9"/> Your confirmation code is <spell>AB12CD</spell>.
```

**Spell tags for codes/IDs (critical for telephony):**
```xml
Your appointment is confirmed. Reference number: <spell>TKT4829</spell>.
```

---

### Layer 5 — LLM System Prompt Engineering (This is where the real gains are)

This is the LiveKit team's official guide and it's the most actionable thing in this whole doc.

The root issue is simple: LLMs are trained on text, then post-trained to produce clean, grammatically correct writing. That's great for chatbots and emails, but it's not how humans talk. Real speech is full of filler words, mid-sentence course corrections, little laughs, soft pauses, and sentences that meander. You can't just say "be conversational" and expect it to stop sounding robotic. If you want a cascaded voice agent to sound like a real person on a call, your system prompt needs to do two things: show the model what you mean, and reinforce the same behaviors from multiple angles.

**Concrete before/after examples in your system prompt:**

LLMs thrive on examples, so write out specific sentences your agent might say. If you have call recordings between customers and human agents, look for patterns you want to replicate.

```
WHAT GOOD OUTPUT LOOKS LIKE:

Bad: "I can definitely help you with that."
Good: Yeah, um <break time="300ms"/> so, I can do that, no problem.

Bad: "I'll need to place you on a brief hold."
Good: Okay so, um <break time="300ms"/> just give me one moment here, <break time="400ms"/> I'm just pulling that up.

Bad: "Your appointment has been scheduled."
Good: Alright, so <break time="200ms"/> yeah, you're all set.
```

**Disfluency timing patterns:**

Filler words alone aren't enough. What makes them feel real is the timing. When humans say "um," they generally pause briefly, then restart with a connector like "so." Agents often miss this by saying "um" and then going at full speed, which lands as fake.

```
RULES:
- After every standalone "um", immediately insert <break time="300ms"/>.
- After the break, always pick up again with "so" or another connector.
- Pattern: "um <break time="300ms"/> so..." not just "um..."
```

**Emotion as guardrails, not decorations:**

Emotion controls work best when they're used as guardrails. Humans don't ping-pong between multiple emotions in one sentence. "Calm"-adjacent tags like `peaceful` tend to sound more human than "big" emotions like `excited`. Set your baseline, then give your model a few specific scenarios where stronger emotions make sense.

```
EMOTIONAL BASELINE:
- Default: <emotion value="calm" /> — warm but grounded, not flat
- Empathy: <emotion value="sympathetic" /> I'm really sorry to hear that.
- Good news: <emotion value="content" /> Great, you're all set!
- Laughter where appropriate: [laughter]

NEVER ping-pong between emotions within one turn.
```

**Personality as audible behaviors (not adjectives):**

"Friendly and helpful" is already the default mode of most LLMs. You need personality traits that map to observable speech patterns — things the model can literally output.

```
SPEECH BEHAVIOR:
- Start sentences with "So," "And," or "Okay so" — break grammar rules deliberately
- Use: "um", "so", "okay", "hm", "like", "ya so", "alright"
- Mid-lookup narration: "Hmm, let me just check that <break time="500ms"/>. One second here."
- Confusion/mishear: "Sorry, <break time="300ms"/> I think I missed that — what did you say?"
- Never use bullet points, numbered lists, markdown, or asterisks
- Never say "I'd be happy to" or "Certainly!"
- Always end responses with terminal punctuation: . ? !
```

**Complete starter system prompt block** (from Cartesia's own docs, for the LLM writing TTS-bound text):

```
You are a voice agent. Everything you output will be spoken aloud by Cartesia Sonic TTS. 
Follow these rules:

1. FORMATTING
- Write plain prose in full sentences. Always end with . ? or !
- NEVER use markdown, bullet points, bold, asterisks, or emoji — Sonic reads them aloud.

2. CAPITALIZATION  
- Normal sentence case only.
- All-caps only for initialisms you want spelled out (FBI, ATM).

3. CODES & ALPHANUMERICS
- Wrap in <spell> tags: Your code is <spell>TKT4829</spell>.
- Or space-delimit: T K T 4 8 2 9

4. PAUSES
- Use punctuation for natural pauses.
- For explicit silence: <break time="400ms"/>

5. FILLER WORDS AND DISFLUENCIES
- Use naturally: "um", "so", "okay", "hm", "ya so", "alright"
- Pattern: "um <break time="300ms"/> so..." always
```

---

### Layer 6 — Audio/Codec Matching for Telephony

This is the silent killer. Codec mismatch degrades audio quality silently, sounds like the voice is "muddy" or "compressed."

For voice agent platforms like LiveKit and Pipecat, use `pcm_s16le` at 16kHz. For Twilio telephony, all audio is transcoded to µ-law encoding at 8kHz — use `pcm_mulaw` at 8000 to avoid double-transcoding quality loss. For European/international telephony (G.711A), use `pcm_alaw` at 8000. The rule: use a consistent encoding and sample rate across your audio pipeline to avoid unnecessary transcoding.

For your LiveKit + Telnyx stack, the right config is:

```python
# LiveKit WebRTC leg (SDK → agent):
output_format = {
    "container": "raw",
    "encoding": "pcm_s16le",
    "sample_rate": 16000
}

# Telnyx SIP/PSTN telephony leg (PCMU North America):
output_format = {
    "container": "raw", 
    "encoding": "pcm_mulaw",
    "sample_rate": 8000
}
```

On the LiveKit SIP side, PCMU is a lightly compressed narrowband codec at 8kHz — high compatibility, low latency, widely used in North America and baseline for PSTN interoperability. If you're sending 16kHz audio into a PSTN-bound SIP trunk, LiveKit does the resampling — but it's cleaner to match natively.

---

### Layer 7 — Continuations (Streaming Prosody Preservation)

This is critical when your LLM streams tokens. Without continuations, each chunk of text sounds like a fresh utterance — no prosody carryover = robotic.

Use continuations when generating chunks of audio that need to sound contiguous (for example, LLM-streamed output). This preserves prosody and voice consistency across chunk boundaries.

In the Cartesia WebSocket API, send chunks with `continue_=True` and only set `continue_=False` (or call `no_more_inputs()`) on the last chunk. LiveKit's plugin handles this automatically when you use `AgentSession`, but if you're doing any custom streaming layer in your SDK, double check you're not creating a new context per sentence.

---

### Layer 8 — Expressive Mode (LiveKit-native, low-effort)

Cartesia's Sonic models work with LiveKit's expressive mode, where the LLM marks up its own replies and LiveKit renders the delivery. Cartesia can set emotional tone (excited, sad, angry, calm), adjust pacing and volume, and insert pauses. Turn it on with `expressive=True` on your `AgentSession`.

```python
session = AgentSession(
    tts=cartesia.TTS(model="sonic-3.5", voice="<id>"),
    expressive=True,   # LLM auto-annotates output for TTS
    ...
)
```

This offloads the SSML injection to the LLM itself — less manual prompt engineering, more dynamic. Worth enabling if you're on LiveKit Agents v1.5+.

---

### Layer 9 — Professional Voice Clone (PVC)

If none of the stock voices feel right for your brand, Cartesia now supports PVCs on Sonic 3.5. Professional Voice Clones on Sonic 3.5 deliver better speaker similarity and more stable generation than on Sonic 3, especially for rare or non-native accents.

Minimum ~10 seconds of clean audio. Done via `play.cartesia.ai` Playground, then you get a `voice_id` to drop into your config.

---

### TL;DR — Priority Order

| Priority | Action | Effort |
|---|---|---|
| 1 | Upgrade to `sonic-3.5` | 1 line |
| 2 | Switch to an Emotive or agent-recommended voice | 1 line |
| 3 | Rewrite LLM system prompt with disfluency examples + SSML breaks | Medium |
| 4 | Add `emotion=["calm", "sympathetic"]` to TTS config | 1 line |
| 5 | Match `output_format` to your telephony codec (mulaw 8k vs pcm_s16le 16k) | Config |
| 6 | Enable `expressive=True` on AgentSession | 1 line |
| 7 | Add `[laughter]` and `<break>` patterns into LLM prompt examples | Medium |
| 8 | PVC if you need a custom branded voice | Playground |

The biggest bang is almost always #3 — the LLM system prompt. Cartesia's model is capable, but it only sounds human when the text it receives is written the way a human actually talks, with pauses, fillers, and SSML timing cues baked in. The audio engine can't fix robotic text.