<<<<<<< HEAD
# Credentials Template - AwaazLabs-UVA-Voice SDK

Delivered by Finova Solutions. Fill real values through a secure channel only.

Do not commit a filled copy of this file. The preferred workflow is to copy each value into the
client application's `.env` files and keep this file as a blank reference.

## Backend Environment

Create these variables in the client's backend environment:

```env
PORT=3100
HOST_ALLOWED_ORIGINS=http://localhost:5174
HOST_PUBLIC_BASE_URL=http://localhost:3100

UVA_SESSION_UPSTREAM_URL=[BACKEND_ONLY_SESSION_UPSTREAM_URL]
UVA_SESSION_REFRESH_UPSTREAM_URL=[OPTIONAL_BACKEND_ONLY_REFRESH_UPSTREAM_URL]
UVA_VOICE_CATALOG_URL=[VOICE_CATALOG_URL]

UVA_PORTAL_API_URL=[PORTAL_API_URL]
UVA_TENANT_ID=[TENANT_ID]
UVA_HMAC_SECRET=[HMAC_SECRET]
UVA_PUBLISHABLE_KEY=[PUBLISHABLE_KEY]
```

## Frontend Environment

Create these variables in the client's frontend environment. For Next.js, rename the public
variables from `VITE_` to `NEXT_PUBLIC_`.

```env
VITE_UVA_PUBLISHABLE_KEY=[PUBLISHABLE_KEY]
VITE_UVA_SESSION_ENDPOINT=http://localhost:3100/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3100/api/voice/session/refresh
VITE_UVA_VOICE_CATALOG_ENDPOINT=http://localhost:3100/api/voices
VITE_UVA_AGENT_ID=[AGENT_ID]
```

## Credential Reference

| Name | Backend | Frontend | Sensitivity | Purpose |
|---|---:|---:|---|---|
| `UVA_TENANT_ID` | Yes | No | Medium | Tenant identifier used by backend signing calls |
| `UVA_HMAC_SECRET` | Yes | No | Critical | Backend-only HMAC signing key |
| `UVA_PUBLISHABLE_KEY` | Yes | Yes | Low | Public tenant identifier sent by browser to backend |
| `UVA_SESSION_UPSTREAM_URL` | Yes | No | Medium | Backend-only session creation upstream |
| `UVA_SESSION_REFRESH_UPSTREAM_URL` | Optional | No | Medium | Backend-only refresh upstream, if separate |
| `UVA_VOICE_CATALOG_URL` | Yes | No | Low | Backend-side source for voice catalog |
| `UVA_PORTAL_API_URL` | Yes | No | Low | Tenant portal API base URL for agent management |
| `AGENT_ID` | Optional | Yes | Low | UUID of an agent created through the backend |

## How To Obtain `AGENT_ID`

Use the backend `@awaazlabs-uva/agents` SDK to create an agent:

```ts
const agent = await agents.createAgent({
  name: 'Support Agent',
  prompt: 'You are a helpful Urdu support assistant.',
  voiceId: 'v_meklc281',
  llmModel: 'gemini-2.5-flash',
});

console.log(agent.id);
```

Put the returned `agent.id` into the frontend variable (`VITE_UVA_AGENT_ID` or
`NEXT_PUBLIC_UVA_AGENT_ID`).

## Rotation Guidance

| Credential | Rotation impact |
|---|---|
| `UVA_HMAC_SECRET` | Coordinate with Finova. Backend agent-management calls fail until the new secret is deployed. |
| `UVA_PUBLISHABLE_KEY` | Rare rotation. Requires frontend redeploy. |
| Dashboard credentials | Human-login only. No SDK runtime impact. |

If `UVA_HMAC_SECRET` is exposed in logs, Git history, or a frontend bundle, treat it as compromised
and contact Finova for rotation.
=======
# Credentials Template — AwaazLabs-UVA-Voice SDK

> **Finova Solutions** — Confidential Onboarding Document
> This document will be completed by your Finova Solutions account manager
> and delivered to you through a secure channel.

---

> [!CAUTION]
> **Never commit this file to version control once it contains real values.**
> Add `credentials-template.md` to your `.gitignore` if you store filled values here.
> The recommended practice is to copy each value directly into your `.env` files
> and keep this file as a blank reference template.

---

## How to Use This Document

