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
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT ?? '',
  refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT ?? '',
  agentId: import.meta.env.VITE_UVA_AGENT_ID ?? '',
  fetchTimeoutMs: Number(import.meta.env.VITE_UVA_FETCH_TIMEOUT_MS || 15000),
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
  pipelineText: 'Loading provider capabilities…',
  packageLabel: '@awaazlabs-uva/voice (resolving…)',
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
      <p class="brand">AwaazLabs UVA</p>
      <h1>Wave 1 browser demo</h1>
      <p>
        Host-style smoke for <code>npm install @awaazlabs-uva/voice</code>
        (browser) and <code>@awaazlabs-uva/agents</code> (this demo’s backend).
        Connect, hear first audio, exercise mute / unlock / timeout / error codes.
      </p>
      <p id="package-badge" class="package-badge">${escapeHtml(state.packageLabel)}</p>
    </header>

    <section class="panel">
      <h2>Session</h2>
      <form id="voice-form" class="form">
        <div class="session-grid">
          <label>
            Publishable key
            <input id="publishable-key" name="publishableKey" value="${escapeHtml(envDefaults.publishableKey)}" autocomplete="off" />
          </label>
          <label>
            Agent ID
            <input id="agent-id" name="agentId" value="${escapeHtml(envDefaults.agentId)}" autocomplete="off" />
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
            fetchTimeoutMs
            <input id="fetch-timeout-ms" name="fetchTimeoutMs" type="number" min="1000" step="1000" value="${escapeHtml(String(envDefaults.fetchTimeoutMs))}" />
          </label>
        </div>

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
          <button id="mute-btn" type="button" disabled>Mute mic</button>
          <button id="timeout-smoke-btn" type="button" title="Points sessionEndpoint at /api/demo/hang to verify timeout error">Timeout smoke</button>
        </div>
      </form>
      <p class="hint">
        Backend signs mint/refresh with HMAC and uses <code>@awaazlabs-uva/agents</code>
        for provider capabilities + pipeline PATCH. Browser never holds the tenant secret.
      </p>
    </section>

    <section class="grid stats-grid">
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
      <article class="panel">
        <h2>Mic</h2>
        <p id="mic-text" class="stat">Live</p>
      </article>
    </section>

    <section class="panel debug-panel">
      <div class="debug-header">
        <h2>First-audio timings</h2>
        <div class="debug-actions">
          <button id="copy-debug-btn" type="button">Copy</button>
          <button id="clear-debug-btn" type="button">Clear</button>
        </div>
      </div>
      <p class="hint debug-hint">
        Cold-start cards are from Connect click. <strong>Session mint</strong> vs
        <strong>LiveKit join</strong> split <code>room_connected</code>.
        <strong>Turn e2e</strong> is the real voice↔voice number from worker
        <code>turn_latency</code> (EOU → TTS TTFB).
        A second user final while the agent is still thinking cancels the first reply
        (watch for back-to-back user finals like “Thank you.”).
      </p>
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

    <section class="panel">
      <h2>Transcript</h2>
      <p class="hint">Segments with the same <code>id</code> replace earlier partials (SDK contract).</p>
      <ul id="transcript-list" class="transcript-list"></ul>
    </section>

    <div id="audio-unlock-banner" class="audio-unlock-banner">
      <p>Audio blocked by the browser — call <code>startAudio()</code> from a click.</p>
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
  if (!agent?.isConnected) return;
  const next = !state.micMuted;
  try {
    await agent.setMicMuted(next);
    state.micMuted = agent.isMicMuted;
    pushDebug('info', state.micMuted ? 'Mic muted' : 'Mic unmuted');
    render();
  } catch (error) {
    renderError(error);
  }
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
  const fetchTimeoutMs = Number(formData.get('fetchTimeoutMs') ?? envDefaults.fetchTimeoutMs);

  resetSessionView();
  state.timing.clickAt = performance.now();
  pushDebug(
    'info',
    'Connect clicked',
    `pipeline ${agentLanguage}/${sttProvider}/${llmProvider}/${ttsProvider} · timeout ${fetchTimeoutMs}ms`,
  );
  setStatus('preparing pipeline');

  try {
    const isHangSmoke = sessionEndpoint.includes('/api/demo/hang');
    if (!isHangSmoke && (!agentLanguage || !sttProvider || !llmProvider || !ttsProvider)) {
      throw new Error('Select language, STT, LLM, and TTS before connecting');
    }

    if (!isHangSmoke) {
      const fingerprint = pipelineFingerprint(
        agentId,
        agentLanguage,
        sttProvider,
        llmProvider,
        ttsProvider,
      );
      const pipelineStarted = performance.now();

      let prepared: { applied: Record<string, string>; skipped?: boolean };
      // Check local fingerprint FIRST — do not await a slow portal round-trip
      // when Connect already knows this combo is on the agent (was +~3s on smoke).
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
        if (pipelineApplyInFlight) {
          pushDebug('info', 'Waiting for background pipeline apply…');
          await pipelineApplyInFlight;
        }
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
            `Pipeline skipped after background apply (+${msSinceClick()}ms)`,
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
      }
      render();
    } else {
      state.timing.pipelineDoneAt = performance.now();
      pushDebug('warn', 'Skipping pipeline — hang timeout smoke');
    }

    setStatus('connecting');
    pushDebug('info', 'Mint + LiveKit connect starting…');
    agent = new AwaazLabsUvaVoice({
      publishableKey,
      sessionEndpoint,
      refreshEndpoint: refreshEndpoint || undefined,
      fetchTimeoutMs: Number.isFinite(fetchTimeoutMs) && fetchTimeoutMs > 0 ? fetchTimeoutMs : 15_000,
    });
    bindAgent(agent);
    const connectStarted = performance.now();
    await agent.connect({ agentId });
    pushDebug(
      'metric',
      `agent.connect() resolved (+${msSinceClick()}ms)`,
      `await ${Math.round(performance.now() - connectStarted)}ms · state=${agent.connectionState}`,
    );
    state.micMuted = agent.isMicMuted;
    muteButton.disabled = false;
    setStatus(agent.connectionState);
  } catch (error) {
    renderError(error);
    setStatus('idle');
    agent = null;
    muteButton.disabled = true;
  }
});

