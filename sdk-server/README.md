# @awaazlabs-uva/agents

**Server-side only. Never import this package in a browser bundle — it holds your tenant HMAC secret.**

Published as `@awaazlabs-uva/agents@0.1.0`. Pin this version. Client integration guide: tenant dashboard → `/docs` (Backend setup, Providers, Security).

Programmatic agent management for an **existing** AwaazLabs UVA tenant (`tenantId` + `tenantSecret`). Copy those from the dashboard **API Keys** page (owners), or ask your AwaazLabs contact.

Companion packages:

- Browser sessions: [`@awaazlabs-uva/voice@1.1.0`](https://www.npmjs.com/package/@awaazlabs-uva/voice)
- Telnyx / PSTN: [`@awaazlabs-uva/telephony@0.1.0`](https://www.npmjs.com/package/@awaazlabs-uva/telephony)

## Install

```bash
npm install @awaazlabs-uva/agents@0.1.0
```

## Usage (backend only)

```ts
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

const agents = new AwaazLabsUvaAgentsClient({
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
  baseUrl: process.env.UVA_API_BASE_URL!, // tenant portal / machine API base
});

// voiceId is required (API). Prefer a voice from getProviderCapabilities() for the language/TTS you choose.
const agent = await agents.createAgent({
  name: 'Support Agent',
  prompt: 'Answer customer questions concisely.',
  voiceId: 'cartesia-sonic-default', // or another catalogue id from getProviderCapabilities()
  agentLanguage: 'en', // or 'ur'
  // Optional: sttProvider, llmProvider, ttsProvider, ttsVoiceId, greeting, firstSpeaker
  firstSpeaker: 'agent',
  greeting: 'Hi, thanks for calling. How can I help?',
});

// Hand agent.id to the browser; connect with @awaazlabs-uva/voice
```

Configured STT / LLM / TTS **stick at runtime** (no silent vendor remap). Language stacks and defaults: dashboard `/docs/providers`.

### Methods

- `createAgent({ name, prompt, voiceId, llmModel?, agentLanguage?, sttProvider?, sttModel?, sttOptions?, llmProvider?, llmOptions?, ttsProvider?, ttsVoiceId?, ttsOptions?, greeting?, firstSpeaker?, toolsBaseUrl?, toolsAuthSecret? })`
- `listAgents()`
- `updateAgent(agentId, { … })`
- `getProviderCapabilities()` — enabled language / provider / model / voice combinations
- `listManagedNumbers({ assignedAgentId? })`
- `assignAgentToNumber(numberId, agentId | null)` / `unassignAgentFromNumber(numberId)`

`ttsVoiceId` takes priority over `voiceId` when both are given. `firstSpeaker` defaults to `'agent'`. Omit `greeting` to let the worker generate an opening line; `greeting: ''` on update clears a custom greeting.

Omitting provider fields keeps platform CREATE defaults for that language (English: Deepgram + Groq + Cartesia; Urdu: Gladia + Gemini + Uplift). Pass providers explicitly to override.

Each call HMAC-signs with `tenantSecret` — wire format: [docs/MACHINE_AGENT_API_CONTRACT.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/docs/MACHINE_AGENT_API_CONTRACT.md).

`extraHeaders` is for tunnels/proxies only; it cannot override auth headers.

## Errors

Throws `AwaazLabsUvaAgentsError` with `status` and `message`. Common: `401` bad signature, `403` suspended, `404` agent missing, `422` unsupported provider/language/model/voice, `429` rate limited.

On `422`, `code` is stable (`unsupported_provider_for_language`, `provider_not_enabled`, `unsupported_model_for_provider`, `unsupported_voice_for_provider`). Branch on `code`, not `message`.

## Security

- `tenantSecret` never leaves your process as a header value — used only to compute HMAC
- No browser build target
- Rotating the tenant secret invalidates prior signatures (same as session mint)

## Development

```bash
npm ci
npm test   # build + Node test runner (signing vectors)
```

## Changelog

See [CHANGELOG.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/sdk-server/CHANGELOG.md).
