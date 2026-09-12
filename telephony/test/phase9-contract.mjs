import assert from 'node:assert/strict';
import { createHash, createHmac } from 'node:crypto';

import {
  AwaazLabsUvaTelephonyError,
  TELEPHONY_MACHINE_OPERATIONS,
  TelephonyClient,
  canonicalJson,
} from '../dist/index.js';

const tenantId = 'tenant-contract-id';
const tenantSecret = 'contract-test-hmac-value';
const timestamp = '1700000000';
const nonce = 'nonce-contract-id';
const baseUrl = 'https://api.example.test';
const numberId = 'number/id contract';
const encodedNumberId = encodeURIComponent(numberId);
const agentId = 'agent-contract-id';
const orderId = 'order-contract-id';
const callId = 'call-contract-id';
const telnyxApiKey = '<REDACTED_TELNYX_API_KEY>';
const fakeApiLikeToken = ['sk', 'FAKE_CONTRACT_PLACEHOLDER'].join('_');
const e164Number = '<E164_NUMBER>';

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status >= 200 && status < 300 ? 'OK' : 'Error',
    async text() {
      return JSON.stringify(body);
    },
  };
}

function expectedSignature(action, body) {
  const payloadHash = createHash('sha256').update(canonicalJson(body)).digest('hex');
  return createHmac('sha256', tenantSecret)
    .update(`${tenantId}.${timestamp}.${nonce}.${action}.${payloadHash}`)
    .digest('hex');
}

function createCapturedClient(responseBody = { ok: true }) {
  const seen = [];
  const client = new TelephonyClient({
    tenantId,
    tenantSecret,
    baseUrl: `${baseUrl}/`,
    extraHeaders: {
      'X-Tenant-Id': 'blocked-tenant',
      'X-Timestamp': '1',
      'X-Nonce': 'blocked-nonce',
      'X-Signature': 'blocked-signature',
      'Content-Type': 'text/plain',
      'X-Contract-Test': 'phase9',
    },
    nowSeconds: () => Number(timestamp),
    nonceFactory: () => nonce,
    fetch: async (url, init) => {
      seen.push({ url, init });
      return jsonResponse(responseBody);
    },
  });
  return { client, seen };
}

