import {
  AwaazLabsUvaVoice,
  AwaazLabsUvaVoiceError,
  type MetricsEvent,
  type TranscriptEvent,
} from '@awaazlabs-uva/voice';
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
  agent_language?: string;
  stt_provider?: string;
  llm_provider?: string;
  tts_provider?: string;
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
  firstAgentSpeakingAt: number | null;
  firstAgentTranscriptAt: number | null;
  firstTurnLatencyAt: number | null;
  lastMetricsAt: number | null;
};

type AppState = {
  status: string;
  transcript: TranscriptEvent[];
  speaking: boolean;
  agentSpeaking: boolean;
  latestMetrics: MetricsEvent | null;
  errors: string[];
  audioBlocked: boolean;
  pipelineText: string;
  debugLog: DebugEntry[];
  timing: TimingSnapshot;
};

const envDefaults = {
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY ?? '',
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT ?? '',
  refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT ?? '',
  agentId: import.meta.env.VITE_UVA_AGENT_ID ?? '',
};

const backendOrigin = (() => {
  try {
    return new URL(envDefaults.sessionEndpoint || 'http://localhost:3000/api/voice/session').origin;
  } catch {
    return 'http://localhost:3000';
  }
})();

const emptyTiming = (): TimingSnapshot => ({
  clickAt: null,
  pipelineDoneAt: null,
  connectedAt: null,
  firstAgentSpeakingAt: null,
  firstAgentTranscriptAt: null,
  firstTurnLatencyAt: null,
  lastMetricsAt: null,
});

const state: AppState = {
  status: 'idle',
  transcript: [],
  speaking: false,
  agentSpeaking: false,
  latestMetrics: null,
  errors: [],
  audioBlocked: false,
  pipelineText: 'Loading provider capabilities…',
  debugLog: [],
  timing: emptyTiming(),
};

let agent: AwaazLabsUvaVoice | null = null;
let capabilities: ProviderCapabilities | null = null;
/** Last pipeline fingerprint successfully applied (or confirmed already on agent). */
let lastAppliedFingerprint = '';
let pipelineApplyTimer: ReturnType<typeof setTimeout> | null = null;
let pipelineApplyInFlight: Promise<void> | null = null;
const MAX_DEBUG_ENTRIES = 200;

function pipelineFingerprint(
  agentId: string,
  agentLanguage: string,
  sttProvider: string,
  llmProvider: string,
  ttsProvider: string,
): string {
  return `${agentId}|${agentLanguage}|${sttProvider}|${llmProvider}|${ttsProvider}`;
}

const appRoot = document.querySelector<HTMLDivElement>('#app');
if (!appRoot) {
  throw new Error('App root not found');
}

