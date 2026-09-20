# 04 — Telephony and Provider Keys

## Carrier: Telnyx (not Twilio)

This SDK’s telephony package (`@awaazlabs-uva/telephony`) integrates with **Telnyx**.

| Provider | Supported in this package? |
|----------|----------------------------|
| **Telnyx** | **Yes** — you must supply your own Telnyx API v2 key |
| Twilio | **No** — not wired in this SDK version |

If your team expected Twilio: you still need a **Telnyx** account for phone numbers and PSTN with AwaazLabs-UVA telephony today.

---

## What you must bring

1. A **paid Telnyx account**  
2. A **Telnyx API v2 key** (backend only)  
3. Enough **Telnyx balance** for number purchase and voice usage  
4. Account permissions to search / purchase / use voice numbers  
5. Any Telnyx **compliance / regulatory** steps required for the countries you buy numbers in  

AwaazLabs does **not** put your Telnyx key in the browser. You pass it only from your backend when calling:

```ts
await telephony.connectTelnyxAccount({ apiKey: process.env.TELNYX_API_KEY! });
// later rotation:
await telephony.rotateTelnyxAccountKey({ apiKey: process.env.TELNYX_API_KEY! });
```

---

## What the platform automates after Telnyx is connected

- Store the tenant Telnyx connection  
- Sync / import / purchase numbers (approved backend flows)  
- Assign managed numbers to agents  
- Inbound routing and outbound trunk configuration helpers  
- Outbound readiness checks  
- Outbound call creation via the platform  

You still need a usable Telnyx voice account; the SDK does not remove Telnyx-side account setup.

---

## Recommended onboarding order

1. Create Telnyx account + API v2 key  
2. Keep the key on your backend only  
3. `connectTelnyxAccount({ apiKey })`  
4. `syncTelnyxOwnedNumbers()` or purchase/import  
5. Create/select agent (`@awaazlabs-uva/agents`)  
6. `assignAgentToNumber(numberId, agentId)`  
7. `configureNumberRouting(numberId)` + `configureOutboundTrunk()` (and SIP/profile helpers if required)  
8. `getOutboundReadiness()` before live outbound calls  
9. `createOutboundCall({ agentId, fromNumberId, toNumber, idempotencyKey })`  

### End-to-end snippet

```ts
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
// Or: searchAvailableNumbers → reserveNumber → purchaseNumber (with idempotencyKey)

await telephony.assignAgentToNumber('<MANAGED_NUMBER_ID>', '<AGENT_ID>');
await telephony.configureNumberRouting('<MANAGED_NUMBER_ID>');
await telephony.configureOutboundTrunk();

const readiness = await telephony.getOutboundReadiness();
if (!readiness.ready) {
  throw new Error(`outbound_not_ready: ${JSON.stringify(readiness.reasons)}`);
}

const call = await telephony.createOutboundCall({
  agentId: '<AGENT_ID>',
  fromNumberId: '<MANAGED_NUMBER_ID>',
  toNumber: '+15551234567', // E.164
  idempotencyKey: randomUUID(),
});

// After ambiguous timeouts, check status — do not mint a new idempotency key blindly
const status = await telephony.getCallStatus(call.telephony_call_id);
```

### Product models

- **You (the client) hold one Telnyx account** and use it for your end users, **or**  
- Each of your customers has their own Telnyx key (rarer; still backend-only)  

End-user browsers never see Telnyx keys.

---

## Security rules (telephony)

- Never put `TELNYX_API_KEY` in frontend env or mobile apps  
- Never expose tenant HMAC in the browser  
- Gate purchase, disable, and outbound call actions behind your own approval UX  
- Do not log raw Telnyx keys or SIP secrets  

---

## Important platform constraints (summary)

- **One active Telnyx connection per tenant** at a time (connect / verifying / rotation-required)  
- Managed numbers and agent assignment are **tenant-scoped**  
- Use **idempotency keys** for purchase and outbound call creation  
- Outbound requires readiness (number + routing + trunk + profile as applicable)  
- LiveKit / SIP infra credentials for the hosted worker stay with the **platform operator**, not in your frontend  

---

## Other provider keys (STT / LLM / TTS)

Speech providers (Groq, Cartesia, Deepgram, etc.) are generally configured on the **hosted worker / tenant capabilities** side. Your integration usually:

- picks `ttsProvider` / voices via `@awaazlabs-uva/agents` and `getProviderCapabilities()`, and  
- does **not** put Cartesia/Groq keys in the browser  

If AwaazLabs asks you to supply a specific provider key for your tenant, it will be listed in the secure credentials message — still backend-only.
