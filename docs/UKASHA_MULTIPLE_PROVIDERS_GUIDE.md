# Ukasha Multiple Providers Guide

This guide explains how to make the internal SDK architecture dynamic for more providers without disturbing the current working Urdu pipeline.

The existing Urdu path must remain the default:

```text
ur + gladia STT + gemini LLM + uplift TTS
```

Use ISO language codes internally:

- `ur` = Urdu
- `en` = English

Dashboard labels may display `Urdu` and `English`, but API, DB, SDK, and worker config should use `ur` and `en`.

## Current Codebase Findings

The active worker pipeline is assembled in `worker/main.py`.

- `worker/main.py` builds `AgentSession(stt=make_stt(), llm=make_llm(cfg.llm_model), tts=make_tts(cfg.voice_id), ...)`.
- `worker/config.py` loads only `prompt`, `voice_id`, and `llm_model` from `agents`.
- `worker/factories.py` instantiates Gladia/Deepgram STT branches, Gemini LLM, and Uplift TTS.
- `supabase/migrations/0001_schema.sql` has `agents.voice_id` and `agents.llm_model`, but no provider/language fields.
- `tenant_portal_api/app.py`, `tenant_portal_api/queries.py`, `sdk-server/src/index.ts`, `client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts`, and `dashboard/src/lib/portalApi.ts` currently expose only `voice_id`/`voiceId` and `llm_model`/`llmModel`.

Currently dynamic:

- Agent prompt: `agents.prompt`
- TTS voice: `agents.voice_id` today, but new code should use canonical `tts_voice_id`
- LLM model: `agents.llm_model`

Currently hard-coded or global:

- STT provider: global `STT_PROVIDER`, default `gladia`
- STT language: hard-coded Urdu in `worker/factories.py`
- LLM provider: hard-coded Gemini through `livekit.plugins.google`
- TTS provider: Uplift for live/record mode
- TTS output format: `PCM_22050_16`
- Provider credentials: worker/backend environment only, currently `GLADIA_API_KEY`, `GOOGLE_API_KEY`, `UPLIFTAI_API_KEY`
- TTS mode: global `UPLIFT_MODE`

## Release Provider Rules

For the current release, supported combinations are intentionally narrow.

Urdu, `ur`:

- STT: Gladia only
- LLM: Gemini only
- TTS: Uplift only

English, `en`:

- STT: Gladia or Deepgram
- LLM: Gemini or Groq
- TTS: ElevenLabs, Fish Audio, Cartesia, or Rime

Do not allow Groq for Urdu in this release. Unsupported language/provider/model/voice combinations must return a clear validation error before a LiveKit room is started.

There must be no silent provider fallback. If a selected provider fails, return a clear error unless fallback behavior is explicitly configured for that agent or tenant.

## Central Capabilities API

Add a central capabilities API and make it the single source of truth for languages, providers, models, voices, option schemas, and enabled status.

Recommended endpoint:

```text
GET /api/provider-capabilities
```

Only combinations with rollout state `enabled` should be returned by the public capabilities API.

Rollout states:

- `planned`: documented internally, not selectable
- `testing`: available only to internal/admin test flows
- `enabled`: returned by the capabilities API and selectable by clients

The future dashboard should read this endpoint and disable unsupported options with a clear explanation. Do not require dashboard implementation changes in this phase.

## Capability Mapping

Capabilities must be validated at this level:

```text
language -> provider -> supported models/voices/options
```

Do not validate only at a broad provider level. A provider can support English STT but not Urdu STT; a TTS provider can support one English voice but not another.

Example capability shape:

```json
{
  "languages": {
    "ur": {
      "label": "Urdu",
      "stt": {
        "gladia": {
          "state": "enabled",
          "models": ["default"],
          "defaultModel": "default"
        }
      },
      "llm": {
        "gemini": {
          "state": "enabled",
          "models": ["gemini-2.5-flash"],
          "defaultModel": "gemini-2.5-flash"
        }
      },
      "tts": {
        "uplift": {
          "state": "enabled",
          "voices": ["v_meklc281"],
          "defaultVoice": "v_meklc281"
        }
      }
    },
    "en": {
      "label": "English",
      "stt": {
        "gladia": { "state": "enabled", "models": ["default"] },
        "deepgram": { "state": "enabled", "models": ["nova-3"] }
      },
      "llm": {
        "gemini": { "state": "enabled", "models": ["gemini-2.5-flash"] },
        "groq": { "state": "enabled", "models": ["llama-3.3-70b-versatile"] }
      },
      "tts": {
        "elevenlabs": { "state": "enabled", "voices": ["<voice-id>"] },
        "fish_audio": { "state": "enabled", "voices": ["<voice-id>"] },
        "cartesia": { "state": "enabled", "voices": ["<voice-id>"] },
        "rime": { "state": "enabled", "voices": ["<voice-id>"] }
      }
    }
  }
}
```

