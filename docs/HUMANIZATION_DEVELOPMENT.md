# Run the implemented conversational development profile

This launcher applies the ordinary-turn policy and all four compatible renderer/streaming
pairs before importing the worker. It starts a fresh process and rejects shared dispatch names.
Production/shared worker defaults remain baseline. Do not restart the existing staging worker.

From the repository root, validate without network/provider calls:

```powershell
.venv\Scripts\python.exe -m worker.development worker --agent-name uva-humanization-dev-habiba --check
```

Then launch the fresh isolated worker in one terminal:

```powershell
.venv\Scripts\python.exe -m worker.development worker --agent-name uva-humanization-dev-habiba
```

In a second terminal launch the control plane with the SAME unique dispatch name:

```powershell
.venv\Scripts\python.exe -m worker.development control-plane --agent-name uva-humanization-dev-habiba
```

The control plane binds only `127.0.0.1:8100`. In a third terminal, start the existing
client backend on a separate port. Its backend `.env` must contain your existing isolated
test-tenant credentials (not customer credentials). Process variables override that file:

```powershell
$env:UVA_CONTROL_PLANE_URL = 'http://127.0.0.1:8100'
$env:PORT = '3101'
$env:HOST_PUBLIC_BASE_URL = 'http://localhost:3101'
$env:HOST_ALLOWED_ORIGINS = 'http://localhost:5175'
Set-Location client-integration-test/backend
npm run dev
```

In a fourth terminal, run the existing frontend against that backend:

```powershell
$env:VITE_UVA_SESSION_ENDPOINT = 'http://localhost:3101/api/voice/session'
$env:VITE_UVA_REFRESH_ENDPOINT = 'http://localhost:3101/api/voice/session/refresh'
Set-Location client-integration-test/frontend
npm run dev -- --port 5175
```

Use `http://localhost:5175` and select an isolated test agent, retaining its existing model
and voice. Do not PATCH customer agents. A unique worker name alone does not redirect the
existing client, whose backend currently uses shared staging. Worker registration is not
proof of browser routing; check the call's `providerSnapshot.worker.dispatch_agent_name`
and worker/job IDs. These commands prepare routing; they do not claim a call has used it.

The profile sets these process-local values:

- `UVA_HUMANIZATION_POLICY_VERSION=conversational_v1`
- `UVA_TTS_RENDERER_CARTESIA=delivery_v1`, `UVA_TTS_STREAMING_CARTESIA=streaming_v1`
- `UVA_TTS_RENDERER_RIME=delivery_v1`, `UVA_TTS_STREAMING_RIME=streaming_v1`
- `UVA_TTS_RENDERER_ELEVENLABS=delivery_v1`, `UVA_TTS_STREAMING_ELEVENLABS=streaming_v1`
- `UVA_TTS_RENDERER_UPLIFT=delivery_v1`, `UVA_TTS_STREAMING_UPLIFT=streaming_v1`
- `UVA_OVERLAP_POLICY=overlap_v1`, `UVA_OPENING_POLICY=opening_v1`
- `UVA_PUBLISH_TURN_LATENCY=1`, `LIVEKIT_AGENT_NAME=uva-humanization-dev-habiba`

Existing provider credentials, models, voices, STT endpointing, and recording/disclosure rules
are inherited unchanged. Rime uses its current Arcana WebSocket defaults. Uplift live calls
require the existing `UPLIFT_MODE=live` and credentials; fixture mode stays fixture and cannot
prove live speech. The launcher pins compatible installed plugin versions, never installs them.
No speculative generation or new provider controls are enabled by the profile.

Rollback: stop only these isolated processes and launch the standard worker under its existing
baseline configuration. The launcher does not write `.env.local` or change the running staging
process. `natural_v1` remains shadow; `conversational_v1` activates bounded per-turn instructions
and lossless current-state facts without activating the full context compactor.
