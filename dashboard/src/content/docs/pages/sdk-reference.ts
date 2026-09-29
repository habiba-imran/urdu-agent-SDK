export const meta = {
  slug: 'sdk-reference',
  title: 'SDK reference',
  eyebrow: 'Reference',
  description: 'Package map and the surfaces you call most often.',
};

export const markdown = `
## Packages

| Package | Runtime | Auth |
|---------|---------|------|
| \`@awaazlabs-uva/voice@1.1.0\` | Browser | Publishable key + your session endpoint |
| \`@awaazlabs-uva/agents@0.1.0\` | Backend | HMAC (\`tenantId\` + \`tenantSecret\`) |
| \`@awaazlabs-uva/telephony@0.1.0\` | Backend | HMAC (\`tenantId\` + \`tenantSecret\`) |

Pin versions in lockfiles.

## Voice (browser)

\`\`\`ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voice = new AwaazLabsUvaVoice({
  publishableKey: '...',
  sessionEndpoint: 'https://your-api.example/api/voice/session',
  refreshEndpoint: 'https://your-api.example/api/voice/session/refresh',
});

await voice.connect({ agentId: '...' });
await voice.disconnect();
voice.setMicMuted(true);
voice.startAudio(); // after audio_blocked
\`\`\`

Events and error codes: [Events and lifecycle](/docs/events-and-lifecycle).

## Agents (backend)

\`\`\`ts
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

const agents = new AwaazLabsUvaAgentsClient({
  baseUrl: process.env.UVA_API_BASE_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});
\`\`\`

Console: **[Agents](/agents)** (read-only inspection).

## Telephony (backend)

\`\`\`ts
import { TelephonyClient } from '@awaazlabs-uva/telephony';

const telephony = new TelephonyClient({
  baseUrl: process.env.UVA_TELEPHONY_API_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});
\`\`\`

Assigned numbers show on **[Agents](/agents)**. Provisioning stays on the telephony SDK.

## Host session contract

Not an npm package — your backend implements \`POST /api/voice/session\` (+ refresh). See [Backend setup](/docs/backend-setup) and [How integration works](/docs/how-integration-works).

## Console vs SDK

| Need | Prefer |
|------|--------|
| Copy env / rotate keys | [API Keys](/credentials) |
| Inspect agent config & numbers | [Agents](/agents) |
| Create / edit agents | \`@awaazlabs-uva/agents\` |
| Numbers & Telnyx | \`@awaazlabs-uva/telephony\` |
| Debug a call | [Sessions](/sessions) |
| Automate provisioning | agents / telephony SDKs |
`;
