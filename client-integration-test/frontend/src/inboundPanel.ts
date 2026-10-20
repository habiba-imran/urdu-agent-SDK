type Entry = { models?: string[]; defaultModel?: string; voices?: string[]; defaultVoice?: string };
type Agent = Record<string, string>;
type Phone = { id: string; e164_number: string; assigned_agent_id?: string; agent_id?: string; routing_status?: string; disabled_at?: string };
type Setup = { tenantId: string; numbers: Phone[]; agents: Agent[]; capabilities: { languages: Record<string, { label: string; stt?: Record<string, Entry>; llm?: Record<string, Entry>; tts?: Record<string, Entry> }> } };

export function mountInboundPanel({ backendOrigin }: { backendOrigin: string }) {
  const root = document.querySelector<HTMLElement>('#inbound-root');
  if (!root) return;
  root.innerHTML = `<section class="panel inbound-panel" aria-labelledby="inbound-title">
    <h2 id="inbound-title">Inbound call settings</h2>
    <p class="hint">Choose a managed phone number, then save its agent’s language, providers, models and voice before calling. Saved settings persist for future calls and also apply wherever that same agent is used.</p>
    <div class="actions"><button id="inbound-refresh" type="button">Refresh inbound settings</button></div>
    <p id="inbound-status" class="feedback" role="status" aria-live="polite">Load inbound settings to begin.</p>
    <label>Inbound number<select id="inbound-number" disabled></select></label>
    <label>Assigned agent ID<input id="inbound-agent-id" readonly value="" placeholder="No assigned agent" /></label>
    <p id="inbound-route" class="hint"></p>
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
    <p id="inbound-saved" class="hint"></p>
    <button id="inbound-save" type="button" disabled>Save for future inbound calls</button>
    <p class="hint">Allow 30 seconds after saving before calling. Saving changes the assigned agent configuration. It does not create or move phone routing. Gemini can be changed explicitly to another enabled LLM here.</p>
  </section>`;
  const el = <T extends HTMLElement>(id: string) => root.querySelector<T>(`#inbound-${id}`)!;
  const select = (id: string) => el<HTMLSelectElement>(id);
  const keys = ['number', 'language', 'stt', 'llm', 'tts', 'stt-model', 'llm-model', 'voice'];
  let setup: Setup | null = null;
  let busy = false;
  const phone = () => setup?.numbers.find(number => number.id === select('number').value);
  const assigned = () => setup?.agents.find(agent => agent.id === (phone()?.assigned_agent_id || phone()?.agent_id));
  function fill(id: string, values: string[], preferred?: string, labels?: string[]) {
    select(id).replaceChildren(...values.map((value, index) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = labels?.[index] || value;
      return option;
    }));
    select(id).value = preferred && values.includes(preferred) ? preferred : values[0] || '';
  }
  function render() {
    for (const key of keys) select(key).disabled = busy || !select(key).options.length || (key !== 'number' && (!assigned() || !!phone()?.disabled_at));
    el<HTMLButtonElement>('save').disabled = busy || !assigned() || !!phone()?.disabled_at || keys.some(key => !select(key).value);
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
    const agent = assigned();
    const number = phone();
    el<HTMLInputElement>('agent-id').value = number?.assigned_agent_id || number?.agent_id || '';
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
    const response = await fetch(`${backendOrigin}${path}`, { signal: AbortSignal.timeout(45000),
      ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || result.error || `Request failed (${response.status})`);
    return result;
  }
  el('refresh').addEventListener('click', async () => {
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
      el('route').textContent = '';
      el('saved').textContent = '';
      el<HTMLInputElement>('agent-id').value = '';
      el('status').textContent = error instanceof Error ? error.message : 'Could not load inbound setup.';
    } finally { busy = false; render(); }
  });
  select('number').addEventListener('change', chooseNumber);
  select('language').addEventListener('change', () => { providers(); el('status').textContent = 'Unsaved changes. Save to use these settings on future calls.'; });
  for (const key of ['stt', 'llm', 'tts']) select(key).addEventListener('change', () => models());
  for (const key of keys.slice(2)) select(key).addEventListener('change', () => { render(); el('status').textContent = 'Unsaved changes. Save to use these settings on future calls.'; });
  el('save').addEventListener('click', async () => {
    if (el<HTMLButtonElement>('save').disabled) return;
    busy = true; render(); el('status').textContent = 'Saving and verifying the number’s assigned agent…';
    try {
      const result = await request(`/api/inbound/numbers/${encodeURIComponent(select('number').value)}/pipeline`, {
        agentLanguage: select('language').value, sttProvider: select('stt').value, sttModel: select('stt-model').value,
        llmProvider: select('llm').value, llmModel: select('llm-model').value, ttsProvider: select('tts').value, ttsVoiceId: select('voice').value,
      });
      setup!.agents = setup!.agents.map(agent => agent.id === result.agent.id ? result.agent : agent);
      setup!.numbers = setup!.numbers.map(number => number.id === result.number.id ? result.number : number);
      chooseNumber();
      el('status').textContent = result.routingReady ? result.message : 'Providers saved and verified. Inbound calls are still blocked: this number’s routing is not ready in the demo tenant.';
    } catch (error) { el('status').textContent = `${error instanceof Error ? error.message : 'Save failed.'} Save may have reached the server. Refresh to confirm stored settings before retrying.`; }
    finally { busy = false; render(); }
  });
}
