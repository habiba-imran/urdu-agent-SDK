import {
  AwaazLabsUvaVoice,
  AwaazLabsUvaVoiceError,
  type MetricsEvent,
  type TranscriptEvent,
} from '@awaazlabs-uva/voice';
import { mountTelephonyPanel } from './telephonyPanel';
import { mountPromptPanel } from './promptPanel';
import { mountInboundPanel } from './inboundPanel';
import './style.css';

type ProviderCapabilityEntry = {
  state: 'enabled';
  models?: string[];
  defaultModel?: string;
  voices?: string[];
  defaultVoice?: string | null;
};

type LanguageCapabilities = {
  label: string;
  stt?: Record<string, ProviderCapabilityEntry>;
  llm?: Record<string, ProviderCapabilityEntry>;
  tts?: Record<string, ProviderCapabilityEntry>;
};

type ProviderCapabilities = {
  languages: Record<string, LanguageCapabilities>;
};

type AgentRecord = {
  id: string;
  name?: string;
  agent_language?: string;
  stt_provider?: string;
  stt_model?: string;
  llm_provider?: string;
  llm_model?: string;
  tts_provider?: string;
  tts_voice_id?: string;
  voice_id?: string;
};

type DebugLevel = 'info' | 'metric' | 'warn' | 'error';

type DebugEntry = {
  t: number;
  level: DebugLevel;
  message: string;
  detail?: string;
};

type TimingSnapshot = {
  clickAt: number | null;
  pipelineDoneAt: number | null;
  connectedAt: number | null;
  /** SDK sessionEndpoint fetch duration (mint path). */
  sessionMintMs: number | null;
  /** SDK room.connect duration (LiveKit join). */
  livekitConnectMs: number | null;
  firstAgentSpeakingAt: number | null;
  firstAgentTranscriptAt: number | null;
  firstTurnLatencyAt: number | null;
  lastMetricsAt: number | null;
  /** Wall time of last finalized user transcript (for perceived turn gap). */
  lastUserFinalAt: number | null;
  /** Wall time of next agent_speaking after that user final. */
  lastAgentReplyAudioAt: number | null;
  lastTurnE2eMs: number | null;
  lastTurnLlmMs: number | null;
  lastTurnTtsTtfbMs: number | null;
  lastTurnSttMs: number | null;
};

type AppState = {
  status: string;
  transcript: TranscriptEvent[];
  speaking: boolean;
  agentSpeaking: boolean;
  micMuted: boolean;
  thinking: boolean;
  latestMetrics: MetricsEvent | null;
  errors: string[];
  audioBlocked: boolean;
  audioReady: boolean;
  pipelineText: string;
  packageLabel: string;
  debugLog: DebugEntry[];
  timing: TimingSnapshot;
};

const ERROR_TAXONOMY: Array<{ code: string; meaning: string }> = [
  { code: 'quota_exceeded', meaning: 'tenant cap reached' },
  { code: 'rate_limit', meaning: 'too many session requests — back off' },
  { code: 'provider_limit', meaning: 'upstream voice/LLM provider limit' },
  { code: 'worker_not_ready', meaning: 'voice worker not ready yet' },
  { code: 'agent_not_found', meaning: 'wrong agentId or tenant' },
  { code: 'timeout', meaning: 'host did not answer within fetchTimeoutMs' },
  { code: 'token_refresh_failed', meaning: 'refresh rejected or retries exhausted' },
  { code: 'session_failed', meaning: 'host misconfiguration or upstream failure' },
];

const envDefaults = {
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY ?? '',
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT || 'http://localhost:3100/api/voice/session',
  refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT ?? '',
  agentId: import.meta.env.VITE_UVA_AGENT_ID ?? '',
  fetchTimeoutMs: Number(import.meta.env.VITE_UVA_FETCH_TIMEOUT_MS || 15000),
};

const backendOrigin = (() => {
  try {
    return new URL(envDefaults.sessionEndpoint || 'http://localhost:3100/api/voice/session').origin;
  } catch {
    return 'http://localhost:3100';
  }
})();

const emptyTiming = (): TimingSnapshot => ({
  clickAt: null,
  pipelineDoneAt: null,
  connectedAt: null,
  sessionMintMs: null,
  livekitConnectMs: null,
  firstAgentSpeakingAt: null,
  firstAgentTranscriptAt: null,
  firstTurnLatencyAt: null,
  lastMetricsAt: null,
  lastUserFinalAt: null,
  lastAgentReplyAudioAt: null,
  lastTurnE2eMs: null,
  lastTurnLlmMs: null,
  lastTurnTtsTtfbMs: null,
  lastTurnSttMs: null,
});

const state: AppState = {
  status: 'idle',
  transcript: [],
  speaking: false,
  agentSpeaking: false,
  micMuted: false,
  thinking: false,
  latestMetrics: null,
  errors: [],
  audioBlocked: false,
  audioReady: false,
  pipelineText: 'Loading provider capabilities…',
  packageLabel: '@awaazlabs-uva/voice (resolving…)',
  debugLog: [],
  timing: emptyTiming(),
};

let agent: AwaazLabsUvaVoice | null = null;
let capabilities: ProviderCapabilities | null = null;
let agents: AgentRecord[] = [];
let sessionBusy = false;
let pipelineBusy = false;
let micBusy = false;
let bootstrapBusy = false;
let servicesReady = false;
let servicesReadyAt = 0;
const savedPipelines = new Map<string, string>();
const MAX_DEBUG_ENTRIES = 200;

const appRoot = document.querySelector<HTMLDivElement>('#app');
if (!appRoot) {
  throw new Error('App root not found');
}

