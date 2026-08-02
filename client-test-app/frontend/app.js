/**
 * UVA Client Test App — Frontend Logic
 * Calls the local Express backend at http://localhost:3001
 */
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const API = import.meta.env.VITE_TEST_BACKEND_URL || 'http://localhost:3001';

// ─── Utility: API fetch ──────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API}${path}`, opts);
  const data = await res.json().catch(() => ({ message: 'No response body' }));
  if (!res.ok) {
    const msg = data.message || data.detail || `HTTP ${res.status}`;
    throw Object.assign(new Error(msg), { status: res.status, code: data.code, detail: data.detail });
  }
  return data;
}

// ─── Toast system ────────────────────────────────────────────────────────────
function toast(type, title, msg) {
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `
    <div class="toast-icon">${icons[type] || 'ℹ️'}</div>
    <div class="toast-content">
      <div class="toast-title">${escHtml(title)}</div>
      ${msg ? `<div class="toast-msg">${escHtml(String(msg))}</div>` : ''}
    </div>
  `;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ─── Loading state helper ─────────────────────────────────────────────────────
function setLoading(btn, loading, label = '') {
  if (!btn) return;
  btn.disabled = loading;
  if (loading) {
    btn._origText = btn.innerHTML;
    btn.innerHTML = `<div class="spinner"></div> ${label || 'Loading…'}`;
  } else {
    btn.innerHTML = btn._origText || btn.innerHTML;
  }
}

// ─── Badge helpers ────────────────────────────────────────────────────────────
function providerBadge(label, value, colorClass) {
  if (!value) return '';
  return `<span class="badge ${colorClass}">${label}: ${escHtml(value)}</span>`;
}

function statusBadge(status) {
  const map = {
    completed: 'badge-green', active: 'badge-green', connected: 'badge-green',
    failed: 'badge-red', error: 'badge-red',
    initiated: 'badge-yellow', ringing: 'badge-yellow', reserved: 'badge-yellow',
    purchased: 'badge-blue', answered: 'badge-blue',
  };
  const cls = map[status?.toLowerCase()] || 'badge-gray';
  return `<span class="badge ${cls}">${escHtml(status || 'unknown')}</span>`;
}

// ─── Tab Navigation ───────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const tabId = btn.dataset.tab;
    document.getElementById(`tab-${tabId}`)?.classList.add('active');

    // Lazy-load data when switching tabs
    if (tabId === 'agents') loadAgents();
    if (tabId === 'numbers') loadManagedNumbers();
    if (tabId === 'calllog') loadCallLog();
    if (tabId === 'providertest') populateProviderTestSelects();
    if (tabId === 'voice') populateVoiceAgentSelect();
  });
});

// ─── SETUP TAB ────────────────────────────────────────────────────────────────

// Check backend health on load
async function checkBackendHealth() {
  try {
    const h = await api('GET', '/api/health');
    updateStatusItem('status-backend', 'pass', 'Backend online', `localhost:3001 — ${h.apiBaseUrl}`);
    document.getElementById('header-backend-badge').innerHTML =
      `<span class="dot pulse" style="background:var(--green)"></span> Backend OK`;
    document.getElementById('header-backend-badge').className = 'badge badge-green';
    return true;
  } catch {
    updateStatusItem('status-backend', 'fail', 'Backend offline', 'Run: npm run backend');
    document.getElementById('header-backend-badge').innerHTML =
      `<span class="dot" style="background:var(--red)"></span> Backend offline`;
    document.getElementById('header-backend-badge').className = 'badge badge-red';
    return false;
  }
}

async function checkConfig() {
  try {
    const cfg = await api('GET', '/api/config');
    if (cfg.tenantId && cfg.hmacSecretSet) {
      updateStatusItem('status-config', 'pass', 'Tenant credentials set',
        `Tenant: ${cfg.tenantId.slice(0, 12)}…`);
      // pre-fill fields
      document.getElementById('cfg-api-url').value = cfg.apiBaseUrl || '';
      document.getElementById('cfg-telephony-url').value = cfg.telephonyApiUrl || cfg.apiBaseUrl || '';
      document.getElementById('cfg-session-url').value = cfg.sessionUpstreamUrl || '';
      document.getElementById('cfg-tenant-id').value = cfg.tenantId || '';
    } else {
      updateStatusItem('status-config', 'fail', 'Tenant credentials missing',
        'Fill in Tenant ID and HMAC Secret');
    }
  } catch { /* ignore */ }
}

