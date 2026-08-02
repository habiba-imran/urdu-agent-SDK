# Credentials and Environment Template

Use this template to separate browser-safe configuration from backend-only secrets.

## Backend environment

```bash
UVA_API_BASE_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_TELEPHONY_API_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_TENANT_ID=<TENANT_UUID>
UVA_HMAC_SECRET=<TENANT_HMAC_SECRET>

# Used only by the backend flow that connects or rotates the tenant Telnyx account.
TELNYX_API_KEY=<TELNYX_API_KEY>

# Optional values your backend may collect from operations/configuration screens.
TELNYX_SIP_FQDN=<TELNYX_SIP_FQDN>
TELNYX_SIP_USERNAME=<TELNYX_SIP_USERNAME>
TELNYX_SIP_SECRET=<TELNYX_SIP_SECRET>
TELNYX_OUTBOUND_ALLOWED_DESTINATIONS=<COMMA_SEPARATED_COUNTRY_OR_REGION_CODES>
```

## Frontend environment

```bash
PUBLIC_UVA_PUBLISHABLE_KEY=<PUBLIC_TENANT_KEY>
PUBLIC_UVA_SESSION_ENDPOINT=<YOUR_BACKEND_SESSION_ENDPOINT>
PUBLIC_UVA_REFRESH_ENDPOINT=<YOUR_BACKEND_SESSION_REFRESH_ENDPOINT>
PUBLIC_UVA_VOICE_CATALOG_ENDPOINT=<YOUR_BACKEND_VOICE_CATALOG_ENDPOINT>
```

Only values prefixed here as `PUBLIC_` are intended for browser code. The tenant HMAC secret, Telnyx API key, SIP secret, and any database/provider credentials must stay on the backend.

## Provider configuration checklist

| Item | Owned by | Notes |
| --- | --- | --- |
| Tenant ID and HMAC secret | AwaazLabs/platform operator | Required for signed backend SDK calls. |
| Publishable key | AwaazLabs/platform operator | Safe for frontend use; identifies the tenant/app. |
| Telnyx API key | Client/backend operator | Submit only from a backend flow to `connectTelnyxAccount` or `rotateTelnyxAccountKey`. |
| Telnyx phone numbers | Client/backend operator | Sync owned numbers or purchase/import numbers through approved backend flows. |
| Agent ID | Client/backend operator | Create or list agents with `@awaazlabs-uva/agents`; assign phone numbers to agent IDs with `@awaazlabs-uva/telephony`. |
| SIP and routing settings | Client/backend operator plus platform operator | Configure after Telnyx is connected and numbers are synced. |
| LiveKit/SIP provider credentials | Platform operator | Required by the hosted backend for real SIP routing. Do not place these in frontend code. |
| Webhook public key/configuration | Platform operator | Required by the hosted backend to verify provider webhooks. |

## Rotation guidance

- Rotate `UVA_HMAC_SECRET` in a coordinated maintenance window because backend SDK requests signed with the old secret will stop working.
- Rotate the Telnyx API key by calling `rotateTelnyxAccountKey({ apiKey })` from backend code.
- Do not print, return, or store raw provider credentials in application logs.
