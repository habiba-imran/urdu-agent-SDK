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

async function telnyxGet(apiKey, pathname, query = {}) {
  const url = new URL(`https://api.telnyx.com${pathname}`);
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    url.searchParams.set(key, String(value));
  }
  return fetchJson(url.toString(), {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: 'application/json',
    },
  });
}

function summarizeConnection(item) {
  return {
    id: item.id ?? null,
    connection_name: item.connection_name ?? null,
    active: item.active ?? null,
    transport_protocol: item.transport_protocol ?? null,
    user_name: item.user_name ?? null,
    inbound: item.inbound
      ? {
          sip_region: item.inbound.sip_region ?? null,
          channel_limit: item.inbound.channel_limit ?? null,
          generate_ringback_tone: item.inbound.generate_ringback_tone ?? null,
        }
      : null,
    outbound: item.outbound
      ? {
          outbound_voice_profile_id: item.outbound.outbound_voice_profile_id ?? null,
          localization: item.outbound.localization ?? null,
        }
      : null,
    created_at: item.created_at ?? null,
    updated_at: item.updated_at ?? null,
  };
}

function summarizeFqdn(item) {
  return {
    id: item.id ?? null,
    connection_id: item.connection_id ?? null,
    fqdn: item.fqdn ?? null,
    port: item.port ?? null,
    dns_record_type: item.dns_record_type ?? null,
    created_at: item.created_at ?? null,
    updated_at: item.updated_at ?? null,
  };
}

async function main() {
  const env = {
    ...readEnvFile(BACKEND_ENV_PATH),
    ...process.env,
  };

  const apiKey = env.TELNYX_API_KEY || '';
  const tenantId = process.argv[2] || env.UVA_TENANT_ID || '';
  const expectedFqdn = process.argv[3] || env.LIVEKIT_SIP_URI || '';

  if (!apiKey) {
    console.error('Missing TELNYX_API_KEY in client-test-app/backend/.env or process env.');
    process.exit(1);
  }
  if (!tenantId) {
    console.error('Missing tenant id argument and UVA_TENANT_ID in client-test-app/backend/.env.');
    process.exit(1);
  }

  const connectionName = `tenant-${tenantId}`;
  console.log(`Inspecting Telnyx FQDN connection ${connectionName}`);
  console.log(`Expected FQDN target: ${expectedFqdn || '(not provided)'}\n`);

  const connectionsRes = await telnyxGet(apiKey, '/v2/fqdn_connections', {
    'filter[connection_name]': connectionName,
  });
  console.log(`GET /v2/fqdn_connections?filter[connection_name]=... -> ${connectionsRes.status} ${connectionsRes.statusText}`);
  if (!connectionsRes.ok) {
    console.log(connectionsRes.json ? JSON.stringify(connectionsRes.json, null, 2) : connectionsRes.text);
    return;
  }

  const connections = Array.isArray(connectionsRes.json?.data) ? connectionsRes.json.data : [];
  console.log(`Matched connections: ${connections.length}`);
  console.log(JSON.stringify(connections.map(summarizeConnection), null, 2));

  const primary = connections.find((item) => String(item?.connection_name || '') === connectionName) || connections[0];
  if (!primary?.id) {
    console.log('\nNo Telnyx FQDN connection found for this tenant.');
    return;
  }

  const fqdnsRes = await telnyxGet(apiKey, '/v2/fqdns', {
    'filter[connection_id]': primary.id,
  });
  console.log(`\nGET /v2/fqdns?filter[connection_id]=... -> ${fqdnsRes.status} ${fqdnsRes.statusText}`);
  if (!fqdnsRes.ok) {
    console.log(fqdnsRes.json ? JSON.stringify(fqdnsRes.json, null, 2) : fqdnsRes.text);
    return;
  }

  const fqdns = Array.isArray(fqdnsRes.json?.data) ? fqdnsRes.json.data : [];
  console.log(`Matched FQDN target records: ${fqdns.length}`);
  console.log(JSON.stringify(fqdns.map(summarizeFqdn), null, 2));

  if (expectedFqdn) {
    const exact = fqdns.find((item) => String(item?.fqdn || '') === expectedFqdn);
    console.log(`\nExpected FQDN present: ${String(Boolean(exact))}`);
    if (exact) {
      console.log(`Matching FQDN record id: ${exact.id}`);
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
