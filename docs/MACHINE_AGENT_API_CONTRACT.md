# Machine Agent-Management API Contract

Defines the contract between a client's own backend (or `@uva/agents`) and `tenant_portal_api`'s
machine-auth routes. This is **not** the tenant-portal JWT flow used by the dashboard
(`/portal/login` + `/portal/agents`) — it is a separate, machine-callable auth model for an
**existing** tenant to manage its own agents programmatically. See
[docs/HOST_BACKEND_CONTRACT.md](HOST_BACKEND_CONTRACT.md) for the analogous session-mint contract;
this document intentionally mirrors its shape.

Scope: existing tenants only. There is no tenant-signup/bootstrap capability here — `tenantId` +
`tenantSecret` must already be provisioned.

## Trust model

- The tenant's raw HMAC secret authenticates every request. It is the same secret already used to
  sign `/v1/session` mint requests (`tenants.hmac_secret`) — reused deliberately rather than
  introducing a second credential, since that would touch tenant provisioning.
- **This secret must never be placed in browser code.** Only a server (your backend, or
  `@uva/agents` running in your backend) may hold it.
- Each request is scoped to one specific action and one specific payload — a captured signature
  for one call cannot be replayed against a different action, a different payload, or
  `/v1/session`.

## Required headers (all three routes below)

- `X-Tenant-Id` — the tenant UUID
- `X-Timestamp` — Unix seconds
- `X-Nonce` — a single-use unique value (e.g. a UUID); rejected on reuse
- `X-Signature` — see "Signature algorithm" below

## Signature algorithm

```text
HMAC-SHA256(tenant_secret, "<tenant_id>.<ts>.<nonce>.<action>.<payload_hash>")
```

Where:

- `tenant_secret` is the raw tenant HMAC secret
- `tenant_id`, `ts`, `nonce` are the same values sent in the headers above
- `action` is fixed per route (never sent as a header — the server derives it from which endpoint
  was called): `agent.create`, `agent.list`, or `agent.update`
- `payload_hash` is `sha256(canonical_json(body)).hexdigest()` (lowercase hex)

### Canonical JSON — must match byte-for-byte

`canonical_json(body)` = JSON with **all object keys recursively sorted**, **no extra whitespace**
(`,`/`:` separators only), and **non-ASCII characters left unescaped** (agent prompts are
Urdu-script text — do not `\uXXXX`-escape them). Encode the resulting string as UTF-8 before
hashing.

- Python (server-side reference): `json.dumps(body, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False).encode("utf-8")`
- JS/TS (client-side reference): recursively sort object keys, `JSON.stringify` each value, join
  with `,`/`:` — see `sdk-server/src/index.ts::canonicalJson()`. Do **not** rely on
  `JSON.stringify(obj)` alone; native key order is insertion order, not sorted.

For `GET /machine/agents` (list), the body is the empty object `{}` (canonical form: `"{}"`).

## Routes

### Create agent

`POST /machine/agents`

Body (all fields required except `llm_model`, which defaults server-side to
`gemini-2.5-flash` if omitted):

```json
{
  "name": "Support Agent",
  "prompt": "آپ ایک مددگار معاون ہیں...",
  "voice_id": "helpdesk-agent",
  "llm_model": "gemini-2.5-flash"
}
```

`action = "agent.create"`. Response: the created agent row (`id`, `name`, `prompt`, `voice_id`,
`llm_model`, `created_at`) — same shape `POST /portal/agents` already returns.

### List agents

`GET /machine/agents`

No body (sign `{}`). `action = "agent.list"`. Response: array of this tenant's agents, same shape
`GET /portal/agents` already returns.

### Update agent

`PATCH /machine/agents/{agent_id}`

Body: any subset of `{name, prompt, voice_id, llm_model}` — **include only the fields you are
changing**. Omitted fields must be entirely absent from the JSON body, not sent as `null`; the
signature covers exactly what you send, and the server only applies the fields present.

`action = "agent.update"`. Response: the updated agent row, or `404` if `agent_id` does not belong
to this tenant (or doesn't exist).

## Error mapping

| Status | Cause |
|---|---|
| `401` | missing signature header, bad signature, timestamp outside the 60s replay window, nonce reuse, unknown tenant, tenant has no secret provisioned |
| `403` | tenant suspended |
| `404` | (update only) `agent_id` not found or belongs to another tenant |
| `429` | per-tenant rate limit exceeded (30 requests/minute across all three routes) |

The browser-facing collapsing rules from `docs/HOST_BACKEND_CONTRACT.md` do not apply here — there
is no browser in this flow. Your backend can surface these statuses/details directly to your own
internal tooling or logs.

## What this contract deliberately does NOT include

- No `Origin` header / CORS-origin-allowlist check — these are server-to-server calls, not
  browser calls, so there is no `Origin` to check against `tenants.allowed_origins`.
- No tenant-creation or secret-issuance endpoint — existing tenants only.
- No separate "management" credential — the session-mint secret is reused; see the residual-risk
  note in this feature's design record (`docs/40-ADR.md`) if you are evaluating whether that's
  acceptable for your deployment.
