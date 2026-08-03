# @awaazlabs-uva/telephony

Backend-only TypeScript SDK for AwaazLabs UVA telephony management.

Use this package from your backend to connect Telnyx, sync/import numbers, assign numbers to agents, configure routing, check outbound readiness, and start outbound calls through signed machine API requests.

## Install

```bash
npm install ./client-submission_v2/sdk/@awaazlabs-uva/telephony/awaazlabs-uva-telephony-0.1.0.tgz
```

## Runtime

```bash
UVA_TELEPHONY_API_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_TENANT_ID=<TENANT_UUID>
UVA_HMAC_SECRET=<TENANT_HMAC_SECRET>
TELNYX_API_KEY=<TELNYX_API_KEY>
```

`UVA_HMAC_SECRET`, Telnyx API keys, SIP secrets, and provider credentials must stay on the backend only.

## Usage

```ts
import {
  AwaazLabsUvaTelephonyError,
  TelephonyClient,
} from '@awaazlabs-uva/telephony';

const client = new TelephonyClient({
  baseUrl: process.env.UVA_TELEPHONY_API_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});

try {
  const connection = await client.getConnectionStatus();

  if (connection.platform_status !== 'active') {
    await client.connectTelnyxAccount({
      apiKey: process.env.TELNYX_API_KEY!,
      label: 'primary',
    });
  }

  await client.syncTelnyxOwnedNumbers();
  const managedNumbers = await client.listManagedPhoneNumbers({ limit: 25 });

  const numberId = '<MANAGED_NUMBER_ID>';
  const agentId = '<AGENT_ID>';

  await client.assignAgentToNumber(numberId, agentId);
  await client.configureNumberRouting(numberId);
  await client.configureOutboundTrunk();

  const readiness = await client.getOutboundReadiness();
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

## Method summary

```ts
new TelephonyClient({ baseUrl, tenantId, tenantSecret, extraHeaders?, fetch?, nowSeconds?, nonceFactory? })

client.connectTelnyxAccount({ apiKey, label? })
client.rotateTelnyxAccountKey({ apiKey })
client.reverifyTelnyxAccount()
client.disconnectTelnyxAccount()
client.getConnectionStatus()

client.listTelnyxOwnedNumbers({ cursor?, limit?, platformStatus?, providerStatus? })
client.listManagedPhoneNumbers({ cursor?, limit?, platformStatus?, providerStatus? })
client.importTelnyxNumber({ e164Number, externalCustomerRef? })
client.syncTelnyxOwnedNumbers()
client.getTelnyxNumberDrift()
client.searchAvailableNumbers({ country, areaCode?, numberType?, features? }) // => AvailableNumber[] with upfront_cost, monthly_cost, currency
client.purchaseNumber({ e164Number, externalCustomerRef?, idempotencyKey }) // => NumberOrderResponse with platform_status and managed_number_id when available immediately
client.getNumberOrderStatus(orderId)
client.disableNumber(numberId)

client.assignAgentToNumber(numberId, agentId)
client.unassignAgentFromNumber(numberId)

client.upsertTelnyxSipConnection({ sipFqdn?, sipUsername?, sipSecret?, providerSipConnectionId? })
client.verifyTelnyxSipConnection()
client.upsertTelnyxOutboundVoiceProfile({ providerOutboundVoiceProfileId?, telnyxSipConnectionId?, allowedDestinations?, concurrencyLimit?, channelLimit?, dailySpendingLimit? })
client.verifyTelnyxOutboundVoiceProfile()
client.configureNumberRouting(numberId)
client.configureOutboundTrunk()
client.getOutboundReadiness()

client.createOutboundCall({ agentId, fromNumberId, toNumber, recipient?, context?, externalCustomerRef?, externalWorkflowRef?, idempotencyKey })
client.getCallStatus(telephonyCallId)
client.listCallRecords({ cursor?, limit?, platformStatus?, providerStatus? })
```

## Inbound setup flow

1. Connect or verify the tenant Telnyx account.
2. Sync/import tenant-owned numbers.
3. Assign the managed number to an agent with `assignAgentToNumber(numberId, agentId)`.
4. Configure number routing with `configureNumberRouting(numberId)`.
5. Confirm provider-side webhook and SIP settings are configured in the hosted backend environment.

## Outbound setup flow

1. Connect or verify the tenant Telnyx account.
2. Sync/import tenant-owned numbers.
3. Configure or verify Telnyx SIP connection and outbound voice profile.
4. Configure the outbound trunk with `configureOutboundTrunk()`.
5. Call `getOutboundReadiness()` and require `is_ready === true` before creating an outbound call.
6. Create a call with a unique `idempotencyKey` only after an approved user/operator action.

## Error handling

```ts
try {
  await client.syncTelnyxOwnedNumbers();
} catch (error) {
  if (error instanceof AwaazLabsUvaTelephonyError) {
    console.error(error.status, error.code, error.message);
  }
  throw error;
}
```

Common error codes include `telephony_auth_failed`, `provider_credentials_missing`, `telnyx_connection_missing`, `telnyx_key_invalid`, `number_not_found`, `number_not_owned_by_tenant`, `number_not_assigned`, `outbound_not_ready`, `regulatory_action_required`, `duplicate_idempotency_key`, and `telephony_request_failed`.

## Number search and purchase behavior

- `searchAvailableNumbers()` returns priced Telnyx inventory rows, including `upfront_cost`, `monthly_cost`, and `currency` when available from the provider.
- `purchaseNumber()` attempts a short post-order reconciliation step so a successful "Buy" action can return `managed_number_id` in the same response when Telnyx has already exposed the purchased number in owned inventory.
- If Telnyx still has the order in a true pending state, the response may still return `platform_status: 'pending'`; in that case check `getNumberOrderStatus(orderId)` instead of creating a second purchase request.

## Security

- Do not import this package in browser code.
- Do not log raw Telnyx API keys, SIP secrets, tenant HMAC secrets, HMAC signatures, provider webhook bodies, or restricted diagnostic payloads.
- Use HTTPS endpoints.
- Use stable idempotency keys for purchase and outbound call operations.
- Validate E.164 phone numbers in your application before requesting outbound calls.
