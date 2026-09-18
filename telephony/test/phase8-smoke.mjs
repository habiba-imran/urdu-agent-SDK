import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';

import {
  AwaazLabsUvaTelephonyError,
  TELEPHONY_MACHINE_OPERATIONS,
  TelephonyClient,
  canonicalJson,
  createPayloadHash,
  createRequestSignature,
  createSignedHeaders,
} from '../dist/index.js';

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

function expectedSignature({ tenantId, timestamp, nonce, action, payloadHash, secret }) {
  return createHmac('sha256', secret)
    .update(`${tenantId}.${timestamp}.${nonce}.${action}.${payloadHash}`)
    .digest('hex');
}

async function testSigningAndCanonicalJson() {
  const body = { z: 1, a: { b: true, a: 'x' }, omitted: undefined };
  const canonicalBody = canonicalJson(body);
  const payloadHash = createPayloadHash(body);
  const signature = createRequestSignature({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    timestamp: '1700000000',
    nonce: 'nonce-id',
    action: 'telephony.number_orders.create',
    body,
  });

  assert.equal(canonicalBody, '{"a":{"a":"x","b":true},"z":1}');
  assert.equal(
    signature,
    expectedSignature({
      tenantId: 'tenant-id',
      timestamp: '1700000000',
      nonce: 'nonce-id',
      action: 'telephony.number_orders.create',
      payloadHash,
      secret: 'tenant-secret',
    }),
  );

  const signed = createSignedHeaders({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    timestamp: '1700000000',
    nonce: 'nonce-id',
    action: 'telephony.number_orders.create',
    body,
  });
  assert.equal(signed.headers['X-Tenant-Id'], 'tenant-id');
  assert.equal(signed.headers['X-Timestamp'], '1700000000');
  assert.equal(signed.headers['X-Nonce'], 'nonce-id');
  assert.equal(signed.payloadHash, payloadHash);
}

async function testFixedOperationsStayMachineScoped() {
  assert.equal(Object.keys(TELEPHONY_MACHINE_OPERATIONS).length, 29);
  assert.equal(
    TELEPHONY_MACHINE_OPERATIONS.createOutboundCall.action,
    'telephony.outbound_calls.create',
  );
  // Every operation must stay on the HMAC-signed /machine/ surface — never a portal
  // (browser-session-authenticated) route. Telephony operations live under
  // /machine/telephony/; getSessionByRoom is the one deliberate exception, a session
  // lookup on /machine/sessions/get (tenant_portal_api/app.py) used to correlate a call
  // with its voice session.
  for (const [name, operation] of Object.entries(TELEPHONY_MACHINE_OPERATIONS)) {
    assert.equal(operation.path.startsWith('/machine/'), true, `${name} is not machine-scoped`);
    if (name !== 'getSessionByRoom') {
      assert.equal(
        operation.path.startsWith('/machine/telephony/'),
        true,
        `${name} is not telephony-scoped`,
      );
    }
  }
  assert.equal(TELEPHONY_MACHINE_OPERATIONS.getSessionByRoom.path, '/machine/sessions/get');
  assert.equal(TELEPHONY_MACHINE_OPERATIONS.getSessionByRoom.action, 'session.get');
}

async function testSnakeCaseBodiesAndHeaderProtection() {
  const seen = [];
  const client = new TelephonyClient({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    baseUrl: 'https://api.example.test/',
    extraHeaders: {
      'X-Tenant-Id': 'bad-tenant',
      'X-Signature': 'bad-signature',
      'Content-Type': 'text/plain',
      'X-Client-Version': 'phase8',
    },
    nowSeconds: () => 1700000000,
    nonceFactory: () => 'nonce-id',
    fetch: async (url, init) => {
      seen.push({ url, init });
      return jsonResponse({ id: 'order-id', platform_status: 'pending' });
    },
  });

  await client.purchaseNumber({
    e164Number: '<E164_NUMBER>',
    externalCustomerRef: '<OPAQUE_CUSTOMER_REF>',
    idempotencyKey: '<IDEMPOTENCY_KEY>',
  });

  assert.equal(seen[0].url, 'https://api.example.test/machine/telephony/number-orders');
  assert.equal(seen[0].init.headers['X-Tenant-Id'], 'tenant-id');
  assert.notEqual(seen[0].init.headers['X-Signature'], 'bad-signature');
  assert.equal(seen[0].init.headers['Content-Type'], 'application/json');
  assert.equal(seen[0].init.headers['X-Client-Version'], 'phase8');
  assert.deepEqual(JSON.parse(seen[0].init.body), {
    e164_number: '<E164_NUMBER>',
    external_customer_ref: '<OPAQUE_CUSTOMER_REF>',
    idempotency_key: '<IDEMPOTENCY_KEY>',
  });
}

