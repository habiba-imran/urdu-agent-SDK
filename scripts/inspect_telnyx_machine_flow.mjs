import { createHash, createHmac, randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const BACKEND_ENV_PATH = path.join(ROOT, 'client-test-app', 'backend', '.env');

function readEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
  const env = {};
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim();
    env[key] = value;
  }
  return env;
}

function canonicalJson(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
}

function createMachineHeaders({ tenantId, secret, action, body = {} }) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID();
  const payloadHash = createHash('sha256').update(canonicalJson(body)).digest('hex');
  const signature = createHmac('sha256', secret)
    .update(`${tenantId}.${timestamp}.${nonce}.${action}.${payloadHash}`)
    .digest('hex');
  return {
    'Content-Type': 'application/json',
    'X-Tenant-Id': tenantId,
    'X-Timestamp': timestamp,
    'X-Nonce': nonce,
    'X-Signature': signature,
  };
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const text = await response.text();
  let parsed = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }
  return {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    contentType: response.headers.get('content-type') || '',
    text,
    json: parsed,
  };
}

function preview(text, limit = 320) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized;
}

async function callMachineRoute({ baseUrl, tenantId, secret, method, route, action, body = {} }) {
  const headers = createMachineHeaders({ tenantId, secret, action, body });
  const response = await fetchJson(`${baseUrl.replace(/\/$/, '')}${route}`, {
    method,
    headers,
    body: method === 'GET' ? undefined : JSON.stringify(body),
  });
  return {
    route,
    action,
    method,
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    contentType: response.contentType,
    json: response.json,
    preview: preview(response.text),
  };
}

async function callTelnyxApi({ apiKey, pathName, query = {} }) {
  const url = new URL(`https://api.telnyx.com${pathName}`);
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    url.searchParams.set(key, String(value));
  }
  const response = await fetchJson(url.toString(), {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: 'application/json',
    },
  });
  return {
    url: url.toString(),
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    contentType: response.contentType,
    json: response.json,
    preview: preview(response.text),
  };
}

async function main() {
  const env = {
    ...readEnvFile(BACKEND_ENV_PATH),
    ...process.env,
  };

  const baseUrl = env.UVA_TELEPHONY_API_URL || env.UVA_API_BASE_URL || 'http://localhost:8002';
  const tenantId = env.UVA_TENANT_ID || '';
  const secret = env.UVA_HMAC_SECRET || '';
  const telnyxApiKey = env.TELNYX_API_KEY || '';
  const country = process.argv[2] || 'US';
  const areaCode = process.argv[3] || '';

  if (!tenantId || !secret) {
    console.error('Missing UVA_TENANT_ID or UVA_HMAC_SECRET. Checked client-test-app/backend/.env and process env.');
    process.exit(1);
  }

  const machineChecks = [
    { method: 'GET', route: '/machine/telephony/telnyx/connection', action: 'telephony.telnyx_connection.status', body: {} },
    { method: 'POST', route: '/machine/telephony/telnyx/owned-numbers/list', action: 'telephony.telnyx_owned_numbers.list', body: {} },
    { method: 'POST', route: '/machine/telephony/numbers/list', action: 'telephony.managed_numbers.list', body: {} },
    { method: 'POST', route: '/machine/telephony/numbers/sync', action: 'telephony.managed_numbers.sync', body: {} },
    {
      method: 'POST',
      route: '/machine/telephony/available-numbers/search',
      action: 'telephony.available_numbers.search',
      body: {
        country,
        ...(areaCode ? { area_code: areaCode } : {}),
        number_type: 'local',
        features: ['voice'],
      },
    },
  ];

  console.log(`\nMachine diagnostics against ${baseUrl}\n`);
  for (const check of machineChecks) {
    const result = await callMachineRoute({ baseUrl, tenantId, secret, ...check });
    console.log(`${result.method} ${result.route} -> ${result.status} ${result.statusText}`);
    if (result.json) {
      console.log(JSON.stringify(result.json, null, 2));
    } else {
      console.log(result.preview || '(empty response)');
    }
    console.log('');
  }

  if (!telnyxApiKey) {
    console.log('No TELNYX_API_KEY found in client-test-app/backend/.env or process env. Skipping direct Telnyx API diagnostics.');
    return;
  }

  console.log('Direct Telnyx API diagnostics\n');

  const balance = await callTelnyxApi({ apiKey: telnyxApiKey, pathName: '/v2/balance' });
  console.log(`GET /v2/balance -> ${balance.status} ${balance.statusText}`);
  console.log(balance.json ? JSON.stringify(balance.json, null, 2) : balance.preview);
  console.log('');

  const owned = await callTelnyxApi({
    apiKey: telnyxApiKey,
    pathName: '/v2/phone_numbers',
  });
  console.log(`GET /v2/phone_numbers -> ${owned.status} ${owned.statusText}`);
  console.log(owned.json ? JSON.stringify(owned.json, null, 2) : owned.preview);
  console.log('');

  const search = await callTelnyxApi({
    apiKey: telnyxApiKey,
    pathName: '/v2/available_phone_numbers',
    query: {
      'filter[country_code]': country,
      ...(areaCode ? { 'filter[national_destination_code]': areaCode } : {}),
      'filter[phone_number_type]': 'local',
      'filter[limit]': '5',
    },
  });
  console.log(`GET /v2/available_phone_numbers -> ${search.status} ${search.statusText}`);
  console.log(search.json ? JSON.stringify(search.json, null, 2) : search.preview);
  console.log('');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