async function checkTelnyxStatus() {
  try {
    const status = await api('GET', '/api/telnyx/status');
    const connected = status.platform_status === 'active' || status.provider_status === 'active' || status.status === 'connected';
    updateStatusItem('status-telnyx', connected ? 'pass' : 'fail',
      connected ? 'Telnyx account connected' : 'Telnyx not connected',
      status.label || status.telnyx_account_id || status.platform_status || '');
    document.getElementById('header-connection-badge').innerHTML =
      `<span class="dot ${connected ? 'pulse' : ''}" style="background:${connected ? 'var(--green)' : 'var(--red)'}"></span> ${connected ? 'Telnyx connected' : 'Telnyx disconnected'}`;
    document.getElementById('header-connection-badge').className = `badge ${connected ? 'badge-green' : 'badge-red'}`;
  } catch (e) {
    updateStatusItem('status-telnyx', 'fail', 'Telnyx status error', e.message);
  }
}

function updateStatusItem(id, state, label, detail) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `readiness-item ${state}`;
  const icons = { pass: '✅', fail: '❌', pending: '⏳' };
  el.innerHTML = `
    <span class="readiness-icon">${icons[state] || '⏳'}</span>
    <div>
      <div class="readiness-label">${escHtml(label)}</div>
      ${detail ? `<div class="readiness-detail">${escHtml(detail)}</div>` : ''}
    </div>
  `;
}

