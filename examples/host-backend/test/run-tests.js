import assert from 'node:assert/strict';
import { createApp } from '../src/createApp.js';
import { createSessionSignature } from '../src/signing.js';

const baseConfig = {
  controlPlaneUrl: 'https://control-plane.example.com',
  tenantId: 'tenant-123',
  hmacSecret: 'secret-abc',
  publishableKey: 'pk-demo',
  allowedOrigins: ['http://localhost:5173'],
  publicBaseUrl: 'http://localhost:3000',
};

function makeJsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function startServer(app) {
  return await new Promise((resolve) => {
    const server = app.listen(0, () => resolve(server));
  });
}

async function testSessionRouteSignsRequests() {
  let seenUrl = '';
  let seenHeaders = {};
  let seenBody = '';
  const app = createApp(baseConfig, async (url, options) => {
    seenUrl = url;
    seenHeaders = options.headers;
    seenBody = options.body;
    return makeJsonResponse({
      token: 'upstream-token',
      wsUrl: 'wss://lk.example.com',
      roomName: 'room-123',
      refreshUrl: '/v1/session/refresh',
      expiresIn: 120,
    });
  });

  const server = await startServer(app);
  const port = server.address().port;
  const response = await fetch(`http://127.0.0.1:${port}/api/voice/session`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Origin: 'http://localhost:5173',
    },
    body: JSON.stringify({ publishableKey: 'pk-demo', agentId: 'agent-123' }),
  });
  const payload = await response.json();
  server.close();

  assert.equal(response.status, 200);
  assert.equal(seenUrl, 'https://control-plane.example.com/v1/session');
  assert.deepEqual(JSON.parse(seenBody), { agent_id: 'agent-123' });
  assert.equal(seenHeaders['X-Tenant-Id'], 'tenant-123');
  assert.equal(seenHeaders.Origin, 'http://localhost:5173');
  assert.equal(
    seenHeaders['X-Signature'],
    createSessionSignature({
      tenantId: 'tenant-123',
      timestamp: seenHeaders['X-Timestamp'],
      nonce: seenHeaders['X-Nonce'],
      agentId: 'agent-123',
      secret: 'secret-abc',
    }),
  );
  assert.equal(payload.refreshUrl, 'http://localhost:3000/api/voice/session/refresh');
}

async function testQuotaMapping() {
  const app = createApp(baseConfig, async () =>
    makeJsonResponse({ error: 'concurrent cap reached' }, 429),
  );

  const server = await startServer(app);
  const port = server.address().port;
  const response = await fetch(`http://127.0.0.1:${port}/api/voice/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ publishableKey: 'pk-demo', agentId: 'agent-123' }),
  });
  const payload = await response.json();
  server.close();

  assert.equal(response.status, 429);
  assert.deepEqual(payload, { error: 'quota_exceeded' });
}

async function testRefreshForwarding() {
  let seenHeaders = {};
  const app = createApp(baseConfig, async (_url, options) => {
    seenHeaders = options.headers;
    return makeJsonResponse({
      token: 'refreshed-token',
      wsUrl: 'wss://lk.example.com',
      roomName: 'room-123',
      refreshUrl: '/v1/session/refresh',
      expiresIn: 120,
    });
  });

  const server = await startServer(app);
  const port = server.address().port;
  const response = await fetch(`http://127.0.0.1:${port}/api/voice/session/refresh`, {
    method: 'POST',
    headers: { Authorization: 'Bearer old-token' },
  });
  const payload = await response.json();
  server.close();

  assert.equal(response.status, 200);
  assert.equal(seenHeaders.Authorization, 'Bearer old-token');
  assert.equal(payload.refreshUrl, 'http://localhost:3000/api/voice/session/refresh');
}

async function main() {
  await testSessionRouteSignsRequests();
  await testQuotaMapping();
  await testRefreshForwarding();
  console.log('host-backend-node tests passed');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