appRoot.innerHTML = `
  <main class="shell">
    <header class="header">
      <p class="brand">AwaazLabs UVA</p>
      <p class="eyebrow">Developer playground</p>
      <h1>A conversation starts here<span class="accent">.</span></h1>
      <p>Configure your agent, shape its instructions, and hear it in action.</p>
      <p id="package-badge" class="package-badge">${escapeHtml(state.packageLabel)}</p>
    </header>
    <nav class="workspace-nav" aria-label="Playground sections"><a href="#session-section">Voice session</a><a href="#prompt-section">Agent prompt</a><a href="#transcript-section">Transcript</a><a href="#diagnostics-section">Diagnostics</a><a href="#inbound-root">Inbound settings</a><a href="#telephony-root">Telephony</a></nav>

    <div class="workspace-grid">
    <section class="panel session-panel" id="session-section">
      <div class="section-heading"><div><p class="eyebrow">01 / Configuration</p><h2>Voice session</h2></div><button id="reload-agents-btn" type="button">Refresh agents</button></div>
      <form id="voice-form" class="form" novalidate>
        <p id="services-status" class="hint" role="status">Preparing backend services… First launch can take a moment.</p>
        <label>Test agent<select id="agent-picker"><option value="">Loading agents…</option></select></label>
        <details class="connection-details"><summary>Connection settings</summary>
        <div class="session-grid">
          <label>
            Publishable key
            <input id="publishable-key" name="publishableKey" required value="${escapeHtml(envDefaults.publishableKey)}" autocomplete="off" />
          </label>
          <label>
            Agent ID
            <input id="agent-id" name="agentId" required value="${escapeHtml(envDefaults.agentId)}" autocomplete="off" />
          </label>
          <label>
            Session endpoint
            <input id="session-endpoint" name="sessionEndpoint" required type="url" value="${escapeHtml(envDefaults.sessionEndpoint)}" />
          </label>
          <label>
            Refresh endpoint
            <input id="refresh-endpoint" name="refreshEndpoint" value="${escapeHtml(envDefaults.refreshEndpoint)}" />
          </label>
          <label>
            fetchTimeoutMs
            <input id="fetch-timeout-ms" name="fetchTimeoutMs" type="number" min="1000" step="1000" value="${escapeHtml(String(envDefaults.fetchTimeoutMs))}" />
          </label>
        </div>
        </details>

        <div class="pipeline-grid">
          <label>
            Language
            <select id="agent-language" name="agentLanguage" disabled>
              <option value="">Loading…</option>
            </select>
          </label>
          <label>
            STT
            <select id="stt-provider" name="sttProvider" disabled>
              <option value="">Loading…</option>
            </select>
          </label>
          <label>
            LLM
            <select id="llm-provider" name="llmProvider" disabled>
              <option value="">Loading…</option>
            </select>
          </label>
          <label>
            TTS
            <select id="tts-provider" name="ttsProvider" disabled>
              <option value="">Loading…</option>
            </select>
          </label>
        </div>

        <div class="pipeline-grid model-grid">
          <label>STT model<select id="stt-model" name="sttModel" disabled><option value="">Loading…</option></select></label>
          <label>LLM model<select id="llm-model" name="llmModel" disabled><option value="">Loading…</option></select></label>
          <label>Voice<select id="tts-voice" name="ttsVoiceId" disabled><option value="">Loading…</option></select></label>
        </div>

        <p id="pipeline-summary" class="hint">Loading provider capabilities…</p>
        <p class="hint">Changes update the selected test agent for its next session.</p>

        <div class="actions">
          <button id="connect-btn" type="submit">Start conversation</button>
          <button id="disconnect-btn" type="button" disabled>End session</button>
          <button id="mute-btn" type="button" disabled>Mute mic</button>
          <button id="apply-pipeline-btn" type="button">Apply pipeline</button>
        </div>
        <p id="session-feedback" class="feedback" role="status" aria-live="polite">Select an agent and review its prompt before connecting.</p>
        <details class="connection-details"><summary>Test connection timeout</summary><p class="hint">Temporarily use an endpoint that never replies, then start a session to test the SDK timeout.</p><div class="actions"><button id="timeout-smoke-btn" type="button">Arm timeout test</button><button id="restore-endpoint-btn" type="button">Restore endpoint</button></div></details>
      </form>
      <p class="hint">
        Backend signs mint/refresh with HMAC and uses <code>@awaazlabs-uva/agents</code>
        for provider capabilities + pipeline PATCH. Browser never holds the tenant secret.
      </p>
    </section>
    <div id="prompt-root"></div>
    </div>

    <section class="grid stats-grid">
      <article class="panel">
        <h2>Status</h2>
        <p id="status-text" class="stat" role="status">idle</p>
      </article>
      <article class="panel">
        <h2>Caller</h2>
        <p id="speaking-text" class="stat">No</p>
      </article>
      <article class="panel">
        <h2>Agent</h2>
        <p id="agent-speaking-text" class="stat">No</p>
      </article>
      <article class="panel">
        <h2>Mic</h2>
        <p id="mic-text" class="stat">Off</p>
      </article>
    </section>

    <section class="panel transcript-panel" id="transcript-section">
      <div class="section-heading"><div><p class="eyebrow">03 / Live conversation</p><h2>Transcript</h2></div><div class="actions"><button id="copy-transcript-btn" type="button" disabled>Copy transcript</button><button id="download-transcript-btn" type="button" disabled>Download</button></div></div>
      <p class="hint">Segments with the same <code>id</code> replace earlier partials (SDK contract).</p>
      <ul id="transcript-list" class="transcript-list" aria-label="Conversation transcript"></ul>
    </section>

    <section class="panel debug-panel" id="diagnostics-section">
      <div class="debug-header">
        <h2>Connection and turn timings</h2>
        <div class="debug-actions">
          <button id="copy-debug-btn" type="button">Copy</button>
          <button id="clear-debug-btn" type="button">Clear</button>
        </div>
      </div>
      <p class="hint debug-hint">
        Cold-start cards are from Connect click. <strong>Session mint</strong> vs
        <strong>LiveKit join</strong> split <code>room_connected</code>.
        <strong>Turn e2e</strong> is a worker timing proxy; TTS TTFB and
        <code>agent_speaking</code> are diagnostics, not caller-acoustic FUAW.
        Room connection and playback readiness are separate. Back-to-back user finals
        may revise an in-flight reply; check the outcome and generation IDs.
      </p>
      <p id="playback-status" class="hint" role="status" aria-atomic="true">Playback not ready</p>
      <div id="timing-summary" class="timing-grid"></div>
      <pre id="debug-log" class="log-box debug-log">Waiting for Connect…</pre>
      <details class="metrics-details">
        <summary>Latest SDK metrics / turn_latency</summary>
        <pre id="metrics-output" class="log-box metrics-nested">No metrics received yet.</pre>
      </details>
      <details class="metrics-details">
        <summary>Errors this session (SDK taxonomy)</summary>
        <pre id="error-output" class="log-box metrics-nested">No errors.</pre>
        <ul class="taxonomy-list">
          ${ERROR_TAXONOMY.map((row) => `<li><code>${row.code}</code> — ${escapeHtml(row.meaning)}</li>`).join('')}
        </ul>
      </details>
    </section>

    <div id="audio-unlock-banner" class="audio-unlock-banner">
      <p>Audio blocked by the browser — call <code>startAudio()</code> from a click.</p>
      <button id="unlock-audio-btn" type="button">Unlock audio</button>
    </div>

    <details class="telephony-disclosure" id="telephony-section"><summary>Phone calls & numbers / Telephony SDK</summary><div id="telephony-root"></div></details>
    <footer>Built with AwaazLabs UVA · Voice, Agents & Telephony SDKs</footer>
  </main>
`;

function requireEl<T extends Element>(selector: string): T {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`Missing element ${selector}`);
  return el;
}

