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
    prompt: 'You are a calm, concise customer support agent.',
    voiceId: 'voice_id_from_catalog',
    llmModel: 'gemini-2.5-flash',
    agentLanguage: 'en',
    ttsProvider: 'cartesia',
    ttsVoiceId: 'voice_id_from_catalog',
    firstSpeaker: 'agent',
    greeting: 'Hi, thanks for calling. How can I help you today?',
  });

  const agents = await client.listAgents();

  await client.updateAgent(agent.id, {
    ttsProvider: 'rime',
    ttsVoiceId: 'voice_id_from_catalog',
  });

  await client.updateAgent(agent.id, {
    firstSpeaker: 'user',
  });

  // Which (language, layer, provider) combinations are enabled right now, plus each TTS
  // provider's own voice IDs - build pickers from this instead of hardcoding options.
  const capabilities = await client.getProviderCapabilities();
  const enVoices = capabilities.languages.en?.tts?.cartesia?.voices ?? [];

  const managedNumbers = await client.listManagedNumbers({
    assignedAgentId: agent.id,
  });
  console.log(managedNumbers.length);

  await client.assignAgentToNumber('<MANAGED_NUMBER_ID>', agent.id);
  await client.unassignAgentFromNumber('<MANAGED_NUMBER_ID>');
} catch (error) {
  if (error instanceof AwaazLabsUvaAgentsError) {
    // `code` is set for 422 provider/language/model/voice/greeting validation failures - a
    // stable string like `unsupported_provider_for_language`, `provider_not_enabled`,
    // `invalid_greeting`, or `invalid_first_speaker`. Auth failures, 404s, etc. leave it
    // undefined; `message` is always human-readable either way.
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
  greeting?,
  firstSpeaker?,
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
  greeting?,
  firstSpeaker?,
})

client.getProviderCapabilities()
client.listManagedNumbers({ assignedAgentId? })
client.assignAgentToNumber(numberId, agentId)
client.unassignAgentFromNumber(numberId)
```

All provider/language/model fields are optional. Omitting them keeps the platform defaults. When both `voiceId` and `ttsVoiceId` are provided, the backend resolves the provider-specific TTS voice selection.

`greeting` is the exact opening line when the agent speaks first (omit it for a generated greeting). `firstSpeaker` is `'agent'` (default, greets immediately) or `'user'` (wait for the caller). On update, `greeting: ''` clears a stored custom greeting. These fields are stored on the agent; do not pass them to `@awaazlabs-uva/voice` `connect()`.

## English TTS (Cartesia and Rime)

Set `agentLanguage: 'en'` and `ttsProvider: 'cartesia'` or `'rime'`. Pick `ttsVoiceId` from `getProviderCapabilities()`. Spoken humanization (pacing, formatting, sanitizers, sample rate) runs on the hosted worker — do not put SSML (`<break>`, `<spell>`), Rime `spell()`, markdown, or filler scripts in `prompt` or `greeting`. Keep `prompt` as character/role.

`ttsOptions` is optional. An empty object still receives platform defaults (Cartesia Sonic 3.5 + calm delivery; Rime Coda + websocket). Switch providers with `updateAgent({ ttsProvider, ttsVoiceId })`.

`getProviderCapabilities()` returns `{ languages: { [lang]: { label, stt?, llm?, tts? } } }`, where each `stt`/`llm` entry is `{ [provider]: { state: 'enabled', models, defaultModel } }` and each `tts` entry is `{ [provider]: { state: 'enabled', voices, defaultVoice } }`. Only currently-`enabled` combinations ever appear — a provider absent from a language's entry means it's either unsupported for that language or not enabled yet; check for key presence before offering it as an option.

`listManagedNumbers()`, `assignAgentToNumber()`, and `unassignAgentFromNumber()` are convenience methods for agent-to-number workflows when your backend wants to keep agent orchestration and number binding close together.

## Errors

Failed calls throw `AwaazLabsUvaAgentsError` with `status`, `message`, and (for 422 provider/language/model/voice/greeting validation failures only) a stable `code` — e.g. `unsupported_provider_for_language`, `provider_not_enabled`, `unsupported_model_for_provider`, `unsupported_voice_for_provider`, `invalid_greeting`, `invalid_first_speaker`. Other failures (auth, suspended tenants, missing agents, rate limits) leave `code` undefined.

## Security notes

- `tenantSecret` must never be sent to the browser, stored in client-side state, or printed in logs.
- This package intentionally has no browser build target.
- `extraHeaders` is for non-auth transport headers only; it cannot override tenant or signature headers.