const routeCases = [
  ['connectTelnyxAccount', 'POST', '/machine/telephony/telnyx/connect', 'telephony.telnyx_connection.connect', (c) => c.connectTelnyxAccount({ apiKey: telnyxApiKey, label: 'contract' }), { api_key: telnyxApiKey, label: 'contract' }],
  ['rotateTelnyxAccountKey', 'POST', '/machine/telephony/telnyx/rotate', 'telephony.telnyx_connection.rotate', (c) => c.rotateTelnyxAccountKey({ apiKey: telnyxApiKey }), { api_key: telnyxApiKey }],
  ['reverifyTelnyxAccount', 'POST', '/machine/telephony/telnyx/reverify', 'telephony.telnyx_connection.reverify', (c) => c.reverifyTelnyxAccount(), {}],
  ['disconnectTelnyxAccount', 'DELETE', '/machine/telephony/telnyx/connection', 'telephony.telnyx_connection.disconnect', (c) => c.disconnectTelnyxAccount(), {}],
  ['getConnectionStatus', 'GET', '/machine/telephony/telnyx/connection', 'telephony.telnyx_connection.status', (c) => c.getConnectionStatus(), {}],
  ['listTelnyxOwnedNumbers', 'POST', '/machine/telephony/telnyx/owned-numbers/list', 'telephony.telnyx_owned_numbers.list', (c) => c.listTelnyxOwnedNumbers({ platformStatus: 'active', limit: 5 }), { limit: 5, platform_status: 'active' }],
  ['listManagedPhoneNumbers', 'POST', '/machine/telephony/numbers/list', 'telephony.managed_numbers.list', (c) => c.listManagedPhoneNumbers({ providerStatus: 'verified', cursor: 'cursor-contract' }), { cursor: 'cursor-contract', provider_status: 'verified' }],
  ['getManagedPhoneNumber', 'POST', '/machine/telephony/numbers/get', 'telephony.managed_numbers.get', (c) => c.getManagedPhoneNumber(numberId), { number_id: numberId }],
  ['importTelnyxNumber', 'POST', '/machine/telephony/numbers/import', 'telephony.managed_numbers.import', (c) => c.importTelnyxNumber({ e164Number, externalCustomerRef: '<OPAQUE_CUSTOMER_REF>' }), { e164_number: e164Number, external_customer_ref: '<OPAQUE_CUSTOMER_REF>' }],
  ['syncTelnyxOwnedNumbers', 'POST', '/machine/telephony/numbers/sync', 'telephony.managed_numbers.sync', (c) => c.syncTelnyxOwnedNumbers(), {}],
  ['getTelnyxNumberDrift', 'POST', '/machine/telephony/numbers/drift', 'telephony.managed_numbers.drift', (c) => c.getTelnyxNumberDrift(), {}],
  ['searchAvailableNumbers', 'POST', '/machine/telephony/available-numbers/search', 'telephony.available_numbers.search', (c) => c.searchAvailableNumbers({ country: 'US', areaCode: '555', numberType: 'local', features: ['voice'] }), { area_code: '555', country: 'US', features: ['voice'], number_type: 'local' }],
  ['reserveNumber', 'POST', '/machine/telephony/number-reservations', 'telephony.number_reservations.create', (c) => c.reserveNumber({ e164Number, idempotencyKey: '<IDEMPOTENCY_KEY>' }), { e164_number: e164Number, idempotency_key: '<IDEMPOTENCY_KEY>' }],
  ['purchaseNumber', 'POST', '/machine/telephony/number-orders', 'telephony.number_orders.create', (c) => c.purchaseNumber({ e164Number, externalCustomerRef: '<OPAQUE_CUSTOMER_REF>', idempotencyKey: '<IDEMPOTENCY_KEY>' }), { e164_number: e164Number, external_customer_ref: '<OPAQUE_CUSTOMER_REF>', idempotency_key: '<IDEMPOTENCY_KEY>' }],
  ['getNumberOrderStatus', 'POST', '/machine/telephony/number-orders/get', 'telephony.number_orders.get', (c) => c.getNumberOrderStatus(orderId), { order_id: orderId }],
  ['assignAgentToNumber', 'PATCH', `/machine/telephony/numbers/${encodedNumberId}/assignment`, 'telephony.numbers.assign_agent', (c) => c.assignAgentToNumber(numberId, agentId), { agent_id: agentId, number_id: numberId }],
  ['unassignAgentFromNumber', 'PATCH', `/machine/telephony/numbers/${encodedNumberId}/assignment`, 'telephony.numbers.assign_agent', (c) => c.unassignAgentFromNumber(numberId), { agent_id: null, number_id: numberId }],
  ['upsertTelnyxSipConnection', 'POST', '/machine/telephony/telnyx/sip-connection', 'telephony.telnyx_sip_connection.upsert', (c) => c.upsertTelnyxSipConnection({ sipFqdn: 'sip.example.test', sipUsername: 'tenant-user', sipSecret: '<REDACTED_SIP_SECRET>', providerSipConnectionId: 'sip-provider-id' }), { provider_sip_connection_id: 'sip-provider-id', sip_fqdn: 'sip.example.test', sip_secret: '<REDACTED_SIP_SECRET>', sip_username: 'tenant-user' }],
  ['verifyTelnyxSipConnection', 'POST', '/machine/telephony/telnyx/sip-connection/test', 'telephony.telnyx_sip_connection.test', (c) => c.verifyTelnyxSipConnection(), {}],
  ['upsertTelnyxOutboundVoiceProfile', 'POST', '/machine/telephony/telnyx/outbound-voice-profile', 'telephony.telnyx_outbound_voice_profile.upsert', (c) => c.upsertTelnyxOutboundVoiceProfile({ providerOutboundVoiceProfileId: 'ovp-provider-id', telnyxSipConnectionId: 'sip-record-id', allowedDestinations: ['US'], concurrencyLimit: 2, channelLimit: 3, dailySpendingLimit: 10 }), { allowed_destinations: ['US'], channel_limit: 3, concurrency_limit: 2, daily_spending_limit: 10, provider_outbound_voice_profile_id: 'ovp-provider-id', telnyx_sip_connection_id: 'sip-record-id' }],
  ['verifyTelnyxOutboundVoiceProfile', 'POST', '/machine/telephony/telnyx/outbound-voice-profile/reverify', 'telephony.telnyx_outbound_voice_profile.reverify', (c) => c.verifyTelnyxOutboundVoiceProfile(), {}],
  ['configureNumberRouting', 'POST', `/machine/telephony/numbers/${encodedNumberId}/routing/configure`, 'telephony.number_routing.configure', (c) => c.configureNumberRouting(numberId), { number_id: numberId }],
  ['configureOutboundTrunk', 'POST', '/machine/telephony/telnyx/outbound-trunk/configure', 'telephony.outbound_trunk.configure', (c) => c.configureOutboundTrunk(), {}],
  ['getOutboundReadiness', 'GET', '/machine/telephony/outbound-readiness', 'telephony.outbound_readiness.get', (c) => c.getOutboundReadiness(), {}],
  ['createOutboundCall', 'POST', '/machine/telephony/outbound-calls', 'telephony.outbound_calls.create', (c) => c.createOutboundCall({ agentId, fromNumberId: numberId, toNumber: '<TO_E164_NUMBER>', recipient: 'Contract Recipient', context: { workflowId: '<WORKFLOW_REF>' }, externalCustomerRef: '<OPAQUE_CUSTOMER_REF>', externalWorkflowRef: '<OPAQUE_WORKFLOW_REF>', idempotencyKey: '<IDEMPOTENCY_KEY>' }), { agent_id: agentId, context: { workflow_id: '<WORKFLOW_REF>' }, external_customer_ref: '<OPAQUE_CUSTOMER_REF>', external_workflow_ref: '<OPAQUE_WORKFLOW_REF>', from_number_id: numberId, idempotency_key: '<IDEMPOTENCY_KEY>', recipient: 'Contract Recipient', to_number: '<TO_E164_NUMBER>' }],
  ['getCallStatus', 'POST', '/machine/telephony/calls/get', 'telephony.calls.get', (c) => c.getCallStatus(callId), { telephony_call_id: callId }],
  ['listCallRecords', 'POST', '/machine/telephony/calls/list', 'telephony.calls.list', (c) => c.listCallRecords({ limit: 10, platformStatus: 'completed' }), { limit: 10, platform_status: 'completed' }],
  ['disableNumber', 'POST', `/machine/telephony/numbers/${encodedNumberId}/disable`, 'telephony.numbers.disable', (c) => c.disableNumber(numberId), { number_id: numberId }],
];