const form = requireEl<HTMLFormElement>('#voice-form');
const statusText = requireEl<HTMLElement>('#status-text');
const speakingText = requireEl<HTMLElement>('#speaking-text');
const agentSpeakingText = requireEl<HTMLElement>('#agent-speaking-text');
const micText = requireEl<HTMLElement>('#mic-text');
const packageBadge = requireEl<HTMLElement>('#package-badge');
const transcriptList = requireEl<HTMLUListElement>('#transcript-list');
const metricsOutput = requireEl<HTMLElement>('#metrics-output');
const errorOutput = requireEl<HTMLElement>('#error-output');
const debugLogEl = requireEl<HTMLElement>('#debug-log');
const timingSummaryEl = requireEl<HTMLElement>('#timing-summary');
const disconnectButton = requireEl<HTMLButtonElement>('#disconnect-btn');
const muteButton = requireEl<HTMLButtonElement>('#mute-btn');
const timeoutSmokeBtn = requireEl<HTMLButtonElement>('#timeout-smoke-btn');
const clearDebugBtn = requireEl<HTMLButtonElement>('#clear-debug-btn');
const copyDebugBtn = requireEl<HTMLButtonElement>('#copy-debug-btn');
const audioUnlockBanner = requireEl<HTMLDivElement>('#audio-unlock-banner');
const unlockAudioBtn = requireEl<HTMLButtonElement>('#unlock-audio-btn');
const languageSelect = requireEl<HTMLSelectElement>('#agent-language');
const sttSelect = requireEl<HTMLSelectElement>('#stt-provider');
const llmSelect = requireEl<HTMLSelectElement>('#llm-provider');
const ttsSelect = requireEl<HTMLSelectElement>('#tts-provider');
const pipelineSummary = requireEl<HTMLElement>('#pipeline-summary');
const sessionEndpointInput = requireEl<HTMLInputElement>('#session-endpoint');
const fetchTimeoutInput = requireEl<HTMLInputElement>('#fetch-timeout-ms');
const agentIdInput = requireEl<HTMLInputElement>('#agent-id');
const agentPicker = requireEl<HTMLSelectElement>('#agent-picker');
const sttModelSelect = requireEl<HTMLSelectElement>('#stt-model');
const llmModelSelect = requireEl<HTMLSelectElement>('#llm-model');
const voiceSelect = requireEl<HTMLSelectElement>('#tts-voice');
const connectButton = requireEl<HTMLButtonElement>('#connect-btn');
const applyPipelineButton = requireEl<HTMLButtonElement>('#apply-pipeline-btn');
const reloadAgentsButton = requireEl<HTMLButtonElement>('#reload-agents-btn');
const sessionFeedback = requireEl<HTMLElement>('#session-feedback');
const promptPanel = mountPromptPanel({ backendOrigin, getAgentId: () => agentIdInput.value, onBusyChange: () => render() });
document.querySelector('#telephony-section')!.insertAdjacentHTML('beforebegin', '<div id="inbound-root"></div>');
mountInboundPanel({ backendOrigin });
let selectedAgentId = agentIdInput.value;

function selectedPipeline() {
  if (!languageSelect.value || !sttSelect.value || !llmSelect.value || !ttsSelect.value || !llmModelSelect.value || !voiceSelect.value) {
    throw new Error('Select an enabled language, providers, models, and voice before connecting.');
  }
  return {
    agentLanguage: languageSelect.value, sttProvider: sttSelect.value,
    llmProvider: llmSelect.value, ttsProvider: ttsSelect.value,
    sttModel: sttModelSelect.value || 'default', llmModel: llmModelSelect.value, ttsVoiceId: voiceSelect.value,
  };
}

function rememberAgentPipeline(record: AgentRecord) {
  const { agent_language, stt_provider, stt_model, llm_provider, llm_model, tts_provider } = record;
  const voice = record.tts_voice_id || record.voice_id;
  if (agent_language && stt_provider && stt_model && llm_provider && llm_model && tts_provider && voice) {
    savedPipelines.set(record.id, JSON.stringify({ agentLanguage: agent_language, sttProvider: stt_provider,
      llmProvider: llm_provider, ttsProvider: tts_provider, sttModel: stt_model, llmModel: llm_model, ttsVoiceId: voice }));
  }
}

async function applySelectedPipeline(agentId: string) {
  const selection = selectedPipeline();
  const result = await preparePipeline(agentId, selection);
  savedPipelines.set(agentId, JSON.stringify(selection));
  const record = agents.find(item => item.id === agentId);
  if (record) Object.assign(record, { agent_language: selection.agentLanguage, stt_provider: selection.sttProvider,
    stt_model: selection.sttModel, llm_provider: selection.llmProvider, llm_model: selection.llmModel,
    tts_provider: selection.ttsProvider, tts_voice_id: selection.ttsVoiceId });
  return result;
}

async function prepareServices() {
  servicesReady = false;
  requireEl<HTMLElement>('#services-status').textContent = 'Preparing backend services… First launch can take a moment.';
  try {
    const response = await fetch(`${backendOrigin}/api/demo/ready`, { signal: AbortSignal.timeout(60000) });
    const result = await response.json();
    servicesReady = response.ok && result.ready === true;
    if (!servicesReady) throw new Error('Backend services are unavailable. Use Refresh agents to retry preparation.');
    servicesReadyAt = performance.now();
    requireEl<HTMLElement>('#services-status').textContent = 'Backend services ready.';
  } catch (error) {
    requireEl<HTMLElement>('#services-status').textContent = 'Backend services are unavailable. Use Refresh agents to retry preparation.';
    throw error;
  }
}

function refillModels(preferred?: AgentRecord) {
  const lang = capabilities?.languages[languageSelect.value];
  for (const [select, values, fallback, current] of [
    [sttModelSelect, lang?.stt?.[sttSelect.value]?.models, lang?.stt?.[sttSelect.value]?.defaultModel || 'default', preferred?.stt_model],
    [llmModelSelect, lang?.llm?.[llmSelect.value]?.models, lang?.llm?.[llmSelect.value]?.defaultModel, preferred?.llm_model],
    [voiceSelect, lang?.tts?.[ttsSelect.value]?.voices, lang?.tts?.[ttsSelect.value]?.defaultVoice, preferred?.tts_voice_id || preferred?.voice_id],
  ] as const) {
    const options = values?.length ? values : fallback ? [fallback] : [];
    fillSelect(select, options.map(value => ({ value, label: value })), pickPreferred(options, current || select.value, fallback || undefined));
    select.disabled = !options.length;
  }
}

