# Telephony Real Provider Staging Runbook

This runbook is for enabling real Telnyx and LiveKit SIP provider mode on Render without changing the public `@awaazlabs-uva/telephony` SDK contract.

## Provider modes

Use exactly one mode per environment:

| Environment | `TELEPHONY_PROVIDER_MODE` | Behavior |
|---|---|---|
| Local automated tests | `mock` | Telnyx and LiveKit adapters may return fake resources. No provider credentials are required. |
| Staging | `real` | Tenant Telnyx credentials are read from encrypted DB references. Missing provider config fails closed. |
| Production | `real` | Same as staging, with production secrets and production Telnyx/LiveKit resources. |

Do not set `TELEPHONY_ALLOW_MOCK_MACHINE_AUTH=1` in Render staging or production. It is only for local route tests.

## Required Render environment variables for real staging

Set these on the deployed tenant portal API service:

```ini
TELEPHONY_PROVIDER_MODE=real
SUPABASE_DB_URL=<staging database connection string>
TELEPHONY_CREDENTIAL_ENCRYPTION_KEY=<stable encryption key for tenant Telnyx credential refs>
LIVEKIT_URL=<LiveKit Cloud URL>
LIVEKIT_API_KEY=<LiveKit API key>
LIVEKIT_API_SECRET=<LiveKit API secret>
TELNYX_PUBLIC_KEY=<Telnyx API v2 Ed25519 webhook public key from Mission Control>
TELEPHONY_WEBHOOK_PUBLIC_BASE_URL=<public tenant API base URL used in Telnyx webhook config>
```

Machine SDK auth must also have a tenant HMAC secret source configured through the existing tenant secret mechanism:

```ini
CP_TENANT_SECRETS={"<tenant_id>":"<tenant hmac secret>"}
```

or the equivalent trusted database-backed tenant secret source already used by `tenant_portal_api.machine_auth`.

Portal JWT routes also require:

```ini
TENANT_PORTAL_JWT_SECRET=<staging tenant portal JWT secret>
```
Telnyx API v2 webhook verification uses Ed25519, not an HMAC signing secret. Configure the base64 public key shown in Telnyx Mission Control under Keys & Credentials. Incoming webhook requests must include:

```http
Telnyx-Signature-Ed25519: <base64 Ed25519 signature>
Telnyx-Timestamp: <unix timestamp seconds>
```

The signed message is the exact raw request body prefixed by the timestamp and pipe separator: `{timestamp}|{raw_body}`. Do not parse and re-serialize JSON before verification.

Keep existing voice stack variables configured as before, including `UPLIFTAI_API_KEY`, `GLADIA_API_KEY`, `GOOGLE_API_KEY`, and any worker deployment variables required by the Urdu voice runtime.

## Fail-closed expectations

In `real` mode:

- Missing tenant Telnyx credential refs return `provider_credentials_missing`.
- Missing `LIVEKIT_URL`, `LIVEKIT_API_KEY`, or `LIVEKIT_API_SECRET` returns `provider_credentials_missing` before any fake trunk, rule, or SIP participant is produced.
- Missing or invalid Telnyx Ed25519 webhook signatures return `webhook_signature_invalid`.
- Fake provider IDs such as `pn_mock_*`, `lk_tr_in_mock_*`, `lk_tr_out_mock_*`, `lk_rule_mock_*`, and `sip_call_mock_*` must not appear in API responses.
- Fixed mock verification timestamps must not be returned after connecting a real Telnyx API key.

## Safe staging validation checklist

These checks avoid paid provider actions unless explicitly approved.

1. Deploy the tenant portal API commit that contains real-provider wiring.
2. Confirm Render has `TELEPHONY_PROVIDER_MODE=real` and does not have `TELEPHONY_ALLOW_MOCK_MACHINE_AUTH=1`.
3. Confirm Supabase migrations `0011` through `0015` are present in local and remote migration history.
4. Confirm health:

```powershell
curl.exe https://<tenant-api-host>/healthz
```

5. From a backend-only shell with `UVA_TELEPHONY_API_URL`, `UVA_TENANT_ID`, and `UVA_HMAC_SECRET`, run the signed SDK status smoke:

```js
await client.getConnectionStatus()
```

A missing Telnyx connection should return `platform_status: "not_connected"`, not `Machine auth unavailable`.

6. Connect a real Telnyx API key through the backend-only SDK or portal API. Do not expose the raw key in a browser.
7. Re-run `getConnectionStatus()`. It should return `platform_status: "active"`, real verification timestamps, and no raw credential fields.
8. Run `listTelnyxOwnedNumbers()` or `syncTelnyxOwnedNumbers()`. The returned provider IDs and phone numbers must come from the real Telnyx account and must not include `pn_mock_*` or `+15550001111`.
9. Configure SIP connection, outbound voice profile, inbound routing, and outbound trunk only after LiveKit variables are present.
10. Validate Telnyx webhooks with `telnyx-signature-ed25519`, `telnyx-timestamp`, and the configured `TELNYX_PUBLIC_KEY`. Unsigned, invalid, stale, and replayed signatures must be rejected; duplicate event IDs must be idempotently ignored.
11. Do not run `purchaseNumber()` or `createOutboundCall()` until paid-action approval is recorded.

## Database impact

No new migration is required for this runbook. Real-provider mode uses the existing telephony schema, especially `tenant_telnyx_connections.encrypted_api_key_ref`, phone-number inventory tables, LiveKit trunk/rule tables, call records, and existing RLS/grant migrations.