1. Your Finova onboarding contact will **deliver the real values** for each placeholder below through a secure channel (encrypted email, 1Password share, or equivalent)
2. Copy each value into the corresponding environment variable in your `.env` files
3. Refer to `docs/INTEGRATION_GUIDE.md` Section 5 for the exact `.env` file structure

---

## Part A: Programmatic SDK Credentials

These credentials are loaded by your **backend** at runtime via environment variables.
They are required to initialise and operate the SDK programmatically.

---

### `UVA_TENANT_ID`

| Property | Value |
|---|---|
| **Description** | Your unique tenant UUID, issued by Finova during account provisioning |
| **Format** | UUID v4 (e.g. `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) |
| **Environment** | Backend `.env` only |
| **SDK Usage** | Passed as `tenantId` to `AwaazLabsUvaAgentsClient`; included in `X-Tenant-Id` request header |
| **Sensitivity** | Medium — identifies your tenant, but alone cannot authorise any action |

**Placeholder value (to be filled by Finova):**
```
UVA_TENANT_ID=[YOUR_TENANT_ID]
```

**How it connects to your code:**
```typescript
// In @awaazlabs-uva/agents initialisation (backend only):
const agents = new AwaazLabsUvaAgentsClient({
  tenantId: process.env.UVA_TENANT_ID!,  // ← this credential
  tenantSecret: process.env.UVA_HMAC_SECRET!,
  baseUrl: process.env.UVA_PORTAL_API_URL!,
});
```

---

### `UVA_HMAC_SECRET`

| Property | Value |
|---|---|
| **Description** | Your tenant's HMAC-SHA256 signing key. Used only by backend-side AwaazLabs-UVA integrations |
| **Format** | Base64-encoded or hex string (≥ 32 bytes) |
| **Environment** | Backend `.env` **ONLY** — **NEVER** expose to the browser |
| **SDK Usage** | Passed as `tenantSecret` to `AwaazLabsUvaAgentsClient`; used locally to compute `X-Signature` headers |
| **Sensitivity** | **CRITICAL** — possession of this secret allows signing requests as your tenant |

> [!WARNING]
> This is the most sensitive credential in your integration.
> If this value is ever exposed (committed to Git, logged to stdout, bundled in a frontend), treat it as **compromised** and contact Finova immediately for a rotation.

**Placeholder value (to be filled by Finova):**
```
UVA_HMAC_SECRET=[YOUR_HMAC_SECRET]
```

**How it connects to your code:**
```typescript
// In @awaazlabs-uva/agents initialisation (backend only):
const agents = new AwaazLabsUvaAgentsClient({
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,  // ← this credential
  baseUrl: process.env.UVA_PORTAL_API_URL!,
});

// Session minting must use the Finova-provided backend-only session adapter or approved starter.
// Do not place raw signing code in frontend code, browser bundles, or AI-generated client prompts.
```

---

### `UVA_PUBLISHABLE_KEY`

| Property | Value |
|---|---|
| **Description** | Your tenant's public identifier. Safe to embed in browser JavaScript |
| **Format** | UUID v4 (typically same as `UVA_TENANT_ID` in the current release) |
| **Environment** | Backend `.env` **and** frontend `.env` |
| **SDK Usage** | Passed as `publishableKey` to `AwaazLabsUvaVoice` in the browser; also sent in the session-mint request body |
| **Sensitivity** | **Low** — identifies but never authorises; the SDK is designed so this can be public |

**Placeholder value (to be filled by Finova):**
```
UVA_PUBLISHABLE_KEY=[YOUR_PUBLISHABLE_KEY]
```

**How it connects to your code:**
```typescript
// In your frontend (browser-safe):
const agent = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,  // ← this credential
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT,
});
```

---

### Backend-only session upstream configuration

| Property | Value |
|---|---|
| **Description** | Backend-only AwaazLabs-UVA session upstream configuration, provided through a secure onboarding channel if your backend starter requires it |
| **Format** | HTTPS URL or adapter-specific configuration value |
| **Environment** | Backend `.env` only |
| **SDK Usage** | Used only by the backend-only session adapter or approved host-backend starter |
| **Sensitivity** | Medium — keep server-side to avoid exposing infrastructure topology |

**Placeholder value (to be filled by Finova):**
```
UVA_SESSION_UPSTREAM_URL=[BACKEND_ONLY_SESSION_UPSTREAM_URL]
```

**How it connects to your code:**
```typescript
// In your backend only:
// Pass this value to the Finova-provided session adapter or approved host-backend starter.
// Do not expose it in frontend env files or public client documentation.
```

---

### `UVA_PORTAL_API_URL`

| Property | Value |
|---|---|
| **Description** | The base URL of the Finova Tenant Portal API. Used by `@awaazlabs-uva/agents` to create, list, and update agents |
| **Format** | HTTPS URL (e.g. `https://portal-api.finova.io`) |
| **Environment** | Backend `.env` only |
| **SDK Usage** | Passed as `baseUrl` to `AwaazLabsUvaAgentsClient` |
| **Sensitivity** | Low — a URL, not a secret |

