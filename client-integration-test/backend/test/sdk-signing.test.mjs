import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, createHmac } from 'node:crypto';
import { createServer } from 'node:http';
import { createAgentsClient } from '../src/createApp.js';
import { createTelephonyClient } from '../src/telephonyRoutes.js';

test('backend factories sign actual Unicode and exponent-form wire bodies in raw mode', async t => {
  const tenantId = 'fixture-tenant';
  const hmacSecret = 'fixture-only-secret';
  const requests = [];
  const upstream = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const raw = Buffer.concat(chunks);
    const action = req.method === 'PATCH' ? 'agent.update' : 'telephony.managed_numbers.list';
    const hash = createHash('sha256').update(raw.length ? raw : '{}').digest('hex');
    const signature = createHmac('sha256', hmacSecret).update(
      `${tenantId}.${req.headers['x-timestamp']}.${req.headers['x-nonce']}.${action}.${hash}`,
    ).digest('hex');
    requests.push({ raw: raw.toString('utf8'), headers: req.headers, valid: signature === req.headers['x-signature'] });
    res.writeHead(signature === req.headers['x-signature'] ? 200 : 401, { 'Content-Type': 'application/json' });
    res.end(req.method === 'PATCH' ? '{"id":"fixture-agent"}' : '[]');
  }).listen(0, '127.0.0.1');
  await new Promise(resolve => upstream.once('listening', resolve));
  t.after(() => new Promise(resolve => { upstream.close(resolve); upstream.closeAllConnections(); }));
  const url = `http://127.0.0.1:${upstream.address().port}`;
  const config = { portalApiUrl: url, telephonyApiUrl: url, tenantId, hmacSecret };
  const agents = await createAgentsClient(config);
  await agents.updateAgent('fixture-agent', {
    greeting: null, llmOptions: { epsilon: 1e-7, '😀': 2, 'Ａ': 1, text: 'آپ' },
  });
  const telephony = await createTelephonyClient(config);
  await telephony.listManagedPhoneNumbers({ limit: 1e-7, cursor: 'آپ😀' });
  assert.equal(requests.length, 2);
  for (const request of requests) {
    assert.equal(request.headers['x-signature-version'], 'raw-body-v1');
    assert.ok(request.valid, 'signature must match the bytes received by the upstream');
    assert.ok(request.raw.includes('1e-7'));
    assert.ok(request.raw.includes('آپ'));
    assert.ok(!request.raw.includes(hmacSecret));
  }
});
