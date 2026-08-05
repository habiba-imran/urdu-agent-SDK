import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const API = import.meta.env.VITE_TEST_BACKEND_URL || 'http://localhost:3001';
const MAX_CLIENT_DEBUG_EVENTS = 60;
const state = {
  numbers: [],
  agents: [],
  debugEvents: [],
  clientDebugEvents: [],
  pendingNumber: null,
  pendingPurchase: null,
  pendingReservation: null,
  voiceClient: null,
  audioNeedsUnlock: false,
  activeCallPoll: null,
};

const TERMINAL_CALL_STATUSES = new Set(['completed', 'busy', 'no_answer', 'failed', 'cancelled']);

function $(id) {
  return document.getElementById(id);
}

function on(id, event, handler) {
  const element = $(id);
  if (element) element.addEventListener(event, handler);
}

function escHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}

function normalizeCollection(result, keys = []) {
  if (Array.isArray(result)) return result;
  for (const key of keys) {
    if (Array.isArray(result?.[key])) return result[key];
  }
  return [];
}

function isoNow() {
  return new Date().toISOString();
}

function pushClientDebugEvent(event) {
  state.clientDebugEvents.unshift({
    id: crypto.randomUUID(),
    createdAt: isoNow(),
    source: 'frontend',
    ...event,
  });
  if (state.clientDebugEvents.length > MAX_CLIENT_DEBUG_EVENTS) {
    state.clientDebugEvents.length = MAX_CLIENT_DEBUG_EVENTS;
  }
  renderDebugPanel();
}

function sortedDebugEvents() {
  return [...state.clientDebugEvents, ...state.debugEvents].sort((a, b) => (
    new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime()
  ));
}