appRoot.innerHTML = `
  <main class="shell">
    <header class="header">
      <h1>UVA Demo</h1>
      <p>
        Browser client for <code>@awaazlabs-uva/voice</code>. Pick language + STT/LLM/TTS,
        then Connect — the host updates the agent pipeline before minting the session.
      </p>
    </header>

    <section class="panel">
      <h2>Connection</h2>
      <form id="voice-form" class="form">
        <label>
          Publishable key
          <input id="publishable-key" name="publishableKey" value="${escapeHtml(envDefaults.publishableKey)}" />
        </label>
        <label>
          Session endpoint
          <input id="session-endpoint" name="sessionEndpoint" value="${escapeHtml(envDefaults.sessionEndpoint)}" />
        </label>
        <label>
          Refresh endpoint
          <input id="refresh-endpoint" name="refreshEndpoint" value="${escapeHtml(envDefaults.refreshEndpoint)}" />
        </label>
        <label>
          Agent ID
          <input id="agent-id" name="agentId" value="${escapeHtml(envDefaults.agentId)}" />
        </label>

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

        <p id="pipeline-summary" class="hint">Loading provider capabilities…</p>

        <div class="actions">
          <button id="connect-btn" type="submit">Connect</button>
          <button id="disconnect-btn" type="button">Disconnect</button>
        </div>
      </form>
      <p class="hint">
        Uses the local SDK package from <code>sdk/</code>. Requires demo backend
        <code>UVA_API_BASE_URL</code> (portal) so provider updates can PATCH the agent.
      </p>
    </section>

    <section class="grid">
      <article class="panel">
        <h2>Status</h2>
        <p id="status-text" class="stat">idle</p>
      </article>
      <article class="panel">
        <h2>Caller</h2>
        <p id="speaking-text" class="stat">No</p>
      </article>
      <article class="panel">
        <h2>Agent</h2>
        <p id="agent-speaking-text" class="stat">No</p>
      </article>
    </section>

    <section class="panel debug-panel">
      <div class="debug-header">
        <h2>Debug log</h2>
        <div class="debug-actions">
          <button id="copy-debug-btn" type="button">Copy</button>
          <button id="clear-debug-btn" type="button">Clear</button>
        </div>
      </div>
      <p class="hint debug-hint">
        Client-side timings from Connect click. First-audio ≈ room connect → agent speaking.
        Worker logs add <code>greeting_cache_hit</code> / <code>prewarm_wait_ms</code>.
      </p>
      <div id="timing-summary" class="timing-grid"></div>
      <pre id="debug-log" class="log-box debug-log">Waiting for Connect…</pre>
      <details class="metrics-details">
        <summary>Latest SDK metrics payload</summary>
        <pre id="metrics-output" class="log-box metrics-nested">No metrics received yet.</pre>
      </details>
      <details class="metrics-details">
        <summary>Errors this session</summary>
        <pre id="error-output" class="log-box metrics-nested">No errors.</pre>
      </details>
    </section>

    <section class="panel">
      <h2>Transcript</h2>
      <ul id="transcript-list" class="transcript-list"></ul>
    </section>

    <div id="audio-unlock-banner" class="audio-unlock-banner">
      <p>Audio blocked by the browser.</p>
      <button id="unlock-audio-btn" type="button">Unlock audio</button>
    </div>
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
const transcriptList = requireEl<HTMLUListElement>('#transcript-list');
const metricsOutput = requireEl<HTMLElement>('#metrics-output');
const errorOutput = requireEl<HTMLElement>('#error-output');
const debugLogEl = requireEl<HTMLElement>('#debug-log');
const timingSummaryEl = requireEl<HTMLElement>('#timing-summary');
const disconnectButton = requireEl<HTMLButtonElement>('#disconnect-btn');
const clearDebugBtn = requireEl<HTMLButtonElement>('#clear-debug-btn');
const copyDebugBtn = requireEl<HTMLButtonElement>('#copy-debug-btn');
const audioUnlockBanner = requireEl<HTMLDivElement>('#audio-unlock-banner');
const unlockAudioBtn = requireEl<HTMLButtonElement>('#unlock-audio-btn');
const languageSelect = requireEl<HTMLSelectElement>('#agent-language');
const sttSelect = requireEl<HTMLSelectElement>('#stt-provider');
const llmSelect = requireEl<HTMLSelectElement>('#llm-provider');
const ttsSelect = requireEl<HTMLSelectElement>('#tts-provider');
const pipelineSummary = requireEl<HTMLElement>('#pipeline-summary');

languageSelect.addEventListener('change', () => {
  refillProvidersForLanguage(languageSelect.value, { keepCurrent: false });
  updatePipelineSummary();
  schedulePipelineApply();
});
sttSelect.addEventListener('change', () => {
  updatePipelineSummary();
  schedulePipelineApply();
});
llmSelect.addEventListener('change', () => {
  updatePipelineSummary();
  schedulePipelineApply();
});
ttsSelect.addEventListener('change', () => {
  updatePipelineSummary();
  schedulePipelineApply();
});

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

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (agent) {
    await agent.disconnect();
    agent = null;
  }

  const formData = new FormData(form);
  const publishableKey = String(formData.get('publishableKey') ?? '').trim();
  const sessionEndpoint = String(formData.get('sessionEndpoint') ?? '').trim();
  const refreshEndpoint = String(formData.get('refreshEndpoint') ?? '').trim();
  const agentId = String(formData.get('agentId') ?? '').trim();
  const agentLanguage = String(formData.get('agentLanguage') ?? '').trim();
  const sttProvider = String(formData.get('sttProvider') ?? '').trim();
  const llmProvider = String(formData.get('llmProvider') ?? '').trim();
  const ttsProvider = String(formData.get('ttsProvider') ?? '').trim();

  resetSessionView();
  state.timing.clickAt = performance.now();
  pushDebug(
    'info',
    'Connect clicked',
    `pipeline ${agentLanguage}/${sttProvider}/${llmProvider}/${ttsProvider}`,
  );
  setStatus('preparing pipeline');

  try {
    if (!agentLanguage || !sttProvider || !llmProvider || !ttsProvider) {
      throw new Error('Select language, STT, LLM, and TTS before connecting');
    }

    const fingerprint = pipelineFingerprint(
      agentId,
      agentLanguage,
      sttProvider,
      llmProvider,
      ttsProvider,
    );
    const pipelineStarted = performance.now();

    // Wait for any in-flight dropdown apply, then skip PATCH when already matching.
    if (pipelineApplyInFlight) {
      pushDebug('info', 'Waiting for background pipeline apply…');
      await pipelineApplyInFlight;
    }

    let prepared: { applied: Record<string, string>; skipped?: boolean };
    if (fingerprint === lastAppliedFingerprint) {
      prepared = {
        skipped: true,
        applied: {
          agentLanguage,
          sttProvider,
          sttModel: 'cached',
          llmProvider,
          llmModel: 'cached',
          ttsProvider,
          ttsVoiceId: 'cached',
        },
      };
      state.timing.pipelineDoneAt = performance.now();
      pushDebug(
        'metric',
        `Pipeline skipped — already applied (+${msSinceClick()}ms)`,
        `duration ${Math.round(state.timing.pipelineDoneAt - pipelineStarted)}ms`,
      );
    } else {
      prepared = await preparePipeline(agentId, {
        agentLanguage,
        sttProvider,
        llmProvider,
        ttsProvider,
      });
      state.timing.pipelineDoneAt = performance.now();
      lastAppliedFingerprint = fingerprint;
      state.pipelineText = formatAppliedPipeline(prepared.applied);
      pushDebug(
        'metric',
        prepared.skipped
          ? `Pipeline unchanged on agent (+${msSinceClick()}ms)`
          : `Pipeline PATCH done (+${msSinceClick()}ms)`,
        `duration ${Math.round(state.timing.pipelineDoneAt - pipelineStarted)}ms · ${formatAppliedPipeline(prepared.applied)}${prepared.skipped ? ' · skipped' : ''}`,
      );
    }
    render();

    setStatus('connecting');
    pushDebug('info', 'Mint + LiveKit connect starting…');
    agent = new AwaazLabsUvaVoice({
      publishableKey,
      sessionEndpoint,
      refreshEndpoint: refreshEndpoint || undefined,
    });
    bindAgent(agent);
    const connectStarted = performance.now();
    await agent.connect({ agentId });
    pushDebug(
      'metric',
      `agent.connect() resolved (+${msSinceClick()}ms)`,
      `await ${Math.round(performance.now() - connectStarted)}ms · state=${agent.connectionState}`,
    );
    setStatus(agent.connectionState);
  } catch (error) {
    renderError(error);
    setStatus('idle');
    agent = null;
  }
});

disconnectButton.addEventListener('click', async () => {
  pushDebug('info', 'Disconnect clicked');
  if (!agent) {
    setStatus('idle');
    return;
  }
  await agent.disconnect();
  agent = null;
  setStatus('idle');
});

unlockAudioBtn.addEventListener('click', async () => {
  pushDebug('info', 'Unlock audio clicked');
  if (agent) {
    await agent.startAudio();
  }
});

void bootstrapPipelineControls();
render();

function bindAgent(client: AwaazLabsUvaVoice): void {
  client.on('connected', () => {
    state.timing.connectedAt = performance.now();
    pushDebug('metric', `Room connected (+${msSinceClick()}ms)`);
    setStatus('connected');
  });
  client.on('disconnected', (reason) => {
    pushDebug('warn', 'Disconnected', reason == null ? undefined : String(reason));
    setStatus('idle');
  });
  client.on('transcript', (entry) => {
    state.transcript = [...state.transcript, entry];
    if (entry.speaker === 'agent' && state.timing.firstAgentTranscriptAt == null) {
      state.timing.firstAgentTranscriptAt = performance.now();
      pushDebug(
        'metric',
        `First agent transcript (+${msSinceClick()}ms)`,
        `${entry.final ? 'final' : 'partial'}: ${truncate(entry.text, 80)}`,
      );
    } else {
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
      pushDebug('metric', `First agent audio (speaking) (+${msSinceClick()}ms)`);
    } else {
      pushDebug('info', isSpeaking ? 'Agent speaking: yes' : 'Agent speaking: no');
    }
    render();
  });
  client.on('metrics_updated', (metrics) => {
    state.latestMetrics = metrics;
    state.timing.lastMetricsAt = performance.now();
    pushDebug('metric', `metrics_updated (+${msSinceClick()}ms)`, summarizeMetrics(metrics));
    render();
  });
  client.on('turn_latency', (metrics) => {
    state.latestMetrics = metrics;
    if (state.timing.firstTurnLatencyAt == null) {
      state.timing.firstTurnLatencyAt = performance.now();
      pushDebug('metric', `First turn_latency (+${msSinceClick()}ms)`, summarizeMetrics(metrics));
    } else {
      pushDebug('metric', `turn_latency (+${msSinceClick()}ms)`, summarizeMetrics(metrics));
    }
    render();
  });
  client.on('error', (error) => renderError(error));
  client.on('ended', (reason) => {
    pushDebug('warn', 'Session ended', reason == null ? undefined : String(reason));
    state.status = `ended${reason ? ` (${String(reason)})` : ''}`;
    state.audioBlocked = false;
    render();
  });
  client.on('audio_blocked', (blocked) => {
    state.audioBlocked = Boolean(blocked);
    pushDebug(blocked ? 'warn' : 'info', blocked ? 'Audio blocked by browser' : 'Audio unblocked');
    render();
  });
}

async function bootstrapPipelineControls(): Promise<void> {
  try {
    const [capsRes, agentsRes] = await Promise.all([
      fetch(`${backendOrigin}/api/provider-capabilities`),
      fetch(`${backendOrigin}/api/agents`),
    ]);

    if (!capsRes.ok) {
      const body = await capsRes.json().catch(() => ({}));
      throw new Error(body.message || body.error || `capabilities HTTP ${capsRes.status}`);
    }

    capabilities = (await capsRes.json()) as ProviderCapabilities;
    const languages = Object.keys(capabilities.languages || {});
    if (languages.length === 0) {
      throw new Error('No enabled languages returned from provider capabilities');
    }

    let preferred: Partial<AgentRecord> = {};
    if (agentsRes.ok) {
      const payload = (await agentsRes.json()) as { agents?: AgentRecord[] };
      preferred = payload.agents?.find((item) => item.id === envDefaults.agentId) ?? {};
    }

    fillSelect(
      languageSelect,
      languages.map((code) => ({
        value: code,
        label: `${capabilities!.languages[code]?.label || code} (${code})`,
      })),
      preferred.agent_language || languages[0],
    );
    languageSelect.disabled = false;

    refillProvidersForLanguage(languageSelect.value, {
      keepCurrent: true,
      preferredStt: preferred.stt_provider,
      preferredLlm: preferred.llm_provider,
      preferredTts: preferred.tts_provider,
    });
    updatePipelineSummary();
    pushDebug('info', 'Provider capabilities loaded', `${languages.length} language(s)`);
    schedulePipelineApply();
  } catch (error) {
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
  const sttModel = lang.stt?.[stt]?.defaultModel || (lang.stt?.[stt]?.models || [])[0] || 'default';
  const llmModel = lang.llm?.[llm]?.defaultModel || (lang.llm?.[llm]?.models || [])[0] || '?';
  const voice = lang.tts?.[tts]?.defaultVoice || (lang.tts?.[tts]?.voices || [])[0] || '?';
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
  },
): Promise<{ applied: Record<string, string>; skipped?: boolean }> {
  const res = await fetch(`${backendOrigin}/api/agents/${encodeURIComponent(agentId)}/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(selection),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.message || body.error || `pipeline HTTP ${res.status}`);
  }
  return body as { applied: Record<string, string>; skipped?: boolean };
}

