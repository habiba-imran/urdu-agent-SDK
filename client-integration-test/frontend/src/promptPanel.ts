import { humanizationMarkup, personaControls, normalizedHumanization, type Humanization } from './humanization';
type AgentConfig = { id: string; name?: string; prompt: string; firstSpeaker: 'agent' | 'user'; greeting: string; humanization?: Humanization };

export function mountPromptPanel(opts: { backendOrigin: string; getAgentId: () => string; onBusyChange?: () => void }) {
  const root = document.querySelector<HTMLElement>('#prompt-root')!;
  root.innerHTML = `
    <section class="panel prompt-panel" id="prompt-section" aria-labelledby="prompt-heading">
      <div class="section-heading"><div><p class="eyebrow">02 / Instructions</p><h2 id="prompt-heading">Agent prompt</h2></div><span id="prompt-state" class="chip">Not loaded</span></div>
      <p class="hint">The saved instructions your agent uses. Save changes before starting a new session.</p>
      <label class="prompt-label" for="agent-prompt">System prompt <span id="prompt-count">0 characters</span></label>
      <textarea id="agent-prompt" dir="auto" rows="12" maxlength="24000" placeholder="Select an agent to load its saved prompt…" disabled></textarea>
      <div class="session-grid opening-grid">
        <label>Who speaks first?<select id="first-speaker" disabled><option value="agent">Agent starts</option><option value="user">Wait for caller</option></select></label>
        <label>Opening line <span class="optional">optional</span><input id="agent-greeting" maxlength="500" dir="auto" placeholder="Leave empty for a generated greeting" disabled /></label>
      </div>
      <div class="actions prompt-actions"><button id="save-prompt-btn" type="button" class="primary" disabled>Save prompt</button><button id="reset-prompt-btn" type="button" disabled>Reset changes</button><button id="reload-prompt-btn" type="button">Reload</button><button id="copy-prompt-btn" type="button" disabled>Copy prompt</button></div>
      <p id="prompt-feedback" class="feedback" role="status" aria-live="polite">Choose an agent to view its prompt.</p>
    </section>`;
  const el = <T extends HTMLElement>(id: string) => root.querySelector<T>(`#${id}`)!;
  const prompt = el<HTMLTextAreaElement>('agent-prompt');
  const speaker = el<HTMLSelectElement>('first-speaker');
  const greeting = el<HTMLInputElement>('agent-greeting');
  const save = el<HTMLButtonElement>('save-prompt-btn');
  const reset = el<HTMLButtonElement>('reset-prompt-btn');
  const reload = el<HTMLButtonElement>('reload-prompt-btn');
  const copy = el<HTMLButtonElement>('copy-prompt-btn');
  const feedback = el('prompt-feedback');
  let saved: AgentConfig | null = null;
  el('agent-prompt').insertAdjacentHTML('afterend', humanizationMarkup('web-persona'));
  const persona = personaControls(root);
  let busy = false;
  let locked = false;
  let requestId = 0;
  const personaDirty = () => !!saved && JSON.stringify(persona.value()) !== JSON.stringify(normalizedHumanization(saved.humanization));
  const isDirty = () => !!saved && (prompt.value !== saved.prompt || speaker.value !== saved.firstSpeaker || greeting.value !== saved.greeting || personaDirty());
  function update() {
    const current = !!saved && saved.id === opts.getAgentId().trim();
    const disabled = locked || busy || !current;
    prompt.disabled = speaker.disabled = disabled;
    persona.lock(disabled);
    greeting.disabled = disabled || speaker.value === 'user';
    save.disabled = disabled || !isDirty() || !prompt.value.trim();
    reset.disabled = disabled || !isDirty();
    reload.disabled = locked || busy || !opts.getAgentId().trim();
    copy.disabled = !prompt.value;
    save.textContent = busy ? 'Working…' : 'Save prompt';
    el('prompt-count').textContent = `${prompt.value.length.toLocaleString()} characters`;
    el('prompt-state').textContent = busy ? 'Loading / saving' : !current ? 'Not loaded' : isDirty() ? 'Unsaved changes' : 'Saved';
    root.setAttribute('aria-busy', String(busy));
  }
  function show(config: AgentConfig) {
    saved = config;
    prompt.value = config.prompt;
    speaker.value = config.firstSpeaker;
    greeting.value = config.greeting;
    persona.set(config.humanization);
    update();
  }
  async function request(agentId: string, init?: RequestInit): Promise<AgentConfig> {
    let response: Response;
    try {
      response = await fetch(`${opts.backendOrigin}/api/agents/${encodeURIComponent(agentId)}/config`, {
        ...init, headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(20000),
      });
    } catch (error) {
      if (error instanceof TypeError) throw new Error(`Cannot reach the client backend at ${opts.backendOrigin}. Check its terminal and allowed frontend origin.`);
      throw error;
    }
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); }
    catch { throw new Error(`Agent configuration returned a non-JSON response (HTTP ${response.status}). Check the backend/API logs.`); }
    if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
    return data;
  }
  async function load() {
    const id = opts.getAgentId().trim();
    const serial = ++requestId;
    saved = null;
    prompt.value = greeting.value = '';
    if (!id) { busy = false; feedback.textContent = 'Choose an agent to view its prompt.'; update(); opts.onBusyChange?.(); return; }
    busy = true;
    feedback.textContent = 'Loading saved agent instructions…';
    update();
    opts.onBusyChange?.();
    try {
      const data = await request(id);
      if (serial !== requestId || opts.getAgentId().trim() !== id) return;
      show(data);
      feedback.textContent = `Loaded ${data.name || id}. Changes apply to new sessions.`;
    } catch (error) {
      if (serial === requestId) feedback.textContent = `Could not load prompt: ${error instanceof Error ? error.message : String(error)}. Use Reload to retry.`;
    } finally {
      if (serial === requestId) { busy = false; update(); opts.onBusyChange?.(); }
    }
  }
  [prompt, speaker, greeting].forEach(input => input.addEventListener('input', () => {
    feedback.textContent = 'Unsaved changes. Save to use these instructions in the next session.';
    update();
    opts.onBusyChange?.();
  }));
  persona.onChange(() => { feedback.textContent = 'Unsaved speech persona. Save before starting a new call.'; update(); opts.onBusyChange?.(); });
  reset.addEventListener('click', () => { if (saved) show(saved); feedback.textContent = 'Restored the last saved instructions.'; opts.onBusyChange?.(); });
  reload.addEventListener('click', () => { if (!isDirty() || confirm('Reload the saved prompt and discard your unsaved changes?')) void load(); });
  save.addEventListener('click', async () => {
    if (save.disabled || !saved) return;
    const id = saved.id;
    busy = true;
    update();
    opts.onBusyChange?.();
    try {
      const data = await request(id, { method: 'POST', body: JSON.stringify({ prompt: prompt.value, firstSpeaker: speaker.value, greeting: greeting.value,
        ...((personaDirty() || saved.humanization) ? { humanization: persona.value() } : {}) }) });
      if (opts.getAgentId().trim() === id) {
        show(data);
        feedback.textContent = 'Prompt saved to the agent. Ready for your next session.';
      }
    } catch (error) {
      feedback.textContent = `Save failed: ${error instanceof Error ? error.message : String(error)}. Your edits are still here.`;
    } finally { busy = false; update(); opts.onBusyChange?.(); }
  });
  copy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(prompt.value); feedback.textContent = 'Prompt copied.'; }
    catch { feedback.textContent = 'Clipboard unavailable. Select the prompt text to copy it.'; }
  });
  update();
  return { load, isDirty, isBusy: () => busy, setLocked(value: boolean) { locked = value; update(); } };
}
