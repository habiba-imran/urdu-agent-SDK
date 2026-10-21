import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createApp, applyPipelineSelection } from '../src/createApp.js';

async function listen(t, server) {
  server = server.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return `http://127.0.0.1:${server.address().port}`;
}

test('prompt routes read and persist Unicode instructions through the installed Agents SDK', async t => {
  let record = { id: 'test-agent', name: 'Test agent', prompt: 'Original', first_speaker: 'agent', greeting: 'Hello', tools_auth_secret: 'never-return-this' };
  const updates = [];
  const portalUrl = await listen(t, createServer(async (req, res) => {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    assert.equal(req.headers['x-signature-version'], 'raw-body-v1');
    if (req.method === 'PATCH') {
      assert.equal(req.url, '/machine/agents/test-agent');
      const body = JSON.parse(raw);
      updates.push(body);
      record = { ...record, ...body };
    }
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify(req.method === 'PATCH' ? record : [record]));
  }));
  const url = await listen(t, createApp({ portalApiUrl: portalUrl, tenantId: 'fixture', hmacSecret: 'fixture-secret', allowedOrigins: [] }));
  const loaded = await (await fetch(`${url}/api/agents/test-agent/config`)).json();
  assert.deepEqual(loaded, { id: 'test-agent', name: 'Test agent', prompt: 'Original', firstSpeaker: 'agent', greeting: 'Hello' });
  const next = { prompt: 'آپ مددگار ہیں۔\nKeep replies concise.', firstSpeaker: 'user', greeting: '' };
  const response = await fetch(`${url}/api/agents/test-agent/config`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...next, toolsAuthSecret: 'must-not-forward' }) });
  assert.equal(response.status, 200);
  assert.deepEqual(updates, [{ prompt: next.prompt, first_speaker: 'user', greeting: '' }]);
  const saved = await response.json();
  assert.deepEqual(saved, { id: 'test-agent', name: 'Test agent', ...next });
  assert.equal((await (await fetch(`${url}/api/agents/test-agent/config`)).json()).prompt, next.prompt);
  assert.equal((await fetch(`${url}/api/agents/missing/config`)).status, 404);
});

test('invalid prompt settings never reach the SDK', async t => {
  const url = await listen(t, createApp({ allowedOrigins: [] }, fetch, () => assert.fail('SDK must not be called')));
  for (const body of [{}, { prompt: ' ', firstSpeaker: 'agent', greeting: '' }, { prompt: 'test', firstSpeaker: 'invalid', greeting: '' }, { prompt: 'test', firstSpeaker: 'agent', greeting: null }]) {
    const response = await fetch(`${url}/api/agents/test-agent/config`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    assert.equal(response.status, 400);
  }
});

test('persona saves through the installed SDK and reads back without exposing secrets', async t => {
  let record = { id: 'persona-agent', prompt: 'Help callers.', llm_options: {}, first_speaker: 'agent', greeting: '' };
  const writes = [];
  const portalUrl = await listen(t, createServer(async (req, res) => {
    let raw = ''; for await (const chunk of req) raw += chunk;
    if (req.method === 'PATCH') {
      writes.push(JSON.parse(raw)); record = { ...record, ...JSON.parse(raw) };
    }
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify(req.method === 'PATCH' ? record : [record]));
  }));
  const url = await listen(t, createApp({ portalApiUrl: portalUrl, tenantId: 'fixture', hmacSecret: 'private-test-secret', allowedOrigins: [] }));
  const settings = { prompt: 'Help callers.', firstSpeaker: 'agent', greeting: '', humanization: { enabled: true, warmth: 'warm', pace: 'normal' } };
  const save = body => fetch(`${url}/api/agents/persona-agent/config`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  assert.equal((await save(settings)).status, 200);
  assert.deepEqual(writes[0].llm_options, { humanization: settings.humanization });
  const stored = await (await fetch(`${url}/api/agents/persona-agent/config`)).json();
  assert.deepEqual(stored.humanization, settings.humanization);
  assert.ok(!JSON.stringify(stored).includes('private-test-secret'));
  assert.equal((await save({ ...settings, humanization: { enabled: 'yes' } })).status, 400);
  assert.equal(writes.length, 1);
  await save({ ...settings, humanization: { enabled: false } });
  assert.deepEqual(writes[1].llm_options.humanization, { enabled: false });
});

const selection = { agentLanguage: 'en', sttProvider: 'stt', sttModel: 's2', llmProvider: 'llm', llmModel: 'l2', ttsProvider: 'tts', ttsVoiceId: 'v2' };
const capabilities = { languages: { en: { stt: { stt: { models: ['s1', 's2'] } }, llm: { llm: { models: ['l1', 'l2'] } }, tts: { tts: { voices: ['v1', 'v2'] } } } } };

test('pipeline uses selected models and voice and rechecks externally changed agents', async () => {
  let current = {};
  let patches = 0;
  const client = {
    getProviderCapabilities: async () => capabilities,
    listAgents: async () => [{ id: 'a', ...current }],
    updateAgent: async (_id, body) => { patches++; current = body; return body; },
  };
  const first = await applyPipelineSelection(client, 'a', selection);
  assert.equal(first.applied.llmModel, 'l2');
  assert.equal(current.voiceId, 'v2');
  assert.equal((await applyPipelineSelection(client, 'a', selection)).skipped, true);
  current = { ...current, llmModel: 'l1' };
  assert.equal((await applyPipelineSelection(client, 'a', selection)).skipped, false);
  assert.equal(patches, 2);
});

test('pipeline rejects unavailable models and voices without writes', async () => {
  const client = { getProviderCapabilities: async () => capabilities, updateAgent: async () => assert.fail('must not write') };
  await assert.rejects(applyPipelineSelection(client, 'a', { ...selection, llmModel: 'unavailable' }), { code: 'unsupported_llm_model' });
  await assert.rejects(applyPipelineSelection(client, 'a', { ...selection, ttsVoiceId: 'unavailable' }), { code: 'unsupported_voice' });
});

test('an empty replacement profile disables the saved profile instead of skipping the update', async () => {
  let current = { id: 'a', ...selection, humanization: { enabled: true } };
  let writes = 0;
  const client = {
    getProviderCapabilities: async () => capabilities,
    listAgents: async () => [current],
    updateAgent: async (_id, body) => { writes++; current = { id: 'a', ...body }; return current; },
  };
  assert.equal((await applyPipelineSelection(client, 'a', { ...selection, humanization: {} })).skipped, false);
  assert.equal((await applyPipelineSelection(client, 'a', { ...selection, humanization: {} })).skipped, true);
  assert.equal(writes, 1);
});
