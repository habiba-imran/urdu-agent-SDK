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
