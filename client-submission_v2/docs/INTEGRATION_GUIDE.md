# AwaazLabs UVA Integration Guide

This guide covers browser voice, backend agent management, and backend telephony management using the packages in `client-submission_v2/sdk`.

For a full method-by-method package inventory, also read `SDK_CAPABILITIES_REFERENCE.md`.

## 1. Architecture

Use the packages in two places:

| Layer | Package | Responsibility |
| --- | --- | --- |
| Browser frontend | `@awaazlabs-uva/voice` | Connects a user to a short-lived LiveKit/WebRTC voice session. |
| Your backend | `@awaazlabs-uva/agents` | Creates, lists, and updates agents with signed machine requests. |
| Your backend | `@awaazlabs-uva/telephony` | Manages Telnyx connection, phone numbers, routing, readiness, and outbound calls with signed machine requests. |

Never import the agents or telephony SDK in browser code. They require the tenant HMAC secret.

## 2. Install packages

Frontend application:

```bash
npm install ./client-submission_v2/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz
```

Backend application:

```bash
npm install ./client-submission_v2/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
npm install ./client-submission_v2/sdk/@awaazlabs-uva/telephony/awaazlabs-uva-telephony-0.1.0.tgz
```

## 3. Backend configuration

```bash
UVA_API_BASE_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_TELEPHONY_API_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_TENANT_ID=<TENANT_UUID>
UVA_HMAC_SECRET=<TENANT_HMAC_SECRET>
TELNYX_API_KEY=<TELNYX_API_KEY>
```

`TELNYX_API_KEY` is needed only by the backend flow that connects or rotates the tenant Telnyx account. Do not persist it in your application unless your own security model requires it.

## 4. Frontend configuration

```bash
PUBLIC_UVA_PUBLISHABLE_KEY=<PUBLIC_TENANT_KEY>
PUBLIC_UVA_SESSION_ENDPOINT=<YOUR_BACKEND_SESSION_ENDPOINT>
PUBLIC_UVA_REFRESH_ENDPOINT=<YOUR_BACKEND_SESSION_REFRESH_ENDPOINT>
PUBLIC_UVA_VOICE_CATALOG_ENDPOINT=<YOUR_BACKEND_VOICE_CATALOG_ENDPOINT>
```

The frontend calls your backend session endpoint. Your backend is responsible for authenticating the user and returning a short-lived session payload.

## 5. Create and manage agents

```ts
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

const agents = new AwaazLabsUvaAgentsClient({
  baseUrl: process.env.UVA_API_BASE_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});

const agent = await agents.createAgent({
  name: 'Support Agent',
  prompt: 'Answer customer questions in a concise and helpful way.',
  voiceId: 'voice_id_from_catalog',
  llmModel: 'gemini-2.5-flash',
  agentLanguage: 'ur',
  sttProvider: 'gladia',
  llmProvider: 'gemini',
  ttsProvider: 'uplift',
});

const allAgents = await agents.listAgents();

await agents.updateAgent(agent.id, {
  prompt: 'Use a friendly, professional tone.',
  ttsProvider: 'rime',
  ttsVoiceId: 'voice_id_from_catalog',
});
```

Agent records include `id`, `name`, `prompt`, `voice_id`, `llm_model`, `created_at`, optional usage metadata, and provider fields such as `agent_language`, `stt_provider`, `stt_model`, `llm_provider`, `tts_provider`, and `tts_voice_id`.

Provider/language/model fields are optional. Omitting them keeps the hosted platform defaults. Set them only when your tenant has the requested provider and language combination enabled.

Before building provider/model/voice pickers in your own product UI, fetch the currently enabled combinations from the backend:

```ts
const capabilities = await agents.getProviderCapabilities();
const urduTtsProviders = Object.keys(capabilities.languages.ur?.tts ?? {});
```

`getProviderCapabilities()` returns only currently enabled combinations. If a provider is absent for a language/layer, treat it as unavailable and do not offer it in the UI. For provider-validation failures, `AwaazLabsUvaAgentsError` includes a stable `code` for cases such as `unsupported_provider_for_language`, `provider_not_enabled`, `unsupported_model_for_provider`, and `unsupported_voice_for_provider`.

The agents SDK also exposes number-assignment helper methods when you want to keep simple agent-to-number binding in the same backend integration layer:

```ts
const managed = await agents.listManagedNumbers({ assignedAgentId: agent.id });
await agents.assignAgentToNumber('<MANAGED_NUMBER_ID>', agent.id);
await agents.unassignAgentFromNumber('<MANAGED_NUMBER_ID>');
```
## 6. Browser voice sessions

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voice = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.PUBLIC_UVA_PUBLISHABLE_KEY,
  sessionEndpoint: import.meta.env.PUBLIC_UVA_SESSION_ENDPOINT,
  refreshEndpoint: import.meta.env.PUBLIC_UVA_REFRESH_ENDPOINT,
});