function formatDebugValue(value) {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function renderDebugPanel() {
  const target = $('debug-log-list');
  if (!target) return;
  const events = sortedDebugEvents();
  if (!events.length) {
    target.innerHTML = '<div class="empty-state"><div class="empty-state-title">No recent diagnostics</div><div class="empty-state-text">Browser requests, backend responses, and telephony diagnostics will appear here.</div></div>';
    return;
  }
  target.innerHTML = events.map((item) => {
    const requestBlock = formatDebugValue(item.request);
    const responseBlock = formatDebugValue(item.response);
    const detailBlock = formatDebugValue(item.detail);
    return `
      <div class="number-card debug-event-card" style="margin-bottom:0.75rem; border-radius: var(--radius-sm)">
        <div>
          <div class="flex justify-between items-center gap-1">
            <div class="number-display" style="font-size:0.9rem">${escHtml(item.scope || item.code || 'event')}</div>
            <div class="number-meta flex gap-1">
              ${item.source ? `<span class="badge badge-blue">${escHtml(item.source)}</span>` : ''}
              ${statusBadge(item.status || (item.ok === false ? 'error' : 'info'))}
            </div>
          </div>
          <div class="number-meta flex gap-1 mt-1">
            ${item.code ? `<span class="badge badge-red">${escHtml(item.code)}</span>` : ''}
            ${item.method ? `<span class="badge badge-gray">${escHtml(item.method)}</span>` : ''}
            ${item.route ? `<span class="badge badge-gray">${escHtml(item.route)}</span>` : ''}
          </div>
          <div class="readiness-detail" style="margin-top:0.5rem">${escHtml(item.createdAt || '')}</div>
          ${item.message ? `<div class="readiness-label" style="margin-top:0.35rem">${escHtml(item.message)}</div>` : ''}
          ${requestBlock ? `<details class="debug-detail"><summary>Request</summary><div class="code-block">${escHtml(requestBlock)}</div></details>` : ''}
          ${responseBlock ? `<details class="debug-detail"><summary>Response</summary><div class="code-block">${escHtml(responseBlock)}</div></details>` : ''}
          ${detailBlock ? `<details class="debug-detail"><summary>Detail</summary><div class="code-block">${escHtml(detailBlock)}</div></details>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

async function api(method, path, body, options = {}) {
  const startedAt = isoNow();
  const response = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(() => ({ message: 'No response body' }));
  if (!options.skipDebugLog && path !== '/api/debug/errors' && path !== '/api/debug/errors/clear') {
    pushClientDebugEvent({
      scope: response.ok ? 'frontend_api_response' : 'frontend_api_error',
      route: path,
      method,
      status: response.status,
      ok: response.ok,
      requestStartedAt: startedAt,
      request: body || null,
      response: payload,
      message: response.ok
        ? `HTTP ${response.status} ${method} ${path}`
        : (payload?.message || payload?.detail?.error?.message || `HTTP ${response.status}`),
    });
  }
  if (!response.ok) {
    const message =
      payload?.message ||
      payload?.detail?.error?.message ||
      payload?.detail ||
      `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.code = payload?.code || payload?.detail?.error?.code;
    error.detail = payload?.detail;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function toast(type, title, message = '') {
  const icons = {
    success: 'OK',
    error: 'ERR',
    info: 'INFO',
    warning: 'WARN',
  };
  const container = $('toast-container');
  if (!container) return;
  const item = document.createElement('div');
  item.className = `toast ${type}`;
  item.innerHTML = `
    <div class="toast-icon">${icons[type] || 'INFO'}</div>
    <div class="toast-content">
      <div class="toast-title">${escHtml(title)}</div>
      ${message ? `<div class="toast-msg">${escHtml(message)}</div>` : ''}
    </div>
  `;
  container.appendChild(item);
  setTimeout(() => item.remove(), 4200);
}

function setLoading(button, loading, label = 'Loading...') {
  if (!button) return;
  button.disabled = loading;
  if (loading) {
    button.dataset.originalLabel = button.innerHTML;
    button.innerHTML = `<div class="spinner"></div> ${escHtml(label)}`;
  } else if (button.dataset.originalLabel) {
    button.innerHTML = button.dataset.originalLabel;
  }
}

function statusBadge(status) {
  const normalized = String(status || 'unknown').toLowerCase();
  const map = {
    active: 'badge-green',
    completed: 'badge-green',
    ready: 'badge-green',
    connected: 'badge-green',
    disabled: 'badge-red',
    failed: 'badge-red',
    error: 'badge-red',
    not_configured: 'badge-yellow',
    pending: 'badge-yellow',
    purchased: 'badge-blue',
    owned: 'badge-blue',
    dialing: 'badge-blue',
    ringing: 'badge-yellow',
  };
  return `<span class="badge ${map[normalized] || 'badge-gray'}">${escHtml(status || 'unknown')}</span>`;
}

function providerBadge(label, value, cls) {
  if (!value) return '';
  return `<span class="badge ${cls}">${escHtml(label)}: ${escHtml(value)}</span>`;
}

function updateStatusItem(id, stateName, label, detail = '') {
  const target = $(id);
  if (!target) return;
  const icons = { pass: 'OK', fail: 'ERR', pending: '...' };
  target.className = `readiness-item ${stateName}`;
  target.innerHTML = `
    <span class="readiness-icon">${icons[stateName] || '...'}</span>
    <div>
      <div class="readiness-label">${escHtml(label)}</div>
      ${detail ? `<div class="readiness-detail">${escHtml(detail)}</div>` : ''}
    </div>
  `;
}

function getAgentLabel(agentId) {
  if (!agentId) return 'Unassigned';
  const agent = state.agents.find((item) => item.id === agentId);
  return agent ? `${agent.name} (${agent.id.slice(0, 8)}...)` : `${agentId.slice(0, 8)}...`;
}

function getNumberLabel(number) {
  return number?.e164_number || number?.phone_number || number?.number || number?.id || '';
}

function getNumberPriceSummary(number) {
  if (!number) return 'Price unavailable';
  const upfront = number.upfront_cost ?? null;
  const monthly = number.monthly_cost ?? null;
  const currency = number.currency || 'USD';
  const parts = [];
  if (upfront) parts.push(`Upfront ${upfront} ${currency}`);
  if (monthly) parts.push(`Monthly ${monthly} ${currency}`);
  return parts.length ? parts.join(' • ') : 'Price unavailable';
}

function syncAgentSelections(agentId) {
  if (!agentId) return;
  ['pt-agent-id', 'call-agent-id', 'inbound-agent-id', 'voice-agent-id'].forEach((id) => {
    const select = $(id);
    if (select) select.value = agentId;
  });
}

function syncNumberSelections(numberId) {
  if (!numberId) return;
  ['pt-number-id', 'call-from-id', 'inbound-number-id'].forEach((id) => {
    const select = $(id);
    if (select) select.value = numberId;
  });
}

function handleNumberSelection(numberId) {
  const number = state.numbers.find((item) => item.id === numberId);
  if (!number) return;
  syncNumberSelections(numberId);
  if (number.assigned_agent_id) syncAgentSelections(number.assigned_agent_id);
}

function getAssignedAgentIdForNumber(numberId) {
  const number = state.numbers.find((item) => item.id === numberId);
  return number?.assigned_agent_id || '';
}

function renderNumberOptions(selectId) {
  const select = $(selectId);
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">-- select a managed number --</option>' +
    state.numbers.map((number) => {
      const suffix = number.assigned_agent_id ? ` -> ${getAgentLabel(number.assigned_agent_id)}` : ' -> unassigned';
      return `<option value="${escHtml(number.id)}">${escHtml(`${getNumberLabel(number)}${suffix}`)}</option>`;
    }).join('');
  if (current) select.value = current;
}

function renderAgentOptions(selectId) {
  const select = $(selectId);
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">-- select an agent --</option>' +
    state.agents.map((agent) => (
      `<option value="${escHtml(agent.id)}">${escHtml(`${agent.name} (${agent.id.slice(0, 8)}...)`)}</option>`
    )).join('');
  if (current) select.value = current;
}

function activateTab(tabName) {
  document.querySelectorAll('.tab-btn').forEach((item) => {
    item.classList.toggle('active', item.dataset.tab === tabName);
  });
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.classList.toggle('active', panel.id === `tab-${tabName}`);
  });
}

async function refreshNumbersAndAgents() {
  const [numbersResult, agentsResult] = await Promise.all([
    api('GET', '/api/telnyx/numbers/managed'),
    api('GET', '/api/agents'),
  ]);
  state.numbers = normalizeCollection(numbersResult, ['data', 'numbers', 'items']);
  state.agents = normalizeCollection(agentsResult, ['agents', 'data', 'items']);
}

async function populateProviderTestSelects() {
  try {
    if (!state.numbers.length || !state.agents.length) {
      await refreshNumbersAndAgents();
    }
  } catch {
    return;
  }
  ['pt-number-id', 'call-from-id', 'inbound-number-id'].forEach(renderNumberOptions);
  ['pt-agent-id', 'call-agent-id', 'inbound-agent-id', 'voice-agent-id'].forEach(renderAgentOptions);
}

function renderReadiness(data) {
  const target = $('readiness-results');
  if (!target) return;
  const ready = data?.is_ready === true;
  const reasons = Array.isArray(data?.reasons) ? data.reasons : [];
  target.innerHTML = `
    <div class="readiness-item ${ready ? 'pass' : 'fail'}" style="margin-bottom:0.75rem; font-weight:600;">
      <span class="readiness-icon">${ready ? 'OK' : 'ERR'}</span>
      <div>
        <div class="readiness-label">Outbound is ${ready ? 'ready' : 'not ready'}</div>
        <div class="readiness-detail">Active numbers: ${escHtml(String(data?.active_numbers_count ?? 0))}</div>
      </div>
    </div>
    ${(reasons.length ? reasons : ['All readiness checks passed.']).map((reason) => `
      <div class="readiness-item ${ready ? 'pass' : 'fail'}">
        <span class="readiness-icon">${ready ? 'OK' : 'ERR'}</span>
        <div><div class="readiness-label">${escHtml(reason)}</div></div>
      </div>
    `).join('')}
  `;
}

function renderTelephonyDiagnostics(detail, toNumber = '') {
  const diagnostics = detail?.diagnostics || null;
  const upstreamProbe = detail?.upstreamProbe || null;
  const readiness = diagnostics?.readiness || null;
  const selectedNumber = diagnostics?.selectedNumber || null;
  const assignedAgent = diagnostics?.assignedAgent || null;
  const notes = diagnostics?.notes || [];
  const likelyCauses = upstreamProbe?.likelyCauses || [];

  return `
    <div class="card" style="border-color: var(--yellow)">
      <div class="card-title">Outbound diagnostics</div>
      <div class="readiness-item fail">
        <span class="readiness-icon">ERR</span>
        <div>
          <div class="readiness-label">${escHtml(upstreamProbe?.status ? `Upstream status ${upstreamProbe.status}` : 'No structured upstream response')}</div>
          <div class="readiness-detail">
            ${escHtml(upstreamProbe?.responseKind || 'unknown')} response
            ${upstreamProbe?.contentType ? `, content-type ${upstreamProbe.contentType}` : ''}
          </div>
        </div>
      </div>
      <div class="readiness-item ${readiness?.is_ready ? 'pass' : 'fail'}">
        <span class="readiness-icon">${readiness?.is_ready ? 'OK' : 'ERR'}</span>
        <div>
          <div class="readiness-label">Platform readiness: ${escHtml(String(readiness?.is_ready ?? 'unknown'))}</div>
          <div class="readiness-detail">Selected number ${escHtml(selectedNumber?.e164Number || selectedNumber?.id || 'not found')} -> ${escHtml(assignedAgent?.name || selectedNumber?.assignedAgentId || 'unassigned')}</div>
        </div>
      </div>
      ${toNumber ? `
        <div class="readiness-item pending">
          <span class="readiness-icon">INFO</span>
          <div>
            <div class="readiness-label">Requested destination</div>
            <div class="readiness-detail">${escHtml(toNumber)}</div>
          </div>
        </div>
      ` : ''}
      ${upstreamProbe?.payloadPreview ? `
        <div class="code-block">${escHtml(upstreamProbe.payloadPreview)}</div>
      ` : ''}
      ${(likelyCauses.length ? likelyCauses : ['No likely cause was inferred from the upstream probe.']).map((item) => `
        <div class="readiness-item pending">
          <span class="readiness-icon">INFO</span>
          <div><div class="readiness-label">${escHtml(item)}</div></div>
        </div>
      `).join('')}
      ${notes.map((item) => `
        <div class="readiness-item pending">
          <span class="readiness-icon">NOTE</span>
          <div><div class="readiness-label">${escHtml(item)}</div></div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderCallStatusCard(call, toNumber = '') {
  const status = String(call?.platform_status || call?.status || 'unknown');
  const providerStatus = call?.provider_status || call?.raw_livekit_sip_participant_status || '';
  const errorCode = call?.error_code || '';
  const errorMessage = call?.error_message || '';
  const callId = call?.telephony_call_id || call?.id || '';
  return `
    <div class="card" style="border-color: ${TERMINAL_CALL_STATUSES.has(status) && status !== 'completed' ? 'var(--red)' : 'var(--green)'}">
      <div class="card-title">Outbound call status</div>
      <div class="flex gap-1 mb-1">
        ${statusBadge(status)}
        ${callId ? `<span class="badge badge-gray mono">${escHtml(callId)}</span>` : ''}
        ${providerStatus ? `<span class="badge badge-blue">${escHtml(providerStatus)}</span>` : ''}
      </div>
      <div class="readiness-detail">From ${escHtml(call?.from_number || '---')} to ${escHtml(toNumber || call?.to_number || '---')}</div>
      ${errorCode ? `
        <div class="readiness-item fail">
          <span class="readiness-icon">ERR</span>
          <div>
            <div class="readiness-label">${escHtml(errorCode)}</div>
            <div class="readiness-detail">${escHtml(errorMessage || 'Provider rejected the call.')}</div>
          </div>
        </div>
      ` : errorMessage ? `
        <div class="readiness-item fail">
          <span class="readiness-icon">ERR</span>
          <div>
            <div class="readiness-label">${escHtml(errorMessage)}</div>
          </div>
        </div>
      ` : `
        <div class="readiness-item pending">
          <span class="readiness-icon">INFO</span>
          <div>
            <div class="readiness-label">Waiting for provider status updates...</div>
          </div>
        </div>
      `}
      <div class="readiness-detail" style="margin-top:0.5rem">
        Started: ${escHtml(call?.started_at || 'pending')}
        ${call?.ended_at ? ` | Ended: ${escHtml(call.ended_at)}` : ''}
      </div>
    </div>
  `;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function renderManagedNumberDiagnostics(detail) {
  const connectionProbe = detail?.connectionProbe || null;
  const syncProbe = detail?.syncProbe || null;
  const listProbe = detail?.listProbe || null;

  function renderProbe(title, probe) {
    if (!probe) return '';
    const likelyCauses = Array.isArray(probe.likelyCauses) ? probe.likelyCauses : [];
    return `
      <div class="readiness-item ${probe.ok ? 'pass' : 'fail'}">
        <span class="readiness-icon">${probe.ok ? 'OK' : 'ERR'}</span>
        <div>
          <div class="readiness-label">${escHtml(title)}: ${escHtml(probe.status ? String(probe.status) : 'no response')}</div>
          <div class="readiness-detail">
            ${escHtml(probe.responseKind || 'unknown')} response
            ${probe.contentType ? `, content-type ${probe.contentType}` : ''}
          </div>
        </div>
      </div>
      ${probe.payloadPreview ? `<div class="code-block">${escHtml(probe.payloadPreview)}</div>` : ''}
      ${likelyCauses.map((item) => `
        <div class="readiness-item pending">
          <span class="readiness-icon">INFO</span>
          <div><div class="readiness-label">${escHtml(item)}</div></div>
        </div>
      `).join('')}
    `;
  }

  return `
    <div class="card" style="border-color: var(--red)">
      <div class="card-title">Managed Number Diagnostics</div>
      ${renderProbe('Connection check', connectionProbe)}
      ${renderProbe('Owned-number sync', syncProbe)}
      ${renderProbe('Managed-number list', listProbe)}
    </div>
  `;
}

async function loadDebugLog() {
  const target = $('debug-log-list');
  if (!target) return;
  target.innerHTML = '<div class="loading-row"><div class="spinner"></div><br/>Loading logs...</div>';
  try {
    const result = await api('GET', '/api/debug/errors', undefined, { skipDebugLog: true });
    state.debugEvents = normalizeCollection(result, ['items', 'data']);
    renderDebugPanel();
  } catch (error) {
    target.innerHTML = `<div class="empty-state"><div class="empty-state-title">Could not load debug log</div><div class="empty-state-text">${escHtml(error.message)}</div></div>`;
  }
}

async function clearDebugLog() {
  try {
    await api('POST', '/api/debug/errors/clear', undefined, { skipDebugLog: true });
    state.clientDebugEvents = [];
    state.debugEvents = [];
    toast('success', 'Debug log cleared');
    renderDebugPanel();
  } catch (error) {
    toast('error', 'Could not clear debug log', error.message);
  }
}

async function checkBackendHealth() {
  try {
    const health = await api('GET', '/api/health');
    updateStatusItem('status-backend', 'pass', 'Backend online', `localhost:3001 -> ${health.apiBaseUrl}`);
    if ($('header-backend-badge')) {
      $('header-backend-badge').textContent = 'Backend OK';
      $('header-backend-badge').className = 'badge badge-green';
    }
    return true;
  } catch (error) {
    updateStatusItem('status-backend', 'fail', 'Backend offline', 'Run npm run backend');
    if ($('header-backend-badge')) {
      $('header-backend-badge').textContent = 'Backend offline';
      $('header-backend-badge').className = 'badge badge-red';
    }
    return false;
  }
}

async function checkConfig() {
  try {
    const config = await api('GET', '/api/config');
    if ($('cfg-api-url')) $('cfg-api-url').value = config.apiBaseUrl || '';
    if ($('cfg-telephony-url')) $('cfg-telephony-url').value = config.telephonyApiUrl || '';
    if ($('cfg-session-url')) $('cfg-session-url').value = config.sessionUpstreamUrl || '';
    if ($('cfg-publishable-key')) $('cfg-publishable-key').value = config.publishableKey || '';
    if ($('cfg-tenant-id')) $('cfg-tenant-id').value = config.tenantId || '';
    if ($('cfg-hmac-secret')) $('cfg-hmac-secret').value = config.hmacSecret || '';
    if ($('cfg-telnyx-key')) $('cfg-telnyx-key').value = config.telnyxApiKey || '';
    if ($('sip-fqdn') && !$('sip-fqdn').value) $('sip-fqdn').value = config.livekitSipUri || '';
    if (config.tenantId && config.hmacSecretSet) {
      updateStatusItem('status-config', 'pass', 'Tenant credentials set', config.tenantId.slice(0, 12) + '...');
    } else {
      updateStatusItem('status-config', 'fail', 'Tenant credentials missing', 'Fill in Tenant ID and HMAC Secret');
    }
  } catch (error) {
    updateStatusItem('status-config', 'fail', 'Tenant credentials check failed', error.message);
  }
}

async function checkTelnyxStatus() {
  try {
    const status = await api('GET', '/api/telnyx/status');
    const connected = status.platform_status === 'active' || status.provider_status === 'active';
    updateStatusItem(
      'status-telnyx',
      connected ? 'pass' : 'fail',
      connected ? 'Telnyx connected' : 'Telnyx not connected',
      status.telnyx_account_id || status.platform_status || '',
    );
    if ($('header-connection-badge')) {
      $('header-connection-badge').textContent = connected ? 'Telnyx connected' : 'Telnyx disconnected';
      $('header-connection-badge').className = `badge ${connected ? 'badge-green' : 'badge-red'}`;
    }
  } catch (error) {
    updateStatusItem('status-telnyx', 'fail', 'Telnyx status error', error.message);
  }
}

async function checkPortalReachable() {
  try {
    await api('GET', '/api/capabilities');
    updateStatusItem('status-portal', 'pass', 'Portal API reachable');
  } catch (error) {
    updateStatusItem('status-portal', 'fail', 'Portal API error', error.message);
  }
}

async function loadAgents() {
  const target = $('agents-list');
  if (!target) return;
  target.innerHTML = '<div class="loading-row"><div class="spinner"></div><br/>Loading agents...</div>';
  try {
    const result = await api('GET', '/api/agents');
    state.agents = normalizeCollection(result, ['agents', 'data', 'items']);
    if (!state.agents.length) {
      target.innerHTML = '<div class="empty-state"><div class="empty-state-title">No agents yet</div><div class="empty-state-text">Create one from the form on the left.</div></div>';
      populateProviderTestSelects();
      return;
    }
    target.innerHTML = state.agents.map((agent) => `
      <div class="agent-card mb-2">
        <div class="agent-header">
          <div>
            <div class="agent-name">${escHtml(agent.name || 'Unnamed agent')}</div>
            <div class="agent-id">${escHtml(agent.id)}</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick='openUpdateModal(${JSON.stringify(agent)})'>Edit</button>
        </div>
        <div class="agent-prompt">${escHtml(agent.prompt || '')}</div>
        <div class="agent-providers">
          ${providerBadge('lang', agent.agent_language, 'badge-gray')}
          ${providerBadge('stt', agent.stt_provider, 'badge-blue')}
          ${providerBadge('llm', agent.llm_provider || agent.llm_model, 'badge-purple')}
          ${providerBadge('tts', agent.tts_provider, 'badge-pink')}
        </div>
      </div>
    `).join('');
    populateProviderTestSelects();
  } catch (error) {
    target.innerHTML = `<div class="empty-state"><div class="empty-state-title">Could not load agents</div><div class="empty-state-text">${escHtml(error.message)}</div></div>`;
  }
}

async function loadManagedNumbers() {
  const target = $('managed-numbers-list');
  if (!target) return;
  target.innerHTML = '<div class="loading-row"><div class="spinner"></div><br/>Loading...</div>';
  try {
    const result = await api('GET', '/api/telnyx/numbers/managed');
    state.numbers = normalizeCollection(result, ['data', 'numbers', 'items']);
    if (result?.sync_warning) {
      toast('warning', 'Numbers refreshed with warning', result.sync_warning);
    }
    if (!state.numbers.length) {
      target.innerHTML = '<div class="empty-state"><div class="empty-state-title">No managed numbers</div><div class="empty-state-text">Sync from Telnyx or purchase a number first.</div></div>';
      populateProviderTestSelects();
      return;
    }
    target.innerHTML = state.numbers.map((number) => {
      const routing = number.routing_status || 'not_configured';
      return `
        <div class="number-card" style="margin-bottom:0.5rem; border-radius: var(--radius-sm)">
          <div>
            <div class="number-display" style="font-size:0.9rem">${escHtml(getNumberLabel(number))}</div>
            <div class="number-meta flex gap-1 mt-1">
              ${statusBadge(number.provisioning_status || number.status || 'active')}
              <span class="badge ${routing === 'ready' ? 'badge-green' : 'badge-yellow'}">Routing: ${escHtml(routing)}</span>
              ${number.assigned_agent_id ? `<span class="badge badge-purple">Agent: ${escHtml(getAgentLabel(number.assigned_agent_id))}</span>` : '<span class="badge badge-gray">Unassigned</span>'}
              <span class="badge badge-gray">${escHtml((number.id || '').slice(0, 12))}...</span>
            </div>
          </div>
          <div class="number-actions">
            <button class="btn btn-secondary btn-sm" onclick="selectManagedNumber('${escHtml(number.id)}')">Use in test</button>
            <button class="btn btn-danger btn-sm" onclick="disableNumber('${escHtml(number.id)}')">Disable</button>
          </div>
        </div>
      `;
    }).join('');
    populateProviderTestSelects();
  } catch (error) {
    if (error.detail?.syncProbe || error.detail?.listProbe || error.detail?.connectionProbe) {
      target.innerHTML = renderManagedNumberDiagnostics(error.detail);
    } else {
      target.innerHTML = `<div class="empty-state"><div class="empty-state-title">Could not load numbers</div><div class="empty-state-text">${escHtml(error.message)}</div></div>`;
    }
    console.error('[Managed Number Diagnostics]', error.detail || error);
    await loadDebugLog();
  }
}

async function loadCallLog() {
  const tbody = $('calllog-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" class="loading-row"><div class="spinner"></div><br/>Loading...</td></tr>';
  try {
    const limit = $('calllog-limit')?.value || '25';
    const result = await api('GET', `/api/calls?limit=${encodeURIComponent(limit)}`, undefined, { skipDebugLog: true });
    const calls = normalizeCollection(result, ['calls', 'data', 'items']);
    if (!calls.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="loading-row">No calls found</td></tr>';
      return;
    }
    tbody.innerHTML = calls.map((call) => `
      <tr>
        <td class="mono">${escHtml((call.telephony_call_id || call.id || '').slice(0, 16))}...</td>
        <td>${escHtml(call.direction || 'outbound')}</td>
        <td class="mono">${escHtml(call.from_number || '---')}</td>
        <td class="mono">${escHtml(call.to_number || '---')}</td>
        <td>
          ${statusBadge(call.platform_status || call.status || 'unknown')}
          ${call.provider_status ? `<div class="readiness-detail">${escHtml(call.provider_status)}</div>` : ''}
          ${call.error_code ? `<div class="readiness-detail">${escHtml(call.error_code)}</div>` : ''}
        </td>
        <td>${escHtml(getAgentLabel(call.agent_id))}</td>
        <td>${escHtml(call.started_at || call.created_at || '---')}</td>
      </tr>
    `).join('');
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-row">Error: ${escHtml(error.message)}</td></tr>`;
  }
}

async function watchOutboundCall(callId, toNumber = '') {
  if (!callId) return;
  const resultBox = $('call-result');
  if (state.activeCallPoll) {
    clearTimeout(state.activeCallPoll);
    state.activeCallPoll = null;
  }
  for (let attempt = 0; attempt < 15; attempt += 1) {
    try {
      const call = await api('GET', `/api/calls/${encodeURIComponent(callId)}`, undefined, { skipDebugLog: true });
      if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.innerHTML = renderCallStatusCard(call, toNumber);
      }
      if (TERMINAL_CALL_STATUSES.has(String(call.platform_status || '').toLowerCase())) {
        await loadCallLog();
        if (String(call.platform_status).toLowerCase() === 'failed') {
          toast('error', 'Outbound call failed', call.error_message || call.error_code || call.provider_status || 'Provider rejected the call.');
        }
        return;
      }
    } catch (error) {
      if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.innerHTML = `
          <div class="card" style="border-color: var(--yellow)">
            <div class="card-title">Outbound call polling interrupted</div>
            <div class="readiness-item pending">
              <span class="readiness-icon">INFO</span>
              <div>
                <div class="readiness-label">${escHtml(error.message)}</div>
              </div>
            </div>
          </div>
        `;
      }
      return;
    }
    await sleep(3000);
  }
  await loadCallLog();
}

async function saveConfig() {
  const button = $('btn-save-config');
  setLoading(button, true, 'Saving...');
  try {
    await api('POST', '/api/config', {
      apiBaseUrl: $('cfg-api-url')?.value.trim() || undefined,
      telephonyApiUrl: $('cfg-telephony-url')?.value.trim() || undefined,
      sessionUpstreamUrl: $('cfg-session-url')?.value.trim() || undefined,
      publishableKey: $('cfg-publishable-key')?.value.trim() || undefined,
      tenantId: $('cfg-tenant-id')?.value.trim() || undefined,
      hmacSecret: $('cfg-hmac-secret')?.value.trim() || undefined,
      telnyxApiKey: $('cfg-telnyx-key')?.value.trim() || undefined,
    });
    state.voiceClient = null;
    toast('success', 'Configuration saved', 'Credentials are stored in backend memory only.');
    await Promise.all([checkConfig(), checkTelnyxStatus()]);
  } catch (error) {
    toast('error', 'Could not save configuration', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function connectTelnyx() {
  const button = $('btn-connect-telnyx');
  setLoading(button, true, 'Connecting...');
  try {
    const result = await api('POST', '/api/telnyx/connect');
    toast('success', 'Telnyx connected', result.telnyx_account_id || result.label || 'Connection active');
    await checkTelnyxStatus();
  } catch (error) {
    toast('error', 'Telnyx connection failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function loadCapabilities() {
  const button = $('btn-load-caps');
  setLoading(button, true, 'Loading...');
  try {
    const capabilities = await api('GET', '/api/capabilities');
    if ($('caps-summary')) $('caps-summary').textContent = JSON.stringify(capabilities, null, 2);
    toast('success', 'Capabilities loaded');
  } catch (error) {
    toast('error', 'Could not load capabilities', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function searchNumbers() {
  const button = $('btn-search-numbers');
  setLoading(button, true, 'Searching...');
  try {
    const params = new URLSearchParams({
      country: $('num-country')?.value || 'US',
      limit: $('num-limit')?.value || '10',
    });
    const areaCode = $('num-area-code')?.value.trim();
    if (areaCode) params.set('areaCode', areaCode);
    const result = await api('GET', `/api/telnyx/numbers/available?${params.toString()}`);
    const numbers = normalizeCollection(result, ['data', 'numbers', 'items']);
    const section = $('search-results-section');
    const grid = $('search-results-grid');
    if (!section || !grid) return;
    if (!numbers.length) {
      section.style.display = 'none';
      toast('warning', 'No numbers found', 'Try a different area code or country.');
      return;
    }
    $('search-result-count').textContent = `${numbers.length} found`;
    grid.innerHTML = numbers.map((number) => `
      <div class="number-card">
        <div>
          <div class="number-display">${escHtml(getNumberLabel(number))}</div>
          <div class="number-meta">${escHtml((number.features || []).join(', ') || number.region || '')}</div>
          <div class="number-price">${escHtml(getNumberPriceSummary(number))}</div>
        </div>
        <div class="number-actions">
          <button class="btn btn-secondary btn-sm" onclick='openReserveModal(${JSON.stringify(encodeURIComponent(JSON.stringify(number)))})'>Reserve</button>
          <button class="btn btn-primary btn-sm" onclick='openPurchaseModal(${JSON.stringify(encodeURIComponent(JSON.stringify(number)))})'>Buy</button>
        </div>
      </div>
    `).join('');
    section.style.display = 'block';
  } catch (error) {
    toast('error', 'Search failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

window.openPurchaseModal = (encodedNumber) => {
  const number = JSON.parse(decodeURIComponent(encodedNumber));
  state.pendingNumber = getNumberLabel(number);
  state.pendingPurchase = {
    number,
    idempotencyKey: crypto.randomUUID(),
  };
  if ($('modal-purchase-number')) $('modal-purchase-number').textContent = getNumberLabel(number);
  if ($('modal-purchase-price')) $('modal-purchase-price').textContent = getNumberPriceSummary(number);
  $('modal-purchase')?.classList.remove('hidden');
};

window.openReserveModal = (encodedNumber) => {
  const number = JSON.parse(decodeURIComponent(encodedNumber));
  state.pendingNumber = getNumberLabel(number);
  state.pendingReservation = {
    number,
    idempotencyKey: crypto.randomUUID(),
  };
  if ($('modal-reserve-number')) $('modal-reserve-number').textContent = getNumberLabel(number);
  if ($('modal-reserve-price')) $('modal-reserve-price').textContent = getNumberPriceSummary(number);
  $('modal-reserve')?.classList.remove('hidden');
};

async function confirmPurchase() {
  const button = $('modal-purchase-confirm');
  if (!state.pendingPurchase?.number) {
    toast('warning', 'No number selected', 'Search again and choose one number to purchase.');
    return;
  }
  setLoading(button, true, 'Purchasing...');
  try {
    const numberLabel = getNumberLabel(state.pendingPurchase.number);
    const result = await api('POST', '/api/telnyx/numbers/purchase', {
      e164Number: numberLabel,
      idempotencyKey: state.pendingPurchase.idempotencyKey,
      priceSnapshot: {
        upfrontCost: state.pendingPurchase.number.upfront_cost ?? null,
        monthlyCost: state.pendingPurchase.number.monthly_cost ?? null,
        currency: state.pendingPurchase.number.currency || 'USD',
      },
    });
    $('modal-purchase')?.classList.add('hidden');
    const detail = result.managed_number_id
      ? `${numberLabel} • managed as ${result.managed_number_id}`
      : `${numberLabel} • ${result.platform_status || 'submitted'}`;
    toast('success', 'Number purchased', detail);
    await loadManagedNumbers();
  } catch (error) {
    toast('error', 'Purchase failed', error.message);
    await loadDebugLog();
  } finally {
    setLoading(button, false);
    state.pendingNumber = null;
    state.pendingPurchase = null;
  }
}

async function confirmReserve() {
  const button = $('modal-reserve-confirm');
  if (!state.pendingReservation?.number) {
    toast('warning', 'No number selected', 'Search again and choose one number to reserve.');
    return;
  }
  setLoading(button, true, 'Reserving...');
  try {
    const numberLabel = getNumberLabel(state.pendingReservation.number);
    await api('POST', '/api/telnyx/numbers/reserve', {
      e164Number: numberLabel,
      idempotencyKey: state.pendingReservation.idempotencyKey,
    });
    $('modal-reserve')?.classList.add('hidden');
    toast('success', 'Number reserved', numberLabel);
  } catch (error) {
    toast('error', 'Reserve failed', error.message);
    await loadDebugLog();
  } finally {
    setLoading(button, false);
    state.pendingNumber = null;
    state.pendingReservation = null;
  }
}

window.disableNumber = async (numberId) => {
  if (!window.confirm(`Disable number ${numberId}?`)) return;
  try {
    await api('POST', `/api/telnyx/numbers/${encodeURIComponent(numberId)}/disable`);
    toast('success', 'Number disabled', numberId);
    await loadManagedNumbers();
  } catch (error) {
    toast('error', 'Disable failed', error.message);
  }
};

window.selectManagedNumber = (numberId) => {
  handleNumberSelection(numberId);
  activateTab('workspace');
};

async function createAgent() {
  const button = $('btn-create-agent');
  const name = $('agent-name')?.value.trim();
  const prompt = $('agent-prompt')?.value.trim();
  const voiceId = $('agent-voice-id')?.value.trim();
  if (!name || !prompt || !voiceId) {
    toast('warning', 'Name, prompt, and voice ID are required for this test app');
    return;
  }
  setLoading(button, true, 'Creating...');
  try {
    const result = await api('POST', '/api/agents', {
      name,
      prompt,
      voiceId,
      ttsVoiceId: voiceId,
      agentLanguage: $('agent-language')?.value || undefined,
      llmModel: $('agent-llm-model')?.value || undefined,
      sttProvider: $('agent-stt')?.value || undefined,
      llmProvider: $('agent-llm')?.value || undefined,
      ttsProvider: $('agent-tts')?.value || undefined,
    });
    toast('success', 'Agent created', `${result.name} (${result.id})`);
    ['agent-name', 'agent-prompt', 'agent-voice-id'].forEach((id) => {
      if ($(id)) $(id).value = '';
    });
    await loadAgents();
  } catch (error) {
    toast('error', 'Agent creation failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

window.openUpdateModal = (agent) => {
  $('update-agent-id').value = agent.id || '';
  $('update-agent-name').value = agent.name || '';
  $('update-agent-prompt').value = agent.prompt || '';
  $('update-agent-stt').value = '';
  $('update-agent-llm').value = '';
  $('update-agent-tts').value = '';
  $('modal-update-agent')?.classList.remove('hidden');
};

async function updateAgent() {
  const button = $('modal-update-confirm');
  setLoading(button, true, 'Saving...');
  try {
    const agentId = $('update-agent-id')?.value;
    const body = {
      name: $('update-agent-name')?.value.trim() || undefined,
      prompt: $('update-agent-prompt')?.value.trim() || undefined,
      sttProvider: $('update-agent-stt')?.value || undefined,
      llmProvider: $('update-agent-llm')?.value || undefined,
      ttsProvider: $('update-agent-tts')?.value || undefined,
    };
    Object.keys(body).forEach((key) => body[key] === undefined && delete body[key]);
    const result = await api('PATCH', `/api/agents/${encodeURIComponent(agentId)}`, body);
    toast('success', 'Agent updated', result.name || agentId);
    $('modal-update-agent')?.classList.add('hidden');
    await loadAgents();
  } catch (error) {
    toast('error', 'Agent update failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function assignNumber() {
  const numberId = $('pt-number-id')?.value;
  const agentId = $('pt-agent-id')?.value;
  if (!numberId || !agentId) {
    toast('warning', 'Select both a managed number and an agent');
    return;
  }
  const button = $('btn-assign-number');
  setLoading(button, true, 'Attaching...');
  try {
    await api('POST', `/api/telnyx/numbers/${encodeURIComponent(numberId)}/assign-agent`, { agentId });
    toast('success', 'Number attached to agent', getAgentLabel(agentId));
    await loadManagedNumbers();
    handleNumberSelection(numberId);
  } catch (error) {
    toast('error', 'Could not attach number', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function unassignNumber() {
  const numberId = $('pt-number-id')?.value;
  if (!numberId) {
    toast('warning', 'Select a managed number first');
    return;
  }
  const button = $('btn-unassign-number');
  setLoading(button, true, 'Unassigning...');
  try {
    await api('POST', `/api/telnyx/numbers/${encodeURIComponent(numberId)}/assign-agent`, { agentId: null });
    toast('success', 'Agent unassigned from number', numberId);
    await loadManagedNumbers();
    handleNumberSelection(numberId);
  } catch (error) {
    toast('error', 'Could not unassign agent', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function configureRouting() {
  const numberId = $('pt-number-id')?.value;
  const agentId = $('pt-agent-id')?.value;
  if (!numberId) {
    toast('warning', 'Select a managed number first');
    return;
  }
  const button = $('btn-configure-routing');
  setLoading(button, true, 'Configuring...');
  try {
    await api('POST', `/api/telnyx/numbers/${encodeURIComponent(numberId)}/configure-routing`, {
      agentId: agentId || undefined,
    });
    toast('success', 'Inbound routing configured', numberId);
    await loadManagedNumbers();
    handleNumberSelection(numberId);
  } catch (error) {
    toast('error', 'Routing configuration failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function checkReadiness() {
  const button = $('btn-check-readiness');
  setLoading(button, true, 'Checking...');
  try {
    const result = await api('GET', '/api/readiness');
    renderReadiness(result);
    toast(result.is_ready ? 'success' : 'warning', result.is_ready ? 'Outbound ready' : 'Outbound not ready');
  } catch (error) {
    renderReadiness({ is_ready: false, reasons: [error.message], active_numbers_count: 0 });
    toast('error', 'Readiness check failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function saveSip() {
  const button = $('btn-upsert-sip');
  setLoading(button, true, 'Saving...');
  try {
    const sipFqdn = $('sip-fqdn')?.value.trim() || undefined;
    if (sipFqdn?.startsWith('+')) {
      throw new Error('SIP FQDN cannot be a phone number. Use a Telnyx-reachable SIP hostname.');
    }
    await api('POST', '/api/telnyx/sip-connection', {
      sipFqdn,
      sipUsername: $('sip-username')?.value.trim() || undefined,
      sipSecret: $('sip-secret')?.value.trim() || undefined,
    });
    toast('success', 'SIP connection saved');
  } catch (error) {
    toast('error', 'SIP save failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function verifySip() {
  const button = $('btn-verify-sip');
  setLoading(button, true, 'Verifying...');
  try {
    await api('POST', '/api/telnyx/sip-connection/verify');
    toast('success', 'SIP verified');
  } catch (error) {
    toast('error', 'SIP verification failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function saveOutboundProfile() {
  const button = $('btn-upsert-ovp');
  setLoading(button, true, 'Saving...');
  try {
    const allowedDestinations = ($('ovp-destinations')?.value || 'US')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    await api('POST', '/api/telnyx/outbound-voice-profile', {
      allowedDestinations,
      concurrencyLimit: Number($('ovp-concurrency')?.value || 2),
    });
    toast('success', 'Outbound voice profile saved');
  } catch (error) {
    toast('error', 'Outbound voice profile save failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function verifyOutboundProfile() {
  const button = $('btn-verify-ovp');
  setLoading(button, true, 'Verifying...');
  try {
    await api('POST', '/api/telnyx/outbound-voice-profile/verify');
    toast('success', 'Outbound voice profile verified');
  } catch (error) {
    toast('error', 'Outbound voice profile verification failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function configureOutboundTrunk() {
  const button = $('btn-configure-trunk');
  setLoading(button, true, 'Configuring...');
  try {
    await api('POST', '/api/telnyx/outbound-trunk');
    toast('success', 'Outbound trunk configured');
  } catch (error) {
    toast('error', 'Outbound trunk configuration failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function simulateInbound() {
  const numberId = $('inbound-number-id')?.value;
  const agentId = $('inbound-agent-id')?.value;
  if (!numberId) {
    toast('warning', 'Select a number to simulate inbound');
    return;
  }
  const button = $('btn-simulate-inbound');
  const resultBox = $('inbound-result');
  setLoading(button, true, 'Simulating...');
  try {
    const result = await api('POST', '/api/inbound/simulate', {
      numberId,
      agentId: agentId || undefined,
    });
    if (resultBox) {
      resultBox.style.display = 'block';
      resultBox.innerHTML = `
        <div class="card" style="border-color: var(--green)">
          <div class="card-title">Inbound simulation passed</div>
          <div class="readiness-item pass">
            <span class="readiness-icon">OK</span>
            <div>
              <div class="readiness-label">${escHtml(result.e164Number || result.numberId)}</div>
              <div class="readiness-detail">Assigned agent: ${escHtml(result.agentName || result.agentId || 'Unknown')}</div>
            </div>
          </div>
          <div class="readiness-item pass">
            <span class="readiness-icon">INFO</span>
            <div>
              <div class="readiness-label">${escHtml(result.message)}</div>
              <div class="readiness-detail">This validates the inbound routing decision locally. A real inbound call still requires dialing the number.</div>
            </div>
          </div>
        </div>
      `;
    }
    handleNumberSelection(numberId);
    toast('success', 'Inbound simulation passed', result.agentName || result.agentId || '');
  } catch (error) {
    if (resultBox) {
      resultBox.style.display = 'block';
      resultBox.innerHTML = `
        <div class="card" style="border-color: var(--red)">
          <div class="card-title">Inbound simulation failed</div>
          <div class="readiness-item fail">
            <span class="readiness-icon">ERR</span>
            <div>
              <div class="readiness-label">${escHtml(error.message)}</div>
              <div class="readiness-detail">Attach the number to an agent and configure routing first.</div>
            </div>
          </div>
        </div>
      `;
    }
    toast('error', 'Inbound simulation failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function runTelephonyDiagnostics() {
  const fromNumberId = $('call-from-id')?.value || $('pt-number-id')?.value || '';
  const agentId = $('call-agent-id')?.value || $('pt-agent-id')?.value || '';
  const toNumber = $('call-to-number')?.value.trim() || '';
  const button = $('btn-run-call-diagnostics');
  const resultBox = $('call-result');
  setLoading(button, true, 'Diagnosing...');
  try {
    const params = new URLSearchParams();
    if (fromNumberId) params.set('numberId', fromNumberId);
    if (agentId) params.set('agentId', agentId);
    if (toNumber) params.set('toNumber', toNumber);
    const result = await api('GET', `/api/telephony/diagnostics?${params.toString()}`);
    if (resultBox) {
      resultBox.style.display = 'block';
      resultBox.innerHTML = renderTelephonyDiagnostics({ diagnostics: result.diagnostics }, toNumber);
    }
    toast('info', 'Diagnostics loaded');
  } catch (error) {
    if (resultBox) {
      resultBox.style.display = 'block';
      resultBox.innerHTML = `
        <div class="card" style="border-color: var(--red)">
          <div class="card-title">Diagnostics failed</div>
          <div class="readiness-item fail">
            <span class="readiness-icon">ERR</span>
            <div>
              <div class="readiness-label">${escHtml(error.message)}</div>
              <div class="readiness-detail">The backend could not assemble the telephony diagnostics bundle.</div>
            </div>
          </div>
        </div>
      `;
    }
    toast('error', 'Diagnostics failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

async function createOutboundCall() {
  const selectedAgentId = $('call-agent-id')?.value;
  const fromNumberId = $('call-from-id')?.value;
  const toNumber = $('call-to-number')?.value.trim();
  const recipient = $('call-recipient')?.value.trim();
  if (!selectedAgentId || !fromNumberId || !toNumber) {
    toast('warning', 'Agent, from number, and destination are required');
    return;
  }
  await refreshNumbersAndAgents();
  populateProviderTestSelects();
  const assignedAgentId = getAssignedAgentIdForNumber(fromNumberId);
  if (!assignedAgentId) {
    toast('warning', 'Attach the selected number to an agent before placing an outbound call');
    return;
  }
  syncAgentSelections(assignedAgentId);
  if (!window.confirm(`Place a real outbound call to ${toNumber}?`)) return;
  const button = $('btn-make-call');
  const resultBox = $('call-result');
  setLoading(button, true, 'Calling...');
  try {
    const result = await api('POST', '/api/outbound-call', {
      agentId: assignedAgentId,
      fromNumberId,
      toNumber,
      recipient,
    });
    if (resultBox) {
      resultBox.style.display = 'block';
      resultBox.innerHTML = `
        <div class="card" style="border-color: var(--green)">
          <div class="card-title">Outbound call started</div>
          <div class="flex gap-1 mb-1">
            <span class="badge badge-green">Dialing</span>
            <span class="badge badge-gray mono">${escHtml(result.telephony_call_id || result.id || '')}</span>
          </div>
          <div style="font-size:0.8rem; color:var(--text-secondary)">To: ${escHtml(toNumber)}</div>
        </div>
      `;
    }
    handleNumberSelection(fromNumberId);
    syncAgentSelections(assignedAgentId);
    toast('success', 'Outbound call placed', toNumber);
    await loadCallLog();
    void watchOutboundCall(result.telephony_call_id || result.id || '', toNumber);
  } catch (error) {
    if (resultBox) {
      resultBox.style.display = 'block';
      if (error.detail?.upstreamProbe || error.detail?.diagnostics) {
        resultBox.innerHTML = renderTelephonyDiagnostics(error.detail, toNumber);
      } else {
        resultBox.innerHTML = `
          <div class="card" style="border-color: var(--red)">
            <div class="card-title">Outbound call failed</div>
            <div class="readiness-item fail">
              <span class="readiness-icon">ERR</span>
              <div>
                <div class="readiness-label">${escHtml(error.message)}</div>
                <div class="readiness-detail">No additional diagnostics were returned by the backend for this failure.</div>
              </div>
            </div>
          </div>
        `;
      }
    }
    toast('error', 'Outbound call failed', error.message);
  } finally {
    setLoading(button, false);
  }
}

function getPublishableKey() {
  return $('cfg-publishable-key')?.value.trim() || import.meta.env.VITE_UVA_PUBLISHABLE_KEY || '';
}

function getVoiceClient() {
  if (state.voiceClient) return state.voiceClient;
  state.voiceClient = new AwaazLabsUvaVoice({
    publishableKey: getPublishableKey(),
    sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT || `${API}/api/voice/session`,
    refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT || `${API}/api/voice/session/refresh`,
  });

  state.voiceClient.on('connected', () => {
    if ($('voice-status-badge')) {
      $('voice-status-badge').className = 'badge badge-green';
      $('voice-status-badge').textContent = 'Connected';
    }
    if ($('btn-voice-connect')) $('btn-voice-connect').style.display = 'none';
    if ($('btn-voice-disconnect')) $('btn-voice-disconnect').style.display = 'block';
    if ($('btn-voice-unlock')) $('btn-voice-unlock').style.display = state.audioNeedsUnlock ? 'block' : 'none';
    if ($('voice-transcript-log')) {
      $('voice-transcript-log').innerHTML = '<div style="color:var(--text-secondary); text-align:center;">Recording started. Speak now.</div>';
    }
  });

  state.voiceClient.on('disconnected', () => {
    if ($('voice-status-badge')) {
      $('voice-status-badge').className = 'badge badge-gray';
      $('voice-status-badge').textContent = 'Disconnected';
    }
    state.audioNeedsUnlock = false;
    if ($('btn-voice-connect')) $('btn-voice-connect').style.display = 'block';
    if ($('btn-voice-disconnect')) $('btn-voice-disconnect').style.display = 'none';
    if ($('btn-voice-unlock')) $('btn-voice-unlock').style.display = 'none';
  });

  state.voiceClient.on('transcript', (event) => {
    const log = $('voice-transcript-log');
    if (!log) return;
    if (log.textContent.includes('Recording started.')) log.innerHTML = '';
    const line = document.createElement('div');
    line.innerHTML = `<strong>${escHtml(event.speaker === 'agent' ? 'Agent' : 'You')}:</strong> ${escHtml(event.text || '')}`;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  });

  state.voiceClient.on('audio_blocked', async (blocked) => {
    state.audioNeedsUnlock = Boolean(blocked);
    if ($('btn-voice-unlock')) $('btn-voice-unlock').style.display = blocked ? 'block' : 'none';
    if (blocked) toast('warning', 'Audio blocked', 'Click Unlock Audio to enable playback.');
  });

  return state.voiceClient;
}

async function connectVoice() {
  const agentId = $('voice-agent-id')?.value;
  if (!agentId) {
    toast('warning', 'Select an agent to start a browser voice session');
    return;
  }
  const button = $('btn-voice-connect');
  setLoading(button, true, 'Connecting...');
  if ($('voice-connection-status')) $('voice-connection-status').style.display = 'block';
  if ($('voice-status-badge')) {
    $('voice-status-badge').className = 'badge badge-yellow';
    $('voice-status-badge').textContent = 'Connecting';
  }
  try {
    state.voiceClient = null;
    await getVoiceClient().connect({ agentId });
  } catch (error) {
    toast('error', 'Voice connection failed', error.message);
    if ($('voice-status-badge')) {
      $('voice-status-badge').className = 'badge badge-red';
      $('voice-status-badge').textContent = 'Connection failed';
    }
  } finally {
    setLoading(button, false);
  }
}

async function unlockVoice() {
  try {
    await state.voiceClient?.startAudio();
    state.audioNeedsUnlock = false;
    if ($('btn-voice-unlock')) $('btn-voice-unlock').style.display = 'none';
    toast('success', 'Audio unlocked');
  } catch (error) {
    toast('error', 'Could not unlock audio', error.message);
  }
}

async function disconnectVoice() {
  await state.voiceClient?.disconnect();
}

function closeModal(id) {
  $(id)?.classList.add('hidden');
  if (id === 'modal-purchase') {
    state.pendingPurchase = null;
  }
  if (id === 'modal-reserve') {
    state.pendingReservation = null;
  }
  state.pendingNumber = null;
}

function registerEvents() {
  document.querySelectorAll('.tab-btn').forEach((button) => {
    button.addEventListener('click', async () => {
      const tabName = button.dataset.tab;
      activateTab(tabName);
      if (tabName === 'workspace') {
        await Promise.all([loadManagedNumbers(), loadAgents(), loadDebugLog()]);
        await populateProviderTestSelects();
      }
      if (tabName === 'activity') {
        await populateProviderTestSelects();
        await loadCallLog();
      }
    });
  });

  on('btn-save-config', 'click', saveConfig);
  on('btn-check-status', 'click', async () => {
    const button = $('btn-check-status');
    setLoading(button, true, 'Checking...');
    try {
      await checkBackendHealth();
      await checkConfig();
      await checkTelnyxStatus();
      await checkPortalReachable();
    } finally {
      setLoading(button, false);
    }
  });
  on('btn-connect-telnyx', 'click', connectTelnyx);
  on('btn-load-caps', 'click', loadCapabilities);
  on('btn-search-numbers', 'click', searchNumbers);
  on('btn-refresh-managed', 'click', loadManagedNumbers);
  on('btn-refresh-debug-log', 'click', loadDebugLog);
  on('btn-clear-debug-log', 'click', clearDebugLog);
  on('btn-sync-numbers', 'click', async () => {
    const button = $('btn-sync-numbers');
    setLoading(button, true, 'Syncing...');
    try {
      await api('POST', '/api/telnyx/numbers/sync');
      toast('success', 'Numbers synced');
      await loadManagedNumbers();
    } catch (error) {
      toast('error', 'Sync failed', error.message);
      await loadDebugLog();
    } finally {
      setLoading(button, false);
    }
  });
  on('modal-purchase-cancel', 'click', () => closeModal('modal-purchase'));
  on('modal-reserve-cancel', 'click', () => closeModal('modal-reserve'));
  on('modal-purchase-confirm', 'click', confirmPurchase);
  on('modal-reserve-confirm', 'click', confirmReserve);
  on('btn-refresh-agents', 'click', loadAgents);
  on('btn-create-agent', 'click', createAgent);
  on('modal-update-cancel', 'click', () => closeModal('modal-update-agent'));
  on('modal-update-confirm', 'click', updateAgent);
  on('btn-assign-number', 'click', assignNumber);
  on('btn-unassign-number', 'click', unassignNumber);
  on('btn-configure-routing', 'click', configureRouting);
  on('btn-check-readiness', 'click', checkReadiness);
  on('btn-upsert-sip', 'click', saveSip);
  on('btn-verify-sip', 'click', verifySip);
  on('btn-upsert-ovp', 'click', saveOutboundProfile);
  on('btn-verify-ovp', 'click', verifyOutboundProfile);
  on('btn-configure-trunk', 'click', configureOutboundTrunk);
  on('btn-simulate-inbound', 'click', simulateInbound);
  on('btn-make-call', 'click', createOutboundCall);
  on('btn-run-call-diagnostics', 'click', runTelephonyDiagnostics);
  on('btn-refresh-calls', 'click', loadCallLog);
  on('calllog-limit', 'change', loadCallLog);
  on('btn-voice-connect', 'click', connectVoice);
  on('btn-voice-unlock', 'click', unlockVoice);
  on('btn-voice-disconnect', 'click', disconnectVoice);

  ['pt-number-id', 'call-from-id', 'inbound-number-id'].forEach((id) => {
    on(id, 'change', (event) => handleNumberSelection(event.target.value));
  });

  ['modal-purchase', 'modal-reserve', 'modal-update-agent'].forEach((id) => {
    on(id, 'click', (event) => {
      if (event.target.id === id) closeModal(id);
    });
  });

}

async function init() {
  registerEvents();
  await checkBackendHealth();
  await checkConfig();
  await Promise.all([checkTelnyxStatus(), checkPortalReachable()]);
  await Promise.all([loadAgents(), loadManagedNumbers()]);
  await populateProviderTestSelects();
}

init();
