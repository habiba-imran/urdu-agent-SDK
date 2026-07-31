# @awaazlabs-uva/telephony

Backend-only Node SDK for signed AwaazLabs UVA machine telephony API calls.

This package is not a browser SDK. It stores the tenant HMAC secret only on the
backend client instance for request signing, never sends that secret, and
accepts Telnyx API keys only as transient method parameters for connection or
rotation calls.

## Package Model

| Package | Runtime | Purpose | Secret boundary |
|---|---|---|---|
| `@awaazlabs-uva/voice` | Browser/WebRTC | Starts voice sessions and receives realtime events | Zero secrets |
| `@awaazlabs-uva/agents` | Node backend only | Creates and updates AI agents | Uses backend HMAC secret |
| `@awaazlabs-uva/telephony` | Node backend only | Manages Telnyx connection, numbers, routing, and calls | Uses backend HMAC secret and transient Telnyx keys |

Never import `@awaazlabs-uva/agents` or `@awaazlabs-uva/telephony` in browser
code. Your frontend should call your own backend routes.

## Install

From a client handoff tarball:

```bash
npm install ./sdk/@awaazlabs-uva/telephony/awaazlabs-uva-telephony-0.1.0.tgz
```

If Finova later publishes this package to an approved registry:

```bash
npm install @awaazlabs-uva/telephony
```

For the current client handoff, use the local `.tgz` file above.

## Backend Environment

Load these from your backend environment. Do not hardcode them in source code.

```env
UVA_TENANT_ID=[YOUR_TENANT_ID]
UVA_HMAC_SECRET=[YOUR_HMAC_SECRET]
UVA_TELEPHONY_API_URL=[YOUR_TELEPHONY_MACHINE_API_URL]
TELNYX_API_KEY=[YOUR_TELNYX_API_KEY]
```

`TELNYX_API_KEY` is needed only when connecting or rotating a Telnyx account.
Do not store it in SDK state, browser storage, logs, prompts, transcripts, or
fixtures.

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

## Method Groups

- Telnyx account: `connectTelnyxAccount`, `rotateTelnyxAccountKey`,
  `reverifyTelnyxAccount`, `disconnectTelnyxAccount`, `getConnectionStatus`
- Number inventory and purchase: `listTelnyxOwnedNumbers`,
  `listManagedPhoneNumbers`, `importTelnyxNumber`, `syncTelnyxOwnedNumbers`,
  `getTelnyxNumberDrift`, `searchAvailableNumbers`, `reserveNumber`,
  `purchaseNumber`, `getNumberOrderStatus`
- Routing and trunks: `assignAgentToNumber`, `unassignAgentFromNumber`,
  `upsertTelnyxSipConnection`, `verifyTelnyxSipConnection`,
  `upsertTelnyxOutboundVoiceProfile`,
  `verifyTelnyxOutboundVoiceProfile`, `configureNumberRouting`,
  `configureOutboundTrunk`, `getOutboundReadiness`
- Calls: `createOutboundCall`, `getCallStatus`, `listCallRecords`,
  `disableNumber`

## Stable Error Handling

Failed calls throw `AwaazLabsUvaTelephonyError`:

| Code | Typical handling |
|---|---|
| `telnyx_connection_missing` | Ask an operator to connect the Telnyx account in a backend/admin flow. |
| `number_order_action_required` | Surface the provider action requirement to an operator. |
| `regulatory_action_required` | Stop automated purchase flow until required documents are approved. |
| `outbound_not_ready` | Check routing, SIP connection, outbound profile, and number assignment. |
| `idempotency_payload_mismatch` | Reuse the original payload or generate a new idempotency key. |
| `number_not_available` | Ask the user to choose another exact number. |
| `unsupported_number_feature` | Treat reservation or requested feature as unavailable for the selected market. |
| `telnyx_key_permission_failed` | Rotate the Telnyx key or grant the required provider permissions. |

Public error objects and SDK responses are redacted. Raw provider payloads,
signatures, Telnyx keys, SIP secrets, and restricted diagnostics are not returned
by this SDK.

## Security Rules

- Calls only `/machine/telephony/*` routes.
- Signs canonical JSON request bodies with fixed action strings from the frozen
  telephony contract.
- Sends `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, and `X-Signature`.
- Blocks `extraHeaders` from overriding auth or JSON body headers.
- Does not log, persist, cache, return, or browser-expose raw Telnyx API keys.
- Does not connect directly to Supabase, Telnyx, LiveKit, or dashboard code.

## Build

```bash
npm run build
npm run lint
npm test
```