voice.on('connected', () => {
  console.log('voice session connected');
});

voice.on('transcript', (event) => {
  console.log(event.final ? 'final' : 'partial', event.text);
});

voice.on('audio_blocked', async (blocked) => {
  if (blocked) {
    // Show a user-initiated button in your UI, then call voice.startAudio().
  }
});

await voice.connect({ agentId: '<AGENT_ID>', voiceId: 'voice_id_from_catalog' });
```

Your session endpoint must return JSON containing `token`, `wsUrl`, and `roomName`. If token refresh is supported, include `refreshUrl` and `expiresIn` or configure `refreshEndpoint`.

Treat the session endpoint as the source of truth for the final session payload. `agentId` is required for browser connect. `voiceId` is an optional compatibility field in the browser API shape and should not replace backend session-side agent/session selection logic.

## 7. Telephony setup

All telephony calls below must run from backend code.

```ts
import {
  AwaazLabsUvaTelephonyError,
  TelephonyClient,
} from '@awaazlabs-uva/telephony';

const telephony = new TelephonyClient({
  baseUrl: process.env.UVA_TELEPHONY_API_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});

try {
  const connection = await telephony.connectTelnyxAccount({
    apiKey: process.env.TELNYX_API_KEY!,
    label: 'primary',
  });

  await telephony.syncTelnyxOwnedNumbers();
  const managedNumbers = await telephony.listManagedPhoneNumbers({ limit: 25 });

  const numberId = '<MANAGED_NUMBER_ID>';
  const agentId = '<AGENT_ID>';

  await telephony.assignAgentToNumber(numberId, agentId);

  await telephony.upsertTelnyxSipConnection({
    sipFqdn: process.env.TELNYX_SIP_FQDN,
    sipUsername: process.env.TELNYX_SIP_USERNAME,
    sipSecret: process.env.TELNYX_SIP_SECRET,
  });
  await telephony.verifyTelnyxSipConnection();

  await telephony.upsertTelnyxOutboundVoiceProfile({
    allowedDestinations: ['US'],
    concurrencyLimit: 2,
  });
  await telephony.verifyTelnyxOutboundVoiceProfile();

  await telephony.configureNumberRouting(numberId);
  await telephony.configureOutboundTrunk();

  const readiness = await telephony.getOutboundReadiness();
  if (readiness.is_ready !== true) {
    console.log('outbound not ready', readiness.reasons);
  }
} catch (error) {
  if (error instanceof AwaazLabsUvaTelephonyError) {
    console.error(error.status, error.code, error.message);
  }
  throw error;
}
```

### Number management methods

```ts
await telephony.getConnectionStatus();
await telephony.reverifyTelnyxAccount();
await telephony.rotateTelnyxAccountKey({ apiKey: '<NEW_TELNYX_API_KEY>' });
await telephony.disconnectTelnyxAccount();
await telephony.listTelnyxOwnedNumbers({ limit: 25 });
await telephony.listManagedPhoneNumbers({ limit: 25 });
await telephony.importTelnyxNumber({ e164Number: '<E164_NUMBER>' });
await telephony.syncTelnyxOwnedNumbers();
await telephony.getTelnyxNumberDrift();
const available = await telephony.searchAvailableNumbers({ country: 'US', areaCode: '<AREA_CODE>' });
console.log(available[0]?.upfront_cost, available[0]?.monthly_cost, available[0]?.currency);
await telephony.reserveNumber({ e164Number: '<E164_NUMBER>', idempotencyKey: '<UNIQUE_KEY>' });
const order = await telephony.purchaseNumber({ e164Number: '<E164_NUMBER>', idempotencyKey: '<UNIQUE_KEY>' });
console.log(order.managed_number_id, order.platform_status);
await telephony.getNumberOrderStatus('<ORDER_ID>');
await telephony.unassignAgentFromNumber('<MANAGED_NUMBER_ID>');
await telephony.disableNumber('<MANAGED_NUMBER_ID>');
```

Only run purchase, disable, and outbound call actions after your product flow has explicit user or operator approval. For real-provider number acquisition, use sync/import for owned numbers or purchase through an approved backend flow.

`searchAvailableNumbers()` returns priced inventory rows including `upfront_cost`, `monthly_cost`, and `currency` when Telnyx provides them. `purchaseNumber()` returns the order status plus `managed_number_id` when the backend can already reconcile the purchased number into managed inventory during that same request.

`reserveNumber()` is part of the SDK contract and can be used only if your hosted platform enables reservation-style flows in your operating model. If your product does not use reservations, you can ignore that method and rely on search plus purchase/import flows instead.

## 8. Inbound telephony flow

1. Connect the tenant Telnyx account from backend code.
2. Sync or import the tenant-owned phone number.
3. Create or select an agent.
4. Assign the managed phone number to the agent with `assignAgentToNumber(numberId, agentId)`.
5. Configure SIP resources if your hosted deployment requires explicit SIP credentials/configuration.
6. Configure routing resources with `configureNumberRouting(numberId)`.
7. The provider routes inbound calls to the configured SIP infrastructure, which dispatches the call to the assigned agent.

Your browser app does not need Telnyx, LiveKit, or HMAC secrets for inbound calls.

## 9. Outbound telephony flow

Check readiness first:

```ts
const readiness = await telephony.getOutboundReadiness();
if (readiness.is_ready !== true) {
  throw new Error(`Outbound is not ready: ${JSON.stringify(readiness.reasons ?? [])}`);
}
```

Create one outbound call per user-approved action. Use a unique idempotency key for each intended call:

```ts
const call = await telephony.createOutboundCall({
  agentId: '<AGENT_ID>',
  fromNumberId: '<MANAGED_NUMBER_ID>',
  toNumber: process.env.OUTBOUND_TO_NUMBER!,
  recipient: 'Customer',
  context: { source: 'crm' },
  idempotencyKey: crypto.randomUUID(),
});