function schedulePipelineApply(): void {
  if (pipelineApplyTimer) clearTimeout(pipelineApplyTimer);
  pipelineApplyTimer = setTimeout(() => {
    void applyPipelineInBackground();
  }, 250);
}

async function applyPipelineInBackground(): Promise<void> {
  const agentId = String(
    (document.querySelector('#agent-id') as HTMLInputElement | null)?.value ?? '',
  ).trim();
  const agentLanguage = languageSelect.value.trim();
  const sttProvider = sttSelect.value.trim();
  const llmProvider = llmSelect.value.trim();
  const ttsProvider = ttsSelect.value.trim();
  if (!agentId || !agentLanguage || !sttProvider || !llmProvider || !ttsProvider) return;

  const fingerprint = pipelineFingerprint(
    agentId,
    agentLanguage,
    sttProvider,
    llmProvider,
    ttsProvider,
  );
  if (fingerprint === lastAppliedFingerprint) return;

  const run = (async () => {
    try {
      pushDebug(
        'info',
        'Applying pipeline in background…',
        `${agentLanguage}/${sttProvider}/${llmProvider}/${ttsProvider}`,
      );
      render();
      const prepared = await preparePipeline(agentId, {
        agentLanguage,
        sttProvider,
        llmProvider,
        ttsProvider,
      });
      lastAppliedFingerprint = fingerprint;
      state.pipelineText = formatAppliedPipeline(prepared.applied);
      pushDebug(
        'metric',
        prepared.skipped ? 'Background pipeline already on agent' : 'Background pipeline applied',
        formatAppliedPipeline(prepared.applied),
      );
      render();
    } catch (error) {
      pushDebug(
        'warn',
        'Background pipeline apply failed',
        error instanceof Error ? error.message : String(error),
      );
      render();
    }
  })();
  pipelineApplyInFlight = run.finally(() => {
    if (pipelineApplyInFlight === run) pipelineApplyInFlight = null;
  });
  await pipelineApplyInFlight;
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
  state.latestMetrics = null;
  state.errors = [];
  state.audioBlocked = false;
  state.timing = emptyTiming();
  state.debugLog = [];
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
  statusText.textContent = state.status;
  speakingText.textContent = state.speaking ? 'Yes' : 'No';
  agentSpeakingText.textContent = state.agentSpeaking ? 'Yes' : 'No';
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
    transcriptList.innerHTML = '<li class="placeholder">No transcript yet.</li>';
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
  const cards: Array<{ label: string; value: string }> = [
    { label: 'Pipeline PATCH', value: deltaMs(timing.clickAt, timing.pipelineDoneAt) },
    { label: 'Room connected', value: deltaMs(timing.clickAt, timing.connectedAt) },
    { label: 'First agent audio', value: deltaMs(timing.clickAt, timing.firstAgentSpeakingAt) },
    {
      label: 'Connect → first audio',
      value: deltaMs(timing.connectedAt, timing.firstAgentSpeakingAt),
    },
    { label: 'First agent transcript', value: deltaMs(timing.clickAt, timing.firstAgentTranscriptAt) },
    { label: 'First turn_latency', value: deltaMs(timing.clickAt, timing.firstTurnLatencyAt) },
  ];
  return cards
    .map(
      (card) =>
        `<div class="timing-card"><span class="timing-label">${escapeHtml(card.label)}</span><span class="timing-value">${escapeHtml(card.value)}</span></div>`,
    )
    .join('');
}

