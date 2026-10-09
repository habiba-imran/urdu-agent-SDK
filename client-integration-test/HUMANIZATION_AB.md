# Controlled humanization A/B — platform operator guide

This standalone client can exercise a prepared platform. These instructions configure only an **isolated platform test worker**; the browser SDK package cannot activate server behavior.

## Before launching

1. Reserve a test tenant and agent; record its ID. The currently configured Demo App Agent is discoverable, but its exclusive reservation has not been confirmed. Do not PATCH a customer agent for these comparisons.
2. Use a unique named dispatch route, for example `uva-humanization-ab-20261010`, **on both the test control plane and test worker**. A separate LiveKit test project also provides isolation. The existing local worker registers as `uva-staging-agent` and can receive shared staging jobs: do not enable candidates on it.
3. Point a separate client backend at that isolated control plane. The existing backend points at staging. A new worker name alone will not redirect staging mint requests. A local control plane can use its existing `LIVEKIT_AGENT_NAME` resolver with a loopback-only listener; keep tenant/provider secrets on the backend.
4. Confirm fresh source by restarting the test worker. Installed `livekit-agents==1.6.5` Python `dev` mode **does not hot-reload**. Editing source, pushing GitHub, or repacking npm is insufficient evidence of a fresh worker.
5. Use the existing browser client with a human operator, mic permission and audio unlock. For audio persistence, use the existing recording policy: job permission, appropriate agent opt-in/local policy, required disclosure and granted consent. The inspected Demo App Agent has `recording_enabled=false`; no recording setting was changed. Native Pakistani Urdu listening requires an appropriate human listener.

Stop before paid calls if these prerequisites are missing. These commands have been prepared and source-checked; they have not been used to register a candidate worker or conduct live calls.

## Four independent pairs

| Provider | Language | Existing default model from local resolver | Existing selectable voice to hold fixed |
| --- | --- | --- | --- |
| Cartesia | English | `sonic-3.5` unless existing agent/env override | Current `cartesia-sonic-default` |
| Rime | English | `arcana` unless existing agent override | Selectable default `rime-arcana-andromeda`, or existing test-agent voice |
| ElevenLabs | English | `eleven_flash_v2_5` unless existing agent override | Selectable default `elevenlabs-adam`, or existing test-agent voice |
| Uplift | Pakistani Urdu | Existing `uplift` path | Hold the chosen existing Urdu voice fixed; API default is `balochi-elder` |

These are configuration observations, not new model/voice recommendations or account/acoustic support claims. Verify actual vendor voice translation and effective model in the serving worker's session snapshot. Do not migrate models. For English pairs keep existing STT/LLM fixed (the inspected demo uses Deepgram Nova-3 / Groq gpt-oss-20b). Urdu uses the existing selectable Gladia/Gemini route. Keep each pair's prompt, voice, options, mic, browser, playback, channel, warm/cold state and recording policy matched. Do not compare different vendors as a model bake-off.

In a **fresh isolated worker terminal at the platform repository root**, choose one provider and arm after the preceding isolation is established:

```powershell
$AbProvider = 'cartesia' # cartesia | rime | elevenlabs | uplift
$AbArm = 'A'           # A = baseline, B = renderer + streaming candidate
$AbDispatchName = 'uva-humanization-ab-20261010'
if ($AbProvider -notin @('cartesia','rime','elevenlabs','uplift')) { throw 'Unsupported provider' }
if ($AbArm -notin @('A','B')) { throw 'Unsupported arm' }
if ($AbDispatchName -notmatch '^uva-humanization-ab-[a-z0-9-]+$') { throw 'Use the isolated dispatch name' }
$env:LIVEKIT_AGENT_NAME = $AbDispatchName
$env:UVA_HUMANIZATION_POLICY_VERSION = 'baseline'
$env:UVA_OVERLAP_POLICY = 'baseline'
$env:UVA_OPENING_POLICY = 'baseline'
$env:UVA_PUBLISH_TURN_LATENCY = '1'
foreach ($AbOtherProvider in @('CARTESIA','RIME','ELEVENLABS','UPLIFT')) {
  Set-Item -Path "Env:UVA_TTS_RENDERER_$AbOtherProvider" -Value 'baseline'
  Set-Item -Path "Env:UVA_TTS_STREAMING_$AbOtherProvider" -Value 'baseline'
}
if ($AbArm -eq 'B') {
  $AbSelected = $AbProvider.ToUpperInvariant()
  Set-Item -Path "Env:UVA_TTS_RENDERER_$AbSelected" -Value 'delivery_v1'
  Set-Item -Path "Env:UVA_TTS_STREAMING_$AbSelected" -Value 'streaming_v1'
}
# Verify the installed environment remains pinned, then launch the existing worker.
.venv\Scripts\python.exe -m worker.main dev
```