## Recommended Registry Structure

Keep `AgentSession(...)` stable. Move provider choice into a registry/factory layer that returns LiveKit-compatible STT, LLM, and TTS objects.

Suggested structure:

```text
worker/providers/
  types.py
  registry.py
  credentials.py
  stt/
    gladia.py
    deepgram.py
  llm/
    gemini.py
    groq.py
  tts/
    uplift.py
    elevenlabs.py
    fish_audio.py
    cartesia.py
    rime.py
```

Target runtime config:

```python
AgentRuntimeConfig(
    agent_language="ur",
    stt_provider="gladia",
    stt_model="default",
    stt_options={},
    llm_provider="gemini",
    llm_model="gemini-2.5-flash",
    llm_options={},
    tts_provider="uplift",
    tts_voice_id="v_meklc281",
    tts_options={},
)
```

Target worker flow:

```python
components = provider_registry.build_components(cfg)
AgentSession(
    stt=components.stt,
    llm=components.llm,
    tts=components.tts,
    vad=_load_vad(),
    userdata=...
)
```

Future providers should require adapter + capability entry + tests, not changes to the main worker pipeline.

## Required Changes

Database:

- Add and backfill `agent_language`, default `ur`.
- Add and backfill `stt_provider`, `stt_model`, `llm_provider`, `tts_provider`, `tts_voice_id`.
- Existing agents must backfill to `ur + gladia + gemini + uplift`.
- Use `tts_voice_id` as the canonical TTS voice field for all new code.
- Keep `agents.voice_id` only as a backward-compatible alias.
- During migration/backfill, keep `voice_id` and `tts_voice_id` synchronized where old clients still depend on `voice_id`.
- Keep `agents.llm_model` readable for backward compatibility.
- Extend voice/catalog storage with `provider`, `provider_voice_id`, `language`, `rollout_state`, and `enabled`.
- Store only non-secret `stt_options`, `llm_options`, and `tts_options`; validate each by its layer/provider schema.

API:

- Add `GET /api/provider-capabilities`.
- Update `tenant_portal_api/app.py` request models.
- Update `tenant_portal_api/queries.py` select/insert/update fields.
- Validate language, provider, model, voice, rollout state, and layer options before saving.
- Continue accepting existing `voice_id`/`voiceId` and `llm_model`/`llmModel`.
- If old and new fields are both provided, provider-specific new fields take priority.
- Specifically, `tts_voice_id`/`ttsVoiceId` takes priority over `voice_id`/`voiceId`.

SDK:

- Update `sdk-server/src/index.ts`.
- Update `client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts`.
- Add optional fields: `agentLanguage`, `sttProvider`, `sttModel`, `sttOptions`, `llmProvider`, `llmOptions`, `ttsProvider`, `ttsVoiceId`, and `ttsOptions`.
- Keep `voiceId` and `llmModel` as aliases for existing clients; new SDK code should prefer `ttsVoiceId`.

Worker:

- Update `worker/config.py` to load the new runtime fields.
- Move provider construction out of ad hoc branches in `worker/factories.py` into provider adapters/registry.
- Update `worker/main.py` only enough to call the registry.
- Keep the current Urdu default behavior unchanged.
- Every STT and TTS adapter must receive `agent_language` from `AgentRuntimeConfig`.
- No provider adapter should retain hard-coded Urdu language values.
- Language-specific provider codes should be resolved inside the adapter or capability layer.
- Add provider dependencies to `requirements.txt` only when adapters are implemented.

Dashboard:

- No dashboard implementation is required in this phase.
- Future dashboard work should read `GET /api/provider-capabilities`.
- Future UI should display friendly labels, filter by `agent_language`, and disable unsupported options with a short explanation.

