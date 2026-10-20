import { afterEach, beforeEach, expect, test, vi } from 'vitest';

const sdk = vi.hoisted(() => ({ clients: [] as any[], connectGate: null as Promise<void> | null }));
vi.mock('@awaazlabs-uva/voice', () => ({
  AwaazLabsUvaVoiceError: class extends Error {},
  AwaazLabsUvaVoice: class {
    events = new Map<string, Function[]>();
    isConnected = false;
    isMicMuted = false;
    connectionState = 'idle';
    connectTiming = null;
    constructor() { sdk.clients.push(this); }
    on(event: string, cb: Function) { this.events.set(event, [...(this.events.get(event) || []), cb]); }
    emit(event: string, value?: unknown) { this.events.get(event)?.forEach(cb => cb(value)); }
    async connect() { await sdk.connectGate; this.isConnected = true; this.connectionState = 'connected'; this.emit('connected'); }
    async disconnect() { this.isConnected = false; this.connectionState = 'idle'; this.emit('disconnected'); }
    async setMicMuted(value: boolean) { this.isMicMuted = value; }
    async startAudio() { this.emit('audio_blocked', false); this.emit('audio_ready', true); }
  },
}));

const $ = <T extends HTMLElement = HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const button = (id: string) => $<HTMLButtonElement>(`#${id}`);
let fetchMock: ReturnType<typeof vi.fn>;
let config: { id: string; prompt: string; firstSpeaker: string; greeting: string };
let failSave = false;
const caps = { languages: { en: { label: 'English', stt: { deepgram: { models: ['s1', 's2'], defaultModel: 's1' } }, llm: { openai: { models: ['l1', 'l2'], defaultModel: 'l1' } }, tts: { cartesia: { voices: ['v1', 'v2'], defaultVoice: 'v1' } } } } };

