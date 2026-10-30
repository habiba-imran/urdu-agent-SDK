# Shared interruption behavior

These changes live in `worker/interruption.py`, the common turn profile, and
`worker/main.py`. They apply to every integration using this worker: browser
Voice SDK sessions and inbound/outbound SIP calls. The client demo is not the
implementation boundary. The worker image copies this module with the rest of
the application; deploy/restart that worker to activate it. No npm publication,
agent/provider change, database migration, or routing change is needed.

## Findings and changes

The installed LiveKit Agents 1.6.5 default `aec_warmup_duration=3.0` substitutes
silence for STT input and ignores audio interruptions during the first three
seconds of agent speech. This is an opening-only guard, not a recurring delay
on every turn. The worker now sets it explicitly: 0.25 seconds for browser audio,
0 for phone calls. Browser SDK capture already requests echo cancellation, noise
suppression, and automatic gain control. A custom capture implementation must
provide its own appropriate echo handling.

Sustained VAD speech previously required 0.65 seconds on browser sessions and
0.55 seconds on phone calls. The new gates are 0.35 and 0.30 seconds respectively.
`min_words=0` is explicit. Nonempty streaming transcripts retain the runtime's
existing interruption fallback; neither STT finalization, semantic end-of-turn,
nor a model request is needed just to stop speech. Silero's 120 ms speech onset
and existing noise threshold remain unchanged. Short noise is still rejected;
speaker echo and noisy-room sensitivity need live listening checks at the faster
thresholds.

Normal streamed TTS replies already clear their output before separate provider
cleanup finishes. Direct audio passed to `say(audio=...)` can instead wait for
the source's `aclose()` before clearing buffered media. The new observer uses
public SpeechHandle/AudioOutput APIs to pause output only after the framework
has accepted interruption of the current, interruptible handle. It releases the
pause after native playout clearing or handle completion. Native clearing still
owns synchronized transcript/history truncation; it never replays the cancelled
source. Outputs without pause support keep native clearing behavior. When native
false-interruption recovery owns pause/resume, this observer leaves it alone.

No bare-VAD force cancellation is enabled. Required disclosures remain locked.
The observer does not cancel tools, repeat writes, generate filler/apologies,
change LLM/TTS/STT providers, or switch on experimental overlap classification.
Existing Cartesia/Uplift transport recovery and provider retry policies remain.

## Coverage

The registry currently enables Gladia and Deepgram STT; Gemini, Groq and Anthropic
LLMs; Cartesia, ElevenLabs and Rime English TTS; and Uplift Urdu TTS. Tests enumerate
all 40 selectable language/provider/channel combinations, plus Nova/Flux variants.
This verifies shared policy coverage, not live provider recognition or audio.

Real installed-framework tests cover brief noise versus sustained speech,
one-word interim interruption, uninterruptible disclosure, and slow direct-audio
cleanup. A test using LiveKit's actual room output and native PCM queue repeats
interruption and then plays fresh audio, checking against the previous
`on_playback_started` synchronizer error. Its room publication is synthetic and
does not connect to LiveKit or a carrier.

Final validation: 411 focused shared-worker tests passed; 24 database integration
tests were skipped because offline mode does not configure a database. All 44
browser SDK tests, TypeScript checks, SDK build, and focused Ruff checks passed.
The new interruption module has 68 offline cases. Existing Nova/Gladia constructor
mocks and the DB-error mock were made independent of live local configuration.
The repository graph refresh was attempted but its existing `uv` launcher failed
with `uv trampoline failed to canonicalize script path`.

## Controlled timing experiment

Run `.venv/Scripts/python.exe scripts/benchmark_interruption.py` from the repository
root. It injects VAD events and deliberately delays a direct audio source's close
by 750 ms. These are single-run worker output-control measurements, **not real
VAD inference, real provider latency, receiver audio, PSTN acceptance, or a
production latency guarantee**.

| Scenario | Previous policy | Updated policy |
| --- | ---: | ---: |
| Browser opening | 3704 ms | 359 ms |
| Browser middle of conversation | 1406 ms | 359 ms |
| Phone opening | 3704 ms | 312 ms |
| Phone middle of conversation | 1344 ms | 312 ms |

The deliberately slow close is part of those previous-policy values. Normal
streamed TTS does not necessarily incur that delay. No live microphones, provider
APIs, telephone calls or existing worker processes were used or restarted.

## Configuration and rollback

Set these only on the worker, never in browser/session request bodies:

| Variable | Default | Bounds / rollback |
| --- | --- | --- |
| `UVA_INTERRUPTION_MIN_DURATION` | unset: browser 0.35 s, phone 0.30 s | 0.15–1.5 s; increase for noisy rooms |
| `UVA_AEC_WARMUP_SECONDS` | unset: browser 0.25 s, phone 0 s | 0–3 s; set 3 to restore the old startup guard |
| `UVA_FAST_INTERRUPTION_OUTPUT` | 1 | Set 0 to use native clearing alone |

Invalid, infinite and NaN timing overrides fall back to channel defaults.
`UVA_INTERRUPTION_MODE=adaptive` and the experimental overlap policy retain their
existing opt-in semantics. `UVA_FORCE_BARGE_IN_FLUSH` remains off by default on
both channels. Worker INFO logs identify `policy=local_vad_20261030`; output-stop
logs explicitly label timing as `worker_output_control`.

Before judging conversational smoothness, listen to real browser/headset/speaker,
inbound and outbound calls after worker deployment, across the intended providers,
English/Urdu, short corrections, background noise and repeated interruptions.
Record caller speech onset to old audio becoming inaudible separately from the
next answer's STT/LLM/TTS delay. Synthetic checks do not establish those results.
