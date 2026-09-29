# 02 — Host Backend Contract

Contract between:

1. Browser SDK `@awaazlabs-uva/voice`  
2. **Your** host backend (included: `host-backend-starter/`)  
3. AwaazLabs control plane (`UVA_CONTROL_PLANE_URL`)

The browser never holds the tenant HMAC secret.

---

## Browser → your backend

### Create session

`POST /api/voice/session`

Request:

```json
{
  "publishableKey": "<PUBLISHABLE_KEY>",
  "agentId": "agent_uuid"
}
```

Success response:

```json
{
  "token": "<livekit-join-token>",
  "wsUrl": "wss://...",
  "roomName": "uuid-room-name",
  "refreshUrl": "https://your-api.example.com/api/voice/session/refresh",
  "expiresIn": 120
}
```

Notes:

- `publishableKey` identifies; it does not authorize alone.  
- `refreshUrl` must point at **your** backend, not the control plane.  

### Refresh session

`POST /api/voice/session/refresh`

Preferred: `Authorization: Bearer <existing-session-token>`

Fallback body:

```json
{ "token": "<existing-session-token>" }
```

Success: same shape as create (`token`, `wsUrl`, `roomName`, `refreshUrl?`, `expiresIn?`).

---

## Your backend → AwaazLabs control plane

Implemented in `host-backend-starter/`. Summary:

### Mint

`POST {UVA_CONTROL_PLANE_URL}/v1/session`

Body:

```json
{ "agent_id": "<agent_uuid>" }
```

Headers:

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `X-Tenant-Id` | your tenant UUID |
| `X-Timestamp` | unix seconds (string) |
| `X-Nonce` | random UUID |
| `X-Signature` | HMAC-SHA256 hex (see below) |
| `Origin` | browser `Origin` when present (forwarded) |

**Signature canonical string:**

```text
${tenantId}.${timestamp}.${nonce}.${agentId}
```

**Algorithm:** `HMAC-SHA256(secret = UVA_HMAC_SECRET, message = canonical)` → lowercase hex digest.

Reference implementation: `host-backend-starter/src/signing.js`.

### Refresh

`POST {UVA_CONTROL_PLANE_URL}/v1/session/refresh`

- Prefer forwarding `Authorization: Bearer <token>`
- Or JSON body `{ "token": "<token>" }`

Rewrite any upstream refresh URL to your public `/api/voice/session/refresh` before returning to the browser.

### Host responsibilities

1. Validate `publishableKey` against `UVA_PUBLISHABLE_KEY`  
2. Sign and call the control plane as above  
3. Return only `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }`  
4. Map upstream failures for the browser SDK (below)  

---

## Status mapping (browser SDK error codes)

Forward HTTP status **and** a short reason in `error`, `detail`, or `code` (or plain text). Empty `429` bodies collapse quota vs rate-limit in the SDK.

| Upstream / host behavior | Browser SDK code |
|--------------------------|------------------|
| `200` | success |
| `404` | `agent_not_found` |
| `429` body mentions rate limit | `rate_limit` |
| `429` body mentions concurrent / monthly / quota | `quota_exceeded` |
| `429` empty / opaque | `quota_exceeded` |
| body mentions `worker_not_ready` | `worker_not_ready` |
| body mentions `provider_limit` | `provider_limit` |
| client wait > `fetchTimeoutMs` | `timeout` |
| other failures | `session_failed` |

---

## Typical backend environment

- `UVA_CONTROL_PLANE_URL` — when control plane is deployed  
- `UVA_TENANT_ID`  
- `UVA_HMAC_SECRET`  
- `UVA_PUBLISHABLE_KEY`  
- `HOST_ALLOWED_ORIGINS`  
- optional `HOST_PUBLIC_BASE_URL`, `PORT`  