beforeEach(async () => {
  vi.resetModules();
  sdk.clients.length = 0;
  sdk.connectGate = null;
  failSave = false;
  config = { id: 'test-agent', prompt: 'Be helpful.', firstSpeaker: 'agent', greeting: '' };
  vi.stubEnv('VITE_UVA_AGENT_ID', 'test-agent');
  vi.stubEnv('VITE_UVA_PUBLISHABLE_KEY', 'public-test');
  vi.stubEnv('VITE_UVA_SESSION_ENDPOINT', 'http://localhost:3100/api/voice/session');
  document.body.innerHTML = '<div id="app"></div>';
  fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    const path = new URL(input).pathname;
    if (path === '/api/provider-capabilities') return Response.json(caps);
    if (path === '/api/agents') return Response.json({ agents: [{ id: 'test-agent', name: 'Test agent', agent_language: 'en', stt_provider: 'deepgram', stt_model: 's1', llm_provider: 'openai', llm_model: 'l1', tts_provider: 'cartesia', tts_voice_id: 'v1' }] });
    if (path === '/api/demo/config') return Response.json({ publishableKey: 'public-test' });
    if (path === '/api/demo/ready') return Response.json({ ready: true });
    if (path.endsWith('/config')) {
      if (init?.method === 'POST') {
        if (failSave) return Response.json({ message: 'Portal unavailable' }, { status: 502 });
        config = { ...config, ...JSON.parse(String(init.body)) };
      }
      return Response.json(config);
    }
    if (path.endsWith('/pipeline')) return Response.json({ applied: JSON.parse(String(init?.body)) });
    if (path.endsWith('/numbers')) return Response.json({ managed: [], owned: [] });
    return Response.json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  await import('../src/main');
  await vi.waitFor(() => expect($<HTMLTextAreaElement>('#agent-prompt').value).toBe('Be helpful.'));
  await vi.waitFor(() => expect(button('connect-btn').disabled).toBe(false));
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

function editPrompt(value: string) {
  $<HTMLTextAreaElement>('#agent-prompt').value = value;
  $('#agent-prompt').dispatchEvent(new Event('input', { bubbles: true }));
}
function submit() { $('#voice-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); }

test('startup loads saved prompt and live capabilities without agent mutations', () => {
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  expect(button('save-prompt-btn').disabled).toBe(true);
  expect(button('disconnect-btn').disabled).toBe(true);
  expect($('#mic-text').textContent).toBe('Off');
  expect($<HTMLSelectElement>('#tts-voice').options.length).toBe(2);
});

test('unchanged saved pipeline does not add portal round trips to connect', async () => {
  submit();
  await vi.waitFor(() => expect(button('disconnect-btn').disabled).toBe(false));
  expect(fetchMock.mock.calls.filter(([path]) => path.endsWith('/pipeline'))).toHaveLength(0);
});

test('failed service preparation blocks connect and refresh can recover', async () => {
  const upstream = fetchMock.getMockImplementation()!;
  let ready = false;
  fetchMock.mockImplementation((input: string, init?: RequestInit) =>
    new URL(input).pathname === '/api/demo/ready'
      ? Promise.resolve(Response.json({ ready }, { status: ready ? 200 : 503 }))
      : upstream(input, init));
  button('reload-agents-btn').click();
  await vi.waitFor(() => expect($('#services-status').textContent).toContain('unavailable'));
  expect(button('connect-btn').disabled).toBe(true);
  submit();
  expect(sdk.clients).toHaveLength(0);
  ready = true;
  button('reload-agents-btn').click();
  await vi.waitFor(() => expect(button('connect-btn').disabled).toBe(false));
  expect($('#services-status').textContent).toBe('Backend services ready.');
});

test('picker requests wait for backend wake-up instead of timing out during it', async () => {
  const upstream = fetchMock.getMockImplementation()!;
  let finish!: (response: Response) => void;
  const gate = new Promise<Response>(resolve => { finish = resolve; });
  fetchMock.mockImplementation((input: string, init?: RequestInit) =>
    new URL(input).pathname === '/api/demo/ready' ? gate : upstream(input, init));
  const agentLoads = () => fetchMock.mock.calls.filter(([path]) => new URL(path).pathname === '/api/agents').length;
  const before = agentLoads();
  button('reload-agents-btn').click();
  await Promise.resolve();
  expect(agentLoads()).toBe(before);
  expect(button('connect-btn').disabled).toBe(true);
  finish(Response.json({ ready: true }));
  await vi.waitFor(() => expect(button('connect-btn').disabled).toBe(false));
  expect(agentLoads()).toBe(before + 1);
});

test('startup cards distinguish total click time from time after room connection', async () => {
  let clock = 1000;
  const now = vi.spyOn(performance, 'now').mockImplementation(() => clock);
  let finish!: () => void;
  sdk.connectGate = new Promise<void>(resolve => { finish = resolve; });
  try {
    submit();
    await vi.waitFor(() => expect(sdk.clients).toHaveLength(1));
    clock = 3000;
    finish();
    await vi.waitFor(() => expect(button('disconnect-btn').disabled).toBe(false));
    clock = 4000;
    sdk.clients[0].emit('agent_speaking', true);
    const cards = new Map([...document.querySelectorAll('.timing-card')].map(card => [
      card.querySelector('.timing-label')!.textContent,
      card.querySelector('.timing-value')!.textContent,
    ]));
    expect(cards.get('Click → active speaker (proxy)')).toBe('3000ms');
    expect(cards.get('Room → active speaker (proxy)')).toBe('1000ms');
  } finally { now.mockRestore(); }
});

test('an edited pipeline is saved once, and reconnect uses the saved configuration', async () => {
  $<HTMLSelectElement>('#llm-model').value = 'l2';
  submit();
  await vi.waitFor(() => expect(button('disconnect-btn').disabled).toBe(false));
  button('disconnect-btn').click();
  await vi.waitFor(() => expect(button('connect-btn').disabled).toBe(false));
  submit();
  await vi.waitFor(() => expect(button('disconnect-btn').disabled).toBe(false));
  expect(fetchMock.mock.calls.filter(([path]) => path.endsWith('/pipeline'))).toHaveLength(1);
});

test('prompt edits block connect, survive failed saves, and persist on retry', async () => {
  editPrompt('آپ مددگار ہیں۔');
  submit();
  expect(sdk.clients).toHaveLength(0);
  expect($('#session-feedback').textContent).toContain('save your prompt');
  failSave = true;
  button('save-prompt-btn').click();
  expect($<HTMLSelectElement>('#agent-picker').disabled).toBe(true);
  await vi.waitFor(() => expect($('#prompt-feedback').textContent).toContain('Save failed'));
  expect($<HTMLTextAreaElement>('#agent-prompt').value).toBe('آپ مددگار ہیں۔');
  failSave = false;
  button('save-prompt-btn').click();
  await vi.waitFor(() => expect($('#prompt-feedback').textContent).toContain('Prompt saved'));
  expect(config.prompt).toBe('آپ مددگار ہیں۔');
  expect(button('save-prompt-btn').disabled).toBe(true);
});

test('reset restores saved instructions and user-first disables the opening line', () => {
  editPrompt('Temporary edit');
  button('reset-prompt-btn').click();
  expect($<HTMLTextAreaElement>('#agent-prompt').value).toBe('Be helpful.');
  $<HTMLSelectElement>('#first-speaker').value = 'user';
  $('#first-speaker').dispatchEvent(new Event('input'));
  expect($<HTMLInputElement>('#agent-greeting').disabled).toBe(true);
});

test('connect is guarded against duplicate submits and locks settings until disconnect', async () => {
  let finish!: () => void;
  sdk.connectGate = new Promise<void>(resolve => { finish = resolve; });
  $<HTMLSelectElement>('#llm-model').value = 'l2';
  submit(); submit();
  await vi.waitFor(() => expect(sdk.clients).toHaveLength(1));
  expect(button('connect-btn').disabled).toBe(true);
  expect($<HTMLTextAreaElement>('#agent-prompt').disabled).toBe(true);
  const pipeline = fetchMock.mock.calls.find(([path]) => path.endsWith('/pipeline'));
  expect(JSON.parse(String(pipeline?.[1]?.body)).llmModel).toBe('l2');
  finish();
  await vi.waitFor(() => expect(button('disconnect-btn').disabled).toBe(false));
  button('mute-btn').click();
  await vi.waitFor(() => expect(button('mute-btn').textContent).toBe('Unmute mic'));
  sdk.clients[0].emit('audio_blocked', true);
  expect($('#audio-unlock-banner').style.display).toBe('flex');
  button('unlock-audio-btn').click();
  await vi.waitFor(() => expect($('#playback-status').textContent).toContain('Playback ready'));
  button('disconnect-btn').click();
  await vi.waitFor(() => expect(button('connect-btn').disabled).toBe(false));
  expect($<HTMLTextAreaElement>('#agent-prompt').disabled).toBe(false);
  expect($('#mic-text').textContent).toBe('Off');
});

test('transcript revisions replace partials and render text safely', async () => {
  submit();
  await vi.waitFor(() => expect(button('disconnect-btn').disabled).toBe(false));
  sdk.clients[0].emit('transcript', { id: '1', speaker: 'user', text: 'Part', final: false });
  sdk.clients[0].emit('transcript', { id: '1', speaker: 'user', text: '<img src=x onerror=alert(1)>', final: true });
  expect(document.querySelectorAll('#transcript-list li')).toHaveLength(1);
  expect(document.querySelector('#transcript-list img')).toBeNull();
  expect($('#transcript-list').textContent).toContain('<img');
  expect(button('download-transcript-btn').disabled).toBe(false);
  document.querySelector<HTMLAnchorElement>('a[href="#telephony-section"]')!.click();
  expect($<HTMLDetailsElement>('#telephony-section').open).toBe(true);
});

test('telephony requests disable repeat actions and recover after failures', async () => {
  await vi.waitFor(() => expect(button('tel-connect-btn').disabled).toBe(false));
  let finish!: (response: Response) => void;
  fetchMock.mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; }));
  button('tel-connect-btn').click();
  expect(button('tel-connect-btn').disabled).toBe(true);
  expect(button('tel-outbound-btn').disabled).toBe(true);
  finish(Response.json({ message: 'Provider unavailable' }, { status: 502 }));
  await vi.waitFor(() => expect($('#tel-feedback').textContent).toContain('Provider unavailable'));
  expect(button('tel-connect-btn').disabled).toBe(false);
});
