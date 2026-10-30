import test from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/createApp.js';

const capabilities = { languages: { en: { stt: { deepgram: { models: ['nova-3'] } },
  llm: { groq: { models: ['fast'] } }, tts: { cartesia: { voices: ['voice'] } } } } };
const draft = { name: 'Support', prompt: 'Help callers. آپ مددگار ہیں۔', firstSpeaker: 'user', greeting: '',
  agentLanguage: 'en', sttProvider: 'deepgram', sttModel: 'nova-3', llmProvider: 'groq', llmModel: 'fast',
  ttsProvider: 'cartesia', ttsVoiceId: 'voice' };

async function setup(t, createAgent) {
  const server = createApp({ allowedOrigins: [] }, fetch, () => ({
    getProviderCapabilities: async () => capabilities, createAgent,
    updateAgent: () => assert.fail('creation must not patch an existing agent'),
  })).listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return body => fetch(`http://127.0.0.1:${server.address().port}/api/agents`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
}

test('creation validates the whole pipeline before a single SDK create and returns only public fields', async t => {
  const writes = [];
  const post = await setup(t, async params => {
    writes.push(params);
    return { id: 'created', name: params.name, stt_provider: params.sttProvider, tools_auth_secret: 'private' };
  });
  const response = await post({ ...draft, toolsAuthSecret: 'must-not-forward', tenantId: 'other-tenant' });
  assert.equal(response.status, 201);
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0], { ...draft, voiceId: 'voice' });
  const result = await response.json();
  assert.equal(result.agent.id, 'created');
  assert.equal(result.applied.llmProvider, 'groq');
  assert.ok(!JSON.stringify(result).includes('private'));
});

test('invalid instructions, provider, model, voice, and duration never create an agent', async t => {
  const post = await setup(t, () => assert.fail('invalid draft must never write'));
  for (const invalid of [{ name: ' ' }, { prompt: '' }, { firstSpeaker: 'invalid' }, { greeting: null },
    { llmProvider: 'disabled' }, { llmModel: 'unknown' }, { ttsVoiceId: 'foreign-voice' },
    { maxCallDurationSeconds: 1 }, { name: 'x'.repeat(121) }]) {
    const response = await post({ ...draft, ...invalid });
    assert.ok(response.status >= 400 && response.status < 500);
  }
});

test('upstream creation failures preserve the status without retrying the write', async t => {
  let attempts = 0;
  const post = await setup(t, () => { attempts++; throw Object.assign(new Error('Unavailable'), { status: 503 }); });
  const response = await post(draft);
  assert.equal(response.status, 503);
  assert.equal((await response.json()).message, 'Unavailable');
  assert.equal(attempts, 1);
});
