# Telnyx Setup And Platform Constraints

This note is for teams integrating `client-submission_v2` into their own backend product.

It focuses on:

- what the client must do on the Telnyx side
- what this SDK/platform automates after the Telnyx account is connected
- the important platform constraints that affect number purchase, assignment, routing, and calling

## 1. Telnyx Responsibilities

For Telnyx only, the client should assume they need:

- a paid Telnyx account
- a Telnyx API v2 key
- enough Telnyx balance for number purchase and voice usage
- account permissions that allow searching, purchasing, and using phone numbers for voice
- any Telnyx-side verification, regulatory, or compliance requirements completed when required by the ordered country or number type

The client does not need to give each end customer direct Telnyx access.

The intended automation model is:

1. P2F keeps one or more Telnyx API keys on its backend only.
2. P2F's product lets its own customers request or buy numbers.
3. P2F's backend calls the telephony SDK and Telnyx-backed flows using P2F's backend-held Telnyx key.
4. Purchased or synced numbers are then assigned to agents and configured for inbound/outbound use.

## 2. What The Client Does Not Need To Manually Build In Telnyx

Once the Telnyx account is connected through the backend SDK flow, this platform is designed to automate or manage:

- storing the tenant's active Telnyx connection
- syncing Telnyx-owned numbers into managed inventory
- importing an existing Telnyx-owned number
- purchasing a number through an approved backend flow
- assigning a managed number to an agent
- configuring inbound routing
- configuring outbound trunking
- checking outbound readiness before calls
- creating outbound calls through the platform

Important: this does not mean "only API key and balance matter." The Telnyx account must still be usable for voice and any required compliance steps must already be satisfied on the Telnyx side.

## 3. Recommended Telnyx Onboarding Flow

For a new client or new tenant:

1. Create a paid Telnyx account.
2. Create a Telnyx API v2 key.
3. Keep that key on backend systems only.
4. Connect the Telnyx account through `connectTelnyxAccount({ apiKey })`.
5. Sync existing owned numbers with `syncTelnyxOwnedNumbers()` or purchase/import numbers through approved backend flows.
6. Assign each managed number to an agent.
7. Configure routing and outbound readiness before creating live calls.

For a product like P2F:

- P2F can use its own Telnyx account and API key on behalf of its customers.
- P2F customers do not need their own Telnyx dashboard access unless P2F wants that operating model.
- Number purchase should happen from P2F backend code, not from browser code.

## 4. Security Rules

- Never put the Telnyx API key in browser code.
- Never expose tenant HMAC secrets in browser code.
- Never let end customers call the backend-only telephony SDK directly from the frontend bundle.
- Treat purchase, disable, and outbound call actions as approval-gated operations in the product flow.

## 5. Important Platform Constraints

These are real backend/data constraints that integrators should know about.

### 5.1 One active Telnyx connection per tenant

The platform allows only one active/verifying/rotation-required Telnyx connection per tenant at a time.

Practical effect:

- if a tenant already has an active connection, use key rotation rather than creating another active connection

### 5.2 One active SIP connection per active Telnyx connection

The platform keeps only one active SIP connection record for a tenant/Telnyx connection pair.

Practical effect:

- the client should update the existing SIP configuration rather than trying to create parallel active SIP records for the same tenant connection

### 5.3 Managed phone numbers are unique per tenant by E.164

There is a tenant-scoped uniqueness rule for active managed numbers by `e164_number`.

Practical effect:

- the same active phone number should not appear twice for the same tenant
- released or deleted numbers are excluded from the active uniqueness rule

### 5.4 Managed phone numbers are unique per tenant by provider number identity

There is also a tenant-scoped unique constraint on `(tenant_id, provider_number_id)`.

Practical effect:

- one Telnyx provider number ID maps to one managed number row for that tenant
- sync and purchase flows upsert by provider number identity
- duplicate rows with the same tenant/provider-number pair are not valid

Note: PostgreSQL still allows multiple `NULL` `provider_number_id` values, so pre-provider or transitional rows remain valid.

### 5.5 One active inbound trunk per managed number

The platform keeps only one active inbound trunk per managed number.

Practical effect:

- routing for one number should converge on a single active LiveKit inbound trunk

### 5.6 One active dispatch rule per managed number

The platform keeps only one active SIP dispatch rule per managed number.

Practical effect:

- a number should resolve to one active inbound dispatch path at a time

### 5.7 One active outbound trunk per tenant connection

The platform keeps only one active outbound trunk per tenant Telnyx connection.

Practical effect:

- outbound trunk configuration is tenant-level infrastructure, not a separate active trunk per number

### 5.8 Idempotency is required for purchase and outbound call creation

The platform stores idempotency records and enforces tenant-scoped uniqueness for repeated actions.

Practical effect:

- each intended number purchase must use its own idempotency key
- each intended outbound call must use its own idempotency key
- reusing the same key with a different payload is a conflict
- do not automatically retry with a new key unless the product is intentionally creating a new purchase or a new call

### 5.9 Outbound calls require readiness, not just a number

Outbound calling is not considered ready just because a Telnyx account is connected.

The platform checks for:

- an active Telnyx connection
- at least one managed number
- at least one managed number assigned to an agent and routing-ready
- an active SIP connection
- an active outbound voice profile

Practical effect:

- the product should always call `getOutboundReadiness()` before allowing a live outbound call

### 5.10 Number assignment is agent-bound

Outbound calls require the selected `fromNumberId` to be assigned to the target agent, and routing-ready when required.

Practical effect:

- a client should not assume any tenant number can dial for any agent without assignment

## 6. Product Design Guidance For P2F

If P2F wants a clean self-serve experience for its own customers, the recommended model is:

- P2F stores the Telnyx API key in its backend only
- P2F offers a "buy number" or "use existing number" flow in its own app
- P2F uses backend SDK calls to purchase, sync, import, assign, route, and verify readiness
- P2F treats number purchase and outbound calling as explicit user-approved actions
- P2F prevents duplicate purchase/call requests by generating one idempotency key per intended action

## 7. Minimum Telnyx Checklist For Client Handoff

Before go-live, the client should confirm:

- paid Telnyx account exists
- API v2 key exists
- account has enough balance
- account can search/order the intended number types
- any required Telnyx regulatory or verification steps are complete
- P2F backend, not browser code, will hold and use the API key

## 8. Summary

The simplest correct statement is:

"The client mainly brings a paid Telnyx account, a backend-held API key, and enough balance. Their product can then automate number purchase and number-to-agent setup through the SDK, but they must still respect Telnyx compliance requirements and the platform's tenant-scoped uniqueness, readiness, and idempotency rules."