const latest = await telephony.getCallStatus(call.telephony_call_id);
const recentCalls = await telephony.listCallRecords({ limit: 25 });
```

`toNumber` must be an E.164 phone number. Do not retry call creation automatically with a new idempotency key after a timeout; first check call status or list call records.

## 10. Error handling

Agents errors use `AwaazLabsUvaAgentsError` with `status`, `message`, and (for 422 provider/language/model/voice validation failures only) a stable `code` — e.g. `unsupported_provider_for_language`, `provider_not_enabled`, `unsupported_model_for_provider`, `unsupported_voice_for_provider`. Other failures (auth, suspended tenants, missing agents, rate limits) leave `code` undefined.

Voice errors use `AwaazLabsUvaVoiceError` with one of:

| Code | Meaning |
| --- | --- |
| `quota_exceeded` | Tenant/session quota was exceeded. |
| `agent_not_found` | The requested agent ID is not available. |
| `session_failed` | Session creation, refresh, media, or connection setup failed. |

Telephony errors use `AwaazLabsUvaTelephonyError` with `status`, `code`, `message`, and optional `detail`. Common codes include:

| Code | Typical action |
| --- | --- |
| `telephony_auth_failed` | Check backend tenant ID, HMAC secret, clock skew, and signed request construction. |
| `telnyx_connection_missing` | Connect the tenant Telnyx account first. |
| `provider_credentials_missing` | Provider credentials are not configured for the requested operation. |
| `telnyx_key_invalid` | Rotate or replace the Telnyx API key. |
| `number_not_found` | Refresh/sync numbers and verify the managed number ID. |
| `number_not_owned_by_tenant` | Do not use cross-tenant number IDs. |
| `number_not_assigned` | Assign the number to an agent before routing/calling. |
| `outbound_not_ready` | Complete connection, number, SIP, routing, and provider readiness steps. |
| `regulatory_action_required` | Complete provider regulatory requirements before continuing. |
| `duplicate_idempotency_key` | Reuse the original response or generate a key only for a new intended action. |
| `telephony_request_failed` | Inspect the status/message and retry only when the operation is safe to retry. |

## 11. Security rules

- Keep `UVA_HMAC_SECRET`, Telnyx API keys, SIP secrets, and provider credentials on the backend only.
- Do not log raw secrets, HMAC signatures, SIP passwords, provider payloads, or full webhook bodies.
- Do not expose backend-only SDKs through a frontend bundle.
- Use HTTPS for every API endpoint.
- Use one idempotency key per intended purchase or outbound call action.
- Validate E.164 phone numbers before sending outbound call requests.
- Keep provider webhook verification enabled in hosted environments.

## 12. Client configuration responsibilities

Before enabling telephony workflows, the client must provide or confirm:

- Tenant API base URL, tenant ID, and HMAC secret for backend services.
- Frontend publishable key and backend voice session endpoints.
- Telnyx API key with the required account permissions.
- Phone number ownership or approved number purchase/import flow.
- Agent IDs to assign to phone numbers.
- SIP/routing configuration values required by the hosted backend.
- Approved outbound destinations, spending/concurrency limits, and operational consent for outbound calls.

## 13. Delivered SDK Surface Summary

The client submission includes these practical capabilities:

- Browser voice session connect/disconnect, transcript events, speaking events, metrics events, autoplay-unlock handling, and voice-catalog fetching.
- Agent CRUD for hosted voice agents, plus provider-capability discovery for multi-provider setups.
- Telnyx connection lifecycle: connect, rotate, reverify, disconnect, and status checks.
- Number inventory management: list owned numbers, list managed numbers, import, sync, drift inspection, search available numbers, reserve, purchase, order-status lookup, disable.
- Agent-number operations: assign and unassign numbers.
- Telephony infrastructure operations: SIP connection upsert/verify, outbound voice profile upsert/verify, inbound routing configuration, outbound trunk configuration, and outbound readiness checks.
- Live outbound call operations: create outbound call, get call status, and list recent call records.
