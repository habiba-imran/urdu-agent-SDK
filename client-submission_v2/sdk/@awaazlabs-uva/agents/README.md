# @awaazlabs-uva/agents

**Server-side only. Never import this package in browser code — it holds your tenant secret.**

Programmatic agent management for an **existing** AwaazLabs-UVA tenant. If you don't have a
`tenantId` + `tenantSecret` yet, this package can't help you get them — that's a platform/tenant
provisioning step outside this package's scope.

This is a different package from [`@awaazlabs-uva/voice`](../voice/README.md) on purpose: `@awaazlabs-uva/voice` is the
public browser bundle that connects an end user to an already-created agent and ships with zero
secrets; `@awaazlabs-uva/agents` is what your own backend uses to create/manage the agents `@awaazlabs-uva/voice` later
connects to.

## Install

From the client-submission root:

```bash
npm install ./sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
```

## Usage (in your backend only)

```ts
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

const agents = new AwaazLabsUvaAgentsClient({
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
  baseUrl: 'https://portal-api.example.com',
  extraHeaders: process.env.NODE_ENV === 'development'
    ? { 'ngrok-skip-browser-warning': 'true' }
    : undefined,
});

const agent = await agents.createAgent({
  name: 'Support Agent',
  prompt: 'آپ ایک مددگار معاون ہیں...',
  voiceId: 'helpdesk-agent',
});

// hand agent.id to your frontend; the frontend uses @awaazlabs-uva/voice + this agentId to connect
```

### Methods

- `createAgent({ name, prompt, voiceId, llmModel?, agentLanguage?, sttProvider?, sttModel?, sttOptions?, llmProvider?, llmOptions?, ttsProvider?, ttsVoiceId?, ttsOptions? })`
- `listAgents()`
- `updateAgent(agentId, { name?, prompt?, voiceId?, llmModel?, agentLanguage?, sttProvider?, sttModel?, sttOptions?, llmProvider?, llmOptions?, ttsProvider?, ttsVoiceId?, ttsOptions? })`

Every field beyond `name`/`prompt`/`voiceId` is optional — omit them all and you get the same
`ur` + Gladia + Gemini + Uplift agent this package has always created. `ttsVoiceId` takes priority
over `voiceId` when both are given (server-resolved). See
`docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md` for what's live vs. planned.

Each call signs its own request with `tenantSecret` (HMAC-SHA256, timestamped, single-use nonce,
scoped to that one action) — see
[docs/INTEGRATION_GUIDE.md](../../../docs/INTEGRATION_GUIDE.md) for the wire contract if
you'd rather implement your own client in another language.

`extraHeaders` is only for development tunnels or corporate proxies. It is merged before the SDK's
auth headers, so it cannot override tenant/signature headers.

## Errors

Failed calls throw `AwaazLabsUvaAgentsError` with a `status` (the HTTP status from `tenant_portal_api`) and
a `message` (the server's `detail` string). Common cases: `401` bad signature/replay/expired
timestamp, `403` tenant suspended, `404` agent not found (update), `422` unsupported/disabled
provider-language-model-voice combination (message is a JSON string with a stable `code`, e.g.
`unsupported_provider_for_language`), `429` rate limited.

## Security notes

- `tenantSecret` never leaves your backend process in this client — it's used locally to compute
  an HMAC signature, never sent as a request body/header value itself.
- This package intentionally has no browser build target. If your bundler pulls this into a
  client-side bundle, that's a misconfiguration to fix, not something this package tries to work
  around.
- Rotating your tenant secret (via your platform's admin) invalidates every previously-issued
  signature going forward, same as it already does for session-mint signing.
