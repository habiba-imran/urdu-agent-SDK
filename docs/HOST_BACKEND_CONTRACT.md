# Host Backend Contract

Phase 3 defines the supported contract between:

- the browser SDK (`@awaazlabs-uva/voice`)
- the host platform's own backend
- the AwaazLabs-UVA session service

The browser never holds the tenant HMAC secret. The host backend owns that secret and is the only
party allowed to delegate session creation to the backend-only session upstream.

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
- `refreshUrl` should point back to the host backend, not the session upstream.

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

## Host backend to AwaazLabs-UVA session service

The browser-facing contract above is the only interface client frontend code should know about.
The host backend must delegate upstream session creation and refresh to the Finova-provided
backend-only session adapter or approved host-backend starter.

Do not publish upstream service URLs, signature headers, replay-window details, nonce construction,
or raw signing algorithms in client-facing documentation or frontend code. Keep that material in the
backend-only adapter/starter and in the secure onboarding channel.

Backend implementation requirements:

- validate `publishableKey` before creating a session
- forward the browser `Origin` to the backend-only session adapter/starter when supported
- return only `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }` to the browser
- rewrite any upstream refresh URL to the host backend's `/api/voice/session/refresh` route before
  returning the response to the browser SDK
- collapse upstream failures into the browser-safe status mapping below

## Error mapping guidance

The upstream session service can return infrastructure-oriented details. The browser SDK should not
depend on those raw internals. The host backend should collapse them to a small browser-safe taxonomy
through status codes:

- upstream `429` -> browser-facing `429`
- upstream `403` or `404` caused by agent lookup/authorization -> browser-facing `404`
- upstream `401`, `403`, `502`, or malformed response -> browser-facing `500` or `502`

## Starter backend env contract

The reference Node starter in `examples/host-backend/` expects backend-only values from the secure
onboarding channel:

- `UVA_SESSION_UPSTREAM_URL`
- `UVA_TENANT_ID`
- `UVA_HMAC_SECRET`
- `UVA_PUBLISHABLE_KEY`
- `HOST_ALLOWED_ORIGINS`
- optional `HOST_PUBLIC_BASE_URL`
- optional `PORT`

The reference starter intentionally models one tenant / one publishable key pair because Phase 3 is
about proving the integration path, not building multi-tenant onboarding yet.
