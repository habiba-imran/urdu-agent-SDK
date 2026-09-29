export const meta = {
  slug: 'telephony',
  title: 'Telephony',
  eyebrow: 'Integrate',
  description: 'Connect Telnyx, attach a number, assign an agent, and test inbound from your backend.',
};

export const markdown = `
## What telephony covers

PSTN calls go: **caller → Telnyx → AwaazLabs telephony path → agent worker**. The browser voice SDK is not on this path. Configure Telnyx with \`@awaazlabs-uva/telephony\` on your backend — this console does not provision numbers or connections.

Telephony does **not** use browser \`/v1/session\` minting.

Assigned numbers appear read-only on **[Agents](/agents)**.

## Backend path (required)

\`\`\`ts title=telephony.ts
import { randomUUID } from 'node:crypto';
import { TelephonyClient } from '@awaazlabs-uva/telephony';

const telephony = new TelephonyClient({
  baseUrl: process.env.UVA_TELEPHONY_API_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});

await telephony.connectTelnyxAccount({
  apiKey: process.env.TELNYX_API_KEY!,
  label: 'primary',
});

await telephony.syncTelnyxOwnedNumbers();
// assignAgentToNumber / configureNumberRouting — see package methods
\`\`\`

Keep this package on the **server** only.

## Outbound

Outbound is supported when your tenant is ready:

\`\`\`ts
const readiness = await telephony.getOutboundReadiness();
if (!readiness.ready) {
  throw new Error(readiness.reasons?.join(', ') || 'outbound_not_ready');
}

const call = await telephony.createOutboundCall({
  agentId,
  fromNumberId: numberId,
  toNumber: '+15551234567',
  idempotencyKey: randomUUID(),
});
\`\`\`

Validate **inbound** first so number + agent assignment are proven.

## Checklist before demoing phone

- [ ] Telnyx connected via \`@awaazlabs-uva/telephony\`  
- [ ] Number attached and assigned to the right agent  
- [ ] Assignment visible on [Agents](/agents)  
- [ ] Agent prompt / voice verified on a browser call first  
- [ ] Inbound test call appears in [Sessions](/sessions)  
`;