function assertSnakeCase(value) {
  if (Array.isArray(value)) {
    value.forEach(assertSnakeCase);
    return;
  }
  if (value === null || typeof value !== 'object') return;
  for (const [key, item] of Object.entries(value)) {
    assert.equal(/[A-Z]/.test(key), false, `${key} is not snake_case`);
    assertSnakeCase(item);
  }
}

async function testAllSdkMethodsMatchFrozenContract() {
  assert.equal(routeCases.length, 28);
  assert.equal(Object.keys(TELEPHONY_MACHINE_OPERATIONS).length, 28);

  for (const [name, method, path, action, call, expectedBody] of routeCases) {
    const { client, seen } = createCapturedClient({ id: `${name}-response`, platform_status: 'ok' });
    await call(client);
    const operation = TELEPHONY_MACHINE_OPERATIONS[name];
    const request = seen[0];

    assert.equal(operation.method, method, name);
    assert.equal(operation.action, action, name);
    assert.equal(operation.path.startsWith('/machine/telephony/'), true, name);
    assert.equal(request.url, `${baseUrl}${path}`, name);
    assert.equal(request.init.method, method, name);
    assert.equal(request.init.headers['X-Tenant-Id'], tenantId, name);
    assert.equal(request.init.headers['X-Timestamp'], timestamp, name);
    assert.equal(request.init.headers['X-Nonce'], nonce, name);
    assert.equal(request.init.headers['X-Signature'], expectedSignature(action, expectedBody), name);
    assert.equal(request.init.headers['Content-Type'], 'application/json', name);
    assert.equal(request.init.headers['X-Contract-Test'], 'phase9', name);

    if (method === 'GET') {
      assert.equal(request.init.body, undefined, name);
    } else {
      assert.deepEqual(JSON.parse(request.init.body), expectedBody, name);
      assert.equal(request.init.body, canonicalJson(expectedBody), name);
    }
    assertSnakeCase(expectedBody);
    assert.equal(JSON.stringify(request.init.headers).includes(tenantSecret), false, name);
  }
}

async function testRestrictedResponseSanitization() {
  const { client } = createCapturedClient({
    id: 'number-contract-id',
    platform_status: 'active',
    provider_error_payload: { diagnostic: true },
    payload: { hidden: true },
    encrypted_api_key_ref: '<SECRET_STORE_REF>',
    nested: { raw_provider_status: 'hidden', safe_field: true },
  });
  const result = await client.disableNumber(numberId);
  assert.deepEqual(result, {
    id: 'number-contract-id',
    platform_status: 'active',
    nested: { safe_field: true },
  });
}