**Placeholder value (to be filled by Finova):**
```
UVA_PORTAL_API_URL=[YOUR_PORTAL_API_URL]
```

**How it connects to your code:**
```typescript
// In @awaazlabs-uva/agents initialisation (backend only):
const agents = new AwaazLabsUvaAgentsClient({
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
  baseUrl: process.env.UVA_PORTAL_API_URL!,  // ← this URL
});
```

---

## Part B: Runtime Agent Identifier

### `AGENT_ID` (per-agent, not a global secret)

| Property | Value |
|---|---|
| **Description** | The UUID of a specific AI agent within your tenant. You create agents via `@awaazlabs-uva/agents`; this is the ID of the one you want browsers to connect to |
| **Format** | UUID v4 |
| **Environment** | Frontend `.env` (safe to expose; identifies an agent, not a secret) |
| **SDK Usage** | Passed as `agentId` in `agent.connect({ agentId })` |
| **Sensitivity** | Low — agent IDs are not secret |

**Placeholder value (create your first agent via the SDK or test app UI):**
```
VITE_UVA_AGENT_ID=[YOUR_AGENT_ID]
```

**How to obtain:** Use the `AgentManager` UI in the test app, or call `agents.createAgent(...)` from your backend and log the returned `id`.

---

## Part C: Dashboard Access Credentials

If your Finova onboarding package includes access to the Finova Operations Dashboard, you will receive separate login credentials. These are **not used in code** — they are for human access to monitoring, usage analytics, and configuration panels only.

| Credential | Description |
|---|---|
| `DASHBOARD_URL` | URL of the Finova web dashboard |
| `DASHBOARD_EMAIL` | Your administrator email address |
| `DASHBOARD_PASSWORD` | Initial login password (change on first login) |

> [!IMPORTANT]
> Dashboard credentials are separate from SDK credentials. Rotating the dashboard password does NOT affect SDK operations. Rotating `UVA_HMAC_SECRET` DOES affect all active sessions and must be coordinated with your engineering team.

---

## Credential Summary Table

| Credential | Backend `.env` | Frontend `.env` | Sensitivity |
|---|---|---|---|
| `UVA_TENANT_ID` | ✅ Required | ❌ Never | Medium |
| `UVA_HMAC_SECRET` | ✅ Required | ❌ **NEVER** | 🔴 Critical |
| `UVA_PUBLISHABLE_KEY` | ✅ Required | ✅ Required | 🟢 Low |
| `UVA_SESSION_UPSTREAM_URL` | If provided | ❌ Never | Medium |
| `UVA_PORTAL_API_URL` | ✅ Required | ❌ Never | 🟢 Low |
| `AGENT_ID` | ❌ Optional | ✅ Recommended | 🟢 Low |
| `DASHBOARD_EMAIL` | ❌ Never | ❌ Never | Medium |
| `DASHBOARD_PASSWORD` | ❌ Never | ❌ Never | 🟡 High |

---

## Credential Rotation

| Credential | How to Rotate | Impact |
|---|---|---|
| `UVA_HMAC_SECRET` | Contact Finova support → coordinate a rotation window | All in-flight HMAC-signed requests will fail until the new secret is deployed |
| `DASHBOARD_PASSWORD` | Self-service via dashboard settings | No SDK impact |
| `UVA_PUBLISHABLE_KEY` | Contact Finova (rare — tied to tenant ID) | Requires frontend redeployment |

---

*Delivered by Finova Solutions. Questions? Contact your account manager.*
>>>>>>> origin/ukasha
