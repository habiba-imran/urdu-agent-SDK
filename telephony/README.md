# @awaazlabs-uva/telephony

Backend-only Node SDK for signed AwaazLabs UVA machine telephony API calls.

This package is not a browser SDK. It stores the tenant HMAC secret only on the backend client instance for request signing, never sends that secret, and accepts Telnyx API keys only as transient method parameters for connection or rotation calls.

## Install

```bash
npm install @awaazlabs-uva/telephony
```

## Usage

```ts
import { TelephonyClient } from '@awaazlabs-uva/telephony';

const telephony = new TelephonyClient({
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
  baseUrl: process.env.UVA_TELEPHONY_API_URL!,
});

await telephony.purchaseNumber({
  e164Number: '<E164_NUMBER>',
  externalCustomerRef: '<OPAQUE_CUSTOMER_REF>',
  idempotencyKey: '<IDEMPOTENCY_KEY>',
});
```

## Security Rules

- Calls only `/machine/telephony/*` routes.
- Signs canonical JSON request bodies with fixed action strings from the frozen telephony contract.
- Sends `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, and `X-Signature`.
- Blocks `extraHeaders` from overriding auth or JSON body headers.
- Does not log, persist, cache, return, or expose raw Telnyx API keys.
- Does not connect directly to Supabase, Telnyx, LiveKit, or dashboard code.

## Build

```bash
npm run build
npm run lint
```