async function changeAgent(id: string) {
  if (promptPanel.isDirty() && !confirm('Switch agents and discard unsaved prompt changes?')) {
    agentIdInput.value = selectedAgentId;
    agentPicker.value = selectedAgentId;
    return;
  }
  selectedAgentId = id;
  agentIdInput.value = id;
  agentPicker.value = id;
  const preferred = agents.find(item => item.id === id);
  if (preferred && capabilities) {
    if (capabilities.languages[preferred.agent_language || '']) languageSelect.value = preferred.agent_language!;
    refillProvidersForLanguage(languageSelect.value, { preferredStt: preferred.stt_provider, preferredLlm: preferred.llm_provider, preferredTts: preferred.tts_provider });
    refillModels(preferred);
    updatePipelineSummary();
  }
  await promptPanel.load();
}
agentPicker.addEventListener('change', () => { void changeAgent(agentPicker.value); });
agentIdInput.addEventListener('change', () => { void changeAgent(agentIdInput.value.trim()); });
reloadAgentsButton.addEventListener('click', () => {
  if (!promptPanel.isDirty() || confirm('Refresh agents and discard unsaved prompt changes?')) void bootstrapPipelineControls();
});
applyPipelineButton.addEventListener('click', async () => {
  if (pipelineBusy || sessionBusy || agent?.isConnected) return;
  pipelineBusy = true;
  render();
  sessionFeedback.textContent = 'Applying pipeline to the selected agent…';
  try {
    if (!agentIdInput.value.trim()) throw new Error('Choose an agent first.');
    const result = await applySelectedPipeline(agentIdInput.value.trim());
    state.pipelineText = formatAppliedPipeline(result.applied);
    sessionFeedback.textContent = 'Pipeline saved. Ready for your next session.';
  } catch (error) {
    renderError(error);
    sessionFeedback.textContent = error instanceof Error ? error.message : 'Could not apply pipeline.';
  } finally { pipelineBusy = false; render(); }
});
requireEl<HTMLButtonElement>('#restore-endpoint-btn').addEventListener('click', () => {
  sessionEndpointInput.value = envDefaults.sessionEndpoint;
  fetchTimeoutInput.value = String(envDefaults.fetchTimeoutMs);
  sessionFeedback.textContent = 'Session endpoint and timeout restored.';
});
function transcriptText() {
  return state.transcript.map(entry => `${entry.speaker}${entry.final ? '' : ' (partial)'}: ${entry.text}`).join('\n');
}
requireEl<HTMLButtonElement>('#copy-transcript-btn').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(transcriptText()); sessionFeedback.textContent = 'Transcript copied.'; }
  catch { sessionFeedback.textContent = 'Clipboard unavailable. Use Download to save the transcript.'; }
});
requireEl<HTMLButtonElement>('#download-transcript-btn').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([transcriptText()], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `awaaz-transcript-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
  link.click();
  URL.revokeObjectURL(url);
});

languageSelect.addEventListener('change', () => {
  refillProvidersForLanguage(languageSelect.value, { keepCurrent: false });
  refillModels();
  updatePipelineSummary();

});
sttSelect.addEventListener('change', () => {
  refillModels();
  updatePipelineSummary();

});
llmSelect.addEventListener('change', () => {
  refillModels();
  updatePipelineSummary();

});
ttsSelect.addEventListener('change', () => {
  refillModels();
  updatePipelineSummary();

});

[sttModelSelect, llmModelSelect, voiceSelect].forEach(select => select.addEventListener('change', updatePipelineSummary));

clearDebugBtn.addEventListener('click', () => {
  state.debugLog = [];
  state.errors = [];
  state.latestMetrics = null;
  state.timing = emptyTiming();
  pushDebug('info', 'Debug log cleared');
  render();
});

copyDebugBtn.addEventListener('click', async () => {
  const text = [
    `package=${state.packageLabel}`,
    formatTimingPlain(state.timing),
    '',
    '--- log ---',
    ...state.debugLog.map(formatDebugLine),
    '',
    '--- latest metrics ---',
    state.latestMetrics ? JSON.stringify(state.latestMetrics, null, 2) : '(none)',
    '',
    '--- errors ---',
    state.errors.length ? state.errors.join('\n') : '(none)',
  ].join('\n');
  try {
    await navigator.clipboard.writeText(text);
    pushDebug('info', 'Copied debug dump to clipboard');
  } catch (error) {
    pushDebug('warn', 'Clipboard copy failed', String(error));
  }
  render();
});

timeoutSmokeBtn.addEventListener('click', () => {
  sessionEndpointInput.value = `${backendOrigin}/api/demo/hang`;
  if (Number(fetchTimeoutInput.value) > 5000) {
    fetchTimeoutInput.value = '5000';
  }
  pushDebug(
    'warn',
    'Timeout smoke armed',
    `sessionEndpoint → /api/demo/hang · fetchTimeoutMs=${fetchTimeoutInput.value} (expect error code timeout)`,
  );
  render();
});

muteButton.addEventListener('click', async () => {
  if (!agent?.isConnected || micBusy) return;
  micBusy = true;
  render();
  const next = !state.micMuted;
  try {
    await agent.setMicMuted(next);
    state.micMuted = agent.isMicMuted;
    pushDebug('info', state.micMuted ? 'Mic muted' : 'Mic unmuted');
    render();
  } catch (error) {
    renderError(error);
  } finally { micBusy = false; render(); }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (sessionBusy || pipelineBusy || agent?.isConnected) return;
  if (bootstrapBusy || !servicesReady) {
    sessionFeedback.textContent = 'Wait for backend preparation, or use Refresh agents to retry.';
    return;
  }
  if (promptPanel.isBusy() || promptPanel.isDirty()) {
    sessionFeedback.textContent = 'Wait for the prompt to load or save your prompt changes before connecting.';
    return;
  }
  if (!form.checkValidity()) {
    requireEl<HTMLDetailsElement>('.connection-details').open = true;
    form.reportValidity();
    return;
  }
  const publishableKey = requireEl<HTMLInputElement>('#publishable-key').value.trim();
  const sessionEndpoint = sessionEndpointInput.value.trim();
  const refreshEndpoint = requireEl<HTMLInputElement>('#refresh-endpoint').value.trim();
  const agentId = agentIdInput.value.trim();
  sessionBusy = true;
  resetSessionView();
  state.timing.clickAt = performance.now();
  setStatus('preparing pipeline');
  sessionFeedback.textContent = 'Preparing your agent…';
  let client: AwaazLabsUvaVoice | null = null;
  try {
    if (agent) { await agent.disconnect(); agent = null; }
    if (!sessionEndpoint.includes('/api/demo/hang') && performance.now() - servicesReadyAt > 60000) await prepareServices();
    if (!sessionEndpoint.includes('/api/demo/hang')) {
      const selection = selectedPipeline();
      if (savedPipelines.get(agentId) === JSON.stringify(selection)) {
        // No local edit: mint with the agent's server-owned configuration. This
        // does not assert that an external editor has left the agent unchanged.
        pushDebug('info', 'Using saved agent settings; pipeline write not required');
      } else {
        const prepared = await applySelectedPipeline(agentId);
        state.pipelineText = formatAppliedPipeline(prepared.applied);
        pushDebug('info', prepared.skipped ? 'Pipeline already matches' : 'Pipeline applied', state.pipelineText);
      }
    }
    state.timing.pipelineDoneAt = performance.now();
    setStatus('connecting');
    sessionFeedback.textContent = 'Connecting… Allow microphone access when prompted.';
    client = new AwaazLabsUvaVoice({
      publishableKey, sessionEndpoint, refreshEndpoint: refreshEndpoint || undefined,
      fetchTimeoutMs: Number(fetchTimeoutInput.value) || 15000,
    });
    agent = client;
    bindAgent(client);
    await client.connect({ agentId });
    state.micMuted = client.isMicMuted;
    setStatus(client.connectionState);
    sessionFeedback.textContent = 'Session connected. Speak when you’re ready.';
  } catch (error) {
    renderError(error);
    if (client) await client.disconnect().catch(() => {});
    agent = null;
    setStatus('idle');
    sessionFeedback.textContent = error instanceof Error ? error.message : 'Connection failed. Check diagnostics and retry.';
  } finally {
    sessionBusy = false;
    render();
  }
});

disconnectButton.addEventListener('click', async () => {
  if (sessionBusy) return;
  pushDebug('info', 'Disconnect clicked');
  if (!agent) {
    setStatus('idle');
    muteButton.disabled = true;
    return;
  }
  sessionBusy = true;
  setStatus('disconnecting');
  try {
    await agent.disconnect();
    agent = null;
    state.micMuted = false;
    sessionFeedback.textContent = 'Session ended. You can adjust your agent and start again.';
    setStatus('idle');
  } catch (error) { renderError(error); }
  finally { sessionBusy = false; render(); }
});

unlockAudioBtn.addEventListener('click', async () => {
  pushDebug('info', 'Unlock audio clicked');
  if (agent) {
    try { await agent.startAudio(); } catch (error) { renderError(error); }
  }
});

state.packageLabel = `npm package · @awaazlabs-uva/voice@${__UVA_VOICE_VERSION__}`;
void bootstrapPipelineControls();
mountTelephonyPanel({
  backendOrigin,
  getAgentId: () => requireEl<HTMLInputElement>('#agent-id').value,
});
render();

const navLinks = document.querySelectorAll<HTMLAnchorElement>('.workspace-nav a');
navLinks.forEach(link => {
  if (link.hash === '#telephony-root') link.href = '#telephony-section';
  link.addEventListener('click', () => {
    if (link.hash === '#telephony-section') requireEl<HTMLDetailsElement>('#telephony-section').open = true;
    navLinks.forEach(item => item.toggleAttribute('aria-current', item === link));
    link.setAttribute('aria-current', 'location');
  });
});
navLinks[0]?.setAttribute('aria-current', 'location');

function bindAgent(client: AwaazLabsUvaVoice): void {
  client.on('connect_timing', (timing) => {
    state.timing.sessionMintMs = timing.mintMs;
    state.timing.livekitConnectMs = timing.livekitConnectMs;
    const host = timing.livekitUrlHost ? ` · host ${timing.livekitUrlHost}` : '';
    const quality = timing.connectionQuality ? ` · quality ${timing.connectionQuality}` : '';
    pushDebug(
      'metric',
      `Connect split mint=${timing.mintMs}ms · livekit=${timing.livekitConnectMs}ms`,
      `${
        timing.livekitConnectMs >= timing.mintMs
          ? 'join-heavy — check LIVEKIT_URL region / ICE'
          : 'mint-heavy — check CP DB / host→CP RTT'
      }${host}${quality}`,
    );
    render();
  });
  client.on('connected', () => {
    state.timing.connectedAt = performance.now();
    state.micMuted = client.isMicMuted;
    muteButton.disabled = false;
    const split = client.connectTiming;
    pushDebug(
      'metric',
      `Room connected (+${msSinceClick()}ms)`,
      split
        ? `mint ${split.mintMs}ms · livekit ${split.livekitConnectMs}ms`
        : undefined,
    );
    setStatus('connected');
  });
  client.on('disconnected', (reason) => {
    pushDebug('warn', 'Disconnected', reason == null ? undefined : String(reason));
    muteButton.disabled = true;
    state.micMuted = false;
    state.audioReady = false;
    state.audioBlocked = false;
    state.thinking = false;
    state.speaking = false;
    state.agentSpeaking = false;
    sessionFeedback.textContent = 'Session disconnected. Ready to reconnect.';
    setStatus('idle');
  });
  client.on('transcript', (entry) => {
    upsertTranscript(entry);
    if (entry.speaker === 'agent' && state.timing.firstAgentTranscriptAt == null) {
      state.timing.firstAgentTranscriptAt = performance.now();
      pushDebug(
        'metric',
        `First agent transcript (+${msSinceClick()}ms)`,
        `${entry.final ? 'final' : 'partial'}: ${truncate(entry.text, 80)}`,
      );
    } else if (entry.speaker === 'user' && entry.final) {
      const prevFinal = state.timing.lastUserFinalAt;
      state.timing.lastUserFinalAt = performance.now();
      state.timing.lastAgentReplyAudioAt = null;
      state.thinking = true;
      setStatus('thinking');
      if (prevFinal != null && state.timing.lastUserFinalAt - prevFinal < 2500) {
        pushDebug(
          'warn',
          'Back-to-back user finals (<2.5s)',
          'A second final while the agent is thinking usually cancels the first reply — perceived turn lag jumps',
        );
      }
      pushDebug(
        'info',
        `Transcript user (final)`,
        truncate(entry.text, 100),
      );
    } else {
      if (entry.speaker === 'agent' && !entry.final && state.thinking) {
        state.thinking = false;
        if (state.status === 'thinking') setStatus('connected');
      }
      pushDebug(
        'info',
        `Transcript ${entry.speaker ?? '?'} (${entry.final ? 'final' : 'partial'})`,
        truncate(entry.text, 100),
      );
    }
    render();
  });
  client.on('speaking', (isSpeaking) => {
    state.speaking = Boolean(isSpeaking);
    pushDebug('info', isSpeaking ? 'Caller speaking: yes' : 'Caller speaking: no');
    render();
  });
  client.on('agent_speaking', (isSpeaking) => {
    state.agentSpeaking = Boolean(isSpeaking);
    if (isSpeaking && state.timing.firstAgentSpeakingAt == null) {
      state.timing.firstAgentSpeakingAt = performance.now();
      pushDebug('metric', `First agent active-speaker signal (+${msSinceClick()}ms)`);
    } else if (
      isSpeaking &&
      state.timing.lastUserFinalAt != null &&
      state.timing.lastAgentReplyAudioAt == null
    ) {
      state.timing.lastAgentReplyAudioAt = performance.now();
      const gap = Math.round(state.timing.lastAgentReplyAudioAt - state.timing.lastUserFinalAt);
      state.thinking = false;
      if (state.status === 'thinking') setStatus('connected');
      pushDebug('metric', `User-final → agent active-speaker signal (proxy) ${gap}ms`);
    } else {
      pushDebug('info', isSpeaking ? 'Agent speaking: yes' : 'Agent speaking: no');
    }
    render();
  });
  client.on('metrics_updated', (metrics) => {
    // The SDK forwards turn_latency here for legacy consumers. The dedicated
    // listener below handles it once; this listener owns aggregates only.
    if (metrics.type !== 'metrics_updated') return;
    state.latestMetrics = metrics;
    state.timing.lastMetricsAt = performance.now();
    pushDebug('metric', `metrics_updated (+${msSinceClick()}ms)`, summarizeMetrics(metrics));
    render();
  });
  client.on('turn_latency', (metrics) => {
    state.latestMetrics = metrics;
    if (metrics.outcome == null || metrics.outcome === 'completed') ingestTurnLatency(metrics);
    if (state.timing.firstTurnLatencyAt == null) {
      state.timing.firstTurnLatencyAt = performance.now();
      pushDebug(
        'metric',
        `First turn_latency event (+${msSinceClick()}ms from Connect)`,
        summarizeMetrics(metrics),
      );
    } else {
      pushDebug('metric', `turn_latency (+${msSinceClick()}ms)`, summarizeMetrics(metrics));
    }
    render();
  });
  client.on('error', (error) => renderError(error));
  client.on('ended', (reason) => {
    pushDebug('warn', 'Session ended', reason == null ? undefined : String(reason));
    state.status = `ended${reason ? ` (${String(reason)})` : ''}`;
    state.thinking = false;
    state.speaking = false;
    state.agentSpeaking = false;
    state.micMuted = false;
    state.audioBlocked = false;
    state.audioReady = false;
    muteButton.disabled = true;
    render();
  });
  client.on('audio_ready', (ready) => {
    state.audioReady = ready;
    pushDebug('info', ready ? 'Playback ready' : 'Playback not ready', 'Browser readiness; does not prove caller hearing');
    render();
  });
  client.on('audio_blocked', (blocked) => {
    state.audioBlocked = Boolean(blocked);
    if (blocked) state.audioReady = false;
    pushDebug(blocked ? 'warn' : 'info', blocked ? 'Audio blocked by browser' : 'Audio unblocked');
    render();
  });
}

function upsertTranscript(entry: TranscriptEvent): void {
  const idx = state.transcript.findIndex((row) => row.id === entry.id);
  if (idx >= 0) {
    const next = state.transcript.slice();
    next[idx] = entry;
    state.transcript = next;
    return;
  }
  state.transcript = [...state.transcript, entry];
}

async function bootstrapPipelineControls(): Promise<void> {
  bootstrapBusy = true;
  render();
  reloadAgentsButton.disabled = true;
  reloadAgentsButton.textContent = 'Loading…';
  try {
    // Cold Render wake-up may exceed the picker requests' 20-second bound.
    // Prepare first so those requests start against a healthy service.
    try {
      await prepareServices();
    } catch (error) {
      // Agent configuration can still load when only the control plane is down.
      // Keep connecting disabled until readiness recovers.
      pushDebug('warn', error instanceof Error ? error.message : 'Backend preparation failed');
    }
    const [capsResult, agentsResult, configResult] = await Promise.allSettled([
      fetch(`${backendOrigin}/api/provider-capabilities`, { signal: AbortSignal.timeout(20000) }),
      fetch(`${backendOrigin}/api/agents`, { signal: AbortSignal.timeout(20000) }),
      fetch(`${backendOrigin}/api/demo/config`, { signal: AbortSignal.timeout(20000) }),
    ]);

    if (configResult.status === 'fulfilled' && configResult.value.ok) {
      const config = await configResult.value.json();
      const key = requireEl<HTMLInputElement>('#publishable-key');
      if (!key.value) key.value = config.publishableKey || '';
    }

    if (agentsResult.status === 'fulfilled' && agentsResult.value.ok) {
      const payload = await agentsResult.value.json() as { agents?: AgentRecord[] };
      agents = payload.agents || [];
      savedPipelines.clear();
      agents.forEach(rememberAgentPipeline);
      const id = agentIdInput.value.trim() || agents[0]?.id || '';
      fillSelect(agentPicker, [{ value: '', label: agents.length ? 'Choose an agent' : 'No agents available — enter an ID in connection settings' }, ...agents.map(item => ({ value: item.id, label: item.name || item.id }))], id);
      agentIdInput.value = id;
      selectedAgentId = id;
      void promptPanel.load();
    } else {
      fillSelect(agentPicker, [{ value: '', label: 'Agents unavailable — enter an ID in connection settings' }], '');
      requireEl<HTMLDetailsElement>('.connection-details').open = true;
      if (agentIdInput.value) void promptPanel.load();
    }

    if (capsResult.status === 'rejected') throw new Error('Backend unavailable. Start the demo backend and use Refresh agents to retry.');
    const capsRes = capsResult.value;
    if (!capsRes.ok) {
      const body = await capsRes.json().catch(() => ({}));
      throw new Error(body.message || body.error || `capabilities HTTP ${capsRes.status}`);
    }
    capabilities = await capsRes.json() as ProviderCapabilities;
    const languages = Object.keys(capabilities.languages || {});
    if (languages.length === 0) {
      throw new Error('No enabled languages returned from provider capabilities');
    }

    const preferred = agents.find(item => item.id === agentIdInput.value);

    fillSelect(
      languageSelect,
      languages.map((code) => ({
        value: code,
        label: `${capabilities!.languages[code]?.label || code} (${code})`,
      })),
      preferred?.agent_language || languages[0],
    );
    languageSelect.disabled = false;

    refillProvidersForLanguage(languageSelect.value, {
      keepCurrent: true,
      preferredStt: preferred?.stt_provider,
      preferredLlm: preferred?.llm_provider,
      preferredTts: preferred?.tts_provider,
    });
    refillModels(preferred);
    updatePipelineSummary();
    pushDebug('info', 'Provider capabilities loaded', `${languages.length} language(s)`);
  } catch (error) {
    capabilities = null;
    fillSelect(agentPicker, [{ value: '', label: 'Agents unavailable — use Refresh agents to retry' }], '');
    for (const select of [languageSelect, sttSelect, llmSelect, ttsSelect, sttModelSelect, llmModelSelect, voiceSelect]) {
      fillSelect(select, [{ value: '', label: 'Unavailable — retry loading' }], '');
    }
    languageSelect.disabled = true;
    sttSelect.disabled = true;
    llmSelect.disabled = true;
    ttsSelect.disabled = true;
    state.pipelineText =
      error instanceof Error
        ? `Provider picker unavailable: ${error.message}`
        : 'Provider picker unavailable';
    renderError(error);
    render();
  } finally {
    bootstrapBusy = false;
    reloadAgentsButton.textContent = 'Refresh agents';
    reloadAgentsButton.disabled = false;
    render();
  }
}

function refillProvidersForLanguage(
  language: string,
  opts: {
    keepCurrent?: boolean;
    preferredStt?: string;
    preferredLlm?: string;
    preferredTts?: string;
  } = {},
): void {
  const lang = capabilities?.languages?.[language];
  if (!lang) {
    fillSelect(sttSelect, [], '');
    fillSelect(llmSelect, [], '');
    fillSelect(ttsSelect, [], '');
    sttSelect.disabled = true;
    llmSelect.disabled = true;
    ttsSelect.disabled = true;
    return;
  }

  const sttKeys = Object.keys(lang.stt || {});
  const llmKeys = Object.keys(lang.llm || {});
  const ttsKeys = Object.keys(lang.tts || {});

  fillSelect(
    sttSelect,
    sttKeys.map((value) => ({ value, label: value })),
    pickPreferred(sttKeys, opts.keepCurrent ? sttSelect.value : '', opts.preferredStt),
  );
  fillSelect(
    llmSelect,
    llmKeys.map((value) => ({ value, label: value })),
    pickPreferred(llmKeys, opts.keepCurrent ? llmSelect.value : '', opts.preferredLlm),
  );
  fillSelect(
    ttsSelect,
    ttsKeys.map((value) => ({ value, label: value })),
    pickPreferred(ttsKeys, opts.keepCurrent ? ttsSelect.value : '', opts.preferredTts),
  );

  sttSelect.disabled = sttKeys.length === 0;
  llmSelect.disabled = llmKeys.length === 0;
  ttsSelect.disabled = ttsKeys.length === 0;
}

function pickPreferred(options: string[], current: string, preferred?: string): string {
  if (current && options.includes(current)) return current;
  if (preferred && options.includes(preferred)) return preferred;
  return options[0] || '';
}

function fillSelect(
  select: HTMLSelectElement,
  options: Array<{ value: string; label: string }>,
  selected: string,
): void {
  select.innerHTML = '';
  if (options.length === 0) {
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = 'None available';
    select.appendChild(empty);
    return;
  }
  for (const option of options) {
    const node = document.createElement('option');
    node.value = option.value;
    node.textContent = option.label;
    if (option.value === selected) node.selected = true;
    select.appendChild(node);
  }
}

function updatePipelineSummary(): void {
  const language = languageSelect.value;
  const lang = capabilities?.languages?.[language];
  if (!lang) {
    state.pipelineText = 'Select a language';
    render();
    return;
  }
  const stt = sttSelect.value;
  const llm = llmSelect.value;
  const tts = ttsSelect.value;
  const sttModel = sttModelSelect.value || 'default';
  const llmModel = llmModelSelect.value || '?';
  const voice = voiceSelect.value || '?';
  state.pipelineText = `Will apply: ${language} · STT ${stt}/${sttModel} · LLM ${llm}/${llmModel} · TTS ${tts}/${voice}`;
  render();
}

async function preparePipeline(
  agentId: string,
  selection: {
    agentLanguage: string;
    sttProvider: string;
    llmProvider: string;
    ttsProvider: string;
    sttModel: string;
    llmModel: string;
    ttsVoiceId: string;
  },
): Promise<{ applied: Record<string, string>; skipped?: boolean }> {
  const res = await fetch(`${backendOrigin}/api/agents/${encodeURIComponent(agentId)}/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(selection),
    signal: AbortSignal.timeout(20000),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.message || body.error || `pipeline HTTP ${res.status}`);
  }
  return body as { applied: Record<string, string>; skipped?: boolean };
}