async function testTelnyxKeyIsNotRetained() {
  const client = new TelephonyClient({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    baseUrl: 'https://api.example.test',
    nowSeconds: () => 1700000000,
    nonceFactory: () => 'nonce-id',
    fetch: async () => jsonResponse({ id: 'connection-id', tenant_id: 'tenant-id', platform_status: 'active' }),
  });
  const apiKey = '<REDACTED_TELNYX_API_KEY>';

  await client.connectTelnyxAccount({ apiKey });

  assert.equal(JSON.stringify(client).includes(apiKey), false);
  assert.equal(JSON.stringify(client).includes('tenant-secret'), false);
}

async function testRestrictedResponseFieldsAreDropped() {
  const client = new TelephonyClient({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    baseUrl: 'https://api.example.test',
    nowSeconds: () => 1700000000,
    nonceFactory: () => 'nonce-id',
    fetch: async () =>
      jsonResponse({
        id: 'number-id',
        platform_status: 'active',
        provider_error_payload: { provider: 'diagnostic' },
        nested: { raw_provider_status: 'hidden', safe: true },
      }),
  });

  const result = await client.disableNumber('number-id');

  assert.deepEqual(result, {
    id: 'number-id',
    platform_status: 'active',
    nested: { safe: true },
  });
}

async function testArrayResponsesAreAcceptedAndSanitized() {
  const client = new TelephonyClient({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    baseUrl: 'https://api.example.test',
    nowSeconds: () => 1700000000,
    nonceFactory: () => 'nonce-id',
    fetch: async () =>
      jsonResponse([
        { id: 'number-id', e164_number: '<E164_NUMBER>', provider_error_payload: { diagnostic: true } },
        { id: 'number-id-2', nested: { payload: { hidden: true }, safe: true } },
      ]),
  });

  const result = await client.listManagedPhoneNumbers({ limit: 5 });

  assert.deepEqual(result, [
    { id: 'number-id', e164_number: '<E164_NUMBER>' },
    { id: 'number-id-2', nested: { safe: true } },
  ]);
}
async function testErrorMappingRedactsDetails() {
  const client = new TelephonyClient({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    baseUrl: 'https://api.example.test',
    nowSeconds: () => 1700000000,
    nonceFactory: () => 'nonce-id',
    fetch: async () =>
      jsonResponse(
        {
          error: {
            code: 'idempotency_payload_mismatch',
            message: 'Signature 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef failed.',
            status: 409,
            detail: { api_key: 'hidden', safe_field: 'kept' },
          },
        },
        409,
      ),
  });

  await assert.rejects(
    () => client.purchaseNumber({ e164Number: '<E164_NUMBER>', idempotencyKey: '<IDEMPOTENCY_KEY>' }),
    (error) => {
      assert.equal(error instanceof AwaazLabsUvaTelephonyError, true);
      assert.equal(error.status, 409);
      assert.equal(error.code, 'idempotency_payload_mismatch');
      assert.equal(error.message.includes('0123456789abcdef'), false);
      assert.deepEqual(error.detail, { api_key: '[REDACTED]', safe_field: 'kept' });
      return true;
    },
  );
}

async function testSessionLookupReachesTheServer() {
  // Regression: fillPath required a /machine/telephony/ prefix, so this operation
  // (/machine/sessions/get) threw telephony_invalid_response before sending anything.
  const seen = [];
  const client = new TelephonyClient({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    baseUrl: 'https://api.example.test',
    fetch: async (url, init) => {
      seen.push({ url, init });
      return jsonResponse({ id: 'session-id', room_name: 'room-1' });
    },
  });

  const session = await client.getSessionByRoom('room-1');
  assert.equal(seen[0].url, 'https://api.example.test/machine/sessions/get');
  assert.deepEqual(JSON.parse(seen[0].init.body), { room_name: 'room-1' });
  assert.equal(session.id, 'session-id');
}

async function testPathParamsCannotEscapeTheMachineSurface() {
  const seen = [];
  const client = new TelephonyClient({
    tenantId: 'tenant-id',
    tenantSecret: 'tenant-secret',
    baseUrl: 'https://api.example.test',
    fetch: async (url, init) => {
      seen.push({ url, init });
      return jsonResponse({ id: 'number-id' });
    },
  });

  await client.disableNumber('../../portal/credentials/secret');
  assert.equal(seen[0].url.startsWith('https://api.example.test/machine/telephony/numbers/'), true);
  assert.equal(seen[0].url.includes('/portal/'), false);
}

await testSigningAndCanonicalJson();
await testFixedOperationsStayMachineScoped();
await testSessionLookupReachesTheServer();
await testPathParamsCannotEscapeTheMachineSurface();
await testSnakeCaseBodiesAndHeaderProtection();
await testTelnyxKeyIsNotRetained();
await testRestrictedResponseFieldsAreDropped();
await testArrayResponsesAreAcceptedAndSanitized();
await testErrorMappingRedactsDetails();

console.log('telephony phase8 smoke passed');
