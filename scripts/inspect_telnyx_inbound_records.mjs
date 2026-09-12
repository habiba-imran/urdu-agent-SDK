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

function summarizeRecord(record) {
  return {
    id: record.id ?? record.uuid ?? null,
    record_type: record.record_type ?? null,
    cli: record.cli ?? null,
    cld: record.cld ?? null,
    direction: record.direction ?? null,
    status: record.status ?? null,
    hangup_cause: record.hangup_cause ?? null,
    call_leg_id: record.call_leg_id ?? record.call_leg_id_full ?? null,
    call_session_id: record.call_session_id ?? null,
    telnyx_session_id: record.telnyx_session_id ?? null,
    connection_id: record.connection_id ?? null,
    start_time: record.start_time ?? record.created_at ?? null,
    end_time: record.end_time ?? record.completed_at ?? record.finished_at ?? null,
    cost: record.cost ?? null,
    rate: record.rate ?? null,
  };
}

function normalizeRecords(response) {
  return Array.isArray(response?.json?.data) ? response.json.data : [];
}

function localFilter(records, didNumber, callerNumber) {
  return records.filter((record) => {
    const cld = String(record?.cld || '');
    const cli = String(record?.cli || '');
    const direction = String(record?.direction || '').toLowerCase();
    if (didNumber && cld !== didNumber) return false;
    if (callerNumber && cli !== callerNumber) return false;
    if (direction && direction !== 'inbound') return false;
    return true;
  });
}

function printFailure(response) {
  console.log(response.json ? JSON.stringify(response.json, null, 2) : response.text);
}

async function runProbe(apiKey, label, query) {
  const response = await telnyxGet(apiKey, '/v2/detail_records', query);
  console.log(`${label} -> ${response.status} ${response.statusText}`);
  if (!response.ok) {
    printFailure(response);
    console.log('');
    return { response, records: [] };
  }
  const records = normalizeRecords(response);
  console.log(`Returned records: ${records.length}`);
  console.log('');
  return { response, records };
}

async function main() {
  const env = {
    ...readEnvFile(BACKEND_ENV_PATH),
    ...process.env,
  };

  const apiKey = env.TELNYX_API_KEY || '';
  const didNumber = process.argv[2] || '+14755587853';
  const callerNumber = process.argv[3] || '';
  const dateRange = process.argv[4] || 'today';

  if (!apiKey) {
    console.error('Missing TELNYX_API_KEY in client-test-app/backend/.env or process env.');
    process.exit(1);
  }

  console.log(`Inspecting Telnyx inbound records for DID ${didNumber}`);
  console.log(`Caller filter: ${callerNumber || '(not provided)'}`);
  console.log(`Date range: ${dateRange}\n`);

  const baseQuery = {
    'filter[record_type]': 'sip-trunking',
    'filter[date_range]': dateRange,
    'page[size]': '100',
    sort: '-created_at',
  };

  const probes = [
    {
      label: 'Probe A: broad sip-trunking search',
      query: baseQuery,
    },
    {
      label: 'Probe B: sip-trunking + cld',
      query: {
        ...baseQuery,
        'filter[cld]': didNumber,
      },
    },
    {
      label: 'Probe C: sip-trunking + cld + direction',
      query: {
        ...baseQuery,
        'filter[cld]': didNumber,
        'filter[direction]': 'inbound',
      },
    },
    {
      label: 'Probe D: sip-trunking + cld + direction + cli',
      query: {
        ...baseQuery,
        'filter[cld]': didNumber,
        'filter[direction]': 'inbound',
        ...(callerNumber ? { 'filter[cli]': callerNumber } : {}),
      },
    },
  ];

  let broadRecords = [];
  for (const probe of probes) {
    const { response, records } = await runProbe(apiKey, probe.label, probe.query);
    if (probe.label === 'Probe A: broad sip-trunking search' && response.ok) {
      broadRecords = records;
    }
    if (response.ok) {
      const filtered = localFilter(records, didNumber, callerNumber);
      if (filtered.length > 0) {
        console.log(`Matched records after local filtering: ${filtered.length}`);
        console.log(JSON.stringify(filtered.map(summarizeRecord), null, 2));
        return;
      }
      console.log('No matching records after local filtering for this probe.\n');
    }
  }

  if (broadRecords.length > 0) {
    const filtered = localFilter(broadRecords, didNumber, callerNumber);
    console.log(`Fallback local filtering on Probe A records matched: ${filtered.length}`);
    console.log(JSON.stringify(filtered.map(summarizeRecord), null, 2));
    if (filtered.length === 0) {
      console.log('\nTelnyx returned sip-trunking records, but none matched this DID/caller pair.');
    }
    return;
  }

  console.log('No successful Telnyx detail-record probe returned usable sip-trunking data.');
  console.log('This points to a Telnyx reporting/query failure rather than a proven SDK routing failure.');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
