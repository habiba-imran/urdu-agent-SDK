# Collective voice experience audit — 2026-10-30

## Verdict

The shared worker has useful latency, interruption and conversational foundations,
but the current evidence does **not** establish consistently natural, humanlike
conversation. Optimizing first audio in isolation can conflict with meaningful
phrasing, prosody, listener feedback and recovery after interruption.

This was an audit. No implementation, local configuration, agent settings, routes,
dependencies, running workers or deployments were changed. This report is the only
new repository artifact from the audit. Earlier uncommitted work was preserved.

Scope: Claude and every currently selectable STT/TTS pairing, for browser and phone
paths. English allows Gladia/Deepgram with Cartesia/ElevenLabs/Rime; Urdu allows
Gladia with Uplift. Nova and Flux are distinct Deepgram runtime variants. Mixed
language exists in runtime language helpers but is not a separately selectable
language in the current provider capability registry. Gemini/Groq tuning is outside
this audit's focus; their existing behavior was not changed.

## Evidence and limits

- Current source and installed LiveKit Agents/provider plugins: **1.6.5**.
- Fresh combined offline regression run: **441 passed**, no skips, one warning.
- Fresh deterministic reproductions: first-chunk boundary, direct acoustic rendering
  of energy/intensity, short listener-feedback classification and effective Rime
  benchmark configuration.
- Fresh synthetic installed-runtime interruption benchmark: current output-control
  response around **359–375 ms WebRTC** and **312–313 ms telephony**. The benchmark
  injects VAD-duration events and a 750 ms source-cleanup delay. It is not a real
  microphone, speech-detection, browser playback or PSTN measurement. Its synthetic
  sink also emitted repeated playback-segment accounting warnings; these numbers
  must not be treated as audible acceptance evidence.
- Previous live provider probes in this chat remain supporting, limited evidence:
  second-turn text-request-to-worker-PCM approximately 1.50 s Cartesia, 2.21 s
  ElevenLabs, 1.53 s Uplift Urdu. They exclude STT and receiver playback, are small
  samples, and are not a controlled comparison. The earlier Rime Coda label was
  incorrect; see finding 8.
- No new paid-provider calls, customer recordings, microphone capture, audible
  listening, remote deployment inspection or persisted agent-profile lookup occurred
  in this audit. No caller-heard latency or native-language quality is established.

Local non-secret settings select Claude Haiku 5.5, low effort, 160 output tokens,
Deepgram Flux, eager EOT enabled at **0.4**, local VAD interruption, turn detector off,
history limit 48 and live Uplift. Humanization/renderer/streaming/overlap environment
flags are unset. An agent's saved `llm_options.humanization` can override the global
humanization/renderer/streaming defaults; the tested agent's saved profile and the
running worker's effective snapshot were not queried. Unset flags do not prove a
specific agent is disabled.

## Findings, in priority order

### 1. P1 — Faster first chunks can conflict with natural phrasing

The Claude soft deadline releases a 4–12 word prefix using whitespace and protected
value checks. It does not require a complete semantic clause or reject weak ending
words. An offline reproduction returned:

> I can help you choose a suitable appointment by first checking the

The input continued with “available times for tomorrow.” This establishes a textual
boundary problem; an audible pause or intonation defect at that boundary remains a
listening risk, not a measured acoustic result. Ending a chunk this way can undermine
the desired speech rhythm even when the first PCM arrives sooner. Uplift's segmented
synthesis makes boundary quality particularly relevant.

Recommendation: combine the first-audio budget with a preference for complete short
clauses, language-aware weak-ending checks and provider-specific continuation
behavior. Keep the timer a soft bound for protected facts. Evaluate the next audible
gap and phrase ending along with first audio; do not simply shorten 120 ms again.

Source: [streaming.py:281](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/streaming.py:281),
[chunk_latency.py:20](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/chunk_latency.py:20),
[context.py:200](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/delivery/context.py:200).

