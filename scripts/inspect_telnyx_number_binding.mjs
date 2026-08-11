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

async function main() {
  const env = {
    ...readEnvFile(BACKEND_ENV_PATH),
    ...process.env,
  };

  const apiKey = env.TELNYX_API_KEY || '';
  const e164Number = process.argv[2] || '+14755587853';
  const expectedConnectionId = process.argv[3] || '3018585419106223381';

  if (!apiKey) {
    console.error('Missing TELNYX_API_KEY in client-test-app/backend/.env or process env.');
    process.exit(1);
  }

  console.log(`Inspecting Telnyx phone number ${e164Number}`);
  console.log(`Expected SIP/FQDN connection id: ${expectedConnectionId}\n`);

  const owned = await telnyxGet(apiKey, '/v2/phone_numbers', {
    'filter[phone_number]': e164Number,
  });
  console.log(`GET /v2/phone_numbers?filter[phone_number]=... -> ${owned.status} ${owned.statusText}`);
  console.log(owned.json ? JSON.stringify(owned.json, null, 2) : owned.text);
  console.log('');

  const item = owned.json?.data?.[0] || null;
  if (!item) {
    console.log('No matching phone number found in Telnyx account.');
    return;
  }

  const actualConnectionId =
    item.connection_id ||
    item.voice?.connection_id ||
    item.connection?.id ||
    null;

  console.log(`Resolved provider number id: ${item.id || '(missing)'}`);
  console.log(`Resolved connection id: ${actualConnectionId || '(missing)'}`);
  console.log(`Expected connection id: ${expectedConnectionId}`);
  console.log(`Binding match: ${String(actualConnectionId === expectedConnectionId)}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
