# @awaazlabs-uva/agents

Server-side agent management SDK for an existing AwaazLabs-UVA tenant.

Never import this package in frontend/browser code. It uses the tenant HMAC secret at runtime and
belongs only in the client's backend.

## Install

From the client's backend project:

```bash
npm install /path/to/client-submission_v2/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
```

## Usage

```ts
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

const agents = new AwaazLabsUvaAgentsClient({
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
  baseUrl: process.env.UVA_PORTAL_API_URL!,
});

const agent = await agents.createAgent({
  name: 'Support Agent',
  prompt: 'You are a helpful Urdu customer support assistant.',
  voiceId: 'v_meklc281',
  llmModel: 'gemini-2.5-flash',
});

console.log(agent.id);
```

## Methods

- `createAgent({ name, prompt, voiceId, llmModel? })`
- `listAgents()`
- `updateAgent(agentId, { name?, prompt?, voiceId?, llmModel? })`

## Security Model

Each request is signed locally in the backend process with `tenantSecret` using HMAC-SHA256,
timestamp, and nonce headers. The raw secret is never sent as a request body or header value.

`extraHeaders` may be used for local tunnels or corporate proxies. It cannot override the SDK's
tenant/signature headers.

## Errors

Failed calls throw `AwaazLabsUvaAgentsError`:

| Status | Meaning |
|---|---|
| 401 | Bad secret, replayed nonce, or expired timestamp |
| 403 | Tenant suspended |
| 404 | Agent not found |
| 429 | Rate limited |

## Documentation

See `../../../docs/INTEGRATION_GUIDE.md` for full backend route examples and validation steps.
