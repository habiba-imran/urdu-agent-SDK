export const meta = {
  slug: 'telephony',
  title: 'Telephony',
  eyebrow: 'Integrate',
  description:
    'Connect Telnyx from your backend, sync or buy numbers, assign an agent, then test inbound and outbound.',
};

export const markdown = `
## What telephony covers

PSTN calls go: **caller → Telnyx → AwaazLabs telephony path → voice runtime**. The browser voice SDK is not on this path. Configure Telnyx with \`@awaazlabs-uva/telephony\` on **your backend** — this console is **read-only** for phone numbers (inspect assignments on [Agents](/agents)).

Telephony does **not** use browser \`/v1/session\` minting.

## What you bring

1. A Telnyx account + **API v2 key** (backend env only — never in the browser)  
2. Balance / permissions to search, purchase, and place voice calls  
3. Any Telnyx **regulatory / address** requirements for countries where you buy numbers  

## Backend setup

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
\`\`\`

\`connectTelnyxAccount\` stores the key for your tenant and provisions SIP + outbound voice profile infrastructure. Keep this package on the **server** only.

## Numbers: sync, search, buy

### Already own numbers on Telnyx

\`\`\`ts
await telephony.syncTelnyxOwnedNumbers();
const managed = await telephony.listManagedPhoneNumbers();
\`\`\`

Or import one E.164: \`importTelnyxNumber({ e164Number: '+1…' })\`.

### Buy a new number

\`\`\`ts
const available = await telephony.searchAvailableNumbers({
  country: 'PK', // ISO 3166-1 alpha-2 — required; do not assume US
  // areaCode: '21',
});

const pick = available[0];
if (!pick) throw new Error('No inventory for that query');

const order = await telephony.purchaseNumber({
  e164Number: pick.e164Number,
  idempotencyKey: randomUUID(),
});
// order.managed_number_id — use for assign
\`\`\`

There is **no reserve/hold step**. Search then purchase promptly with a stable idempotency key.

Purchase can fail with regulatory / KYC / balance errors from Telnyx — complete those requirements in Telnyx Mission Control for that country, then retry.

## Assign agent (inbound routing)

\`\`\`ts
await telephony.assignAgentToNumber(managedNumberId, agentId);
\`\`\`

Assign binds the number to your Telnyx SIP connection and configures LiveKit inbound routing. After this, the number should show as assigned on **[Agents](/agents)**.

You do **not** need a separate \`configureNumberRouting\` call after assign — assign already configures routing.

## Inbound test

1. Assign a number to an agent (above)  
2. Place a real PSTN call to that E.164  
3. Confirm a session row on **[Sessions](/sessions)**  

If the call does not connect, check agent assignment on Agents and that your AwaazLabs environment is online (SIP + voice runtime).

## Outbound

\`\`\`ts
const readiness = await telephony.getOutboundReadiness();
if (!readiness.is_ready && !readiness.ready) {
  throw new Error((readiness.reasons || []).join(', ') || 'outbound_not_ready');
}

const call = await telephony.createOutboundCall({
  agentId,
  fromNumberId: managedNumberId,
  toNumber: '+923001234567', // E.164
  idempotencyKey: randomUUID(),
});
\`\`\`

Outbound destinations follow the platform outbound voice profile whitelist (configured for your environment). Dialing a country that is not enabled returns \`outbound_destination_disabled\` before the call is placed — see [Errors](/docs/errors-and-troubleshooting).

Prove **inbound** first, then outbound.

## Checklist

- [ ] \`connectTelnyxAccount\` with backend Telnyx key  
- [ ] Number synced or purchased; \`managed_number_id\` known  
- [ ] \`assignAgentToNumber\` — visible on [Agents](/agents)  
- [ ] Inbound test call appears in [Sessions](/sessions)  
- [ ] \`getOutboundReadiness\` ready before live outbound  
- [ ] Destination country enabled for your outbound tests  
`;