document.getElementById('btn-save-config').addEventListener('click', async () => {
  const btn = document.getElementById('btn-save-config');
  setLoading(btn, true, 'Saving…');
  try {
    const apiInput = document.getElementById('cfg-api-url').value.trim();
    const telephonyInput = document.getElementById('cfg-telephony-url').value.trim();
    const apiLooksLocalPlaceholder = /^https?:\/\/(localhost|127\.0\.0\.1):8000\/?$/i.test(apiInput);
    const telephonyLooksRemote = /^https:\/\//i.test(telephonyInput) && !/\/\/(localhost|127\.0\.0\.1)(:|\/|$)/i.test(telephonyInput);
    const resolvedApiBaseUrl = apiLooksLocalPlaceholder && telephonyLooksRemote
      ? telephonyInput
      : (apiInput || telephonyInput || undefined);

    const body = {
      apiBaseUrl: resolvedApiBaseUrl,
      telephonyApiUrl: telephonyInput || resolvedApiBaseUrl,
      sessionUpstreamUrl: document.getElementById('cfg-session-url').value.trim() || undefined,
      publishableKey: document.getElementById('cfg-publishable-key').value.trim() || undefined,
      tenantId: document.getElementById('cfg-tenant-id').value.trim() || undefined,
      hmacSecret: document.getElementById('cfg-hmac-secret').value.trim() || undefined,
      telnyxApiKey: document.getElementById('cfg-telnyx-key').value.trim() || undefined,
    };
    await api('POST', '/api/config', body);
    voiceClient = null;
    toast('success', 'Configuration saved', 'Credentials stored in backend memory.');
    await checkConfig();
  } catch (e) {
    toast('error', 'Failed to save config', e.message);
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('btn-check-status').addEventListener('click', async () => {
  const btn = document.getElementById('btn-check-status');
  setLoading(btn, true, 'Checking…');
  try {
    await checkBackendHealth();
    await checkConfig();
    await checkTelnyxStatus();
    await checkPortalReachable();
    toast('info', 'Status check complete', '');
  } catch { /* errors handled inside */ } finally {
    setLoading(btn, false);
  }
});

async function checkPortalReachable() {
  try {
    // Try fetching capabilities — this will hit the portal API through our backend
    await api('GET', '/api/capabilities');
    updateStatusItem('status-portal', 'pass', 'Portal API reachable', '');
  } catch (e) {
    updateStatusItem('status-portal', 'fail', 'Portal API error', e.message);
  }
}

document.getElementById('btn-connect-telnyx').addEventListener('click', async () => {
  const btn = document.getElementById('btn-connect-telnyx');
  setLoading(btn, true, 'Connecting…');
  try {
    const result = await api('POST', '/api/telnyx/connect');
    toast('success', 'Telnyx account connected!', result.label || result.account_id || '');
    await checkTelnyxStatus();
  } catch (e) {
    toast('error', 'Telnyx connection failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('btn-load-caps').addEventListener('click', async () => {
  const btn = document.getElementById('btn-load-caps');
  setLoading(btn, true, 'Loading…');
  try {
    const caps = await api('GET', '/api/capabilities');
    const summary = document.getElementById('caps-summary');
    summary.textContent = JSON.stringify(caps, null, 2);
    toast('success', 'Provider capabilities loaded', '');
  } catch (e) {
    toast('error', 'Failed to load capabilities', e.message);
  } finally {
    setLoading(btn, false);
  }
});

// ─── PHONE NUMBERS TAB ────────────────────────────────────────────────────────

document.getElementById('btn-search-numbers').addEventListener('click', async () => {
  const btn = document.getElementById('btn-search-numbers');
  setLoading(btn, true, 'Searching…');
  try {
    const country = document.getElementById('num-country').value;
    const areaCode = document.getElementById('num-area-code').value.trim();
    const limit = document.getElementById('num-limit').value;
    const params = new URLSearchParams({ country, limit });
    if (areaCode) params.set('areaCode', areaCode);

    const result = await api('GET', `/api/telnyx/numbers/available?${params}`);
    renderSearchResults(result);
  } catch (e) {
    toast('error', 'Search failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

function renderSearchResults(data) {
  const section = document.getElementById('search-results-section');
  const grid = document.getElementById('search-results-grid');
  const count = document.getElementById('search-result-count');

  const numbers = data.data || data.numbers || data || [];
  if (!Array.isArray(numbers) || numbers.length === 0) {
    toast('warning', 'No available numbers found', 'Try a different area code or country.');
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';
  count.textContent = `${numbers.length} found`;
  grid.innerHTML = numbers.map(n => {
    const num = n.phone_number || n.e164_number || n.number || n;
    const monthly = n.monthly_cost?.amount || n.monthly_cost || n.cost?.monthly?.amount || '';
    const features = Array.isArray(n.features) ? n.features.map(f => f.name || f).join(', ') : '';
    return `
      <div class="number-card">
        <div>
          <div class="number-display">${escHtml(num)}</div>
          <div class="number-meta">
            ${monthly ? `$${escHtml(String(monthly))}/mo · ` : ''}${escHtml(features || n.region_information?.[0]?.region_name || '')}
          </div>
        </div>
        <div class="number-actions">
          <button class="btn btn-primary btn-sm" onclick="openPurchaseModal('${escHtml(num)}')">Buy</button>
        </div>
      </div>
    `;
  }).join('');
}

async function loadManagedNumbers() {
  const el = document.getElementById('managed-numbers-list');
  el.innerHTML = `<div class="loading-row"><div class="spinner"></div><br/>Loading…</div>`;
  try {
    const result = await api('GET', '/api/telnyx/numbers/managed');
    const numbers = result.data || result.numbers || result || [];
    if (!Array.isArray(numbers) || numbers.length === 0) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">📭</div>
        <div class="empty-state-title">No managed numbers</div>
        <div class="empty-state-text">Sync from Telnyx or purchase a number</div>
      </div>`;
      return;
    }
    el.innerHTML = numbers.map(n => {
      const num = n.phone_number || n.e164_number || n.number || n.id;
      const assigned = n.agent_id ? `<span class="badge badge-purple">Agent: ${escHtml(n.agent_id?.slice(0,8))}…</span>` : '';
      const status = n.status || n.state || 'active';
      return `
        <div class="number-card" style="margin-bottom:0.5rem; border-radius: var(--radius-sm)">
          <div>
            <div class="number-display" style="font-size:0.9rem">${escHtml(num)}</div>
            <div class="number-meta flex gap-1 mt-1">
              ${statusBadge(status)} ${assigned}
              <span class="badge badge-gray">${escHtml(n.id?.slice(0,12) || '')}…</span>
            </div>
          </div>
          <button class="btn btn-danger btn-sm" onclick="disableNumber('${escHtml(n.id || num)}')">Disable</button>
        </div>
      `;
    }).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-title">Error</div><div class="empty-state-text">${escHtml(e.message)}</div></div>`;
  }
}

document.getElementById('btn-refresh-managed').addEventListener('click', loadManagedNumbers);

document.getElementById('btn-sync-numbers').addEventListener('click', async () => {
  const btn = document.getElementById('btn-sync-numbers');
  setLoading(btn, true, 'Syncing…');
  try {
    const result = await api('POST', '/api/telnyx/numbers/sync');
    toast('success', 'Numbers synced!', JSON.stringify(result).slice(0, 80));
    await loadManagedNumbers();
  } catch (e) {
    toast('error', 'Sync failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

window.disableNumber = async (numberId) => {
  if (!confirm(`Disable number ${numberId}? This will remove it from UVA routing.`)) return;
  try {
    await api('POST', `/api/telnyx/numbers/${encodeURIComponent(numberId)}/disable`);
    toast('success', 'Number disabled', numberId);
    loadManagedNumbers();
  } catch (e) {
    toast('error', 'Failed to disable number', e.message);
  }
};

// ─── Purchase Modal ────────────────────────────────────────────────
let _pendingNumber = null;

window.openPurchaseModal = (num) => {
  _pendingNumber = num;
  document.getElementById('modal-purchase-number').textContent = num;
  document.getElementById('modal-purchase').classList.remove('hidden');
};


document.getElementById('modal-purchase-cancel').addEventListener('click', () => {
  document.getElementById('modal-purchase').classList.add('hidden');
  _pendingNumber = null;
});

document.getElementById('modal-purchase-confirm').addEventListener('click', async () => {
  const btn = document.getElementById('modal-purchase-confirm');
  setLoading(btn, true, 'Purchasing…');
  try {
    const result = await api('POST', '/api/telnyx/numbers/purchase', { e164Number: _pendingNumber });
    document.getElementById('modal-purchase').classList.add('hidden');
    toast('success', 'Number purchased!', _pendingNumber);
    _pendingNumber = null;
    loadManagedNumbers();
  } catch (e) {
    toast('error', 'Purchase failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

// Close modals on overlay click
['modal-purchase', 'modal-update-agent'].forEach(id => {
  document.getElementById(id).addEventListener('click', (e) => {
    if (e.target.id === id) {
      document.getElementById(id).classList.add('hidden');
      _pendingNumber = null;
    }
  });
});

// ─── AGENTS TAB ───────────────────────────────────────────────────────────────

async function loadAgents() {
  const el = document.getElementById('agents-list');
  el.innerHTML = `<div class="loading-row"><div class="spinner"></div><br/>Loading agents…</div>`;
  try {
    const result = await api('GET', '/api/agents');
    const agents = result.agents || result.data || result || [];
    if (!Array.isArray(agents) || agents.length === 0) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">🤖</div>
        <div class="empty-state-title">No agents yet</div>
        <div class="empty-state-text">Create your first agent using the form</div>
      </div>`;
      return;
    }
    el.innerHTML = agents.map(a => `
      <div class="agent-card mb-2">
        <div class="agent-header">
          <div>
            <div class="agent-name">${escHtml(a.name)}</div>
            <div class="agent-id">${escHtml(a.id)}</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="openUpdateModal(${JSON.stringify(a).replace(/"/g, '&quot;')})">✏️</button>
        </div>
        <div class="agent-prompt">${escHtml(a.prompt || '')}</div>
        <div class="agent-providers">
          ${providerBadge('lang', a.agent_language, 'badge-gray')}
          ${providerBadge('stt', a.stt_provider, 'badge-blue')}
          ${providerBadge('llm', a.llm_provider || 'gemini', 'badge-purple')}
          ${a.llm_model ? `<span class="badge badge-gray">${escHtml(a.llm_model)}</span>` : ''}
          ${providerBadge('tts', a.tts_provider, 'badge-pink')}
        </div>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-title">Error</div><div class="empty-state-text">${escHtml(e.message)}</div></div>`;
  }
}

document.getElementById('btn-refresh-agents').addEventListener('click', loadAgents);

document.getElementById('btn-create-agent').addEventListener('click', async () => {
  const btn = document.getElementById('btn-create-agent');
  const name = document.getElementById('agent-name').value.trim();
  const prompt = document.getElementById('agent-prompt').value.trim();
  const voiceId = document.getElementById('agent-voice-id').value.trim();
  if (!name || !prompt || !voiceId) {
    toast('warning', 'Name, prompt, and voice ID are required', 'Use a real enabled voice ID from the hosted voice catalog.');
    return;
  }
  setLoading(btn, true, 'Creating…');
  try {
    const body = {
      name,
      prompt,
      agentLanguage: document.getElementById('agent-language').value || undefined,
      llmModel: document.getElementById('agent-llm-model').value || undefined,
      sttProvider: document.getElementById('agent-stt').value || undefined,
      llmProvider: document.getElementById('agent-llm').value || undefined,
      ttsProvider: document.getElementById('agent-tts').value || undefined,
      ttsVoiceId: voiceId,
      voiceId,
    };
    // Remove undefined keys
    Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);
    const agent = await api('POST', '/api/agents', body);
    toast('success', `Agent created: ${agent.name}`, `ID: ${agent.id}`);
    // Clear form
    ['agent-name', 'agent-prompt', 'agent-voice-id'].forEach(id => {
      document.getElementById(id).value = '';
    });
    await loadAgents();
  } catch (e) {
    toast('error', 'Failed to create agent', e.message);
  } finally {
    setLoading(btn, false);
  }
});

window.openUpdateModal = (agent) => {
  document.getElementById('update-agent-id').value = agent.id;
  document.getElementById('update-agent-name').value = agent.name || '';
  document.getElementById('update-agent-prompt').value = agent.prompt || '';
  document.getElementById('update-agent-stt').value = '';
  document.getElementById('update-agent-llm').value = '';
  document.getElementById('update-agent-tts').value = '';
  document.getElementById('modal-update-agent').classList.remove('hidden');
};

document.getElementById('modal-update-cancel').addEventListener('click', () => {
  document.getElementById('modal-update-agent').classList.add('hidden');
});

document.getElementById('modal-update-confirm').addEventListener('click', async () => {
  const btn = document.getElementById('modal-update-confirm');
  const agentId = document.getElementById('update-agent-id').value;
  setLoading(btn, true, 'Saving…');
  try {
    const body = {
      name: document.getElementById('update-agent-name').value.trim() || undefined,
      prompt: document.getElementById('update-agent-prompt').value.trim() || undefined,
      sttProvider: document.getElementById('update-agent-stt').value || undefined,
      llmProvider: document.getElementById('update-agent-llm').value || undefined,
      ttsProvider: document.getElementById('update-agent-tts').value || undefined,
    };
    Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);
    const updated = await api('PATCH', `/api/agents/${encodeURIComponent(agentId)}`, body);
    toast('success', `Agent updated: ${updated.name}`, '');
    document.getElementById('modal-update-agent').classList.add('hidden');
    await loadAgents();
  } catch (e) {
    toast('error', 'Failed to update agent', e.message);
  } finally {
    setLoading(btn, false);
  }
});

// ─── PROVIDER TEST TAB ────────────────────────────────────────────────────────

async function populateProviderTestSelects() {
  // Load managed numbers
  try {
    const result = await api('GET', '/api/telnyx/numbers/managed');
    const numbers = result.data || result.numbers || result || [];
    ['pt-number-id', 'call-from-id'].forEach(id => {
      const sel = document.getElementById(id);
      sel.innerHTML = '<option value="">— select a managed number —</option>' +
        numbers.map(n => `<option value="${escHtml(n.id)}">${escHtml(n.phone_number || n.id)}</option>`).join('');
    });
  } catch { /* silently ignore */ }

  // Load agents
  try {
    const result = await api('GET', '/api/agents');
    const agents = result.agents || result.data || result || [];
    ['pt-agent-id', 'call-agent-id', 'voice-agent-id'].forEach(id => {
      const sel = document.getElementById(id);
      if (!sel) return;
      sel.innerHTML = '<option value="">— select an agent —</option>' +
        agents.map(a => `<option value="${escHtml(a.id)}">${escHtml(a.name)} (${escHtml(a.id.slice(0, 8))}…)</option>`).join('');
    });
  } catch { /* silently ignore */ }
}

async function populateVoiceAgentSelect() {
  await populateProviderTestSelects();
}

document.getElementById('btn-assign-number').addEventListener('click', async () => {
  const numberId = document.getElementById('pt-number-id').value;
  const agentId = document.getElementById('pt-agent-id').value;
  if (!numberId || !agentId) {
    toast('warning', 'Select a number and an agent', '');
    return;
  }
  const btn = document.getElementById('btn-assign-number');
  setLoading(btn, true, 'Assigning…');
  try {
    await api('POST', `/api/telnyx/numbers/${encodeURIComponent(numberId)}/assign-agent`, { agentId });
    toast('success', 'Number assigned to agent!', `Number: ${numberId}`);
  } catch (e) {
    toast('error', 'Failed to assign number', e.message);
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('btn-configure-routing').addEventListener('click', async () => {
  const numberId = document.getElementById('pt-number-id').value;
  if (!numberId) { toast('warning', 'Select a number first', ''); return; }
  const btn = document.getElementById('btn-configure-routing');
  setLoading(btn, true, 'Configuring…');
  try {
    await api('POST', `/api/telnyx/numbers/${encodeURIComponent(numberId)}/configure-routing`);
    toast('success', 'Routing configured!', '');
  } catch (e) {
    toast('error', 'Failed to configure routing', e.message);
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('btn-check-readiness').addEventListener('click', async () => {
  const btn = document.getElementById('btn-check-readiness');
  setLoading(btn, true, 'Checking…');
  try {
    const result = await api('GET', '/api/readiness');
    renderReadiness(result);
  } catch (e) {
    toast('error', 'Readiness check failed', e.message);
    document.getElementById('readiness-results').innerHTML = `
      <div class="readiness-item fail">
        <span class="readiness-icon">❌</span>
        <div><div class="readiness-label">Check failed</div><div class="readiness-detail">${escHtml(e.message)}</div></div>
      </div>
    `;
  } finally {
    setLoading(btn, false);
  }
});

function renderReadiness(data) {
  const el = document.getElementById('readiness-results');
  const ready = data.is_ready === true;
  const reasons = data.reasons || [];
  const checks = data.checks || {};

  const checkItems = Object.entries(checks).length > 0
    ? Object.entries(checks).map(([key, val]) => {
        const passed = val === true || val?.passed === true;
        return `
          <div class="readiness-item ${passed ? 'pass' : 'fail'}">
            <span class="readiness-icon">${passed ? '✅' : '❌'}</span>
            <div>
              <div class="readiness-label">${escHtml(key.replace(/_/g, ' '))}</div>
              ${typeof val === 'string' ? `<div class="readiness-detail">${escHtml(val)}</div>` : ''}
            </div>
          </div>
        `;
      }).join('')
    : reasons.map(r => `
        <div class="readiness-item fail">
          <span class="readiness-icon">❌</span>
          <div><div class="readiness-label">${escHtml(r)}</div></div>
        </div>
      `).join('');

  el.innerHTML = `
    <div class="readiness-item ${ready ? 'pass' : 'fail'}" style="margin-bottom:0.75rem; font-weight:600">
      <span class="readiness-icon">${ready ? '🟢' : '🔴'}</span>
      <div><div class="readiness-label">Outbound is ${ready ? 'READY' : 'NOT READY'}</div></div>
    </div>
    ${checkItems || (ready ? '<div class="readiness-item pass"><span class="readiness-icon">✅</span><div class="readiness-label">All checks passed</div></div>' : '')}
  `;

  if (ready) toast('success', 'Outbound is ready!', '');
  else toast('warning', 'Outbound not ready', reasons[0] || 'See checks above');
}

// SIP
document.getElementById('btn-upsert-sip').addEventListener('click', async () => {
  const btn = document.getElementById('btn-upsert-sip');
  setLoading(btn, true, 'Saving…');
  try {
    await api('POST', '/api/telnyx/sip-connection', {
      sipFqdn: document.getElementById('sip-fqdn').value.trim(),
      sipUsername: document.getElementById('sip-username').value.trim(),
      sipSecret: document.getElementById('sip-secret').value.trim(),
    });
    toast('success', 'SIP connection saved', '');
  } catch (e) {
    toast('error', 'SIP save failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('btn-verify-sip').addEventListener('click', async () => {
  const btn = document.getElementById('btn-verify-sip');
  setLoading(btn, true, 'Verifying…');
  try {
    const r = await api('POST', '/api/telnyx/sip-connection/verify');
    toast('success', 'SIP verified!', r.message || '');
  } catch (e) {
    toast('error', 'SIP verification failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

// OVP
document.getElementById('btn-upsert-ovp').addEventListener('click', async () => {
  const btn = document.getElementById('btn-upsert-ovp');
  setLoading(btn, true, 'Saving…');
  try {
    const dest = document.getElementById('ovp-destinations').value.split(',').map(s => s.trim()).filter(Boolean);
    const conc = parseInt(document.getElementById('ovp-concurrency').value, 10) || 2;
    await api('POST', '/api/telnyx/outbound-voice-profile', {
      allowedDestinations: dest,
      concurrencyLimit: conc,
    });
    toast('success', 'Outbound voice profile saved', '');
  } catch (e) {
    toast('error', 'OVP save failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('btn-verify-ovp').addEventListener('click', async () => {
  const btn = document.getElementById('btn-verify-ovp');
  setLoading(btn, true, 'Verifying…');
  try {
    const r = await api('POST', '/api/telnyx/outbound-voice-profile/verify');
    toast('success', 'OVP verified!', r.message || '');
  } catch (e) {
    toast('error', 'OVP verification failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('btn-configure-trunk').addEventListener('click', async () => {
  const btn = document.getElementById('btn-configure-trunk');
  setLoading(btn, true, 'Configuring…');
  try {
    await api('POST', '/api/telnyx/outbound-trunk');
    toast('success', 'Outbound trunk configured!', '');
  } catch (e) {
    toast('error', 'Trunk config failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

// Outbound call
document.getElementById('btn-make-call').addEventListener('click', async () => {
  const agentId = document.getElementById('call-agent-id').value;
  const fromNumberId = document.getElementById('call-from-id').value;
  const toNumber = document.getElementById('call-to-number').value.trim();
  const recipient = document.getElementById('call-recipient').value.trim();

  if (!agentId || !fromNumberId || !toNumber) {
    toast('warning', 'Fill in all required call fields', 'Agent, From Number, and To Number are required');
    return;
  }

  if (!confirm(`Place a real outbound call to ${toNumber}? This will charge your Telnyx account.`)) return;

  const btn = document.getElementById('btn-make-call');
  setLoading(btn, true, 'Calling…');
  try {
    const call = await api('POST', '/api/outbound-call', {
      agentId, fromNumberId, toNumber, recipient,
    });
    const resultEl = document.getElementById('call-result');
    resultEl.style.display = 'block';
    resultEl.innerHTML = `
      <div class="card" style="border-color: var(--green)">
        <div class="card-title">📞 Call Initiated</div>
        <div class="flex gap-1 mb-1">
          <span class="badge badge-green">Call started</span>
          <span class="badge badge-gray mono">${escHtml(call.telephony_call_id || call.id || '')}</span>
        </div>
        <div style="font-size:0.8rem; color:var(--text-secondary)">To: ${escHtml(toNumber)}</div>
      </div>
    `;
    toast('success', 'Outbound call placed!', `To: ${toNumber}`);
  } catch (e) {
    toast('error', 'Call failed', e.message);
  } finally {
    setLoading(btn, false);
  }
});

// ─── CALL LOG TAB ─────────────────────────────────────────────────────────────

async function loadCallLog() {
  const tbody = document.getElementById('calllog-tbody');
  tbody.innerHTML = '<tr><td colspan="7" class="loading-row"><div class="spinner"></div><br/>Loading…</td></tr>';
  try {
    const limit = document.getElementById('calllog-limit').value;
    const result = await api('GET', `/api/calls?limit=${limit}`);
    const calls = result.data || result.calls || result || [];

    if (!Array.isArray(calls) || calls.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="loading-row">No calls found</td></tr>';
      return;
    }

    tbody.innerHTML = calls.map(c => {
      const started = c.started_at || c.created_at || c.initiated_at || '';
      const direction = c.direction || 'outbound';
      return `
        <tr>
          <td class="mono">${escHtml((c.telephony_call_id || c.id || '').slice(0, 16))}…</td>
          <td>${direction === 'outbound' ? '↗️' : '↙️'} ${escHtml(direction)}</td>
          <td class="mono">${escHtml(c.from_number || c.from || '—')}</td>
          <td class="mono">${escHtml(c.to_number || c.to || '—')}</td>
          <td>${statusBadge(c.status || c.state)}</td>
          <td class="mono">${escHtml((c.agent_id || '—').slice(0, 12))}${c.agent_id ? '…' : ''}</td>
          <td>${started ? escHtml(new Date(started).toLocaleString()) : '—'}</td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-row" style="color:var(--red)">Error: ${escHtml(e.message)}</td></tr>`;
  }
}

document.getElementById('btn-refresh-calls').addEventListener('click', loadCallLog);
document.getElementById('calllog-limit').addEventListener('change', loadCallLog);

// ─── BROWSER VOICE SESSION ────────────────────────────────────────────────────

let voiceClient = null;
let audioNeedsUnlock = false;

function getPublishableKey() {
  return document.getElementById('cfg-publishable-key')?.value.trim() || import.meta.env.VITE_UVA_PUBLISHABLE_KEY || '';
}

function getVoiceClient() {
  if (voiceClient) return voiceClient;

  voiceClient = new AwaazLabsUvaVoice({
    publishableKey: getPublishableKey(),
    sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT || `${API}/api/voice/session`,
    refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT || `${API}/api/voice/session/refresh`,
  });

  voiceClient.on('connected', () => {
    document.getElementById('voice-status-badge').className = 'badge badge-green';
    document.getElementById('voice-status-badge').innerHTML = '<span class="dot pulse"></span> Connected';
    document.getElementById('btn-voice-connect').style.display = 'none';
    document.getElementById('btn-voice-unlock').style.display = audioNeedsUnlock ? 'block' : 'none';
    document.getElementById('btn-voice-disconnect').style.display = 'block';
    
    document.getElementById('voice-transcript-log').innerHTML = 
      `<div style="color:var(--text-secondary); text-align:center;">Recording started... Speak now!</div>`;
  });

  voiceClient.on('disconnected', () => {
    document.getElementById('voice-status-badge').className = 'badge badge-gray';
    document.getElementById('voice-status-badge').textContent = 'Disconnected';
    audioNeedsUnlock = false;
    document.getElementById('btn-voice-connect').style.display = 'block';
    document.getElementById('btn-voice-unlock').style.display = 'none';
    document.getElementById('btn-voice-disconnect').style.display = 'none';
  });

  voiceClient.on('transcript', (event) => {
    const log = document.getElementById('voice-transcript-log');
    if (log.innerHTML.includes('Recording started')) log.innerHTML = '';
    
    // Remove the partial indicator if the message is final
    const id = event.id || Math.random().toString(36).substring(7);
    const existing = document.getElementById(`msg-${id}`);
    
    const sender = event.speaker === 'agent' ? '🤖 Agent' : '👤 You';
    const color = event.speaker === 'agent' ? 'var(--blue)' : 'var(--green)';
    const text = escHtml(event.text || '');
    
    if (existing) {
      existing.innerHTML = `<strong style="color:${color}">${sender}:</strong> ${text}`;
      if (!event.final) existing.style.opacity = '0.7';
      else existing.style.opacity = '1';
    } else {
      const el = document.createElement('div');
      el.id = `msg-${id}`;
      el.style.opacity = event.final ? '1' : '0.7';
      el.innerHTML = `<strong style="color:${color}">${sender}:</strong> ${text}`;
      log.appendChild(el);
      log.scrollTop = log.scrollHeight;
    }
  });

  voiceClient.on('audio_blocked', async (blocked) => {
    audioNeedsUnlock = Boolean(blocked);
    document.getElementById('btn-voice-unlock').style.display = audioNeedsUnlock ? 'block' : 'none';
    if (blocked) {
      toast('warning', 'Audio blocked', 'Click Unlock Audio to start playback.');
      document.getElementById('voice-status-badge').textContent = 'Audio blocked - unlock required';
    }
  });

  return voiceClient;
}

document.getElementById('btn-voice-connect').addEventListener('click', async () => {
  const agentId = document.getElementById('voice-agent-id').value;
  if (!agentId) return toast('warning', 'Select an agent to connect', '');

  const btn = document.getElementById('btn-voice-connect');
  setLoading(btn, true, 'Connecting…');
  document.getElementById('voice-connection-status').style.display = 'block';
  document.getElementById('voice-status-badge').className = 'badge badge-yellow';
  document.getElementById('voice-status-badge').textContent = 'Minting token...';

  try {
    voiceClient = null;
    const vc = getVoiceClient();
    await vc.connect({ agentId });
  } catch (e) {
    toast('error', 'Voice connection failed', e.message);
    document.getElementById('voice-status-badge').className = 'badge badge-red';
    document.getElementById('voice-status-badge').textContent = 'Error connecting';
  } finally {
    setLoading(btn, false);
  }
});

document.getElementById('btn-voice-unlock').addEventListener('click', async () => {
  if (!voiceClient) return;
  try {
    await voiceClient.startAudio();
    audioNeedsUnlock = false;
    document.getElementById('btn-voice-unlock').style.display = 'none';
    toast('success', 'Audio unlocked', '');
  } catch (e) {
    toast('error', 'Audio unlock failed', e.message);
  }
});

document.getElementById('btn-voice-disconnect').addEventListener('click', async () => {
  if (voiceClient) {
    await voiceClient.disconnect();
  }
});

// ─── INIT ─────────────────────────────────────────────────────────────────────
(async () => {
  await checkBackendHealth();
  await checkConfig();
  // Load agents immediately (first tab with data)
  await loadAgents();
})();
