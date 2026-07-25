import {
  AwaazLabsUvaVoice,
  AwaazLabsUvaVoiceError,
  type MetricsEvent,
  type TranscriptEvent,
} from '@awaazlabs-uva/voice';
import './style.css';

type AppState = {
  status: string;
  transcript: TranscriptEvent[];
  speaking: boolean;
  agentSpeaking: boolean;
  metricsText: string;
  errorText: string;
  audioBlocked: boolean;
};

const envDefaults = {
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY ?? '',
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT ?? '',
  refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT ?? '',
  agentId: import.meta.env.VITE_UVA_AGENT_ID ?? '',
};

const state: AppState = {
  status: 'idle',
  transcript: [],
  speaking: false,
  agentSpeaking: false,
  metricsText: 'No metrics received yet.',
  errorText: '',
  audioBlocked: false,
};

let agent: AwaazLabsUvaVoice | null = null;

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) {
  throw new Error('App root not found');
}

app.innerHTML = `
  <main class="shell">
    <section class="panel hero">
      <p class="eyebrow">Phase 0 Example Consumer</p>
      <h1>Basic Web Client</h1>
      <p class="lede">
        This app uses <code>@awaazlabs-uva/voice</code> in the browser and expects a host-owned session endpoint.
      </p>
    </section>

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
        <div class="actions">
          <button id="connect-btn" type="submit">Connect</button>
          <button id="disconnect-btn" type="button">Disconnect</button>
        </div>
      </form>
      <p class="hint">
        Pair this app with <code>examples/host-backend</code> or another host-owned backend that implements the documented session contract.
      </p>
    </section>

    <section class="grid">
      <article class="panel stat-card">
        <h2>Status</h2>
        <p id="status-text" class="stat">idle</p>
      </article>
      <article class="panel stat-card">
        <h2>Caller Speaking</h2>
        <p id="speaking-text" class="stat">No</p>
      </article>
      <article class="panel stat-card">
        <h2>Agent Speaking</h2>
        <p id="agent-speaking-text" class="stat">No</p>
      </article>
    </section>

    <section class="grid">
      <article class="panel">
        <h2>Transcript</h2>
        <ul id="transcript-list" class="transcript-list"></ul>
      </article>
      <article class="panel">
        <h2>Metrics</h2>
        <pre id="metrics-output" class="log-box">No metrics received yet.</pre>
      </article>
    </section>

    <section class="panel">
      <h2>Errors</h2>
      <pre id="error-output" class="log-box">No errors.</pre>
    </section>

    <div id="audio-unlock-banner" class="audio-unlock-banner" style="display:none">
      <p>Audio blocked by browser autoplay policy.</p>
      <button id="unlock-audio-btn" type="button">Unlock Audio</button>
    </div>
  </main>
`;

const formElement = document.querySelector<HTMLFormElement>('#voice-form');
const statusTextElement = document.querySelector<HTMLElement>('#status-text');
const speakingTextElement = document.querySelector<HTMLElement>('#speaking-text');
const agentSpeakingTextElement = document.querySelector<HTMLElement>('#agent-speaking-text');
const transcriptListElement = document.querySelector<HTMLUListElement>('#transcript-list');
const metricsOutputElement = document.querySelector<HTMLElement>('#metrics-output');
const errorOutputElement = document.querySelector<HTMLElement>('#error-output');
const connectButtonElement = document.querySelector<HTMLButtonElement>('#connect-btn');
const disconnectButtonElement = document.querySelector<HTMLButtonElement>('#disconnect-btn');
const audioUnlockBannerElement = document.querySelector<HTMLDivElement>('#audio-unlock-banner');
const unlockAudioBtnElement = document.querySelector<HTMLButtonElement>('#unlock-audio-btn');

if (
  !formElement ||
  !statusTextElement ||
  !speakingTextElement ||
  !agentSpeakingTextElement ||
  !transcriptListElement ||
  !metricsOutputElement ||
  !errorOutputElement ||
  !connectButtonElement ||
  !disconnectButtonElement
) {
  throw new Error('Example app UI failed to initialize');
}

