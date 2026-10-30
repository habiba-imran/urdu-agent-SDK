import { humanizationMarkup, personaControls, type Humanization } from './humanization';
import { providerCards, providerName, type PipelineAgent } from './providers';
type Entry = { models?: string[]; defaultModel?: string; voices?: string[]; defaultVoice?: string };
type Agent = PipelineAgent & { humanization?: Humanization; maxCallDurationSeconds?: number };
type Phone = { id: string; e164_number: string; assigned_agent_id?: string; agent_id?: string; routing_status?: string; disabled_at?: string };
type Setup = { tenantId: string; numbers: Phone[]; agents: Agent[]; capabilities: { languages: Record<string, { label: string; stt?: Record<string, Entry>; llm?: Record<string, Entry>; tts?: Record<string, Entry> }> } };

export function mountInboundPanel({ backendOrigin }: { backendOrigin: string }) {
  const root = document.querySelector<HTMLElement>('#inbound-root');
  if (!root) return;
  root.innerHTML = `<section class="panel inbound-panel" aria-labelledby="inbound-title">
    <div class="section-heading"><div><p class="eyebrow">03 / Receive calls</p><h2 id="inbound-title">Inbound calls</h2><p class="hint">Your number. Your agent. Every incoming conversation, connected.</p></div><button id="inbound-refresh" type="button">Refresh inbound settings</button></div>
    <p id="inbound-status" class="feedback" role="status" aria-live="polite">Load inbound settings to begin.</p>
    <div class="call-selection-grid"><label>01 · Phone number<select id="inbound-number" disabled></select></label><label>02 · Answering agent<select id="inbound-agent-picker" disabled></select></label></div>
    <input id="inbound-agent-id" type="hidden" readonly value="" />
    <div id="inbound-provider-cards" aria-label="Answering agent saved providers"></div>
    <div class="route-strip"><span class="route-indicator" aria-hidden="true"></span><p id="inbound-route" class="hint"></p><button id="inbound-assign" type="button" disabled>Save agent & enable routing</button></div>
    <details class="inbound-provider-details"><summary>Edit this agent’s providers & voice</summary><p class="hint">Changes apply to every new call using this agent. Save the number’s agent assignment before editing providers.</p>
    <div class="pipeline-grid">
      <label>Language<select id="inbound-language" disabled></select></label>
      <label>STT provider<select id="inbound-stt" disabled></select></label>
      <label>LLM provider<select id="inbound-llm" disabled></select></label>
      <label>TTS provider<select id="inbound-tts" disabled></select></label>
    </div>
    <div class="pipeline-grid model-grid">
      <label>STT model<select id="inbound-stt-model" disabled></select></label>
      <label>LLM model<select id="inbound-llm-model" disabled></select></label>
      <label>Voice<select id="inbound-voice" disabled></select></label>
    </div>
    <label>Maximum call duration (minutes)<input id="inbound-duration" type="number" min="1" max="120" step="any" value="30" disabled /></label>
    <p id="inbound-saved" class="hint"></p>
    <button id="inbound-save" type="button" disabled>Save for future inbound calls</button>
    <p class="hint">Allow 30 seconds after provider changes before calling. Active calls keep their current settings.</p></details>
  </section>`;
  const el = <T extends HTMLElement>(id: string) => root.querySelector<T>(`#inbound-${id}`)!;
  const select = (id: string) => el<HTMLSelectElement>(id);
  el('saved').insertAdjacentHTML('beforebegin', humanizationMarkup('inbound-persona'));
  const persona = personaControls(root);
  const duration = el<HTMLInputElement>("duration");
  const keys = ['number', 'language', 'stt', 'llm', 'tts', 'stt-model', 'llm-model', 'voice'];
  let setup: Setup | null = null;
  let busy = false;
  let dirty = false;
  const phone = () => setup?.numbers.find(number => number.id === select('number').value);
  const assigned = () => setup?.agents.find(agent => agent.id === (phone()?.assigned_agent_id || phone()?.agent_id));
  function fill(id: string, values: string[], preferred?: string, labels?: string[]) {
    select(id).replaceChildren(...values.map((value, index) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = labels?.[index] || (['stt', 'llm', 'tts'].includes(id) ? providerName(value) : value);
      return option;
    }));
    select(id).value = preferred && values.includes(preferred) ? preferred : values[0] || '';
  }
  function render() {
    const pendingAssignment = select('agent-picker').value !== assigned()?.id;
    select('agent-picker').disabled = busy || !setup?.agents.length || !phone() || !!phone()?.disabled_at;
    el<HTMLButtonElement>('assign').disabled = busy || !phone() || !!phone()?.disabled_at || !select('agent-picker').value;
    persona.lock(busy || !assigned() || !!phone()?.disabled_at);
    duration.disabled = busy || !assigned() || !!phone()?.disabled_at;
    for (const key of keys) select(key).disabled = busy || !select(key).options.length || (key !== 'number' && (!assigned() || !!phone()?.disabled_at));
    el<HTMLButtonElement>('save').disabled = busy || pendingAssignment || !assigned() || !!phone()?.disabled_at || keys.some(key => !select(key).value);
    el<HTMLButtonElement>('refresh').disabled = busy;
    el<HTMLButtonElement>('save').textContent = busy ? 'Working…' : 'Save for future inbound calls';
  }
  function models(preferred?: Agent) {
    const lang = setup?.capabilities.languages[select('language').value];
    for (const [id, entry, saved] of [
      ['stt-model', lang?.stt?.[select('stt').value], preferred?.stt_model],
      ['llm-model', lang?.llm?.[select('llm').value], preferred?.llm_model],
      ['voice', lang?.tts?.[select('tts').value], preferred?.tts_voice_id || preferred?.voice_id],
    ] as const) {
      const values = id === 'voice' ? entry?.voices : entry?.models;
      const fallback = id === 'voice' ? entry?.defaultVoice : entry?.defaultModel;
      fill(id, values?.length ? values : fallback ? [fallback] : id === 'stt-model' && entry ? ['default'] : [], saved || select(id).value || fallback);
    }
    render();
  }
  function providers(preferred?: Agent) {
    const lang = setup?.capabilities.languages[select('language').value];
    for (const key of ['stt', 'llm', 'tts'] as const) fill(key, Object.keys(lang?.[key] || {}), preferred?.[`${key}_provider`] || select(key).value);
    models(preferred);
  }
  function chooseNumber() {
    dirty = false;
    const agent = assigned();
    const number = phone();
    persona.set(agent?.humanization);
    duration.value = String((agent?.maxCallDurationSeconds ?? 1800) / 60);
    el<HTMLInputElement>('agent-id').value = number?.assigned_agent_id || number?.agent_id || '';
    fill('agent-picker', ['', ...(setup?.agents.map(item => item.id) || [])], agent?.id || '', ['Choose an agent', ...(setup?.agents.map(item => item.name || item.id) || [])]);
    el('provider-cards').innerHTML = providerCards(agent);
    root!.querySelector<HTMLElement>('.route-strip')!.dataset.ready = String(number?.routing_status === 'ready' && !number.disabled_at);
    el('route').textContent = number
      ? `Tenant ${setup!.tenantId} · Agent ${agent?.name || agent?.id || 'unassigned'} · Routing: ${number.routing_status || 'unknown'}. ${number.routing_status === 'ready' && !number.disabled_at ? 'Dial ' + number.e164_number + ' at least 30 seconds after saving.' : 'Inbound calls are blocked in this tenant until routing is ready. Use the telephony panel to review the route; existing routes in other tenants remain unchanged.'}`
      : 'No managed numbers in this tenant. Sync or import a number in the telephony panel, then refresh here.';
    const languages = Object.keys(setup?.capabilities.languages || {});
    fill('language', languages, agent?.agent_language, languages.map(key => setup!.capabilities.languages[key].label));
    providers(agent);
    el('saved').textContent = agent ? `Stored: STT ${agent.stt_provider}/${agent.stt_model} · LLM ${agent.llm_provider}/${agent.llm_model} · TTS ${agent.tts_provider}/${agent.tts_voice_id || agent.voice_id}` : 'Assign an agent in the telephony panel first.';
    el('status').textContent = 'Loaded stored settings. Review and save before your next call.';
  }
  async function request(path: string, body?: unknown) {
    const response = await fetch(`${backendOrigin}${path}`, { signal: AbortSignal.timeout(path.endsWith('/assign') ? 150000 : 45000),
      ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || result.error || `Request failed (${response.status})`);
    return result;
  }
  async function load() {
    if (busy) return;
    busy = true; render(); el('status').textContent = 'Loading this tenant’s inbound numbers and providers…';
    try {
      const current = select('number').value;
      setup = await request('/api/inbound/setup');
      const preferred = current || setup!.numbers.find(number => number.assigned_agent_id || number.agent_id)?.id;
      fill('number', setup!.numbers.map(number => number.id), preferred, setup!.numbers.map(number => `${number.e164_number} · ${number.routing_status || 'unknown'}`));
      chooseNumber();
      el('status').textContent = 'Select providers and save before your next call.';
    } catch (error) {
      setup = null;
      for (const key of keys) fill(key, []);
      fill('agent-picker', []);
      el('provider-cards').innerHTML = providerCards();
      root!.querySelector<HTMLElement>('.route-strip')!.dataset.ready = 'false';
      el('route').textContent = '';
      el('saved').textContent = '';
      el<HTMLInputElement>('agent-id').value = '';
      el('status').textContent = error instanceof Error ? error.message : 'Could not load inbound setup.';
    } finally { busy = false; render(); }
  }
  el('refresh').addEventListener('click', () => { void load(); });
  function refreshIfClean() {
    if (!root!.isConnected || busy) return;
    if (dirty) { el('status').textContent = 'Settings changed in another panel. Your edits are preserved; refresh to review the latest assignment before saving.'; return; }
    void load();
  }
  document.addEventListener('playground:agents-updated', refreshIfClean);
  document.addEventListener('playground:phone-updated', refreshIfClean);
  root.addEventListener('input', () => { dirty = true; });
  root.addEventListener('change', event => { if ((event.target as HTMLElement).id !== 'inbound-number') dirty = true; });
  select('agent-picker').addEventListener('change', () => {
    el('provider-cards').innerHTML = providerCards(setup?.agents.find(item => item.id === select('agent-picker').value));
    el('status').textContent = 'Save agent & enable routing to apply this assignment to incoming calls.';
    render();
  });
  el('assign').addEventListener('click', async () => {
    if (el<HTMLButtonElement>('assign').disabled) return;
    busy = true; render(); el('status').textContent = 'Saving assignment and configuring phone routing…';
    let message = '';
    try {
      const result = await request('/api/telephony/assign', { numberId: select('number').value, agentId: select('agent-picker').value });
      if (result.assigned?.assigned_agent_id !== select('agent-picker').value || result.assigned?.routing_status !== 'ready') throw new Error('The assignment or routing could not be verified.');
      message = 'Agent assigned and routing verified. Incoming calls will reach the selected agent.';
      document.dispatchEvent(new Event('playground:phone-updated'));
    } catch (error) {
      message = `${error instanceof Error ? error.message : 'Routing failed.'} Refresh to confirm the saved assignment and route before retrying.`;
    } finally {
      busy = false; await load(); el('status').textContent = message;
    }
  });
  persona.onChange(() => { el('status').textContent = 'Unsaved speech persona. Save before calling.'; });
  select('number').addEventListener('change', chooseNumber);
  select('language').addEventListener('change', () => { providers(); el('status').textContent = 'Unsaved changes. Save to use these settings on future calls.'; });
  for (const key of ['stt', 'llm', 'tts']) select(key).addEventListener('change', () => models());
  for (const key of keys.slice(2)) select(key).addEventListener('change', () => { render(); el('status').textContent = 'Unsaved changes. Save to use these settings on future calls.'; });
  duration.addEventListener('input', () => { duration.reportValidity(); });
  el('save').addEventListener('click', async () => {
    if (el<HTMLButtonElement>('save').disabled || !duration.reportValidity()) return;
    busy = true; render(); el('status').textContent = 'Saving and verifying the number’s assigned agent…';
    try {
      const result = await request(`/api/inbound/numbers/${encodeURIComponent(select('number').value)}/pipeline`, {
        expectedAgentId: assigned()?.id,
        agentLanguage: select('language').value, sttProvider: select('stt').value, sttModel: select('stt-model').value,
        llmProvider: select('llm').value, llmModel: select('llm-model').value, ttsProvider: select('tts').value, ttsVoiceId: select('voice').value,
        humanization: persona.value(),
        maxCallDurationSeconds: Math.round(Number(duration.value) * 60),
      });
      setup!.agents = setup!.agents.map(agent => agent.id === result.agent.id ? result.agent : agent);
      setup!.numbers = setup!.numbers.map(number => number.id === result.number.id ? result.number : number);
      chooseNumber();
      document.dispatchEvent(new CustomEvent('playground:agent-saved', { detail: result.agent }));
      el('status').textContent = result.routingReady ? result.message : 'Providers saved and verified. Inbound calls are still blocked: this number’s routing is not ready in the demo tenant.';
    } catch (error) { el('status').textContent = `${error instanceof Error ? error.message : 'Save failed.'} Save may have reached the server. Refresh to confirm stored settings before retrying.`; }
    finally { busy = false; render(); }
  });
  void load();
}
