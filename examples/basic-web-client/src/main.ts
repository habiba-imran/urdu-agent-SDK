import { UrduVoiceAgent, UvaError, type MetricsEvent, type TranscriptEvent } from '@uva/voice';
import './style.css';

type AppState = {
  status: string;
  transcript: TranscriptEvent[];
  speaking: boolean;
  agentSpeaking: boolean;
  metricsText: string;
  errorText: string;
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
};

let agent: UrduVoiceAgent | null = null;

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
        This app uses <code>@uva/voice</code> in the browser and expects a host-owned session endpoint.
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
        Until the official host-backend starter exists, this app needs a compatible session endpoint supplied by the host platform or a temporary local bridge.
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
    agent = new UrduVoiceAgent({
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

function bindAgent(client: UrduVoiceAgent): void {
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
    state.speaking = isSpeaking;
    render();
  });
  client.on('agent_speaking', (isSpeaking) => {
    state.agentSpeaking = isSpeaking;
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
    render();
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
  render();
}

function renderError(error: unknown): void {
  if (isUvaError(error)) {
    state.errorText = `${error.code}: ${error.message}`;
  } else if (error instanceof Error) {
    state.errorText = error.message;
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

function isUvaError(error: unknown): error is UvaError {
  return error instanceof UvaError;
}

function escapeHtml(value: string): string {
  return value
    .split('&').join('&amp;')
    .split('<').join('&lt;')
    .split('>').join('&gt;')
    .split('"').join('&quot;')
    .split("'").join('&#39;');
}
