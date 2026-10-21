// Tests for @awaazlabs-uva/agents (audit §2 item 26: the server SDK had no test script).
//
// Runs against the compiled dist/ with Node's built-in test runner — no extra dependencies.
// `npm test` builds first. fetch is stubbed; nothing here touches the network.
//
// The signing vector below was generated from the SERVER's own code, not re-derived here:
//   tenant_portal_api/machine_auth.py::payload_hash + expected_signature
// so a drift between the SDK's canonical JSON / HMAC message and the portal's verifier fails
// this test instead of failing every signed request in production with a 401.

import assert from 'node:assert/strict';
import { createHash, createHmac } from 'node:crypto';
import { afterEach, beforeEach, describe, it, mock } from 'node:test';

import {
  AwaazLabsUvaAgentsClient,
  AwaazLabsUvaAgentsError,
  UvaAgentsClient,
  UvaAgentsError,
  validateHumanization,
} from '../dist/index.js';

const TENANT_ID = '11111111-2222-3333-4444-555555555555';
const SECRET = 'secret-xyz';
const TS_SEC = 1726500000;
const NONCE = 'nonce-abc';

// Server-generated vector (see header comment). Includes Urdu-script text, a nested object,
// an array, a float and a null, so key sorting, ensure_ascii=False and number formatting are
// all exercised.
const VECTOR_BODY = {
  name: 'Support Agent',
  prompt: 'آپ ایک مددگار معاون ہیں',
  voice_id: 'helpdesk-agent',
  llm_model: 'gemini-2.5-flash',
  tts_options: { speed: 1.1, emotion: ['calm'] },
  greeting: null,
};
const VECTOR_SIGNATURE = '9d9600d4160115ca655205072d2ecff1878050c4307bbb3c7334dee92cd0ef87';

let calls;

function stubFetch(responder) {
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    const { status = 200, body = null, statusText = 'OK' } = responder(url, init) ?? {};
    const text = body === null ? '' : typeof body === 'string' ? body : JSON.stringify(body);
    return new Response(text, { status, statusText });
  };
}

function client(overrides = {}) {
  return new AwaazLabsUvaAgentsClient({
    tenantId: TENANT_ID,
    tenantSecret: SECRET,
    baseUrl: 'https://portal-api.example.com/',
    ...overrides,
  });
}

const realFetch = globalThis.fetch;

it('saves the same persona profile for every channel through signed agent create and update', async () => {
  stubFetch(() => ({ body: { id: 'agent-persona' } }));
  const humanization = { enabled: true, warmth: 'warm', formality: 'casual', energy: 'balanced', adaptivePace: true };
  await client({ signatureVersion: 'raw-body-v1' }).createAgent({ name: 'Test', prompt: 'Test persona', voiceId: 'test', humanization });
  await client({ signatureVersion: 'raw-body-v1' }).updateAgent('agent-persona', { humanization: { enabled: false } });
  assert.deepEqual(JSON.parse(calls[0].init.body).llm_options, { humanization });
  assert.deepEqual(JSON.parse(calls[1].init.body), { llm_options: { humanization: { enabled: false } } });
  assert.equal(calls[1].init.headers['X-Signature-Version'], 'raw-body-v1');
});

it('rejects unsupported persona fields without a request', async () => {
  for (const value of [null, [], { enabled: 'true' }, { pitch: 2 }, { warmth: 'ignore rules' }]) {
    assert.throws(() => validateHumanization(value));
  }
  stubFetch(() => assert.fail('invalid persona must not reach the network'));
  await assert.rejects(client().updateAgent('a', { humanization: { adaptivePace: 'yes' } }));
  assert.equal(calls.length, 0);
});

it('preserves HTTP status for plain-text and HTML API failures', async () => {
  for (const body of ['Internal Server Error', '<html>Bad Gateway</html>']) {
    stubFetch(() => ({ status: 500, statusText: 'Internal Server Error', body }));
    await assert.rejects(client().updateAgent('a', { prompt: 'Test' }), error =>
      error instanceof AwaazLabsUvaAgentsError && error.status === 500 && error.code === 'upstream_error' &&
      error.message.includes('HTTP 500') && !error.message.includes('Unexpected token') && !error.message.includes('<html>'));
  }
});

