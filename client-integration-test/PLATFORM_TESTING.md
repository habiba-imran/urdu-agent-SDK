# Platform operator settings for isolated humanization testing

These are **worker environment settings**, not frontend or client host configuration. Copying this client folder does not grant clients control of them. Keep existing test service/provider credentials, URLs, models and voices; select a dedicated tenant/agent. Do not paste platform secrets into this folder's frontend env.

For turn-stage diagnostics in the SDK, explicitly enable the existing room publication flag **in the terminal that launches the test worker**, then restart that worker:

```powershell
$env:UVA_PUBLISH_TURN_LATENCY = '1'
```

This works with baseline as well as candidate settings. The worker logs `turn telemetry room_publication` and its effective configuration at session wiring; a client package version does not enable worker candidates. Copy the SDK `turn_latency` / `metrics_updated` payloads and the matching worker logs for investigation. Missing fields stay unknown; active-speaker delay is a proxy, and provider TTFB is not caller-heard FUAW. Set this flag to `0` and restart the test worker when room diagnostics are no longer needed. Production publication defaults stay off.

All candidate controls default to `baseline`. Core write/truth/failure/close guards are already active. For a deliberate local candidate comparison, an operator can set process-local values in the terminal that launches the isolated worker:

```powershell
$env:UVA_HUMANIZATION_POLICY_VERSION = 'natural_v1_shadow'
$env:UVA_OVERLAP_POLICY = 'overlap_v1'
$env:UVA_OPENING_POLICY = 'opening_v1'
# Choose ONLY the TTS provider under test:
$env:UVA_TTS_RENDERER_CARTESIA = 'delivery_v1'
$env:UVA_TTS_STREAMING_CARTESIA = 'streaming_v1'
# Launch the existing isolated worker with its normal project command.
```

For another provider use `UVA_TTS_RENDERER_RIME` / `UVA_TTS_STREAMING_RIME`, `..._ELEVENLABS`, or `..._UPLIFT`, with the same values. Streaming requires that provider's renderer to be `delivery_v1`. Current streaming is audited with LiveKit agents and provider plugins **1.6.5**; keep the project environment pinned. Do not enable all providers as a fallback strategy.

`UVA_HUMANIZATION_POLICY_VERSION=natural_v1` still resolves to **natural_v1_shadow**; it does not enable the general TurnPlan prompt. Overlap/opening/rendering/streaming are independent switches. Core truth safeguards remain active in baseline too. Confirm **effective** versions in telemetry, rather than inferring them from what was typed into a shell.

Use a fresh isolated worker process for each baseline/candidate comparison. Set the selected candidate variables back to `baseline` and restart that worker for rollback. This file does not change your `.env.local`, provider configuration, deployment or production defaults.

Candidate synthesis/overlap/opening require live acoustic verification. Uplift fixtures do not prove live Urdu TTS; provider keys alone do not establish an available test route. Inspect deployment-specific schema status separately: the committed additive `0039_telephony_calls_provider_call_ids.sql` migration supports provider call correlation, but a GitHub push does not apply it. Have the platform operator apply approved migrations through the existing deployment process; clients do not manage platform migrations.


For a controlled four-provider comparison, follow [the isolated A/B operator guide](HUMANIZATION_AB.md). The live inspection found the current local worker registered under the shared staging name with all candidate flags unset. Do not turn on candidates on that worker. Restart an isolated worker explicitly: installed Python `dev` mode does not reload changed source. The master policy still leaves general TurnPlan guidance shadow-only. The initial A/B recipe holds overlap/opening/master policy fixed and changes only the selected renderer/streaming pair; it has not been run live.
