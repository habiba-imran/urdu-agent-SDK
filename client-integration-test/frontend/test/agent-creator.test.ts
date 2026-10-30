import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { mountAgentCreator } from '../src/agentCreator';

const capabilities = { languages: { en: { label: 'English',
  stt: { deepgram: { models: ['nova-3'] } }, llm: { groq: { models: ['fast'] }, anthropic: { models: ['claude'] } },
  tts: { cartesia: { voices: ['voice'] }, rime: { voices: ['rime-voice'] } } } } };
const el = <T extends HTMLElement = HTMLElement>(id: string) => document.querySelector<T>(`#create-${id}`)!;
let request: ReturnType<typeof vi.fn>;
let created: ReturnType<typeof vi.fn>;
function submit() { document.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true })); }
beforeEach(() => {
  document.body.innerHTML = '';
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  request = vi.fn(async () => Response.json({ agent: { id: 'new', name: 'Support' } }, { status: 201 }));
  created = vi.fn(async () => {});
  vi.stubGlobal('fetch', request);
  const creator = mountAgentCreator({ backendOrigin: 'http://localhost:3100', getCapabilities: () => capabilities,
    onCreated: created, onBusyChange: () => {} });
  creator.open();
  el<HTMLInputElement>('name').value = 'Support';
  el<HTMLTextAreaElement>('prompt').value = 'Help callers. <script>no HTML</script>';
});
afterEach(() => vi.unstubAllGlobals());

test('review is read-only, displays the actual providers, and confirmation creates once', async () => {
  el<HTMLSelectElement>('llm').value = 'anthropic'; el('llm').dispatchEvent(new Event('change'));
  el<HTMLSelectElement>('tts').value = 'rime'; el('tts').dispatchEvent(new Event('change'));
  expect(el<HTMLSelectElement>('llm-model').value).toBe('claude');
  expect(el<HTMLSelectElement>('tts-model').value).toBe('rime-voice');
  submit();
  expect(request).not.toHaveBeenCalled();
  expect(el('review').hidden).toBe(false);
  expect(el('review').textContent).toContain('Anthropic');
  expect(el('review').textContent).toContain('Rime');
  expect(el('review').querySelector('script')).toBeNull();
  submit(); submit();
  await vi.waitFor(() => expect(created).toHaveBeenCalledTimes(1));
  expect(request).toHaveBeenCalledTimes(1);
  const body = JSON.parse(request.mock.calls[0][1].body);
  expect(body.llmProvider).toBe('anthropic'); expect(body.ttsVoiceId).toBe('rime-voice');
});

test('back preserves the draft and a timeout cannot cause a duplicate creation', async () => {
  submit(); el('back').click();
  expect(el<HTMLTextAreaElement>('prompt').value).toContain('Help callers');
  request.mockRejectedValueOnce(new DOMException('Timed out', 'TimeoutError'));
  submit(); submit();
  await vi.waitFor(() => expect(el('feedback').textContent).toContain('may already have been created'));
  submit();
  expect(request).toHaveBeenCalledTimes(1);
  expect(created).not.toHaveBeenCalled();
});