Stop that isolated worker and use a fresh process for the other arm. `streaming_v1` requires selected `delivery_v1`, agents **1.6.5** and selected provider plugin **1.6.5**. Rime native streaming additionally requires its compatible WebSocket path (current Arcana defaults use it). Uplift must already be genuinely configured in live mode; fixture playback is not live evidence. Other provider flags remain baseline during the selected pair.

This first comparison isolates the existing TTS renderer/streaming bundle. Master policy, overlap and opening stay baseline in both arms. `natural_v1` resolves to shadow and does not activate general TurnPlan guidance. A separate renderer-only diagnostic arm may be useful if the B arm shows chunk gaps, but do not mix that intervention into the initial pair.

## Fixed conversation and evidence

Use the same seven steps in both arms, with synthetic test facts and no consequential business writes:

1. Greeting/introduction: “Hello.” / “السلام علیکم۔”
2. Service question: “What cleaning services do you offer?” / “آپ صفائی کی کون سی سہولت دیتے ہیں؟”
3. Follow-up: “Can you tell me a little more?” / “کیا کچھ مزید تفصیل بتا سکتے ہیں؟”
4. Hesitation/correction: “Friday… sorry, I meant Monday.” / “جمعہ… معاف کیجیے، میرا مطلب پیر تھا۔”
5. Concern: “I'm worried this won't get sorted out.” / “مجھے فکر ہے کہ یہ مسئلہ حل نہیں ہوگا۔”
6. Short interruption during agent speech: “Wait, stop.” / “ایک لمحہ، رک جائیں۔”
7. Closing: “Thank you, goodbye.” / “شکریہ، خدا حافظ۔”

The test persona must contain the same approved synthetic service facts in both arms. The current minimal demo persona contains no service facts, so do not grade invented services as business correctness. Urdu examples are authored prompts, not native-listener validation.

For every call retain: arm/provider/language, session/room IDs, worker registration and job logs, `turn telemetry room_publication` configuration log, SDK `turn_latency`/`metrics_updated` JSON, canonical transcript and consenting recording reference if available. New `providerSnapshot.worker` includes public worker/job IDs, dispatch name, process ID and an instrumentation revision. It is a runtime provenance marker, not proof of every source file/voice/account feature. Compare it with the worker's checkout/build and registration logs. Missing fields stay unknown.

For B retain worker `speech_stream_metrics` (chunk_wait, inter_chunk_gap, cancellation and synthesis counters). These are server/synthesis diagnostics, not receiver audio gaps. Provider request TTFB, server e2e and active-speaker delays are not caller-heard FUAW.

Have a human listen to matched A/B audio and record better/worse/indistinguishable plus concrete observations about rhythm, pauses, intonation, phrasing, pronunciation, gaps, response delay, interruption and voice identity. Native Urdu needs a suitable listener. Without listening, leave each judgment **NOT ASSESSED**. An offline compile or synthetic regression pass is not a listening score.

After testing, stop only the isolated services and discard/clear their process-local candidate/room-diagnostic settings. Production defaults and the current shared staging worker stay unchanged.
