# Host Backend Contract & Integration Specification
## Control-Plane Facing Protocol for Tenant Backends

> **Audience**: Host platform developers building a backend integration to mint LiveKit voice session tokens.
> **Security Rule**: The host platform's backend holds the raw HMAC secret. The browser client NEVER sees the HMAC secret.

---

## 1. Authentication & HMAC Signature Protocol

Every request from a host platform's backend server to the VaaS Control Plane (`POST /v1/session`) must include five required headers:

| Header | Description | Example |
|---|---|---|
| `X-Tenant-Id` | The UUID of the tenant account issued at onboarding. | `15e96da6-6b75-4a28-bd7b-ac018986368d` |
| `X-Timestamp` | Unix timestamp in seconds (integer string). Must be within 60s of control-plane clock. | `1774135200` |
| `X-Nonce` | Cryptographically random string (e.g. 16 hex chars). Must be unique per request within 60s. | `4f8a9b2c1d3e5f7a` |
| `X-Signature` | Hex-encoded HMAC-SHA256 signature of the payload string using the raw tenant HMAC secret. | `a3b8c...` |
| `Content-Type` | Must be `application/json`. | `application/json` |

### Signature Payload Formula
Construct the exact plaintext string:
```text
<tenant_id>.<timestamp>.<nonce>.<agent_id>
```

Calculate the HMAC-SHA256:
```python
import hmac, hashlib
signature = hmac.new(
    hmac_secret.encode('utf-8'),
    f"{tenant_id}.{timestamp}.{nonce}.{agent_id}".encode('utf-8'),
    hashlib.sha256
).hexdigest()
```

---

## 2. API Endpoints

### 2.1 Mint Session (`POST /v1/session`)

**Request Body**:
```json
{
  "agent_id": "3b5b7720-4cce-4ac0-a765-6a3685e1bdf0"
}
```

**Success Response (`200 OK`)**:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "wsUrl": "wss://your-livekit-server.livekit.cloud",
  "roomName": "uva-15e96da6-6b75-4a28-bd7b-ac018986368d-1774135200-4f8a9b2c"
}
```

### 2.2 Refresh Session Token (`POST /v1/session/refresh`)

**Request Body**:
```json
{
  "token": "<expiring-livekit-jwt-token>"
}
```

**Success Response (`200 OK`)**:
```json
{
  "token": "<newly-minted-livekit-jwt-token>",
  "wsUrl": "wss://your-livekit-server.livekit.cloud",
  "roomName": "uva-15e96da6-6b75-4a28-bd7b-ac018986368d-1774135200-4f8a9b2c"
}
```

---

## 3. Error Responses & Status Codes

| HTTP Status | Error Detail | Meaning / Action |
|---|---|---|
| `400 Bad Request` | `missing header: ...` / `stale timestamp` | Missing signature headers or timestamp > 60s skew. |
| `401 Unauthorized` | `invalid signature` | HMAC signature mismatch. Check HMAC secret. |
| `403 Forbidden` | `origin not allowed` / `tenant suspended` | Tenant origin or account status blocked. |
| `404 Not Found` | `agent_not_found` | Provided `agent_id` does not exist for this tenant. |
| `429 Too Many Requests` | `rate limit exceeded` / `concurrent limit reached` | Active call count or rate limit exceeded. |

---

## 4. Node.js Reference Signature Snippet

```javascript
import crypto from 'crypto';

function signSessionRequest(tenantId, secret, timestamp, nonce, agentId) {
  const payload = `${tenantId}.${timestamp}.${nonce}.${agentId}`;
  return crypto.createHmac('sha256', secret).update(payload).digest('hex');
}
```