### 2. P1 — Emotional intent only partially reaches the acoustic renderer

Persona settings produce energy and intensity values, and those values reach Claude's
wording guidance. However, the common renderer does not use `DeliveryIntent.energy`
or `intensity` to change TTS text/options. With the same wording, affect and pace,
changing both from low to high produced identical rendered output for all four
providers in an offline reproduction. This does not mean the model cannot phrase a
reply differently; it means these controls are indirect rather than direct acoustic
controls. There is also no degraded-capability marker specifically for these fields.

Current integration capability differences matter:

| TTS path | Direct delivery control in this integration | Limitation relevant to naturalness |
| --- | --- | --- |
| Cartesia Sonic-3-family English | Emotion tags, speed, supported pauses | Energy/intensity and emphasis are not mapped; audible transitions unverified |
| ElevenLabs supported Flash/Turbo/v2 paths | Saved voice settings and supported speed changes | No per-clause emotion tag mapping; v3 audio-tag path is explicitly gated out on the pinned plugin |
| Rime Arcana default | Saved speed setting; wording and selected voice | Common renderer does not enable verified emotion or adaptive-speed control for Arcana |
| Rime Coda/Mist explicit selections | Supported speed mapping; wording and pronunciation paths | No common per-turn emotion mapping; model and speaker must be a valid pair |
| Uplift Urdu | Wording, punctuation, selected voice, optional account phrase config | No common direct emotion/speed mapping; chunks use separate synthesis segments |

This is a description of the installed integration, not a claim that a provider's
entire product lacks these capabilities. Cartesia has the richest wired controls;
that does not establish that its voice sounds best to listeners.

Recommendation: expose and log effective provider-specific support, distinguish
wording guidance from acoustic controls, and map only verified controls. Test subtle
question endings, reassurance, correction and excitement with matched utterances.
Do not add unsupported tags or rotate emotions randomly.

Source: [persona.py:62](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/persona.py:62),
[context_projection.py:142](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/context_projection.py:142),
[renderers.py:136](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/delivery/renderers.py:136),
[capabilities.py:94](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/delivery/capabilities.py:94).

### 3. P1 — Persona activation and natural overlap are separate policies

An enabled saved persona turns on conversational guidance and delivery/streaming.
It does not enable `UVA_OVERLAP_POLICY=overlap_v1`. That policy is independently
global and is unset locally. Baseline false-interruption resume is off. Consequently,
an agent can have an enabled persona while ordinary listener feedback still triggers
an interruption through native VAD/transcript handling rather than the optional
semantic tolerance path.

Recommendation: verify one per-session effective snapshot covering conversational,
delivery, streaming, overlap, VAD and recovery settings. Evaluate a coordinated
interaction profile in isolation. Do not enable overlap globally without noise,
speaker-echo, turn-taking and false-resume evidence.

Source: [persona.py:57](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/persona.py:57),
[delivery/policy.py:37](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/delivery/policy.py:37),
[coordinator.py:9](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/coordinator.py:9),
[runtime.py:62](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/runtime.py:62).

### 4. P1 — Optional backchannel tolerance misses equivalent natural feedback

Even with the optional overlap policy, the classifier relies on a small exact-text
set. In the same free-form speaking state with 300 ms duration, `mhm`, `okay` and
`yeah` returned CONTINUE, while `mm-hmm` and `uh huh` returned YIELD. Removing the
hyphen produces `mmhmm`, which is not in the accepted set. These are reproducible
classification differences, not measured caller false-interruption rates.

Recommendation: normalize common STT spellings and test English, Urdu and permitted
mixed utterances. Preserve explicit stop/correction priority, question-answer
contexts and structured-value capture; “yes” must not be dropped when it answers a
confirmation question. Blanket suppression of short utterances would be unsafe.

Source: [coordinator.py:28](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/coordinator.py:28),
[agent.py:30](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/agent.py:30).