async function testStableErrorMappingAndRedaction() {
  const cases = [
    ['telnyx_connection_missing', 409],
    ['number_order_action_required', 409],
    ['livekit_outbound_trunk_failed', 502],
    ['telephony_auth_failed', 401],
    ['outbound_not_ready', 409],
    ['idempotency_payload_mismatch', 409],
    ['telnyx_key_permission_failed', 403],
  ];

  for (const [code, status] of cases) {
    const client = new TelephonyClient({
      tenantId,
      tenantSecret,
      baseUrl,
      nowSeconds: () => Number(timestamp),
      nonceFactory: () => nonce,
      fetch: async () => jsonResponse({
        error: {
          code,
          status,
          message: `Failed with ${fakeApiLikeToken} and ${'a'.repeat(64)}`,
          detail: {
            api_key: telnyxApiKey,
            payload: { hidden: true },
            safe_field: code,
          },
        },
      }, status),
    });

    await assert.rejects(
      () => client.getConnectionStatus(),
      (error) => {
        assert.equal(error instanceof AwaazLabsUvaTelephonyError, true, code);
        assert.equal(error.status, status, code);
        assert.equal(error.code, code, code);
        assert.equal(error.message.includes(fakeApiLikeToken), false, code);
        assert.equal(error.message.includes('aaaaaaaa'), false, code);
        assert.deepEqual(error.detail, {
          api_key: '[REDACTED]',
          payload: '[REDACTED]',
          safe_field: code,
        }, code);
        return true;
      },
    );
  }
}

async function testNestedFastApiErrorMappingAndRedaction() {
  const client = new TelephonyClient({
    tenantId,
    tenantSecret,
    baseUrl,
    nowSeconds: () => Number(timestamp),
    nonceFactory: () => nonce,
    fetch: async () => jsonResponse({
      detail: {
        error: {
          code: 'telephony_auth_failed',
          status: 401,
          message: `bad signature ${fakeApiLikeToken}`,
          detail: {
            signature: 'hidden-signature-value',
            safe_field: 'kept',
          },
        },
      },
    }, 401),
  });

  await assert.rejects(
    () => client.getConnectionStatus(),
    (error) => {
      assert.equal(error instanceof AwaazLabsUvaTelephonyError, true);
      assert.equal(error.status, 401);
      assert.equal(error.code, 'telephony_auth_failed');
      assert.equal(error.message.includes(fakeApiLikeToken), false);
      assert.deepEqual(error.detail, {
        safe_field: 'kept',
        signature: '[REDACTED]',
      });
      return true;
    },
  );
}
async function testSecretsAreNotLeakedBeyondRequiredWireFields() {
  for (const [name, , , , call] of routeCases) {
    const { client, seen } = createCapturedClient({ ok: true });
    await call(client);
    const serialized = JSON.stringify(seen[0].init);

    assert.equal(serialized.includes(tenantSecret), false, name);
    if (name !== 'connectTelnyxAccount' && name !== 'rotateTelnyxAccountKey') {
      assert.equal(serialized.includes(telnyxApiKey), false, name);
    }
    assert.equal(JSON.stringify(client).includes(tenantSecret), false, name);
    assert.equal(JSON.stringify(client).includes(telnyxApiKey), false, name);
  }
}

async function testGetAndIdentifierBodiesAreSigned() {
  const names = [
    'getConnectionStatus',
    'getOutboundReadiness',
    'getNumberOrderStatus',
    'assignAgentToNumber',
    'unassignAgentFromNumber',
    'configureNumberRouting',
    'createOutboundCall',
    'getCallStatus',
    'listCallRecords',
    'disableNumber',
  ];

  for (const [name, method, , action, call, expectedBody] of routeCases.filter(([item]) => names.includes(item))) {
    const { client, seen } = createCapturedClient({ ok: true });
    await call(client);
    const requestBody = method === 'GET' ? {} : JSON.parse(seen[0].init.body);
    assert.deepEqual(requestBody, expectedBody, name);
    assert.equal(seen[0].init.headers['X-Signature'], expectedSignature(action, expectedBody), name);
  }
}

await testAllSdkMethodsMatchFrozenContract();
await testRestrictedResponseSanitization();
await testStableErrorMappingAndRedaction();
await testNestedFastApiErrorMappingAndRedaction();
await testSecretsAreNotLeakedBeyondRequiredWireFields();
await testGetAndIdentifierBodiesAreSigned();

console.log('telephony phase9 contract tests passed');
