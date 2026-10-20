import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createApp } from '../src/createApp.js';

async function listen(t, server) {
  server = server.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return `http://127.0.0.1:${server.address().port}`;
}

async function host(t, { ready = false, failure = false, staysUnready = false } = {}) {
  const calls = [];
  let number = { id: 'number-1', e164_number: '+15551234567', assigned_agent_id: 'agent-1', routing_status: ready ? 'ready' : 'not_configured' };
  const portal = await listen(t, createServer(async (req, res) => {
    calls.push(req.url);
    assert.equal(req.headers['x-signature-version'], 'raw-body-v1');
    for await (const _ of req) { /* consume body */ }
    res.setHeader('Content-Type', 'application/json');
    if (req.url.endsWith('/assignment')) {
      if (failure) {
        res.statusCode = 502;
        res.end(JSON.stringify({ error: { code: 'livekit_sip_dispatch_rule_failed', message: 'Failed to create or configure LiveKit SIP dispatch rule.', status: 502 } }));
        return;
      }
      if (!staysUnready) number = { ...number, routing_status: 'ready' };
    }
    res.end(JSON.stringify(req.url.endsWith('/list') ? [number] : number));
  }));
  const base = await listen(t, createApp({ allowedOrigins: [], telephonyApiUrl: portal, tenantId: 'fixture', hmacSecret: 'fixture-secret' }));
  return { base, calls };
}

const post = (base, path, body) => fetch(`${base}/api/telephony/${path}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

test('assignment uses the SDK auto-routing once without a duplicate configure call', async t => {
  const { base, calls } = await host(t);
  const response = await post(base, 'assign', { numberId: 'number-1', agentId: 'agent-1' });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).routing.routing_status, 'ready');
  assert.equal(calls.filter(path => path.endsWith('/assignment')).length, 1);
  assert.equal(calls.filter(path => path.includes('/routing/')).length, 0);
});

test('an already routed assignment skips provider mutations', async t => {
  const { base, calls } = await host(t, { ready: true });
  assert.equal((await post(base, 'assign', { numberId: 'number-1', agentId: 'agent-1' })).status, 200);
  assert.deepEqual(calls, ['/machine/telephony/numbers/get']);
});

test('routing failure returns a failure and the verified persisted assignment state', async t => {
  const { base } = await host(t, { failure: true });
  const response = await post(base, 'assign', { numberId: 'number-1', agentId: 'agent-1' });
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), {
    error: 'livekit_sip_dispatch_rule_failed', message: 'Failed to create or configure LiveKit SIP dispatch rule.',
    assignmentSaved: true, routingStatus: 'not_configured',
  });
});

test('a successful SDK response without ready routing is not reported as ready', async t => {
  const { base } = await host(t, { staysUnready: true });
  const response = await post(base, 'assign', { numberId: 'number-1', agentId: 'agent-1' });
  assert.equal(response.status, 409);
  assert.equal((await response.json()).routingStatus, 'not_configured');
});

test('importing an already managed number returns the existing record without insertion', async t => {
  const { base, calls } = await host(t);
  const response = await post(base, 'import', { e164Number: '+15551234567' });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).alreadyManaged, true);
  assert.deepEqual(calls, ['/machine/telephony/numbers/list']);
});
