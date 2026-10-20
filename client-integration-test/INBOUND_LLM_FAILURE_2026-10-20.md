# Inbound LLM failure and latency correction, 2026-10-20

The pasted PSTN logs show the SIP participant reached the existing inbound
worker. The conversation then failed in the Gemini LLM stage. This is separate
from the demo tenant's outbound routing blocker; neither phone route was moved.

## What the pasted timing actually shows

The turn's monotonic timestamps are:

| Event | Seconds |
| --- | ---: |
| User speech stopped | 283512.984 |
| LLM node entered | 283513.359 |
| Failed speech terminated | 283519.421 |

The model produced no useful text and TTS never started for this turn. It failed
6,062 ms after LLM entry, 6,437 ms after observed speech stop. The old `e2eMs: 689`
was the partial end-of-utterance metric, not response audio latency. First reply
audio and successful response latency are unavailable for this failed turn.

The configured legacy model `gemini-2.5-flash` resolves to `gemini-3.6-flash` in
the existing adapter. Its HTTP timeout is 30 seconds, while the separate useful
progress watchdog bounds conversational silence to six seconds. Increasing the
HTTP timeout does not extend that bound or improve response time.

## Local fixes

- Error/cancelled turns publish null `e2eMs`, `roundTripMs`, and breakdown e2e;
  partial EOU-only turns cannot become response-latency samples.
- Provider errors include `failureElapsedMs` from observed speech stop to terminal
  reporting, when the speech-stop timestamp exists. It is a failure diagnostic.
- LLM warm-up starts alongside STT/TTS warm-up, giving it the opening/setup window.
  Static greeting audio never waits for LLM readiness.
- Warm-up closes its stream in `finally`, including deadline/cancellation paths.
- Provider failure logs include error type, elapsed time, whether useful output
  was seen, and the progress budget without dumping request content or credentials.
- The demo debug summary includes `failureElapsedMs`.

The six-second watchdog, configured provider/model, baseline humanization flags,
business tools, and route ownership are unchanged.

## Live provider checks

A standalone minimal arithmetic request through the installed Google plugin took
26,359 ms to first text. In a fresh client with three sequential requests, first
text took 10,860 / 2,656 / 2,281 ms. These are LLM-only measurements; they are not
telephone or browser audio latencies.

Two isolated native WebRTC audio probes used the existing inbound dispatch
metadata with a uniquely named disposable worker, continuous synthetic microphone,
and the unchanged agent prompt, Gemini model, STT and TTS. No PSTN call was placed.

| Native probe | Setup + join + first received active PCM | Identity reply after input clip | LLM arithmetic reply |
| --- | ---: | ---: | --- |
| First | 14,461.2 ms | 1,899.0 ms | Failed |
| Second | 9,254.8 ms | 3,197.8 ms | Failed |

Identity is a deterministic platform reply and does not prove Gemini generation.
The first LLM request returned HTTP 503, `UNAVAILABLE`, with Google's message that
the model was experiencing high demand. The second also terminated without a
model reply. Earlier warm-up cannot resolve provider unavailability, and these
checks do not establish a passing inbound conversation.

Only test rooms and the disposable worker were removed. The user's running
worker and the existing SIP dispatch rule were left in place. Applying the local
code fixes to that running worker requires its normal restart after active calls
finish.

## Validation

157 focused Python tests passed, including actual installed AgentSession synthetic
provider integration, timing, cancellation, provider failure, interruption and
endpointing regressions. Four legacy provider mocks conflict with imports in one
combined test invocation; their phase-2 and phase-4 suites passed in isolated
processes (9 and 14 tests respectively). The remaining focused group passed 134.

Graph refresh was attempted but the installed launcher failed with
`uv trampoline failed to canonicalize script path`.

Implementation checks pass. Live Gemini conversation acceptance fails. Caller-heard
PSTN/browser playback latency and subjective humanization remain unverified.