beforeEach(() => {
  mock.timers.enable({ apis: ['Date'], now: TS_SEC * 1000 });
});

afterEach(() => {
  mock.timers.reset();
  mock.restoreAll();
  globalThis.fetch = realFetch;
});

describe('constructor', () => {
  it('rejects blank required options', () => {
    assert.throws(() => client({ tenantId: '  ' }), /tenantId is required/);
    assert.throws(() => client({ tenantSecret: '' }), /tenantSecret is required/);
    assert.throws(() => client({ baseUrl: ' ' }), /baseUrl is required/);
  });

  it('exports the short aliases as the same classes', () => {
    assert.equal(UvaAgentsClient, AwaazLabsUvaAgentsClient);
    assert.equal(UvaAgentsError, AwaazLabsUvaAgentsError);
  });
});

describe('request signing', () => {
  it('test helper reproduces the server-generated signature (anchors the checks below)', () => {
    assert.equal(expectedSignature(VECTOR_BODY, NONCE, 'agent.create'), VECTOR_SIGNATURE);
  });

  it('signs POST bodies exactly as the tenant portal verifies them', async () => {
    stubFetch(() => ({ body: { id: 'agent-1' } }));
    await client().createAgent({
      name: VECTOR_BODY.name,
      prompt: VECTOR_BODY.prompt,
      voiceId: VECTOR_BODY.voice_id,
      ttsOptions: VECTOR_BODY.tts_options,
    });

    const { init } = calls[0];
    const nonce = init.headers['X-Nonce'];
    assert.equal(init.headers['X-Tenant-Id'], TENANT_ID);
    assert.equal(init.headers['X-Timestamp'], String(TS_SEC));
    assert.match(nonce, /^[0-9a-f-]{36}$/);
    // Urdu text must go over the wire unescaped, matching the hash the server recomputes.
    assert.ok(init.body.includes(VECTOR_BODY.prompt));
    assert.equal(
      init.headers['X-Signature'],
      expectedSignature(JSON.parse(init.body), nonce, 'agent.create'),
    );
  });

  it('signs GET requests over an empty object and sends no body', async () => {
    stubFetch(() => ({ body: [] }));
    await client().listAgents();

    const { url, init } = calls[0];
    assert.equal(url, 'https://portal-api.example.com/machine/agents');
    assert.equal(init.method, 'GET');
    assert.equal(init.body, undefined);
    assert.equal(init.headers['X-Signature'], expectedSignature({}, init.headers['X-Nonce'], 'agent.list'));
  });

  it('does not let extraHeaders override auth headers', async () => {
    stubFetch(() => ({ body: [] }));
    await client({
      extraHeaders: { 'X-Tenant-Id': 'attacker', 'X-Signature': 'forged', 'ngrok-skip-browser-warning': 'true' },
    }).listAgents();

    const { headers } = calls[0].init;
    assert.equal(headers['X-Tenant-Id'], TENANT_ID);
    assert.notEqual(headers['X-Signature'], 'forged');
    assert.equal(headers['ngrok-skip-browser-warning'], 'true');
  });
});

describe('request bodies', () => {
  it('createAgent maps camelCase params to snake_case and defaults llm_model', async () => {
    stubFetch(() => ({ body: { id: 'agent-1' } }));
    await client().createAgent({
      name: 'A',
      prompt: 'P',
      voiceId: 'v1',
      agentLanguage: 'en',
      llmProvider: 'groq',
      ttsProvider: 'cartesia',
      ttsVoiceId: 'cartesia-voice',
      firstSpeaker: 'user',
    });

    const { url, init } = calls[0];
    assert.equal(url, 'https://portal-api.example.com/machine/agents');
    assert.equal(init.method, 'POST');
    assert.deepEqual(JSON.parse(init.body), {
      name: 'A',
      prompt: 'P',
      voice_id: 'v1',
      llm_model: 'gemini-2.5-flash',
      agent_language: 'en',
      llm_provider: 'groq',
      tts_provider: 'cartesia',
      tts_voice_id: 'cartesia-voice',
      first_speaker: 'user',
    });
  });

  it('updateAgent sends only provided fields and keeps an empty greeting (clears it)', async () => {
    stubFetch(() => ({ body: { id: 'agent-1' } }));
    await client().updateAgent('agent-1', { prompt: 'new', greeting: '' });

    const { url, init } = calls[0];
    assert.equal(url, 'https://portal-api.example.com/machine/agents/agent-1');
    assert.equal(init.method, 'PATCH');
    assert.deepEqual(JSON.parse(init.body), { prompt: 'new', greeting: '' });
  });

  it('unassignAgentFromNumber sends agent_id: null', async () => {
    stubFetch(() => ({ body: { id: 'num-1' } }));
    await client().unassignAgentFromNumber('num-1');

    const { url, init } = calls[0];
    assert.equal(url, 'https://portal-api.example.com/machine/telephony/numbers/num-1/assignment');
    assert.deepEqual(JSON.parse(init.body), { agent_id: null });
  });
});

