# @awaazlabs-uva/agents

Backend-only TypeScript SDK for creating, listing, and updating AwaazLabs UVA voice agents.

## Install

```bash
npm install ./client-submission_v2/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
```

## Runtime

Use this package only from backend code. It signs machine API requests with your tenant HMAC secret.

```bash
UVA_API_BASE_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_TENANT_ID=<TENANT_UUID>
UVA_HMAC_SECRET=<TENANT_HMAC_SECRET>
```

## Usage

```ts
import {
  AwaazLabsUvaAgentsClient,
  AwaazLabsUvaAgentsError,
} from '@awaazlabs-uva/agents';

const client = new AwaazLabsUvaAgentsClient({
  baseUrl: process.env.UVA_API_BASE_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});

try {
  const agent = await client.createAgent({
    name: 'Support Agent',
    prompt: 'Answer customer questions clearly and helpfully.',
    voiceId: 'voice_id_from_catalog',
    llmModel: 'gemini-2.5-flash',
    agentLanguage: 'ur',
    sttProvider: 'gladia',
    llmProvider: 'gemini',
    ttsProvider: 'uplift',
  });

  const agents = await client.listAgents();

  await client.updateAgent(agent.id, {
    prompt: 'Use a friendly, professional tone.',
    ttsProvider: 'rime',
    ttsVoiceId: 'voice_id_from_catalog',
  });

  // Which (language, layer, provider) combinations are enabled right now, plus each TTS
  // provider's own voice IDs - build pickers from this instead of hardcoding options.
  const capabilities = await client.getProviderCapabilities();
  const enVoices = capabilities.languages.en?.tts?.cartesia?.voices ?? [];
} catch (error) {
  if (error instanceof AwaazLabsUvaAgentsError) {
    // `code` is only set for provider/language/model/voice validation failures (422) - a
    // stable string like `unsupported_provider_for_language` or `provider_not_enabled` to
    // branch on. Auth failures, 404s, etc. leave it undefined; `message` is always
    // human-readable either way.
    console.error(error.status, error.code, error.message);
  }
  throw error;
}
```

## API

```ts
new AwaazLabsUvaAgentsClient({ baseUrl, tenantId, tenantSecret, extraHeaders? })

client.createAgent({
  name,
  prompt,
  voiceId,
  llmModel?,
  agentLanguage?,
  sttProvider?,
  sttModel?,
  sttOptions?,
  llmProvider?,
  llmOptions?,
  ttsProvider?,
  ttsVoiceId?,
  ttsOptions?,
})

client.listAgents()

client.updateAgent(agentId, {
  name?,
  prompt?,
  voiceId?,
  llmModel?,
  agentLanguage?,
  sttProvider?,
  sttModel?,
  sttOptions?,
  llmProvider?,
  llmOptions?,
  ttsProvider?,
  ttsVoiceId?,
  ttsOptions?,
})

client.getProviderCapabilities()
```

All provider/language/model fields are optional. Omitting them keeps the platform defaults. When both `voiceId` and `ttsVoiceId` are provided, the backend resolves the provider-specific TTS voice selection.

`getProviderCapabilities()` returns `{ languages: { [lang]: { label, stt?, llm?, tts? } } }`, where each `stt`/`llm` entry is `{ [provider]: { state: 'enabled', models, defaultModel } }` and each `tts` entry is `{ [provider]: { state: 'enabled', voices, defaultVoice } }`. Only currently-`enabled` combinations ever appear — a provider absent from a language's entry means it's either unsupported for that language or not enabled yet; check for key presence before offering it as an option.

## Errors

Failed calls throw `AwaazLabsUvaAgentsError` with `status`, `message`, and (for 422 provider/language/model/voice validation failures only) a stable `code` — e.g. `unsupported_provider_for_language`, `provider_not_enabled`, `unsupported_model_for_provider`, `unsupported_voice_for_provider`. Other failures (auth, suspended tenants, missing agents, rate limits) leave `code` undefined.

## Security notes

- `tenantSecret` must never be sent to the browser, stored in client-side state, or printed in logs.
- This package intentionally has no browser build target.
- `extraHeaders` is for non-auth transport headers only; it cannot override tenant or signature headers.