function formatAppliedPipeline(applied: Record<string, string>): string {
  return `Applied: ${applied.agentLanguage} · STT ${applied.sttProvider}/${applied.sttModel} · LLM ${applied.llmProvider}/${applied.llmModel} · TTS ${applied.ttsProvider}/${applied.ttsVoiceId}`;
}

function setStatus(status: string): void {
  state.status = status;
  render();
}

function resetSessionView(): void {
  state.transcript = [];
  state.speaking = false;
  state.agentSpeaking = false;
  state.micMuted = false;
  state.thinking = false;
  state.latestMetrics = null;
  state.errors = [];
  state.audioBlocked = false;
  state.audioReady = false;
  state.timing = emptyTiming();
  state.debugLog = [];
  muteButton.disabled = true;
  muteButton.textContent = 'Mute mic';
  render();
}

function pushDebug(level: DebugLevel, message: string, detail?: string): void {
  state.debugLog = [
    ...state.debugLog,
    { t: performance.now(), level, message, detail },
  ].slice(-MAX_DEBUG_ENTRIES);
}

function msSinceClick(): number {
  if (state.timing.clickAt == null) return 0;
  return Math.round(performance.now() - state.timing.clickAt);
}

function renderError(error: unknown): void {
  let text: string;
  if (error instanceof AwaazLabsUvaVoiceError) {
    text = `${error.code}: ${error.message}`;
  } else if (error && typeof error === 'object' && 'message' in error) {
    text = String((error as { message: unknown }).message);
  } else {
    text = 'Unknown error';
  }
  state.errors = [...state.errors, `[+${msSinceClick()}ms] ${text}`];
  pushDebug('error', text);
  render();
}

