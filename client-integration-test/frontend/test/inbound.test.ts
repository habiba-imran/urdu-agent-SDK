import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import { mountInboundPanel } from '../src/inboundPanel';

const el = <T extends HTMLElement = HTMLElement>(id: string) => document.querySelector<T>(`#inbound-${id}`)!;
let fetchMock: ReturnType<typeof vi.fn>;
const agent = { id: 'assigned', name: 'Inbound agent', agent_language: 'en', stt_provider: 'deepgram', stt_model: 'nova-3', llm_provider: 'gemini', llm_model: 'flash', tts_provider: 'cartesia', tts_voice_id: 'voice' };
const number = { id: 'phone', e164_number: '+15551234567', assigned_agent_id: 'assigned', routing_status: 'not_configured' };
beforeEach(() => {
  document.body.innerHTML = '<div id="inbound-root"></div>';
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const applied = JSON.parse(String(init.body));
      return Response.json({ agent: { ...agent, llm_provider: applied.llmProvider, llm_model: applied.llmModel }, number, routingReady: false });
    }
    return Response.json({ tenantId: 'demo', numbers: [{ id: 'unassigned', e164_number: '+15550000000' }, number], agents: [agent], capabilities: { languages: { en: { label: 'English', stt: { deepgram: { models: ['nova-3'] } }, llm: { gemini: { models: ['flash'] }, groq: { models: ['fast'] } }, tts: { cartesia: { voices: ['voice'] } } } } } });
  });
  vi.stubGlobal('fetch', fetchMock);
  mountInboundPanel({ backendOrigin: 'http://localhost:3100' });
});
afterEach(() => vi.unstubAllGlobals());
async function load() {
  await vi.waitFor(() => expect(el<HTMLButtonElement>('save').disabled).toBe(false));
}
test('loading selects the number’s saved pipeline without mutation and exposes route blocker', async () => {
  await load();
  expect(el<HTMLSelectElement>('llm').value).toBe('gemini');
  expect(el<HTMLInputElement>('agent-id').value).toBe('assigned');
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(el('route').textContent).toContain('Inbound calls are blocked');
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
});

test('inbound persona is saved for the assigned agent in the number-scoped request', async () => {
  await load();
  const enabled = document.querySelector<HTMLSelectElement>('#inbound-persona-enabled')!;
  enabled.value = 'true'; enabled.dispatchEvent(new Event('change'));
  el('save').click();
  await vi.waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true));
  const write = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!;
  expect(write[0]).toContain('/numbers/phone/pipeline');
  expect(JSON.parse(String(write[1]?.body)).humanization.enabled).toBe(true);
});
test('explicit provider switch updates model and persists once without claiming routing success', async () => {
  await load();
  el<HTMLSelectElement>('llm').value = 'groq';
  el('llm').dispatchEvent(new Event('change'));
  expect(el<HTMLSelectElement>('llm-model').value).toBe('fast');
  expect(el('status').textContent).toContain('Unsaved');
  el('save').click(); el('save').click();
  await vi.waitFor(() => expect(el('status').textContent).toContain('Providers saved and verified'));
  expect(el('status').textContent).toContain('still blocked');
  const writes = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST');
  expect(writes).toHaveLength(1);
  expect(writes[0][0]).toContain('/numbers/phone/pipeline');
  expect(JSON.parse(String(writes[0][1]?.body)).llmProvider).toBe('groq');
});
test('failed save unlocks controls and requests readback before retrying', async () => {
  await load();
  fetchMock.mockResolvedValueOnce(Response.json({ message: 'Provider save unavailable' }, { status: 502 }));
  el('save').click();
  await vi.waitFor(() => expect(el('status').textContent).toContain('Refresh to confirm'));
  expect(el<HTMLButtonElement>('refresh').disabled).toBe(false);
});
