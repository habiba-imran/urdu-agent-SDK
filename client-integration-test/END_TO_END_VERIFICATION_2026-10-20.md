# Automated voice verification — 20 October 2026

**Overall result: live path is not healthy enough to mark PASS.** The configured
English route produced real replies, but three live sessions exposed startup and
provider failures. No provider, model, voice, prompt, deployment, credential, or
humanization policy was changed to make the results pass.

## Launch commands

Use three PowerShell terminals. The app's local backend is the SDK host: it still
has to run even though the control plane and tenant API in its `.env` are deployed.

Worker, from the platform root:

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:UVA_PUBLISH_TURN_LATENCY = '1'
.\.venv\Scripts\python.exe -m worker.main dev
```

The installed venv was executed successfully: Python 3.12.10, LiveKit Agents and
plugins 1.6.5, RTC 1.1.13. It automatically loads `.env.local`, including the
`uva-staging-agent` dispatch name. Restart after source changes; Python `dev` mode
does not reload this installed version. The UTF-8 settings avoid the Windows
cp1252 logging error observed during the probe. The telemetry setting publishes
diagnostics to the client; it does not activate new humanization behavior.

Local app backend:

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent\client-integration-test
npm.cmd run dev:backend
```

Frontend:

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent\client-integration-test
npm.cmd run dev:frontend
```

Open http://localhost:5174/. Do not start duplicate listeners if these app servers
are already running. The temporary verification worker was stopped after testing.

## Method and scope

Three WebRTC sessions used the app's actual local backend and configured deployed
control plane/tenant API, the local worker, LiveKit Cloud, and real providers.
The configured Demo App Agent used Deepgram Nova-3, Groq openai/gpt-oss-20b, and
Cartesia sonic-3.5 through the existing selected voice.

The automated Python client checked the current pipeline, minted through
`/api/voice/session`, joined LiveKit, published synthetic 16 kHz microphone audio,
received remote PCM, and collected transcripts and turn diagnostics. Worker/job
IDs and the serving process in the packets matched the local worker registration.
Agent configuration and provider selection were preserved.

Timing starts immediately before the explicit pipeline preparation step. This is
an automated analogue of the app connection workflow, **not an actual browser
button click**. First active PCM uses an int16 RMS threshold of 120 on received
20 ms frames. It is neither first useful word nor proof of speaker playback.
Browser autoplay, microphone permissions, audible naturalness, Urdu/mixed speech,
PSTN, long-call refresh, and concurrent capacity were not verified. The user chose
automated checks only. Agent recording was disabled and no received audio was saved.

## Observations

| Measurement | Initial attempt | Warm attempt 1 | Warm attempt 2 |
| --- | ---: | ---: | ---: |
| Pipeline preparation | 2.108 s | 3.975 s | 2.397 s |
| Host session mint | 25.758 s | 2.310 s | 2.146 s |
| Automated LiveKit join | 8.409 s | 4.962 s | 4.833 s |
| Workflow to room connected | 36.276 s | 11.248 s | 9.376 s |
| Workflow to first active received PCM | Not detected | 17.166 s | 15.015 s |
| Subsequent outcome | Greeting synthesis failed | Replies worked, then Groq 429 | Deepgram connection failed |

- **Cold startup failed:** `GREETING_TTS_UNAVAILABLE`. Greeting synthesis hit its
  six-second bound; the receiver saw frames but no non-silent greeting. The backend
  logged a successful mint after 25.731 s, while the frontend's actual configured
  SDK timeout is 15 s. That mint is too slow for the current browser configuration.
- **Warm startup is still slow:** about 15–17 s through the automated workflow;
  about 5.6–5.9 s from native room connection to received greeting audio. Two samples
  are not a percentile or reliability estimate.
- **Turn audio worked in one session:** the synthetic identity and arithmetic
  clips were followed by active reply PCM after 1.818 s and 2.978 s from clip end.
  The transcript included a truthful AI identification and the correct arithmetic
  answer. Pauses in the original multi-sentence input clips caused extra STT finals
  and cancelled generations; these are not clean single-utterance benchmark scores.
- **Worker timings arrived:** one completed LLM turn reported LLM TTFT 1.208 s,
  TTS TTFB 0.255 s, and worker e2e proxy 2.118 s. These measure different boundaries
  from received audio and must not be substituted for caller-heard latency.
- **Groq rate limit:** HTTP 429, token-per-minute limit 8,000. The worker ended the
  first warm session after the provider error. Closing playback was not verified.
- **STT failure:** the second warm session delivered its greeting, then logged
  `failed to connect to deepgram` and `bounded_provider_failure stage=STT`; it closed
  before a user reply. The current STT connect bound is five seconds with no retries.
- **Interruption:** worker logs show interrupted generations. The stop probe began
  during a receive-side gap, so its numeric stop measurement is invalid. Reliable
  barge-in stop timing remains unverified.
- **Cleanup:** logs recorded session close, quota decrement, transcript and usage
  persistence for these jobs. Normal test usage changed `state/usage_ledger.json`;
  that usage was preserved rather than erased. No business write tool was exercised.

## Humanization gates

**IMPLEMENTATION GATE — PASS for the focused checks run:** 451 tests passed, no
skips, one existing Starlette warning. These covered startup/latency, session opening,
the four humanization batches, conversational behavior, final P0, and live-call
regression fixtures. The initial offline setup yielded 448 passes/3 failures;
the full rerun with a dummy loopback database URL passed all 451. No real database
connection was used by that unit suite, and its network guard remained enabled.

**ACTIVATION GATE — NOT PASSED:** actual worker telemetry reported baseline policy,
renderer, streaming, overlap and opening. New conversational humanization was not
active. A successful synthetic test suite does not prove audible humanization.
No candidate was enabled on the shared staging dispatch, and no listening score
is claimed. Core baseline safeguards still ran; the live identity answer was truthful.

## Evidence and next work

Local evidence is in `tmp/worker-e2e-20261020/`: `worker.log`, `audio-results.json`,
and `audio-repeat-results.json`. The first probe revision did not promote a missing
closing reply into its top-level error list; the per-turn error and worker Groq
failure are authoritative. The probe has since been adjusted to stop on disconnection
and preserve missing-reply errors. No clean-session pass is inferred from that field.

The reproducible harness is `scripts/verify-audio.py`; create synthetic input clips
with `scripts/make-probe-input.ps1 -OutputDirectory <directory>`, then run the Python
script with `--input-dir <directory> --output <json-path> --runs 2`. Optional
`--interruption` exercises interruption without claiming acoustic stop timing.

Priority follow-up is to reduce deployed mint cold latency, investigate provider
connection reliability and the Groq token budget, then repeat clean single-utterance
sessions. A larger browser timeout can accommodate cold minting, but does not fix
its latency. Humanization comparisons need a separate isolated dispatch/control
plane route and matched baseline/candidate evidence; the present audit did not
activate or optimize those policies.

Required graph refresh was attempted and failed with the installed graphify
launcher error `uv trampoline failed to canonicalize script path`.
