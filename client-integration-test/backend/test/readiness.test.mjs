import test from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/createApp.js';

const config = { allowedOrigins: [], controlPlaneUrl: 'https://cp.invalid', portalApiUrl: 'https://api.invalid' };
async function host(t, upstream) {
  const server = createApp(config, upstream).listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return `http://127.0.0.1:${server.address().port}`;
}

test('service preparation checks health without minting sessions or exposing upstream details', async t => {
  const calls = [];
  const base = await host(t, async (url, init) => {
    calls.push(url);
    assert.equal(init.method, undefined);
    return Response.json({ status: 'ok', private: 'must-not-reach-browser' });
  });
  const first = await (await fetch(`${base}/api/demo/ready`)).json();
  assert.equal(first.ready, true);
  assert.ok(!JSON.stringify(first).includes('must-not-reach-browser'));
  assert.deepEqual(calls.sort(), ['https://api.invalid/healthz', 'https://cp.invalid/healthz']);
  await fetch(`${base}/api/demo/ready`);
  assert.equal(calls.length, 2, 'warm readiness should not repeat network checks immediately');
});

test('concurrent readiness requests share one preparation', async t => {
  let finish;
  const gate = new Promise(resolve => { finish = resolve; });
  let calls = 0;
  const base = await host(t, async () => { calls++; await gate; return Response.json({}); });
  const first = fetch(`${base}/api/demo/ready`);
  const second = fetch(`${base}/api/demo/ready`);
  while (calls < 2) await new Promise(resolve => setTimeout(resolve, 1));
  finish();
  assert.equal((await first).status, 200);
  assert.equal((await second).status, 200);
  assert.equal(calls, 2);
});

test('unhealthy preparation can be retried and does not claim ready', async t => {
  let healthy = false;
  const base = await host(t, async () => Response.json({}, { status: healthy ? 200 : 503 }));
  assert.equal((await fetch(`${base}/api/demo/ready`)).status, 503);
  healthy = true;
  const response = await fetch(`${base}/api/demo/ready`);
  assert.equal(response.status, 200);
  assert.equal((await response.json()).ready, true);
});
