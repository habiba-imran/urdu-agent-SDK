# @awaazlabs-uva/telephony

Backend-only Node SDK for HMAC-signed AwaazLabs UVA machine telephony API calls.

Published as `@awaazlabs-uva/telephony@0.1.0`. Pin this version. Never import in a browser bundle. Client guide: dashboard → `/docs/telephony`.

This package stores the tenant HMAC secret only on the backend client for request signing. Telnyx API keys are transient method parameters for connect/rotate — never cached in SDK state.

## Package model

| Package | Runtime | Purpose | Secret boundary |
|---|---|---|---|
| `@awaazlabs-uva/voice@1.1.0` | Browser | WebRTC sessions | Zero secrets |
| `@awaazlabs-uva/agents@0.1.0` | Node backend | Create / update agents | Tenant HMAC |
| `@awaazlabs-uva/telephony@0.1.0` | Node backend | Telnyx, numbers, routing, PSTN | Tenant HMAC + transient Telnyx keys |

## Install

```bash
npm install @awaazlabs-uva/telephony@0.1.0
```

Releases publish from the canonical repo with npm provenance on a `telephony-v<version>` tag (see `.github/workflows/release-sdk.yml`).

## Backend environment

```env
UVA_TENANT_ID=[YOUR_TENANT_ID]
UVA_HMAC_SECRET=[YOUR_HMAC_SECRET]
UVA_TELEPHONY_API_URL=[YOUR_TELEPHONY_MACHINE_API_URL]
TELNYX_API_KEY=[YOUR_TELNYX_API_KEY]
```

`TELNYX_API_KEY` is needed only when connecting or rotating a Telnyx account.

## Usage

```ts
import {
  AwaazLabsUvaTelephonyError,
  TelephonyClient,
} from '@awaazlabs-uva/telephony';
import { randomUUID } from 'node:crypto';

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

const telephony = new TelephonyClient({
  tenantId: requireEnv('UVA_TENANT_ID'),
  tenantSecret: requireEnv('UVA_HMAC_SECRET'),
  baseUrl: requireEnv('UVA_TELEPHONY_API_URL'),
});

try {
  const status = await telephony.getConnectionStatus();

  if (status.platform_status !== 'active') {
    await telephony.connectTelnyxAccount({
      apiKey: requireEnv('TELNYX_API_KEY'),
      label: 'primary',
    });
  }

  const order = await telephony.purchaseNumber({
    e164Number: '<E164_NUMBER>',
    externalCustomerRef: '<OPAQUE_CUSTOMER_REF>',
    idempotencyKey: randomUUID(),
  });

  console.log(order.platform_status);
} catch (error) {
  if (error instanceof AwaazLabsUvaTelephonyError) {
    console.error(error.status, error.code, error.message);
  }
  throw error;
}
```

After purchase (or sync/import), `assignAgentToNumber(managedNumberId, agentId)` routes inbound. Assigned numbers appear read-only on the dashboard **Agents** page. Full flow: dashboard `/docs/telephony`.

## Method groups

- Telnyx account: `connectTelnyxAccount`, `rotateTelnyxAccountKey`,
  `reverifyTelnyxAccount`, `disconnectTelnyxAccount`, `getConnectionStatus`
- Numbers: `listTelnyxOwnedNumbers`, `listManagedPhoneNumbers`,
  `getManagedPhoneNumber`, `importTelnyxNumber`, `syncTelnyxOwnedNumbers`,
  `getTelnyxNumberDrift`, `searchAvailableNumbers`, `purchaseNumber`,
  `getNumberOrderStatus`
- Routing: `assignAgentToNumber`, `unassignAgentFromNumber`,
  `upsertTelnyxSipConnection`, `verifyTelnyxSipConnection`,
  `upsertTelnyxOutboundVoiceProfile`, `verifyTelnyxOutboundVoiceProfile`,
  `configureNumberRouting`, `configureOutboundTrunk`, `getOutboundReadiness`
- Calls: `createOutboundCall`, `getCallStatus`, `listCallRecords`, `disableNumber`
- Sessions: `getSessionByRoom` — correlate a room name with its voice session

## Stable error handling

Failed calls throw `AwaazLabsUvaTelephonyError`:

| Code | Typical handling |
|---|---|
| `telnyx_connection_missing` | Connect the Telnyx account first |
| `number_order_action_required` | Surface provider action to an operator |
| `regulatory_action_required` | Complete Telnyx KYC / docs, then retry |
| `outbound_not_ready` | Check SIP, OVP, number assignment (`getOutboundReadiness`) |
| `outbound_destination_disabled` | Destination country not on the platform whitelist |
| `idempotency_payload_mismatch` | Reuse original payload or new idempotency key |
| `number_not_available` | Choose another E.164 |
| `unsupported_number_feature` | Feature unavailable for that market |
| `telnyx_key_permission_failed` | Rotate key or grant Telnyx permissions |

Responses are redacted — no raw Telnyx keys, SIP secrets, or provider dumps.

## Number search and purchase

- `searchAvailableNumbers()` returns priced inventory when Telnyx supplies costs
- `purchaseNumber()` may return `managed_number_id` immediately after short reconciliation
- Pending orders: poll `getNumberOrderStatus(orderId)` — do not double-purchase

Country is required on search (ISO 3166-1 alpha-2). Do not assume US.

## Security

- Calls only `/machine/*` routes
- Signs with frozen telephony contract action strings
- Sends `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature`
- Does not connect directly to Telnyx, LiveKit, or Supabase from this client

## Build

```bash
npm ci
npm run build
npm run lint
npm test
```

## Changelog

See [CHANGELOG.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/telephony/CHANGELOG.md).
