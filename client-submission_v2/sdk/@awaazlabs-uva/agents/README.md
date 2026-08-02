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
  });

  const agents = await client.listAgents();

  await client.updateAgent(agent.id, {
    prompt: 'Use a friendly, professional tone.',
  });
} catch (error) {
  if (error instanceof AwaazLabsUvaAgentsError) {
    console.error(error.status, error.message);
  }
  throw error;
}
```

## API

```ts
new AwaazLabsUvaAgentsClient({ baseUrl, tenantId, tenantSecret, extraHeaders? })

client.createAgent({ name, prompt, voiceId, llmModel? })
client.listAgents()
client.updateAgent(agentId, { name?, prompt?, voiceId?, llmModel? })
```

`tenantSecret` must never be sent to the browser, stored in client-side state, or printed in logs.