### 5. P1 — Long-call active Claude context is still not bounded by the history setting

The 48-item history hygiene limit operates on `session.history`. Source explicitly
states this does not bound the separate active `Agent.chat_ctx` passed to the model.
Conversational projection copies that context and adds current state; it does not
replace the growing history. Stable prefix caching is useful but does not establish
stable long-call request size or TTFT.

Recommendation: measure 20+ turn requests and create an ephemeral model-input budget
that preserves recent dialogue, paired tool calls/results, current confirmed facts,
corrections and committed/unknown write outcomes. Keep the full audit transcript.
Do not delete history indiscriminately to improve a latency number.

Source: [history.py:152](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/history.py:152),
[context_projection.py:158](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/context_projection.py:158).

### 6. P1 — The metrics do not yet establish continuous caller-heard speech quality

`inter_chunk_gap_ms` is declared and emitted but never populated in the current
worker source. `caller_heard_latency_ms` remains explicitly unavailable. Worker
audio lead is estimated using handoff duration and elapsed time. It must not be
interpreted as a receiver queue or a measured residual-audio duration after barge-in.
Provider-aligned transcription is disabled in session construction; interrupted
history reconciliation uses only available synchronized-text/output evidence and
conservatively omits uncertain suffixes.

Recommendation: correlate user speech end, speech authorization, first meaningful
receiver audio, audible gaps, interruption onset and actual receiver silence in the
same session. Preserve unavailable measurements as unavailable. Measure continuation
after the interruption as well as how quickly the old voice stops.

Source: [streaming.py:373](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/streaming.py:373),
[streaming.py:453](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/streaming.py:453),
[main.py:578](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/main.py:578),
[history.py:107](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/history.py:107).

### 7. P2 — Slow tools can still create unacknowledged silence

The tool orchestrator has a delayed acknowledgement mechanism but is constructed
with `bridges_enabled=False`. A callback is bound for eligible sessions, but that
does not enable the scheduler. There is therefore no guaranteed deterministic
delayed spoken bridge for a slow operation; Claude may still choose to acknowledge
it in generated speech. This is not a recommendation to add filler every turn.

Recommendation: evaluate a short, factual, once-only bridge only for genuinely slow
operations. Suppress it while the caller speaks and retire it when the result arrives.
Speech interruption must continue to preserve business writes and their outcomes.

Source: [runtime.py:78](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/runtime.py:78),
[orchestrator.py:155](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/orchestrator.py:155).

### 8. P1 for measurement validity — Earlier Rime benchmark was mislabelled

The pairing probe selects `DefaultCodaVoice` (`lyra`) but passes empty TTS options.
The real resolver selects **Arcana**, WebSocket, immediate segmentation and speed
1.1. The probe's comment that the worker default is Coda is incorrect. Its output
also reports the LLM model without the effective TTS model/voice settings. The
previous report's “Rime Coda” timing must not be used as a verified Coda result or
as a controlled comparison with the catalog's normal Arcana voice.

Recommendation: explicitly select matching TTS model/voice pairs, print non-secret
effective TTS settings, and rerun matched measurements before ranking Rime. This
audit records the correction without altering the earlier code/report.

Source: [benchmark_claude_tts.py:52](C:/Users/habiba/Desktop/SDK/sdk-agent/scripts/benchmark_claude_tts.py:52),
[rime_options.py:28](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/providers/tts/rime_options.py:28),
[rime_options.py:110](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/providers/tts/rime_options.py:110).

### 9. P2 — Emotional adaptation is primarily lexical, not acoustic

Concern, confusion and excitement are identified through explicit text patterns.
Supportive tone is retained for a short fixed number of turns. The system does not
measure the caller's vocal emotion, intonation or pace for these decisions.
Equivalent wording outside the patterns can miss a delivery cue; there is no basis
to claim comprehensive emotional understanding.