describe('error mapping', () => {
  it('surfaces the stable code from provider-validation errors', async () => {
    stubFetch(() => ({
      status: 422,
      body: { detail: { code: 'unsupported_provider_for_language', reason: 'groq is not available for ur' } },
    }));

    await assert.rejects(client().createAgent({ name: 'A', prompt: 'P', voiceId: 'v' }), (err) => {
      assert.ok(err instanceof AwaazLabsUvaAgentsError);
      assert.equal(err.status, 422);
      assert.equal(err.code, 'unsupported_provider_for_language');
      assert.equal(err.message, 'groq is not available for ur');
      return true;
    });
  });

  it('uses plain string details with no code', async () => {
    stubFetch(() => ({ status: 401, body: { detail: 'invalid signature' } }));

    await assert.rejects(client().listAgents(), (err) => {
      assert.equal(err.status, 401);
      assert.equal(err.code, undefined);
      assert.equal(err.message, 'invalid signature');
      return true;
    });
  });

  it('falls back to statusText when the error body is empty', async () => {
    stubFetch(() => ({ status: 503, statusText: 'Service Unavailable' }));

    await assert.rejects(client().listAgents(), (err) => {
      assert.equal(err.status, 503);
      assert.equal(err.message, 'Service Unavailable');
      return true;
    });
  });
});

// --- helpers -------------------------------------------------------------------------------

// Mirrors tenant_portal_api/machine_auth.py::payload_hash
// (json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False) -> UTF-8 -> sha256).
function canonical(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  return `{${Object.keys(value)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`)
    .join(',')}}`;
}

function expectedSignature(body, nonce, action) {
  const bodyHash = createHash('sha256').update(canonical(body), 'utf8').digest('hex');
  const message = `${TENANT_ID}.${TS_SEC}.${nonce}.${action}.${bodyHash}`;
  return createHmac('sha256', SECRET).update(message).digest('hex');
}


describe('wire-body signing opt-in', () => {
  for (const signatureVersion of ['canonical-json-v1', 'raw-body-v1']) {
    it(`sends the exact signed UTF-8 bytes in ${signatureVersion}`, async () => {
      stubFetch(() => ({ body: { id: 'agent-1' } }));
      await client({ signatureVersion, extraHeaders: { 'x-signature-version': 'unknown' } })
        .createAgent({ name: 'Fixture', prompt: '\u0622\u067e', voiceId: 'v',
          greeting: null, llmOptions: { epsilon: 1e-7, '\ud83d\ude00': 2, '\uff21': 1 } });
      const { init } = calls[0];
      assert.equal(init.headers['X-Signature-Version'], signatureVersion);
      assert.equal(init.headers['x-signature-version'], undefined);
      assert.equal(JSON.parse(init.body).greeting, null);
      const digest = createHash('sha256').update(init.body, 'utf8').digest('hex');
      const expected = createHmac('sha256', SECRET).update(
        `${TENANT_ID}.${init.headers['X-Timestamp']}.${init.headers['X-Nonce']}.agent.create.${digest}`
      ).digest('hex');
      assert.equal(init.headers['X-Signature'], expected);
    });
  }
  it('keeps legacy mode the default', async () => {
    stubFetch(() => ({ body: [] }));
    await client().listAgents();
    assert.equal(calls[0].init.headers['X-Signature-Version'], 'canonical-json-v1');
  });
});