Docs:

- Update `client-submission_v2/docs/INTEGRATION_GUIDE.md`.
- Update `client-submission_v2/docs/credentials-template.md`.
- Update `sdk-server/README.md`.
- Update `client-submission_v2/sdk/@awaazlabs-uva/agents/README.md`.

## Credential Handling

Provider credentials must remain backend/worker only.

Never expose provider API keys in:

- `@awaazlabs-uva/voice`
- frontend `.env`
- dashboard browser bundle
- client-side SDK docs
- agent prompt text
- `stt_options`, `llm_options`, or `tts_options`

Recommended pattern:

- AwaazLabs-owned provider keys stay in worker deployment environment variables.
- Tenant-owned provider keys, if supported later, must be stored server-side only and encrypted.
- A credential resolver should map selected provider to the correct backend credential.
- Missing credentials should fail clearly, for example `provider_credentials_missing`.

## Layer Options Validation

Do not accept unrestricted JSON.

Use separate option fields by layer:

```python
stt_options = {}
llm_options = {}
tts_options = {}
```

Do not use one generic `provider_options` blob. Each adapter must define an allowed schema for its own layer options. Unknown, unsupported, or wrong-type options should be rejected during agent create/update and checked again in the worker.

Examples:

- ElevenLabs may allow specific voice tuning fields.
- Cartesia may allow speed/emotion fields if supported.
- Uplift currently should not accept fake SSML/rate/emotion options.

## Backward Compatibility

Existing Urdu agents must continue to work without updates.

Backfill defaults:

```text
agent_language = ur
stt_provider = gladia
stt_model = default
llm_provider = gemini
llm_model = agents.llm_model
tts_provider = uplift
tts_voice_id = agents.voice_id
```

Compatibility rules:

- Continue accepting existing `voiceId` and `llmModel`.
- Continue returning `voice_id` and `llm_model` for existing SDK consumers.
- Treat `tts_voice_id` as canonical for all new code.
- Keep `voice_id` only as a backward-compatible alias and synchronize it with `tts_voice_id` where required during migration/backfill.
- If both `tts_voice_id`/`ttsVoiceId` and `voice_id`/`voiceId` are provided, `tts_voice_id`/`ttsVoiceId` takes priority.
- New provider-specific fields take priority when both old and new fields are provided.
- Existing agents default to `ur + gladia + gemini + uplift`.
- Do not change the current Gladia/Gemini/Uplift behavior until registry tests and Urdu E2E tests pass.

## Error Handling

Return clear errors from API create/update and worker startup:

- `unsupported_language`
- `unsupported_provider_for_language`
- `unsupported_model_for_provider`
- `unsupported_voice_for_provider`
- `provider_not_enabled`
- `invalid_stt_options`
- `invalid_llm_options`
- `invalid_tts_options`
- `provider_credentials_missing`
- `provider_runtime_failure`

Provider runtime failures should not silently switch providers. Explicit fallback can be added later as a named config, but it must be visible in DB/API config and covered by tests.

## Essential Tests

Before enabling new providers, add focused tests:

- Mandatory existing Urdu end-to-end regression test.
- Transcript received.
- TTS audio received.
- Interruption still works.
- Audio sample rate/channel compatibility.
- Adapter smoke tests for every enabled provider.
- End-to-end tests only for approved English provider combinations.
- Schema/default test: old agents default to `ur + gladia + gemini + uplift`.
- API validation tests for invalid combinations, such as `ur + groq` or `ur + elevenlabs`.
- Capabilities API returns only `enabled` combinations.
- Layer options schema rejects unknown options.
- Missing credential returns a clear error.
- SDK backward compatibility for `voiceId` and `llmModel`.

## Future Provider Process

To add a provider or language later:

1. Add the provider adapter under `worker/providers/<layer>/`.
2. Add dependency pins in `requirements.txt`.
3. Add models/voices/options to the capability registry or capability table.
4. Mark rollout state as `planned`, then `testing`, then `enabled`.
5. Add validation and smoke tests.
6. Expose it through `GET /api/provider-capabilities` only after it is `enabled`.

The long-term goal is simple: future providers and languages should not require changes to `worker/main.py` or the core `AgentSession` pipeline.
