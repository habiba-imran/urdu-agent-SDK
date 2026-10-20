# Latency fixes and live verification — 20 October 2026

Avoidable startup work is removed. Warm startup improved from 15–17 seconds to
8.75–10.43 seconds across four subsequent automated sessions. It is still too
slow to describe as instant. The latest continuous-microphone runs measured
10.07 and 10.43 seconds to receive non-silent greeting PCM, with reply gaps of
1.13–2.78 seconds. These are small samples, not service guarantees or percentiles.

## Changes

- `worker/main.py`: normal WebRTC sessions without verified phone metadata no
  longer open a remote database connection and query telephony calls twice during
  startup. Trusted mint/SIP identity resolves locally. Actual telephony database
  fallback runs off the realtime event loop using the existing process pool;
  failure still leaves caller ownership unknown. Write authorization is preserved.
- Frontend: unchanged loaded/saved pipeline selections skip portal validation/write
  round trips on connect. Local edits still validate and save. This uses the
  agent's current server configuration; Refresh agents reloads external edits.
- Backend/frontend: `/api/demo/ready` checks control-plane and tenant-API health
  concurrently, shares concurrent requests, and caches success for 30 seconds.
  Page preparation finishes before picker requests start, avoiding their shorter
  timeout during service wake-up. Connect stays disabled on failed preparation;
  Refresh agents retries. After 60 seconds the next connect rechecks health.
  This neither verifies worker/provider health nor pre-mints a paid session.
- Metrics: distinguish click-to-active-speaker from room-to-active-speaker.
  Neither is labelled received audio. Setup is labelled "Before session mint"
  because an unchanged connection no longer performs a pipeline PATCH.
- Probe: keeps synthetic microphone frames flowing, including silence between
  utterances, and reports backend preparation separately. Stopping frames between
  clips can distort STT endpointing and reply timings.

No agent prompt, provider/model/voice, deployed backend, LiveKit transport defaults,
or humanization candidate setting was changed by these latency fixes.

## Received-audio results

The configured English demo used Deepgram Nova-3, Groq `openai/gpt-oss-20b`,
Cartesia `sonic-3.5`, published Voice SDK 1.1.1, and the local `uva-staging-agent`
worker with LiveKit Agents/plugins 1.6.5 and native RTC 1.1.13.

Latest runs with continuous microphone input:

| Measurement | Warm run 1 | Warm run 2 |
| --- | ---: | ---: |
| Pipeline preparation | <1 ms | <1 ms |
| Session mint | 2.067 s | 1.467 s |
| Native LiveKit join | 5.304 s | 4.838 s |
| Workflow to room connected | 7.372 s | 6.305 s |
| Workflow to subscribed audio track | 9.253 s | 9.652 s |
| Workflow to first active received PCM | **10.067 s** | **10.432 s** |
| Identity question: clip end to reply PCM | 1.133 s | 1.622 s |
| Arithmetic question: clip end to reply PCM | 2.782 s | 2.680 s |
| Goodbye: clip end to reply PCM | 2.441 s | 1.361 s |
| Reported provider/session errors | 0 | 0 |

Backend preparation before this pair took 1.094 seconds. Worker diagnostic values
on the arithmetic turns were LLM TTFT 702/720 ms, TTS TTFB 449/458 ms, and worker
e2e proxies 2,467/1,991 ms. They measure different boundaries from received audio.

An earlier three-run batch after the fixes measured startup 11.408, 8.751 and
9.391 seconds, also without reported provider/session errors. Its first backend
preparation took **22.952 seconds before the connection workflow**: at least
34.36 seconds including that preparation and the first startup. This cold wait
is displayed during page preparation; the infrastructure cold start still exists.
The batch used finite microphone clips; its reply gaps ranged 1.343–5.241 seconds.
The slow first arithmetic turn included a 3.293-second Groq TTFT. It is retained
as an outlier, rather than excluded from the evidence.

All five post-fix sessions received greetings and three replies, with no reported
provider/session failures. The earlier audit's Groq 429 and Deepgram connection
failure have not been proven permanently resolved by this small successful sample.

## Remaining delay

After the worker change, the first job reached its opening gate in 172 ms after
joining; subsequent observed startup was about 500 ms, versus the prior 1.7–3 s
of worker startup work. This does not include worker LiveKit join, subscription,
provider synthesis or downstream media transport.

A network-only probe created temporary rooms without dispatching an agent:
default join 4.883 s, single-peer-connection 5.385 s, relay 5.373 s. A further
debug run took 5.289 s, including roughly 3.1–3.3 s from ICE checking to connected.
Those settings did not improve the measured path and were left unchanged.
The latest speech sessions still include about five seconds in native join,
1.5–2.1 seconds minting, and 2.7–4.1 seconds between client room connection and
received greeting. The latter spans worker join/readiness and media delivery;
it is not attributed entirely to Python or TTS.

## Evidence and checks

Local ignored evidence: `tmp/latency-fix-20261020/audio-results.json`,
`continuous-audio-results.json`, `worker.log`, and `rtc-debug.log`. Debug logs
can include private transport details; do not publish them unredacted.

IMPLEMENTATION GATE: 484 focused worker regressions passed, covering latency,
opening, caller identity, telephony fallback, write gates, humanization batches,
and live-call fixtures. Scoped Ruff and Python compilation passed. Demo verification
passed 15 backend tests, 11 DOM tests, TypeScript, production build, and published
package checks. Existing warnings: Starlette httpx deprecation, Vite bundle size,
and an invalid pre-existing noqa comment outside the changed worker block.
The initial broader test selection included retired `tests/test_latency.py`, which
cannot collect because its CER `config` module was removed; it is excluded from
the 484-test result.

`git diff --check` passed. Required graph refresh was attempted; the installed
graphify launcher failed with `uv trampoline failed to canonicalize script path`.

ACTIVATION GATE: real provider/native-WebRTC received audio verified for the
configured English baseline only. Browser click-to-speaker latency, actual first
useful word, microphone permission/autoplay behavior, subjective humanization,
Urdu/mixed speech, PSTN, and concurrent load remain unverified. New humanization
policies remain baseline/off; no audible candidate activation is claimed.

The timer begins before connection setup, after explicit page/backend preparation.
First active PCM means RMS >120 in a received 20 ms, 16 kHz mono frame. The
continuous synthetic microphone sends silence between single-sentence clips;
reply timing starts when the last queued input frame reaches scheduled playout.
The user requested automated checks only. Received audio was not saved.

## Run locally

Use three PowerShell terminals. Run one worker instance for this dispatch.
Existing deployed control-plane/tenant-API URLs remain in the demo backend `.env`;
the local backend below is still required as the SDK host.

Worker:

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:UVA_PUBLISH_TURN_LATENCY = '1'
.\.venv\Scripts\python.exe -m worker.main dev
```

The worker loads `.env.local`. Restart after Python source changes: this installed
`dev` mode does not reload them automatically. Keep the worker running between
client calls so worker initialization and greeting cache stay warm.

Demo backend:

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent\client-integration-test
npm.cmd run dev:backend
```

Demo frontend:

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent\client-integration-test
npm.cmd run dev:frontend
```

Open http://localhost:5174/ and wait for "Backend services ready" and the loaded
prompt/picker before starting the demo. This avoids the initial deployed-service
wake-up during the client presentation; the measured warm connection delay above
still applies.
