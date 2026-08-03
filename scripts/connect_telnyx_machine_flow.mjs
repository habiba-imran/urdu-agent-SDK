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
    env[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
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
    text,
    json: parsed,
  };
}

async function callMachine({ baseUrl, tenantId, secret, method, route, action, body = {} }) {
  const headers = createMachineHeaders({ tenantId, secret, action, body });
  return fetchJson(`${baseUrl.replace(/\/$/, '')}${route}`, {
    method,
    headers,
    body: method === 'GET' ? undefined : JSON.stringify(body),
  });
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

  if (!tenantId || !secret || !telnyxApiKey) {
    console.error('Missing UVA_TENANT_ID, UVA_HMAC_SECRET, or TELNYX_API_KEY.');
    process.exit(1);
  }

  const desiredFingerprint = createHash('sha256').update(telnyxApiKey).digest('hex').slice(0, 12);
  console.log(`Desired key fingerprint from current TELNYX_API_KEY: ${desiredFingerprint}\n`);

  const connectBody = { api_key: telnyxApiKey, label: 'primary' };
  const connect = await callMachine({
    baseUrl,
    tenantId,
    secret,
    method: 'POST',
    route: '/machine/telephony/telnyx/connect',
    action: 'telephony.telnyx_connection.connect',
    body: connectBody,
  });

  console.log(`POST /machine/telephony/telnyx/connect -> ${connect.status} ${connect.statusText}`);
  console.log(connect.json ? JSON.stringify(connect.json, null, 2) : connect.text);
  console.log('');

  let rotate = null;
  const connectErrorCode = connect.json?.detail?.error?.code || connect.json?.error?.code || null;
  if (connect.status === 409 && connectErrorCode === 'call_state_conflict') {
    console.log('Existing active connection detected, attempting key rotation instead.\n');
    rotate = await callMachine({
      baseUrl,
      tenantId,
      secret,
      method: 'POST',
      route: '/machine/telephony/telnyx/rotate',
      action: 'telephony.telnyx_connection.rotate',
      body: { api_key: telnyxApiKey },
    });
    console.log(`POST /machine/telephony/telnyx/rotate -> ${rotate.status} ${rotate.statusText}`);
    console.log(rotate.json ? JSON.stringify(rotate.json, null, 2) : rotate.text);
    console.log('');
  }

  const status = await callMachine({
    baseUrl,
    tenantId,
    secret,
    method: 'GET',
    route: '/machine/telephony/telnyx/connection',
    action: 'telephony.telnyx_connection.status',
    body: {},
  });

  console.log(`GET /machine/telephony/telnyx/connection -> ${status.status} ${status.statusText}`);
  console.log(status.json ? JSON.stringify(status.json, null, 2) : status.text);

  const activeFingerprint = status.json?.key_fingerprint || null;
  if (activeFingerprint) {
    console.log('');
    if (activeFingerprint === desiredFingerprint) {
      console.log(`Fingerprint match confirmed: ${activeFingerprint}`);
    } else {
      console.log(`Fingerprint mismatch remains. Active=${activeFingerprint}, Desired=${desiredFingerprint}`);
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