function formatTimingPlain(timing: TimingSnapshot): string {
  return [
    `pipeline_patch_ms=${deltaMs(timing.clickAt, timing.pipelineDoneAt)}`,
    `room_connected_ms=${deltaMs(timing.clickAt, timing.connectedAt)}`,
    `first_agent_audio_ms=${deltaMs(timing.clickAt, timing.firstAgentSpeakingAt)}`,
    `connect_to_first_audio_ms=${deltaMs(timing.connectedAt, timing.firstAgentSpeakingAt)}`,
    `first_agent_transcript_ms=${deltaMs(timing.clickAt, timing.firstAgentTranscriptAt)}`,
    `first_turn_latency_ms=${deltaMs(timing.clickAt, timing.firstTurnLatencyAt)}`,
  ].join('\n');
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
    'stt_ms',
    'llm_ms',
    'tts_ttfb_ms',
    'e2e_ms',
    'stt_p50_ms',
    'llm_p50_ms',
    'tts_ttfb_p50_ms',
    'e2e_p50_ms',
    'opening_mode',
    'greeting_cache_hit',
    'prewarm_wait_ms',
    'ms_since_connect',
  ];
  const parts: string[] = [`type=${metrics.type}`];
  for (const key of keys) {
    if (metrics[key] != null) parts.push(`${key}=${String(metrics[key])}`);
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
