import { escapeHtml, providerCards, providerName, type PipelineAgent } from './providers';

type Entry = { models?: string[]; defaultModel?: string; voices?: string[]; defaultVoice?: string | null };
type Capabilities = { languages: Record<string, { label: string; stt?: Record<string, Entry>; llm?: Record<string, Entry>; tts?: Record<string, Entry> }> };

export function mountAgentCreator(opts: { backendOrigin: string; getCapabilities: () => Capabilities | null;
  onCreated: (agent: PipelineAgent) => Promise<void>; onBusyChange: () => void }) {
  const dialog = document.createElement('dialog');
  dialog.className = 'agent-dialog';
  dialog.setAttribute('aria-labelledby', 'create-title');
  dialog.innerHTML = `<form id="create-agent-form">
    <div class="section-heading"><div><p class="eyebrow">New agent</p><h2 id="create-title">Give your agent a voice.</h2></div><button type="button" id="create-close" aria-label="Close agent creation">×</button></div>
    <p class="hint">Set its instructions and providers, then review everything before creating.</p>
    <div id="create-fields" class="creator-fields">
      <label>Agent name<input id="create-name" maxlength="120" required placeholder="e.g. Customer support" /></label>
      <label>Instructions<textarea id="create-prompt" maxlength="24000" required rows="5" placeholder="Describe who the agent is and how it should help callers…"></textarea></label>
      <div class="session-grid"><label>Who speaks first?<select id="create-speaker"><option value="agent">Agent starts</option><option value="user">Wait for caller</option></select></label><label>Opening line (optional)<input id="create-greeting" maxlength="500" placeholder="Hi, how can I help?" /></label></div>
      <label>Language<select id="create-language" required></select></label>
      <div class="creator-providers">${['stt', 'llm', 'tts'].map(key => `<fieldset><legend>${key.toUpperCase()}</legend><label>Provider<select id="create-${key}" required></select></label><label>${key === 'tts' ? 'Voice' : 'Model'}<select id="create-${key}-model" required></select></label></fieldset>`).join('')}</div>
    </div>
    <div id="create-review" hidden></div>
    <p id="create-feedback" class="feedback" role="status" aria-live="polite"></p>
    <div class="dialog-actions"><button type="button" id="create-back" hidden>Back to editing</button><button type="submit" id="create-submit" class="primary">Review agent</button></div>
  </form>`;
  document.body.append(dialog);
  const el = <T extends HTMLElement>(key: string) => dialog.querySelector<T>(`#create-${key}`)!;
  const select = (key: string) => el<HTMLSelectElement>(key);
  let reviewing = false;
  let busy = false;
  let uncertain = false;
  const fill = (key: string, values: string[], label = (value: string) => value, preferred?: string) => {
    select(key).replaceChildren(...values.map(value => { const option = document.createElement('option'); option.value = value; option.textContent = label(value); return option; }));
    select(key).value = preferred && values.includes(preferred) ? preferred : values[0] || '';
  };
  function models(key: 'stt' | 'llm' | 'tts') {
    const entry = opts.getCapabilities()?.languages[select('language').value]?.[key]?.[select(key).value];
    const values = key === 'tts' ? entry?.voices : entry?.models;
    const fallback = key === 'tts' ? entry?.defaultVoice : entry?.defaultModel || (entry ? 'default' : '');
    fill(`${key}-model`, values?.length ? values : fallback ? [fallback] : [], undefined, fallback || undefined);
  }
  function providers() {
    const language = opts.getCapabilities()?.languages[select('language').value];
    for (const key of ['stt', 'llm', 'tts'] as const) { fill(key, Object.keys(language?.[key] || {}), providerName); models(key); }
  }
  function selection() {
    return { name: el<HTMLInputElement>('name').value.trim(), prompt: el<HTMLTextAreaElement>('prompt').value,
      firstSpeaker: select('speaker').value, greeting: el<HTMLInputElement>('greeting').value,
      agentLanguage: select('language').value, sttProvider: select('stt').value, sttModel: select('stt-model').value,
      llmProvider: select('llm').value, llmModel: select('llm-model').value,
      ttsProvider: select('tts').value, ttsVoiceId: select('tts-model').value };
  }
  function edit() {
    reviewing = false; el('fields').hidden = false; el('review').hidden = true;
    el('back').hidden = true; el('submit').textContent = 'Review agent'; el('feedback').textContent = '';
  }
  select('language').addEventListener('change', providers);
  for (const key of ['stt', 'llm', 'tts'] as const) select(key).addEventListener('change', () => models(key));
  select('speaker').addEventListener('change', () => { el<HTMLInputElement>('greeting').disabled = select('speaker').value === 'user'; });
  el('back').addEventListener('click', edit);
  el('close').addEventListener('click', () => { if (!busy) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.querySelector('form')!.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || uncertain || !dialog.querySelector('form')!.reportValidity()) return;
    const draft = selection();
    if (!draft.name || !draft.prompt.trim()) { el('feedback').textContent = 'Enter a name and instructions.'; return; }
    if (!reviewing) {
      reviewing = true;
      el('review').innerHTML = `<p class="eyebrow">Review & confirm</p><h3>${escapeHtml(draft.name)}</h3><p class="hint">${escapeHtml(opts.getCapabilities()?.languages[draft.agentLanguage]?.label)} · ${draft.firstSpeaker === 'agent' ? 'Agent speaks first' : 'Waits for caller'}</p>${providerCards({ stt_provider: draft.sttProvider, stt_model: draft.sttModel, llm_provider: draft.llmProvider, llm_model: draft.llmModel, tts_provider: draft.ttsProvider, tts_voice_id: draft.ttsVoiceId })}<p class="review-prompt">${escapeHtml(draft.prompt)}</p><p class="hint">Opening line: ${escapeHtml(draft.firstSpeaker === 'user' ? 'Wait for caller' : draft.greeting || 'Generated greeting')}</p>`;
      el('fields').hidden = true; el('review').hidden = false; el('back').hidden = false;
      el('submit').textContent = 'Confirm & create agent'; return;
    }
    busy = true; opts.onBusyChange();
    dialog.querySelectorAll<HTMLButtonElement>('button').forEach(button => { button.disabled = true; });
    el('feedback').textContent = 'Creating your agent…';
    try {
      const response = await fetch(`${opts.backendOrigin}/api/agents`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft), signal: AbortSignal.timeout(45000) });
      const text = await response.text();
      let result;
      try { result = JSON.parse(text); } catch { throw new Error(`Unexpected response (HTTP ${response.status}).`); }
      if (!response.ok) throw new Error(result.message || result.error || `HTTP ${response.status}`);
      // Creation succeeded even if refreshing another panel fails. Never submit again here.
      uncertain = true;
      await opts.onCreated(result.agent);
      dialog.querySelector('form')!.reset();
      dialog.close();
    } catch (error) {
      uncertain = true;
      el('feedback').textContent = `${error instanceof Error ? error.message : 'Creation failed.'} Refresh agents before trying again; the agent may already have been created.`;
    } finally {
      busy = false;
      el<HTMLButtonElement>('close').disabled = false;
      opts.onBusyChange();
    }
  });
  return { isBusy: () => busy, open() {
    if (!opts.getCapabilities()) return;
    reviewing = false; uncertain = false; edit();
    dialog.querySelectorAll<HTMLButtonElement>('button').forEach(button => { button.disabled = false; });
    const languages = opts.getCapabilities()!.languages;
    fill('language', Object.keys(languages), value => languages[value].label); providers();
    dialog.showModal(); el('name').focus();
  } };
}
