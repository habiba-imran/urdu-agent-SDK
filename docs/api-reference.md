# Control Plane API Reference Specification
## Urdu Voice-Agent-as-a-Service (VaaS) Platform

> **Version**: 1.0.0  
> **Base URL**: `[CONTROL_PLANE_BASE_URL]` (Production) / `http://localhost:8000` (Dev)

The Control Plane is the core authentication, session minting, quota enforcement, and LiveKit dispatch engine of the VaaS platform. Host backends authenticate requests to the Control Plane using HMAC-SHA256 signatures and receive scoped LiveKit WebRTC access JWTs.

---

## 1. Authentication Mechanics

Requests to production endpoints (`/v1/session`) require HMAC authentication headers signed by the host platform's secret.

### Required Headers

| Header Name | Type | Description | Example |
|---|---|---|---|
| `X-Tenant-Id` | String (UUID) | The tenant UUID assigned during onboarding. | `15e96da6-6b75-4a28-bd7b-ac018986368d` |
| `X-Timestamp` | String (Unix Ts) | Current UTC Unix timestamp in seconds. Replayed requests >60s skew are rejected. | `1774135200` |
| `X-Nonce` | String | Random hex string (min 16 chars). Replayed nonces within 60s are rejected. | `a4f8b9c2d1e3f5a7` |
| `X-Signature` | String (Hex) | HMAC-SHA256 signature of `<tenant_id>.<timestamp>.<nonce>.<agent_id>` using tenant secret. | `f2d3a...` |
| `Content-Type` | String | Must be `application/json`. | `application/json` |

---

## 2. Endpoints

### 2.1 Mint Voice Session

Mints a short-lived (120s) LiveKit WebRTC access token, verifies tenant concurrency and minute quotas, and dispatches the LiveKit voice worker to the generated room.

- **HTTP Method**: `POST`
- **Path**: `/v1/session`

#### Request Body
```json
{
  "agent_id": "3b5b7720-4cce-4ac0-a765-6a3685e1bdf0"
}
```

#### Success Response (`200 OK`)
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "wsUrl": "wss://your-livekit-server.livekit.cloud",
  "roomName": "uva-15e96da6-6b75-4a28-bd7b-ac018986368d-1774135200-a4f8b9c2"
}
```

#### Error Responses

- **`400 Bad Request`**: Missing headers or timestamp skew > 60 seconds.
  ```json
  { "detail": "stale timestamp (skew > 60s)" }
  ```
- **`401 Unauthorized`**: Signature mismatch or invalid tenant secret.
  ```json
  { "detail": "invalid signature" }
  ```
- **`403 Forbidden`**: Tenant account suspended or origin not allowed.
  ```json
  { "detail": "tenant suspended" }
  ```
- **`404 Not Found`**: Provided `agent_id` does not exist or does not belong to the tenant.
  ```json
  { "detail": "agent not found" }
  ```
- **`429 Too Many Requests`**: Concurrent call limit or rate limit exceeded.
  ```json
  { "detail": "concurrent call limit reached" }
  ```

---

### 2.2 Refresh Session Token

Refreshes an expiring LiveKit WebRTC access token for an active call. Client SDKs issue this request automatically at `T-60s` before token expiration.

- **HTTP Method**: `POST`
- **Path**: `/v1/session/refresh`

#### Request Body
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Success Response (`200 OK`)
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "wsUrl": "wss://your-livekit-server.livekit.cloud",
  "roomName": "uva-15e96da6-6b75-4a28-bd7b-ac018986368d-1774135200-a4f8b9c2"
}
```

#### Error Responses
- **`401 Unauthorized`**: Token invalid, expired past grace period, or tampered.

---

### 2.3 Dev Session Mint (Dev Sandbox Only)

Development-only endpoint for quick testing without building an HMAC backend handler. Enabled when `publishableKey` is configured in dev environment.

- **HTTP Method**: `POST`
- **Path**: `/v1/session/dev-mint`

#### Request Body
```json
{
  "agentId": "3b5b7720-4cce-4ac0-a765-6a3685e1bdf0",
  "publishableKey": "15e96da6-6b75-4a28-bd7b-ac018986368d"
}
```

---

### 2.4 Health Check

Minimal liveness probe for load balancers and Render health monitoring.

- **HTTP Method**: `GET`
- **Path**: `/healthz`

#### Success Response (`200 OK`)
```json
{
  "status": "ok",
  "service": "uva-control-plane"
}
```

---

## 3. Interactive API Documentation

Interactive Swagger UI and ReDoc documentation are auto-generated and served at runtime:
- **Swagger UI**: `[CONTROL_PLANE_BASE_URL]/docs`
- **ReDoc**: `[CONTROL_PLANE_BASE_URL]/redoc`
