type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

type ManagedNumber = {
  id?: string;
  number_id?: string;
  e164_number?: string;
  e164?: string;
  phone_number?: string;
  agent_id?: string | null;
  assigned_agent_id?: string | null;
  platform_status?: string;
  provider_status?: string;
  [key: string]: unknown;
};

function numberId(row: ManagedNumber): string {
  return String(row.id || row.number_id || '');
}

function numberE164(row: ManagedNumber): string {
  return String(row.e164_number || row.e164 || row.phone_number || '');
}

function agentOnNumber(row: ManagedNumber): string {
  return String(row.agent_id || row.assigned_agent_id || '') || '—';
}

export function mountTelephonyPanel(opts: {
  backendOrigin: string;
  getAgentId: () => string;
}): void {
  const root = document.querySelector<HTMLDivElement>('#telephony-root');
  if (!root) return;

  root.innerHTML = `
    <section class="panel telephony-panel">
      <h2>Telephony (Telnyx · npm @awaazlabs-uva/telephony)</h2>
      <p class="hint">
        Telnyx API key stays in <code>backend/.env</code> only. This panel talks to
        <strong>your host backend</strong>, which signs calls with the tenant HMAC.
      </p>

      <div class="telephony-status" id="tel-status">Checking Telnyx connection…</div>

      <div class="actions telephony-actions">
        <button id="tel-connect-btn" type="button">Connect / refresh Telnyx</button>
        <button id="tel-sync-btn" type="button">Sync account numbers</button>
        <button id="tel-refresh-btn" type="button">Refresh lists</button>
        <button id="tel-prepare-btn" type="button">Prepare outbound</button>
        <button id="tel-calls-btn" type="button">Recent calls</button>
      </div>

      <div class="telephony-grid">
        <div>
          <h3 class="telephony-subhead">Managed numbers (platform)</h3>
          <div id="tel-managed" class="telephony-list">Loading…</div>
        </div>
        <div>
          <h3 class="telephony-subhead">Owned on Telnyx (provider)</h3>
          <div id="tel-owned" class="telephony-list">Loading…</div>
        </div>
      </div>

      <div class="telephony-grid">
        <div>
          <h3 class="telephony-subhead">Buy a number</h3>
          <div class="telephony-buy-row">
            <label>
              Country
              <input id="tel-country" value="US" maxlength="2" />
            </label>
            <label>
              Area code
              <input id="tel-area" placeholder="415" />
            </label>
            <button id="tel-search-btn" type="button">Search</button>
          </div>
          <div id="tel-search-results" class="telephony-list">Search to list purchasable numbers.</div>
        </div>
        <div>
          <h3 class="telephony-subhead">Assign + calls</h3>
          <label>
            Managed number id
            <input id="tel-number-id" placeholder="from managed list" autocomplete="off" />
          </label>
          <label>
            Agent id (defaults to Session field)
            <input id="tel-agent-id" placeholder="agent uuid" autocomplete="off" />
          </label>
          <div class="actions">
            <button id="tel-assign-btn" type="button">Assign to agent + configure inbound routing</button>
          </div>
          <p class="hint" id="tel-inbound-hint">
            Inbound: after assign + routing, dial the E.164 number from a real phone.
          </p>
          <label>
            Outbound to (E.164)
            <input id="tel-to-number" placeholder="+15551234567" autocomplete="off" />
          </label>
          <div class="actions">
            <button id="tel-outbound-btn" type="button">Place outbound call</button>
          </div>
        </div>
      </div>

      <pre id="tel-log" class="log-box telephony-log">Telephony log…</pre>
    </section>
  `;

  const els = {
    status: root.querySelector<HTMLElement>('#tel-status')!,
    managed: root.querySelector<HTMLElement>('#tel-managed')!,
    owned: root.querySelector<HTMLElement>('#tel-owned')!,
    searchResults: root.querySelector<HTMLElement>('#tel-search-results')!,
    log: root.querySelector<HTMLElement>('#tel-log')!,
    numberId: root.querySelector<HTMLInputElement>('#tel-number-id')!,
    agentId: root.querySelector<HTMLInputElement>('#tel-agent-id')!,
    toNumber: root.querySelector<HTMLInputElement>('#tel-to-number')!,
    country: root.querySelector<HTMLInputElement>('#tel-country')!,
    area: root.querySelector<HTMLInputElement>('#tel-area')!,
    connectBtn: root.querySelector<HTMLButtonElement>('#tel-connect-btn')!,
    syncBtn: root.querySelector<HTMLButtonElement>('#tel-sync-btn')!,
    refreshBtn: root.querySelector<HTMLButtonElement>('#tel-refresh-btn')!,
    prepareBtn: root.querySelector<HTMLButtonElement>('#tel-prepare-btn')!,
    callsBtn: root.querySelector<HTMLButtonElement>('#tel-calls-btn')!,
    searchBtn: root.querySelector<HTMLButtonElement>('#tel-search-btn')!,
    assignBtn: root.querySelector<HTMLButtonElement>('#tel-assign-btn')!,
    outboundBtn: root.querySelector<HTMLButtonElement>('#tel-outbound-btn')!,
  };

  function log(title: string, payload: Json) {
    const block = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
    els.log.textContent = `${new Date().toLocaleTimeString()} · ${title}\n${block}\n\n${els.log.textContent}`;
  }

  async function api(path: string, init?: RequestInit) {
    const res = await fetch(`${opts.backendOrigin}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
      ...init,
    });
    const text = await res.text();
    let body: any = text;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      /* keep */
    }
    if (!res.ok) {
      const err = new Error(body?.message || body?.error || `${res.status} ${path}`);
      (err as any).body = body;
      (err as any).status = res.status;
      throw err;
    }
    return body;
  }

  function renderManaged(rows: ManagedNumber[]) {
    if (!rows.length) {
      els.managed.textContent = 'No managed numbers yet — Connect + Sync, or Buy.';
      return;
    }
    els.managed.innerHTML = rows
      .map((row) => {
        const id = numberId(row);
        const e164 = numberE164(row);
        return `<button type="button" class="telephony-item" data-id="${id}" data-e164="${e164}">
          <strong>${e164 || '(no e164)'}</strong>
          <span>${id}</span>
          <span>agent: ${agentOnNumber(row)}</span>
          <span>${row.platform_status || row.provider_status || ''}</span>
        </button>`;
      })
      .join('');
    els.managed.querySelectorAll<HTMLButtonElement>('.telephony-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        els.numberId.value = btn.dataset.id || '';
        log('selected managed number', { id: btn.dataset.id, e164: btn.dataset.e164 });
      });
    });
  }

  function renderOwned(rows: ManagedNumber[]) {
    if (!rows.length) {
      els.owned.textContent = 'No owned Telnyx numbers returned.';
      return;
    }
    els.owned.innerHTML = rows
      .map((row) => {
        const e164 = numberE164(row);
        return `<div class="telephony-item static">
          <strong>${e164 || JSON.stringify(row).slice(0, 80)}</strong>
          <button type="button" class="telephony-mini" data-import="${e164}">Import to platform</button>
        </div>`;
      })
      .join('');
    els.owned.querySelectorAll<HTMLButtonElement>('[data-import]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          const data = await api('/api/telephony/import', {
            method: 'POST',
            body: JSON.stringify({ e164Number: btn.dataset.import }),
          });
          log('import', data);
          await refreshNumbers();
        } catch (err: any) {
          log('import failed', err?.body || err?.message || String(err));
        }
      });
    });
  }

  function renderSearch(rows: any[]) {
    if (!rows.length) {
      els.searchResults.textContent = 'No available numbers for that query.';
      return;
    }
    els.searchResults.innerHTML = rows
      .slice(0, 25)
      .map((row) => {
        const e164 = row.e164_number || row.e164 || '';
        const cost = [row.upfront_cost, row.monthly_cost, row.currency].filter(Boolean).join(' / ');
        return `<div class="telephony-item static">
          <strong>${e164}</strong>
          <span>${row.region || row.number_type || ''} ${cost}</span>
          <button type="button" class="telephony-mini" data-buy="${e164}">Purchase</button>
        </div>`;
      })
      .join('');
    els.searchResults.querySelectorAll<HTMLButtonElement>('[data-buy]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!confirm(`Purchase ${btn.dataset.buy}? This spends Telnyx balance.`)) return;
        try {
          const data = await api('/api/telephony/purchase', {
            method: 'POST',
            body: JSON.stringify({ e164Number: btn.dataset.buy }),
          });
          log('purchase', data);
          const managed = (data.managed || []) as ManagedNumber[];
          renderManaged(managed);
          const bought = managed.find((m) => numberE164(m) === btn.dataset.buy);
          if (bought) els.numberId.value = numberId(bought);
        } catch (err: any) {
          log('purchase failed', err?.body || err?.message || String(err));
        }
      });
    });
  }

  async function refreshStatus() {
    try {
      const data = await api('/api/telephony/status');
      const ready = data.readiness?.ready ?? data.readiness?.is_ready;
      const conn = data.connection?.platform_status || data.connectionError || 'unknown';
      els.status.innerHTML = `
        <span>Telnyx key in env: <strong>${data.telnyxKeyConfigured ? 'yes' : 'NO'}</strong></span>
        · <span>connection: <strong>${conn}</strong></span>
        · <span>outbound ready: <strong>${ready === true ? 'yes' : ready === false ? 'no' : 'n/a'}</strong></span>
      `;
      log('status', data);
    } catch (err: any) {
      els.status.textContent = `Status failed: ${err?.message || err}`;
      log('status failed', err?.body || err?.message || String(err));
    }
  }

  async function refreshNumbers() {
    try {
      const data = await api('/api/telephony/numbers');
      renderManaged(data.managed || []);
      renderOwned(data.owned || []);
      log('numbers', { managed: (data.managed || []).length, owned: (data.owned || []).length });
    } catch (err: any) {
      els.managed.textContent = 'Failed to load managed numbers.';
      els.owned.textContent = 'Failed to load owned numbers.';
      log('numbers failed', err?.body || err?.message || String(err));
    }
  }

  function resolveAgentId() {
    return els.agentId.value.trim() || opts.getAgentId().trim();
  }

  els.connectBtn.addEventListener('click', async () => {
    try {
      const data = await api('/api/telephony/connect', { method: 'POST', body: '{}' });
      log('connect', data);
      await refreshStatus();
    } catch (err: any) {
      log('connect failed', err?.body || err?.message || String(err));
    }
  });

  els.syncBtn.addEventListener('click', async () => {
    try {
      const data = await api('/api/telephony/sync', { method: 'POST', body: '{}' });
      renderManaged(data.managed || []);
      renderOwned(data.owned || []);
      log('sync', data);
      await refreshStatus();
    } catch (err: any) {
      log('sync failed', err?.body || err?.message || String(err));
    }
  });

  els.refreshBtn.addEventListener('click', async () => {
    await refreshStatus();
    await refreshNumbers();
  });

  els.prepareBtn.addEventListener('click', async () => {
    try {
      const data = await api('/api/telephony/prepare-outbound', { method: 'POST', body: '{}' });
      log('prepare outbound', data);
      await refreshStatus();
    } catch (err: any) {
      log('prepare failed', err?.body || err?.message || String(err));
    }
  });

  els.callsBtn.addEventListener('click', async () => {
    try {
      const data = await api('/api/telephony/calls');
      log('recent calls', data);
    } catch (err: any) {
      log('calls failed', err?.body || err?.message || String(err));
    }
  });

  els.searchBtn.addEventListener('click', async () => {
    try {
      const country = els.country.value.trim() || 'US';
      const areaCode = els.area.value.trim();
      const qs = new URLSearchParams({ country });
      if (areaCode) qs.set('areaCode', areaCode);
      const data = await api(`/api/telephony/search?${qs}`);
      renderSearch(data.numbers || []);
      log('search', { count: (data.numbers || []).length, country, areaCode });
    } catch (err: any) {
      log('search failed', err?.body || err?.message || String(err));
    }
  });

  els.assignBtn.addEventListener('click', async () => {
    try {
      const numberIdValue = els.numberId.value.trim();
      const agentId = resolveAgentId();
      if (!numberIdValue || !agentId) {
        log('assign blocked', 'Pick a managed number id and set agent id');
        return;
      }
      const data = await api('/api/telephony/assign', {
        method: 'POST',
        body: JSON.stringify({ numberId: numberIdValue, agentId }),
      });
      log('assign + inbound routing', data);
      els.status.insertAdjacentHTML(
        'beforeend',
        ` · <span>inbound: call the assigned E.164; agent ${agentId.slice(0, 8)}…</span>`,
      );
      await refreshNumbers();
    } catch (err: any) {
      log('assign failed', err?.body || err?.message || String(err));
    }
  });

  els.outboundBtn.addEventListener('click', async () => {
    try {
      const fromNumberId = els.numberId.value.trim();
      const agentId = resolveAgentId();
      const toNumber = els.toNumber.value.trim();
      if (!fromNumberId || !agentId || !toNumber) {
        log('outbound blocked', 'Need managed number id, agent id, and E.164 destination');
        return;
      }
      const data = await api('/api/telephony/outbound', {
        method: 'POST',
        body: JSON.stringify({ fromNumberId, agentId, toNumber }),
      });
      log('outbound call', data);
      const callId = data.call?.telephony_call_id;
      if (callId) {
        setTimeout(async () => {
          try {
            const status = await api(`/api/telephony/calls/${encodeURIComponent(callId)}`);
            log('outbound status', status);
          } catch (err: any) {
            log('outbound status failed', err?.body || err?.message || String(err));
          }
        }, 2500);
      }
    } catch (err: any) {
      log('outbound failed', err?.body || err?.message || String(err));
    }
  });

  els.agentId.value = opts.getAgentId();
  void refreshStatus();
  void refreshNumbers();
}