function render(): void {
  const connected = !!agent?.isConnected;
  const locked = sessionBusy || connected || pipelineBusy;
  connectButton.disabled = locked || bootstrapBusy || !servicesReady || promptPanel.isBusy() || promptPanel.isDirty();
  connectButton.textContent = sessionBusy ? (state.status === 'disconnecting' ? 'Ending session…' : 'Connecting…') : connected ? 'Session live' : 'Start conversation';
  disconnectButton.disabled = !connected || sessionBusy;
  muteButton.disabled = !connected || micBusy || sessionBusy;
  muteButton.setAttribute('aria-pressed', String(state.micMuted));
  applyPipelineButton.disabled = locked || !capabilities || bootstrapBusy;
  applyPipelineButton.textContent = pipelineBusy ? 'Applying…' : 'Apply pipeline';
  reloadAgentsButton.disabled = locked || bootstrapBusy || promptPanel.isBusy();
  for (const input of form.querySelectorAll<HTMLInputElement>('input')) input.disabled = locked || bootstrapBusy;
  agentPicker.disabled = locked || bootstrapBusy || promptPanel.isBusy();
  agentIdInput.disabled = locked || bootstrapBusy || promptPanel.isBusy();
  for (const select of [languageSelect, sttSelect, llmSelect, ttsSelect, sttModelSelect, llmModelSelect, voiceSelect]) {
    select.disabled = locked || bootstrapBusy || !capabilities || !select.value;
  }
  timeoutSmokeBtn.disabled = locked;
  requireEl<HTMLButtonElement>('#restore-endpoint-btn').disabled = locked;
  promptPanel.setLocked(locked || bootstrapBusy);
  requireEl<HTMLButtonElement>('#copy-transcript-btn').disabled = !state.transcript.length;
  requireEl<HTMLButtonElement>('#download-transcript-btn').disabled = !state.transcript.length;
  statusText.dataset.active = String(connected);
  statusText.textContent = state.thinking ? 'thinking (LLM/TTS…)' : state.status;
  speakingText.textContent = state.speaking ? 'Yes' : 'No';
  agentSpeakingText.textContent = state.agentSpeaking ? 'Yes' : 'No';
  micText.textContent = connected ? state.micMuted ? 'Muted' : 'Live' : 'Off';
  muteButton.textContent = state.micMuted ? 'Unmute mic' : 'Mute mic';
  packageBadge.textContent = state.packageLabel;
  requireEl<HTMLElement>('#playback-status').textContent = state.audioReady
    ? 'Playback ready — caller hearing still requires listening verification'
    : state.audioBlocked ? 'Playback blocked — click Unlock audio' : 'Playback not ready';
  metricsOutput.textContent = state.latestMetrics
    ? JSON.stringify(state.latestMetrics, null, 2)
    : 'No metrics received yet.';
  errorOutput.textContent = state.errors.length ? state.errors.join('\n') : 'No errors.';
  pipelineSummary.textContent = state.pipelineText;
  timingSummaryEl.innerHTML = formatTimingCards(state.timing);
  debugLogEl.textContent =
    state.debugLog.length === 0
      ? 'Waiting for Connect…'
      : state.debugLog.map(formatDebugLine).join('\n');
  debugLogEl.scrollTop = debugLogEl.scrollHeight;

  audioUnlockBanner.style.display = state.audioBlocked ? 'flex' : 'none';

  if (state.transcript.length === 0) {
    transcriptList.innerHTML = '<li class="placeholder"><strong>Your conversation will appear here</strong><span>Start a session to see live caller and agent transcripts.</span></li>';
  } else {
    transcriptList.innerHTML = state.transcript
      .map((entry) => {
        const finalLabel = entry.final ? 'final' : 'partial';
        const speaker = entry.speaker ?? 'unknown';
        return `<li><span class="badge">${speaker} · ${finalLabel}</span><span>${escapeHtml(entry.text)}</span></li>`;
      })
      .join('');
  }
}