const form = formElement;
const statusText = statusTextElement;
const speakingText = speakingTextElement;
const agentSpeakingText = agentSpeakingTextElement;
const transcriptList = transcriptListElement;
const metricsOutput = metricsOutputElement;
const errorOutput = errorOutputElement;
const connectButton = connectButtonElement;
const disconnectButton = disconnectButtonElement;
const audioUnlockBanner = audioUnlockBannerElement;
const unlockAudioBtn = unlockAudioBtnElement;

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

  resetSessionView();
  setStatus('connecting');

  try {
    agent = new AwaazLabsUvaVoice({
      publishableKey,
      sessionEndpoint,
      refreshEndpoint: refreshEndpoint || undefined,
    });
    bindAgent(agent);
    await agent.connect({ agentId });
    setStatus(agent.connectionState);
  } catch (error) {
    renderError(error);
    setStatus('idle');
    agent = null;
  }
});

disconnectButton.addEventListener('click', async () => {
  if (!agent) {
    setStatus('idle');
    return;
  }
  await agent.disconnect();
  agent = null;
  setStatus('idle');
});

render();

function bindAgent(client: AwaazLabsUvaVoice): void {
  client.on('connected', () => {
    setStatus('connected');
  });
  client.on('disconnected', () => {
    setStatus('idle');
  });
  client.on('transcript', (entry) => {
    state.transcript = [...state.transcript, entry];
    render();
  });
  client.on('speaking', (isSpeaking) => {
    state.speaking = Boolean(isSpeaking);
    render();
  });
  client.on('agent_speaking', (isSpeaking) => {
    state.agentSpeaking = Boolean(isSpeaking);
    render();
  });
  client.on('metrics_updated', (metrics) => {
    state.metricsText = formatMetrics(metrics);
    render();
  });
  client.on('error', (error) => {
    renderError(error);
  });
  client.on('ended', (reason) => {
    state.status = `ended${reason ? ` (${String(reason)})` : ''}`;
    state.audioBlocked = false;
    render();
  });
  client.on('audio_blocked', (blocked) => {
    state.audioBlocked = Boolean(blocked);
    render();
  });
}

// This must be a real user click so the browser allows remote audio playback.
if (unlockAudioBtn) {
  unlockAudioBtn.addEventListener('click', async () => {
    if (agent) {
      await agent.startAudio();
    }
  });
}

function setStatus(status: string): void {
  state.status = status;
  render();
}

function resetSessionView(): void {
  state.transcript = [];
  state.speaking = false;
  state.agentSpeaking = false;
  state.metricsText = 'No metrics received yet.';
  state.errorText = '';
  state.audioBlocked = false;
  render();
}

function renderError(error: unknown): void {
  if (isAwaazLabsUvaVoiceError(error)) {
    state.errorText = `${error.code}: ${error.message}`;
  } else if (error && typeof error === 'object' && 'message' in error) {
    state.errorText = String((error as { message: unknown }).message);
  } else {
    state.errorText = 'Unknown error';
  }
  render();
}

function render(): void {
  statusText.textContent = state.status;
  speakingText.textContent = state.speaking ? 'Yes' : 'No';
  agentSpeakingText.textContent = state.agentSpeaking ? 'Yes' : 'No';
  metricsOutput.textContent = state.metricsText;
  errorOutput.textContent = state.errorText || 'No errors.';

  if (audioUnlockBanner) {
    audioUnlockBanner.style.display = state.audioBlocked ? 'flex' : 'none';
  }

  if (state.transcript.length === 0) {
    transcriptList.innerHTML = '<li class="placeholder">No transcript yet.</li>';
  } else {
    transcriptList.innerHTML = state.transcript
      .map((entry) => {
        const finalLabel = entry.final ? 'final' : 'partial';
        return `<li><span class="badge">${finalLabel}</span><span>${escapeHtml(entry.text)}</span></li>`;
      })
      .join('');
  }
}

function formatMetrics(metrics: MetricsEvent): string {
  return JSON.stringify(metrics, null, 2);
}

function isAwaazLabsUvaVoiceError(error: unknown): error is AwaazLabsUvaVoiceError {
  return error instanceof AwaazLabsUvaVoiceError;
}

function escapeHtml(value: string): string {
  return value
    .split('&').join('&amp;')
    .split('<').join('&lt;')
    .split('>').join('&gt;')
    .split('"').join('&quot;')
    .split("'").join('&#39;');
}
