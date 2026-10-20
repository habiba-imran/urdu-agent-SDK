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

test('status checks connection and readiness concurrently', async t => {
  const waiting = [];
  const portal = await listen(t, createServer((req, res) => {
    waiting.push({ path: req.url, res });
    if (waiting.length !== 2) return;
    for (const entry of waiting) {
      entry.res.setHeader('Content-Type', 'application/json');
      entry.res.end(JSON.stringify(entry.path.endsWith('/connection') ? { platform_status: 'active' } : { is_ready: false }));
    }
  }));
  const base = await listen(t, createApp({ allowedOrigins: [], telephonyApiUrl: portal, tenantId: 'fixture', hmacSecret: 'fixture', telephonyReadTimeoutMs: 300 }));
  const response = await fetch(`${base}/api/telephony/status`);
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.tenantId, 'fixture');
  assert.equal(body.connection.platform_status, 'active');
  assert.equal(body.connectionError, null);
  assert.equal(body.readiness.is_ready, false);
});

test('a hanging status read returns a bounded partial result', async t => {
  const portal = await listen(t, createServer((req, res) => {
    if (req.url.endsWith('/connection')) return; // Simulate a provider that never replies.
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ is_ready: false }));
  }));
  const base = await listen(t, createApp({ allowedOrigins: [], telephonyApiUrl: portal, tenantId: 'fixture', hmacSecret: 'fixture', telephonyReadTimeoutMs: 50 }));
  const response = await fetch(`${base}/api/telephony/status`, { signal: AbortSignal.timeout(2000) });
  const body = await response.json();
  assert.equal(body.connection, null);
  assert.equal(typeof body.connectionError, 'string');
  assert.equal(body.readiness.is_ready, false);
});

test('machine POST list operations use the read deadline too', async t => {
  const portal = await listen(t, createServer((req, res) => {
    if (req.url.endsWith('/numbers/list')) return;
    res.setHeader('Content-Type', 'application/json');
    res.end('[]');
  }));
  const base = await listen(t, createApp({ allowedOrigins: [], telephonyApiUrl: portal, tenantId: 'fixture', hmacSecret: 'fixture', telephonyReadTimeoutMs: 50 }));
  const response = await fetch(`${base}/api/telephony/numbers`, { signal: AbortSignal.timeout(2000) });
  assert.equal(response.ok, false);
  assert.equal((await response.json()).error, 'telephony_request_failed');
});

test('sequential provisioning steps share one total deadline', async t => {
  const portal = await listen(t, createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    if (req.url.endsWith('/sync')) setTimeout(() => res.end('{}'), 20);
    else setTimeout(() => res.end('[]'), 350);
  }));
  const base = await listen(t, createApp({ allowedOrigins: [], telephonyApiUrl: portal, tenantId: 'fixture', hmacSecret: 'fixture', telephonyReadTimeoutMs: 1000, telephonyOperationTimeoutMs: 200 }));
  const response = await post(base, 'sync', {});
  assert.equal(response.ok, false);
  assert.equal((await response.json()).error, 'telephony_request_failed');
});

