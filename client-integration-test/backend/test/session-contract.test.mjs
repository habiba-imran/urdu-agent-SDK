import test from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/createApp.js';
const config = {
  controlPlaneUrl: 'https://control-plane.invalid', portalApiUrl: '', telephonyApiUrl: '',
  tenantId: 'test-tenant', hmacSecret: 'test-only-secret', publishableKey: 'test-public-key',
  allowedOrigins: ['http://localhost:5174'], publicBaseUrl: 'http://localhost:3100',
};
async function host(t, upstream) {
  const server = createApp(config, upstream).listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return `http://127.0.0.1:${server.address().port}`;
}
const minted = { token: 'test-room-token', wsUrl: 'wss://room.invalid', roomName: 'test-room', expiresIn: 120 };
const post = (body, headers = {}) => ({ method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'http://localhost:5174', ...headers }, body: JSON.stringify(body) });
test('mint preserves public contract and keeps humanization controls platform-owned', async t => {
  let calls = 0;
  const url = await host(t, async (url, init) => {
    calls++;
    assert.equal(url, `${config.controlPlaneUrl}/v1/session`);
    assert.deepEqual(JSON.parse(init.body), { agent_id: 'test-agent' });
    return Response.json(minted);
  });
  const response = await fetch(`${url}/api/voice/session`, post({ publishableKey: config.publishableKey, agentId: 'test-agent', humanizationPolicy: 'natural_v1', UVA_OPENING_POLICY: 'opening_v1' }));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('access-control-allow-origin'), 'http://localhost:5174');
  const result = await response.json();
  assert.equal(result.token, minted.token);
  assert.equal(result.refreshUrl, 'http://localhost:3100/api/voice/session/refresh');
  assert.ok(!JSON.stringify(result).includes(config.hmacSecret));
  assert.equal(calls, 1);
});
test('invalid publishable key never reaches platform', async t => {
  const url = await host(t, async () => { assert.fail('upstream called'); });
  const response = await fetch(`${url}/api/voice/session`, post({ publishableKey: 'wrong', agentId: 'test-agent' }));
  assert.equal(response.status, 401);
});
test('refresh forwards bearer without tenant secrets in browser response', async t => {
  const url = await host(t, async (url, init) => {
    assert.equal(url, `${config.controlPlaneUrl}/v1/session/refresh`);
    assert.equal(init.headers.Authorization, 'Bearer old-test-token');
    return Response.json({ ...minted, token: 'new-test-token' });
  });
  const response = await fetch(`${url}/api/voice/session/refresh`, post({}, { Authorization: 'Bearer old-test-token' }));
  assert.equal(response.status, 200);
  assert.equal((await response.json()).token, 'new-test-token');
});
for (const [status, detail, expectedStatus, expectedError] of [
  [429, 'rate_limit', 429, 'rate_limit'], [503, 'worker_not_ready', 503, 'worker_not_ready'],
  [404, 'agent_not_found', 404, 'agent_not_found'], [500, 'internal failure', 502, 'session_failed'],
]) {
  test(`mint propagates ${detail} safely`, async t => {
    const url = await host(t, async () => Response.json({ detail }, { status }));
    const response = await fetch(`${url}/api/voice/session`, post({ publishableKey: config.publishableKey, agentId: 'test-agent' }));
    assert.equal(response.status, expectedStatus);
    assert.equal((await response.json()).error, expectedError);
  });
}
