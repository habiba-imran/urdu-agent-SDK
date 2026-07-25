# Host Backend Contract

Phase 3 defines the supported contract between:

- the browser SDK (`@awaazlabs-uva/voice`)
- the host platform's own backend
- the AwaazLabs-UVA control plane

The browser never holds the tenant HMAC secret. The host backend owns that secret and is the only
party allowed to sign control-plane mint requests.

## Browser to host backend

### Create session

`POST /api/voice/session`

Request body:

```json
{
  "publishableKey": "pk_demo",
  "agentId": "agent_uuid"
}
```

Expected success response:

```json
{
  "token": "<livekit-join-token>",
  "wsUrl": "wss://your-livekit-instance",
  "roomName": "uuid-room-name",
  "refreshUrl": "https://host.example.com/api/voice/session/refresh",
  "expiresIn": 120
}
```

Notes:

- `publishableKey` is a browser-safe identifier. It does not authorize the session by itself.
- `agentId` is the public integration handle the host app uses to target an agent.
- `refreshUrl` should point back to the host backend, not the control plane.

Recommended browser-facing status mapping:

- `200` -> session minted successfully
- `404` -> `agent_not_found`
- `429` -> `quota_exceeded`
- anything else -> `session_failed`

### Refresh session

`POST /api/voice/session/refresh`

Preferred request shape:

- `Authorization: Bearer <existing-session-token>`

Fallback request shape:

```json
{
  "token": "<existing-session-token>"
}
```

Expected success response:

```json
{
  "token": "<refreshed-livekit-token>",
  "wsUrl": "wss://your-livekit-instance",
  "roomName": "uuid-room-name",
  "refreshUrl": "https://host.example.com/api/voice/session/refresh",
  "expiresIn": 120
}
```

## Host backend to control plane

### Create session

`POST /v1/session`

Required headers:

- `X-Tenant-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

Optional forwarded header:

- `Origin`

Required body:

```json
{
  "agent_id": "agent_uuid"
}
```

Signature algorithm:

```text
HMAC-SHA256(tenant_secret, "<tenant_id>.<ts>.<nonce>.<agent_id>")
```

Where:

- `tenant_secret` is the raw host-owned HMAC secret for that tenant
- `tenant_id` is the UUID bound to that secret
- `ts` is a Unix timestamp in seconds
- `nonce` is a single-use unique value
- `agent_id` is the same UUID sent in the body

Control-plane expectations that the host backend must respect:

- replay window is 60 seconds
- nonce is single-use
- body field name is `agent_id` (snake_case), not `agentId`
- the host backend should forward the browser `Origin` header when present so tenant allowlists
  still apply end to end

Expected success response from the control plane:

```json
{
  "token": "<livekit-join-token>",
  "wsUrl": "wss://your-livekit-instance",
  "roomName": "uuid-room-name",
  "refreshUrl": "/v1/session/refresh",
  "expiresIn": 120
}
```

Important normalization rule:

- the host backend should rewrite `refreshUrl` to its own `/api/voice/session/refresh` route before
  returning the response to the browser SDK

### Refresh session

`POST /v1/session/refresh`

Supported request forms:

- `Authorization: Bearer <existing-session-token>`
- or body `{ "token": "<existing-session-token>" }`

No HMAC headers are required for refresh in the current control-plane implementation.

## Error mapping guidance

The control plane can return infrastructure-oriented details such as:

- `bad signature`
- `timestamp outside replay window`
- `nonce replay`
- `tenant not active`
- `origin not allowed`
- `agent dispatch failed`

The browser SDK should not depend on those raw internals. The host backend should collapse them to a
small browser-safe taxonomy through status codes:

- upstream `429` -> browser-facing `429`
- upstream `403` or `404` caused by agent lookup/authorization -> browser-facing `404`
- upstream `401`, `403`, `502`, or malformed response -> browser-facing `500` or `502`

## Starter backend env contract

The reference Node starter in `examples/host-backend/` expects:

- `UVA_CONTROL_PLANE_URL`
- `UVA_TENANT_ID`
- `UVA_HMAC_SECRET`
- `UVA_PUBLISHABLE_KEY`
- `HOST_ALLOWED_ORIGINS`
- optional `HOST_PUBLIC_BASE_URL`
- optional `PORT`

The reference starter intentionally models one tenant / one publishable key pair because Phase 3 is
about proving the integration path, not building multi-tenant onboarding yet.
