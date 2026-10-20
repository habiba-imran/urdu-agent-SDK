import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import { mountInboundRoutes } from '../src/inboundRoutes.js';
import { applyPipelineSelection } from '../src/createApp.js';

const caps = { languages: { en: { stt: { deepgram: { models: ['nova-3'] } }, llm: { gemini: { models: ['gemini-model'] }, groq: { models: ['groq-model'] } }, tts: { cartesia: { voices: ['voice-1'] } } } } };
const selection = { agentLanguage: 'en', sttProvider: 'deepgram', sttModel: 'nova-3', llmProvider: 'groq', llmModel: 'groq-model', ttsProvider: 'cartesia', ttsVoiceId: 'voice-1', agentId: 'wrong-browser-agent' };

async function host(t, { routing = 'ready', missing = false, stale = false, changed = false } = {}) {
  let agent = { id: 'assigned-agent', name: 'Inbound', prompt: 'Help callers', llm_provider: 'gemini', tools_auth_secret: 'never-return-this' };
  const writes = [];
  let reads = 0;
  const phone = { id: 'phone-1', assigned_agent_id: 'assigned-agent', routing_status: routing, e164_number: '+15551234567' };
  const client = {
    listAgents: async () => missing ? [] : [agent], getProviderCapabilities: async () => caps,
    updateAgent: async (id, body) => {
      writes.push({ id, body });
      if (!stale) agent = { ...agent, agent_language: body.agentLanguage, stt_provider: body.sttProvider, stt_model: body.sttModel,
        llm_provider: body.llmProvider, llm_model: body.llmModel, tts_provider: body.ttsProvider, tts_voice_id: body.ttsVoiceId };
      return agent;
    },
  };
  const telephony = { listManagedPhoneNumbers: async () => [phone], getManagedPhoneNumber: async () => {
    reads++;
    return changed && reads > 1 ? { ...phone, assigned_agent_id: 'other-agent' } : phone;
  } };
  const app = express(); app.use(express.json());
  const matches = (saved, applied) => saved?.llm_provider === applied.llmProvider && saved?.llm_model === applied.llmModel;
  mountInboundRoutes(app, { tenantId: 'demo-tenant' }, async () => client, applyPipelineSelection, matches, async () => telephony);
  const server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const url = `http://127.0.0.1:${server.address().port}`;
  return { writes, get: () => fetch(`${url}/api/inbound/setup`), save: (body = selection) => fetch(`${url}/api/inbound/numbers/phone-1/pipeline`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }) };
}
test('setup returns tenant-scoped settings without tool secrets or writes', async t => {
  const { get, writes } = await host(t);
  const response = await get();
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.tenantId, 'demo-tenant');
  assert.equal(result.numbers[0].assigned_agent_id, 'assigned-agent');
  assert.ok(!JSON.stringify(result).includes('never-return-this'));
  assert.equal(writes.length, 0);
});
test('provider save uses assigned agent rather than browser agent and verifies readback', async t => {
  const { save, writes } = await host(t);
  const response = await save();
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.agent.llm_provider, 'groq');
  assert.equal(result.routingReady, true);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].id, 'assigned-agent');
  assert.equal(writes[0].body.sttProvider, 'deepgram');
  assert.equal(writes[0].body.ttsProvider, 'cartesia');
  assert.equal(writes[0].body.prompt, undefined);
});
test('unrouted demo number can save providers without claiming calls are ready', async t => {
  const { save } = await host(t, { routing: 'not_configured' });
  const response = await save();
  assert.equal(response.status, 200);
  assert.equal((await response.json()).routingReady, false);
});
test('unsupported model is rejected before writes', async t => {
  const { save, writes } = await host(t);
  assert.equal((await save({ ...selection, llmModel: 'wrong-model' })).status, 422);
  assert.equal(writes.length, 0);
});
for (const [options, code, status] of [
  [{ missing: true }, 'inbound_agent_missing', 404],
  [{ stale: true }, 'inbound_save_unverified', 502],
  [{ changed: true }, 'inbound_assignment_changed', 409],
]) test(`save fails clearly for ${code}`, async t => {
  const { save } = await host(t, options);
  const response = await save();
  assert.equal(response.status, status);
  assert.equal((await response.json()).error, code);
});