function deltaMs(from: number | null, to: number | null): string {
  if (from == null || to == null) return '—';
  return `${Math.round(to - from)}ms`;
}

function formatTimingCards(timing: TimingSnapshot): string {
  const perceived =
    timing.lastUserFinalAt != null && timing.lastAgentReplyAudioAt != null
      ? `${Math.round(timing.lastAgentReplyAudioAt - timing.lastUserFinalAt)}ms`
      : '—';
  const cards: Array<{ label: string; value: string }> = [
    { label: 'Before session mint', value: deltaMs(timing.clickAt, timing.pipelineDoneAt) },
    {
      label: 'Session mint',
      value: timing.sessionMintMs != null ? `${timing.sessionMintMs}ms` : '—',
    },
    {
      label: 'LiveKit join',
      value: timing.livekitConnectMs != null ? `${timing.livekitConnectMs}ms` : '—',
    },
    { label: 'Room connected', value: deltaMs(timing.clickAt, timing.connectedAt) },
    { label: 'Click → active speaker (proxy)', value: deltaMs(timing.clickAt, timing.firstAgentSpeakingAt) },
    { label: 'Room → active speaker (proxy)', value: deltaMs(timing.connectedAt, timing.firstAgentSpeakingAt) },
    { label: 'Turn e2e (worker)', value: timing.lastTurnE2eMs != null ? `${timing.lastTurnE2eMs}ms` : '—' },
    { label: 'Turn LLM TTFT', value: timing.lastTurnLlmMs != null ? `${timing.lastTurnLlmMs}ms` : '—' },
    { label: 'Turn TTS TTFB', value: timing.lastTurnTtsTtfbMs != null ? `${timing.lastTurnTtsTtfbMs}ms` : '—' },
    { label: 'User-final → active speaker (proxy)', value: perceived },
    { label: 'Turn STT', value: timing.lastTurnSttMs != null ? `${timing.lastTurnSttMs}ms` : '—' },
  ];
  return cards
    .map(
      (card) =>
        `<div class="timing-card"><span class="timing-label">${escapeHtml(card.label)}</span><span class="timing-value">${escapeHtml(card.value)}</span></div>`,
    )
    .join('');
}