Recommendation: expand scenario coverage first, keep restrained content-grounded
delivery, and evaluate emotional continuity across several turns. Avoid introducing
another slow model call or unstable acoustic guesses merely to animate the voice.

Source: [turn_plan.py:153](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/turn_plan.py:153),
[runtime.py:182](C:/Users/habiba/Desktop/SDK/sdk-agent/worker/humanization/runtime.py:182).

## What is already working and should be preserved

- Claude streams through the existing adapter; stable-prefix caching and HTTP/2 are
  implemented. No unnecessary second rewrite/planner model is needed for this audit.
- Local interruption accepts sustained voice without waiting for an STT final.
  The output-stop observer acts on already accepted interruptions, retains native
  pause ownership and protects uninterruptible disclosures.
- Native framework cancellation, tool/write authority and committed business effects
  remain separate from speech cancellation. Interrupted assistant history is cloned
  before ephemeral reconciliation.
- Session-scoped TTS leases isolate exact settings; failed/interrupted leases retire.
  Uplift warm-up has owned task cleanup, and its native Claude path can synthesize
  protected prefixes before full text completion.
- Canonical text, literal-value protection and provider-specific rendering provide
  a sound base. Naturalness should improve without sacrificing these safeguards.

## Recommended coordinated validation and implementation order

1. Fix benchmark identity, identify the actual running worker version and inspect the
   tested agent's effective per-session policies. Preserve the current baseline.
2. Address phrase-boundary quality together with first-audio latency. Compare both
   first meaningful audio and subsequent gaps on matched prompts.
3. Exercise backchannels, deliberate takeovers and false recovery as one turn-taking
   policy. Include noisy speakers, headphones and telephone double-talk.
4. Validate provider-specific affect/pace mappings, including question endings,
   reassurance and changes in emotional context. Listen to the exact rendered audio.
5. Bound long-call model input safely and evaluate delayed tool acknowledgement.
6. Run matched baseline/candidate sessions across the supported Claude combinations
   and channels. Test Nova and Flux separately; preserve the Urdu language policy.

Use the same scenario set to join the three concerns: a normal question; a short
backchannel during the answer; an explicit stop; a correction mid-sentence; a phone
number/date read-back; a frustrated caller; a genuine question ending; a slow lookup;
an interrupted committed action; a false interruption; and a 20+ turn conversation.
Record cold and warm turns separately. Count false cutoffs, successful takeovers,
duplicate/repeated clauses, factual errors and audible gaps. Report distributions
for receiver-side response and stop timing, with sufficient samples before claiming
tail percentiles. Collect native Urdu listening judgments for the Urdu lane.

The under-one-second goal is a target, not a current result. Prior provider timings
cannot simply be summed because speculative STT/LLM/TTS work can overlap, and
meaningless early audio would not satisfy a natural response-time goal.

**IMPLEMENTATION GATE:** targeted current-source regressions pass; the gaps above
prevent a feature-complete naturalness claim.

**ACTIVATION GATE:** natural prosody, emotional appropriateness, receiver-heard latency,
real barge-in, browser/PSTN behavior, long-call/load behavior and deployed activation
are unverified by this audit. No global activation or configuration change was made.

## Fresh verification command

```powershell
$env:CI_UNIT_FORCE_OFFLINE='1'
.\.venv\Scripts\python.exe -m pytest tests/test_claude_latency.py tests/test_humanization_conversational.py tests/test_humanization_batch_b.py tests/test_humanization_batch_c.py tests/test_humanization_batch_d.py tests/test_humanization_phase6.py tests/test_humanization_turn_plan_phase3.py tests/test_humanization_observability.py tests/test_humanization_observability_framework.py tests/test_smooth_interruption.py tests/test_interruption_transport_recovery.py tests/test_provider_retries.py -q --disable-warnings
.\.venv\Scripts\python.exe scripts/benchmark_interruption.py
```

The graph file was absent, so no graph query was available. Source was not modified;
an AST graph update is not needed for this report-only audit.