// A portal that enforces the real dependency chain: the outbound voice profile and the
// outbound trunk both 409 without a SIP connection, and the trunk 409s without an active
// profile. Prepare-outbound used to call the trunk first, so it could never converge.
async function orderedPortal(t, { sipParamsRequired = false } = {}) {
  const seen = [];
  const state = { sip: false, profile: false, trunk: false, link: false };
  const portal = await listen(t, createServer(async (req, res) => {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    const body = raw ? JSON.parse(raw) : {};
    const path = new URL(req.url, 'http://x').pathname;
    seen.push(path.replace('/machine/telephony/', ''));
    res.setHeader('Content-Type', 'application/json');
    const conflict = (code, message) => {
      res.statusCode = 409;
      res.end(JSON.stringify({ error: { code, message, status: 409 } }));
    };

    if (path.endsWith('/telnyx/sip-connection')) {
      if (sipParamsRequired && !body.sip_fqdn && !body.sip_username && !body.sip_secret
          && !body.outbound_voice_profile_provider_id) {
        return conflict('sip_params_required', 'fixture demands explicit SIP params');
      }
      state.sip = true;
      if (body.outbound_voice_profile_provider_id) state.link = true;
      return res.end(JSON.stringify({ id: 'sip-1', platform_status: 'active' }));
    }
    if (path.endsWith('/telnyx/outbound-voice-profile')) {
      if (!state.sip) return conflict('sip_verification_failed', 'Tenant Telnyx SIP connection is required before outbound voice profile setup.');
      state.profile = true;
      return res.end(JSON.stringify({ id: 'ovp-1', provider_outbound_voice_profile_id: 'telnyx-ovp-1', platform_status: 'active' }));
    }
    if (path.endsWith('/telnyx/outbound-trunk/configure')) {
      if (!state.sip) return conflict('sip_verification_failed', 'Tenant Telnyx SIP connection is required before outbound trunk setup.');
      if (!state.profile) return conflict('outbound_voice_profile_missing', 'Tenant outbound voice profile is not configured.');
      state.trunk = true;
      return res.end(JSON.stringify({ outbound_trunk_id: 'trunk-1', platform_status: 'active' }));
    }
    if (path.endsWith('/outbound-readiness')) {
      const isReady = state.sip && state.profile && state.trunk;
      return res.end(JSON.stringify({
        is_ready: isReady,
        sip_status: state.sip ? 'active' : 'not_configured',
        outbound_profile_status: state.profile ? 'active' : 'not_configured',
        reasons: isReady ? [] : ['Tenant Telnyx SIP connection is not active.'],
      }));
    }
    res.statusCode = 404;
    res.end('{}');
  }));
  const base = await listen(t, createApp({
    allowedOrigins: [], telephonyApiUrl: portal, tenantId: 'fixture', hmacSecret: 'fixture-secret',
  }));
  return { base, seen, state };
}

test('prepare-outbound provisions in the order the portal enforces', async t => {
  const { base, seen, state } = await orderedPortal(t);
  const res = await post(base, 'prepare-outbound', {});
  const body = await res.json();

  assert.equal(res.status, 200, `expected readiness, got ${res.status}: ${JSON.stringify(body)}`);
  assert.equal(body.readiness.is_ready, true);
  assert.deepEqual(body.failures, []);
  assert.deepEqual(seen, [
    'telnyx/sip-connection',
    'telnyx/outbound-voice-profile',
    'telnyx/outbound-trunk/configure',
    'outbound-readiness',
  ]);
  // No profile-link round trip: the portal's upsert routes drop
  // outbound_voice_profile_provider_id, so the portal does the attach internally instead.
  assert.equal(state.link, false);
});

test('prepare-outbound creates the SIP connection without TELNYX_SIP_* env vars', async t => {
  const { base, state } = await orderedPortal(t);
  const res = await post(base, 'prepare-outbound', {});
  assert.equal(res.status, 200);
  assert.ok(state.sip, 'SIP must be provisioned from an empty config, not gated on env overrides');
});

test('prepare-outbound reports failure instead of a 200 success envelope', async t => {
  const { base } = await orderedPortal(t, { sipParamsRequired: true });
  const res = await post(base, 'prepare-outbound', {});
  const body = await res.json();

  assert.equal(res.status, 409);
  assert.equal(body.error, 'outbound_not_ready');
  assert.equal(body.readiness.is_ready, false);
  assert.deepEqual(body.failures.map(f => f.step), ['sip']);
  assert.match(body.message, /sip: /);
});

test('prepare-outbound stops at the first failed step rather than piling up 409s', async t => {
  const { base, seen } = await orderedPortal(t, { sipParamsRequired: true });
  await post(base, 'prepare-outbound', {});
  assert.deepEqual(seen, ['telnyx/sip-connection', 'outbound-readiness']);
});