function formatTimingPlain(timing: TimingSnapshot): string {
  const perceived =
    timing.lastUserFinalAt != null && timing.lastAgentReplyAudioAt != null
      ? String(Math.round(timing.lastAgentReplyAudioAt - timing.lastUserFinalAt))
      : '—';
  return [
    `before_session_mint_ms=${deltaMs(timing.clickAt, timing.pipelineDoneAt)}`,
    `session_mint_ms=${timing.sessionMintMs ?? '—'}`,
    `livekit_connect_ms=${timing.livekitConnectMs ?? '—'}`,
    `room_connected_ms=${deltaMs(timing.clickAt, timing.connectedAt)}`,
    `click_to_active_speaker_proxy_ms=${deltaMs(timing.clickAt, timing.firstAgentSpeakingAt)}`,
    `room_to_active_speaker_proxy_ms=${deltaMs(timing.connectedAt, timing.firstAgentSpeakingAt)}`,
    `turn_e2e_ms=${timing.lastTurnE2eMs ?? '—'}`,
    `turn_llm_ttft_ms=${timing.lastTurnLlmMs ?? '—'}`,
    `turn_tts_ttfb_ms=${timing.lastTurnTtsTtfbMs ?? '—'}`,
    `turn_stt_ms=${timing.lastTurnSttMs ?? '—'}`,
    `user_final_to_active_speaker_proxy_ms=${perceived}`,
  ].join('\n');
}

function ingestTurnLatency(metrics: MetricsEvent): void {
  const num = (keys: string[]): number | null => {
    for (const key of keys) {
      const raw = metrics[key];
      if (typeof raw === 'number' && Number.isFinite(raw)) return Math.round(raw);
      if (typeof raw === 'string' && raw.trim() && Number.isFinite(Number(raw))) {
        return Math.round(Number(raw));
      }
    }
    return null;
  };
  state.timing.lastTurnE2eMs = num(['e2eMs', 'e2e_ms', 'roundTripMs', 'round_trip_ms']);
  state.timing.lastTurnLlmMs = num(['llmMs', 'llm_ms', 'llmTtftMs', 'llm_ms_ttft']);
  state.timing.lastTurnTtsTtfbMs = num(['ttsTtfbMs', 'tts_ttfb_ms', 'ttsLatencyMs']);
  state.timing.lastTurnSttMs = num(['sttMs', 'stt_ms']);
}

function formatDebugLine(entry: DebugEntry): string {
  const abs = new Date(performance.timeOrigin + entry.t).toISOString().slice(11, 23);
  const rel =
    state.timing.clickAt == null ? '   —  ' : `+${String(Math.round(entry.t - state.timing.clickAt)).padStart(5, ' ')}ms`;
  const level = entry.level.toUpperCase().padEnd(6, ' ');
  const detail = entry.detail ? ` | ${entry.detail}` : '';
  return `${abs} ${rel} ${level} ${entry.message}${detail}`;
}

function summarizeMetrics(metrics: MetricsEvent): string {
  const keys = [
    'humanization_policy_version',
    'component_versions',
    'session_id',
    'user_turn_id',
    'assistant_turn_id',
    'generation_id',
    'outcome',
    'failureElapsedMs',
    'sequence',
    'latencyKind',
    'e2eMs',
    'e2e_ms',
    'sttMs',
    'stt_ms',
    'turnMs',
    'turn_ms',
    'llmMs',
    'llm_ms',
    'ttsTtfbMs',
    'tts_ttfb_ms',
    'roundTripMs',
    'llmTtftMs',
    'ttsLatencyMs',
    'opening_mode',
    'greeting_cache_hit',
    'prewarm_wait_ms',
    'ms_since_connect',
  ];
  const parts: string[] = [`type=${metrics.type}`];
  for (const key of keys) {
    if (metrics[key] != null) parts.push(`${key}=${typeof metrics[key] === 'object' ? JSON.stringify(metrics[key]) : String(metrics[key])}`);
  }
  if (parts.length === 1) {
    const preview = JSON.stringify(metrics);
    return truncate(preview, 160);
  }
  return parts.join(' ');
}

function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

function escapeHtml(value: string): string {
  return value
    .split('&')
    .join('&amp;')
    .split('<')
    .join('&lt;')
    .split('>')
    .join('&gt;')
    .split('"')
    .join('&quot;')
    .split("'")
    .join('&#39;');
}