disconnectButton.addEventListener('click', async () => {
  pushDebug('info', 'Disconnect clicked');
  if (!agent) {
    setStatus('idle');
    muteButton.disabled = true;
    return;
  }
  await agent.disconnect();
  agent = null;
  state.micMuted = false;
  muteButton.disabled = true;
  setStatus('idle');
});

unlockAudioBtn.addEventListener('click', async () => {
  pushDebug('info', 'Unlock audio clicked');
  if (agent) {
    await agent.startAudio();
  }
});

state.packageLabel = `npm · @awaazlabs-uva/voice@${__UVA_VOICE_VERSION__}`;
void bootstrapPipelineControls();
render();

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
      pushDebug('metric', `First agent audio (speaking) (+${msSinceClick()}ms)`);
    } else if (
      isSpeaking &&
      state.timing.lastUserFinalAt != null &&
      state.timing.lastAgentReplyAudioAt == null
    ) {
      state.timing.lastAgentReplyAudioAt = performance.now();
      const gap = Math.round(state.timing.lastAgentReplyAudioAt - state.timing.lastUserFinalAt);
      state.thinking = false;
      if (state.status === 'thinking') setStatus('connected');
      pushDebug('metric', `User-final → agent audio (perceived) ${gap}ms`);
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
    ingestTurnLatency(metrics);
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
    state.audioBlocked = false;
    muteButton.disabled = true;
    render();
  });
  client.on('audio_blocked', (blocked) => {
    state.audioBlocked = Boolean(blocked);
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
  state.micMuted = false;
  state.thinking = false;
  state.latestMetrics = null;
  state.errors = [];
  state.audioBlocked = false;
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
  statusText.textContent = state.thinking ? 'thinking (LLM/TTS…)' : state.status;
  speakingText.textContent = state.speaking ? 'Yes' : 'No';
  agentSpeakingText.textContent = state.agentSpeaking ? 'Yes' : 'No';
  micText.textContent = state.micMuted ? 'Muted' : 'Live';
  muteButton.textContent = state.micMuted ? 'Unmute mic' : 'Mute mic';
  packageBadge.textContent = state.packageLabel;
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
  const perceived =
    timing.lastUserFinalAt != null && timing.lastAgentReplyAudioAt != null
      ? `${Math.round(timing.lastAgentReplyAudioAt - timing.lastUserFinalAt)}ms`
      : '—';
  const cards: Array<{ label: string; value: string }> = [
    { label: 'Pipeline PATCH', value: deltaMs(timing.clickAt, timing.pipelineDoneAt) },
    {
      label: 'Session mint',
      value: timing.sessionMintMs != null ? `${timing.sessionMintMs}ms` : '—',
    },
    {
      label: 'LiveKit join',
      value: timing.livekitConnectMs != null ? `${timing.livekitConnectMs}ms` : '—',
    },
    { label: 'Room connected', value: deltaMs(timing.clickAt, timing.connectedAt) },
    { label: 'Connect → first audio', value: deltaMs(timing.connectedAt, timing.firstAgentSpeakingAt) },
    { label: 'Turn e2e (worker)', value: timing.lastTurnE2eMs != null ? `${timing.lastTurnE2eMs}ms` : '—' },
    { label: 'Turn LLM TTFT', value: timing.lastTurnLlmMs != null ? `${timing.lastTurnLlmMs}ms` : '—' },
    { label: 'Turn TTS TTFB', value: timing.lastTurnTtsTtfbMs != null ? `${timing.lastTurnTtsTtfbMs}ms` : '—' },
    { label: 'User-final → audio', value: perceived },
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
    `pipeline_patch_ms=${deltaMs(timing.clickAt, timing.pipelineDoneAt)}`,
    `session_mint_ms=${timing.sessionMintMs ?? '—'}`,
    `livekit_connect_ms=${timing.livekitConnectMs ?? '—'}`,
    `room_connected_ms=${deltaMs(timing.clickAt, timing.connectedAt)}`,
    `connect_to_first_audio_ms=${deltaMs(timing.connectedAt, timing.firstAgentSpeakingAt)}`,
    `turn_e2e_ms=${timing.lastTurnE2eMs ?? '—'}`,
    `turn_llm_ttft_ms=${timing.lastTurnLlmMs ?? '—'}`,
    `turn_tts_ttfb_ms=${timing.lastTurnTtsTtfbMs ?? '—'}`,
    `turn_stt_ms=${timing.lastTurnSttMs ?? '—'}`,
    `user_final_to_audio_ms=${perceived}`,
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
