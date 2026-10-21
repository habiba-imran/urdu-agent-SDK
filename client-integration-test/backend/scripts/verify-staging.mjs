import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { loadConfig } from '../src/config.js';
import { createApp } from '../src/createApp.js';
import { createTelephonyClient } from '../src/telephonyRoutes.js';

// Restrict this runner to the verified staging portal; no production fallback.
const stagingOrigin = 'https://uva-tenant-portal-staging.onrender.com';
const config = loadConfig();
for (const url of [config.portalApiUrl, config.telephonyApiUrl]) {
  assert.equal(new URL(url).href, `${stagingOrigin}/`, 'staging portal URL required');
}
const require = createRequire(import.meta.url);
for (const name of ['@awaazlabs-uva/agents', '@awaazlabs-uva/telephony']) {
  const pkg = JSON.parse(readFileSync(resolve(dirname(require.resolve(name)), '../package.json'), 'utf8'));
  assert.equal(pkg.version, name === '@awaazlabs-uva/agents' ? '0.1.2-humanization.0' : '0.1.1');
  console.log(`PASS: installed ${name}@${pkg.version}`);
}
const server = createApp(config).listen(0, '127.0.0.1');
await new Promise(resolve => server.once('listening', resolve));
try {
  const origin = `http://127.0.0.1:${server.address().port}`;
  for (const route of ['/api/provider-capabilities', '/api/agents', '/api/telephony/calls']) {
    const response = await fetch(`${origin}${route}`, { signal: AbortSignal.timeout(60000) });
    assert.equal(response.status, 200, `${route}: HTTP ${response.status}`);
    const body = await response.json();
    if (route === '/api/agents') assert.ok(Array.isArray(body.agents));
    if (route === '/api/telephony/calls') assert.ok(Array.isArray(body.calls));
    console.log(`PASS: actual backend ${route} against staging`);
  }
  // The factory is also used by all other telephony handlers. Exercise its
  // managed-number POST without invoking provider operations or writes.
  const telephony = await createTelephonyClient(config);
  const numbers = await telephony.listManagedPhoneNumbers({});
  assert.ok(Array.isArray(numbers));
  console.log('PASS: actual telephony factory managed-number POST against staging');
} finally {
  await new Promise(resolve => { server.close(resolve); server.closeAllConnections(); });
}
