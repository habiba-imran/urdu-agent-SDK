import { randomUUID } from 'node:crypto';

function sendError(res, err, fallback = 'telephony_error') {
  const status = Number(err?.status || err?.statusCode || 500);
  res.status(status >= 400 && status < 600 ? status : 500).json({
    error: err?.code || fallback,
    message: err instanceof Error ? err.message : String(err),
  });
}

function asList(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.numbers)) return payload.numbers;
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

export function createTelephonyClient(config) {
  if (!config.telephonyApiUrl) {
    const err = new Error('UVA_TELEPHONY_API_URL / UVA_API_BASE_URL is not set');
    err.status = 501;
    err.code = 'telephony_not_configured';
    throw err;
  }
  // Dynamic import keeps createApp sync-friendly at boot.
  return import('@awaazlabs-uva/telephony').then(({ TelephonyClient }) => {
    const operationBudget = AbortSignal.timeout(config.telephonyOperationTimeoutMs ?? 120000);
    return new TelephonyClient({
      baseUrl: config.telephonyApiUrl,
      tenantId: config.tenantId,
      tenantSecret: config.hmacSecret,
      signatureVersion: 'raw-body-v1',
      fetch: (url, init) => {
        // Several machine reads use POST. Do not give list/status requests the
        // provisioning timeout, or multiply the budget across sequential steps.
        const path = new URL(url).pathname;
        const readOnly = init?.method === 'GET' || /\/(list|get|search|drift)$/.test(path);
        const deadline = readOnly ? AbortSignal.timeout(config.telephonyReadTimeoutMs ?? 10000) : operationBudget;
        return fetch(url, { ...init, signal: AbortSignal.any([operationBudget, deadline]) });
      },
    });
  });
}

/**
 * Client-host telephony routes using npm @awaazlabs-uva/telephony.
 * Telnyx API key stays on the backend (.env) — never sent to the browser.
 */
export function mountTelephonyRoutes(app, config) {
  app.get('/api/telephony/status', async (_req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const [connectionResult, readinessResult] = await Promise.allSettled([
        telephony.getConnectionStatus(), telephony.getOutboundReadiness(),
      ]);
      const connection = connectionResult.status === 'fulfilled' ? connectionResult.value : null;
      const connectionError = connectionResult.status === 'rejected'
        ? (connectionResult.reason instanceof Error ? connectionResult.reason.message : String(connectionResult.reason)) : null;
      const readiness = readinessResult.status === 'fulfilled' ? readinessResult.value
        : { error: readinessResult.reason instanceof Error ? readinessResult.reason.message : String(readinessResult.reason) };
      res.json({
        tenantId: config.tenantId,
        telnyxKeyConfigured: Boolean(config.telnyxApiKey),
        connection,
        connectionError,
        readiness,
      });
    } catch (err) {
      sendError(res, err, 'telephony_status_failed');
    }
  });

  app.post('/api/telephony/connect', async (_req, res) => {
    try {
      if (!config.telnyxApiKey) {
        res.status(400).json({
          error: 'telnyx_key_missing',
          message: 'Set TELNYX_API_KEY in backend/.env',
        });
        return;
      }
      const telephony = await createTelephonyClient(config);
      let connection;
      try {
        connection = await telephony.connectTelnyxAccount({
          apiKey: config.telnyxApiKey,
          label: 'client-integration-test',
        });
      } catch (err) {
        // Already connected / rotation path: try rotate then status.
        const message = err instanceof Error ? err.message : String(err);
        if (/already|exist|connected|active/i.test(message) || Number(err?.status) === 409) {
          try {
            connection = await telephony.rotateTelnyxAccountKey({
              apiKey: config.telnyxApiKey,
            });
          } catch {
            connection = await telephony.getConnectionStatus();
          }
        } else {
          throw err;
        }
      }
      res.json({ connection });
    } catch (err) {
      sendError(res, err, 'telephony_connect_failed');
    }
  });

  app.post('/api/telephony/sync', async (_req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const sync = await telephony.syncTelnyxOwnedNumbers();
      const managed = await telephony.listManagedPhoneNumbers();
      const owned = await telephony.listTelnyxOwnedNumbers();
      res.json({
        sync,
        managed: asList(managed),
        owned: asList(owned),
      });
    } catch (err) {
      sendError(res, err, 'telephony_sync_failed');
    }
  });

  app.get('/api/telephony/numbers', async (_req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const [managed, owned] = await Promise.all([
        telephony.listManagedPhoneNumbers(),
        telephony.listTelnyxOwnedNumbers().catch(() => []),
      ]);
      res.json({
        managed: asList(managed),
        owned: asList(owned),
      });
    } catch (err) {
      sendError(res, err, 'telephony_list_failed');
    }
  });

  app.get('/api/telephony/search', async (req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const country = String(req.query.country || 'US').trim().toUpperCase();
      const areaCode = String(req.query.areaCode || '').trim() || undefined;
      const numberType = String(req.query.numberType || '').trim() || undefined;
      const results = await telephony.searchAvailableNumbers({
        country,
        areaCode,
        numberType,
      });
      res.json({ numbers: Array.isArray(results) ? results : asList(results) });
    } catch (err) {
      sendError(res, err, 'telephony_search_failed');
    }
  });

  app.post('/api/telephony/purchase', async (req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const e164Number = String(req.body?.e164Number || '').trim();
      if (!e164Number) {
        res.status(400).json({ error: 'e164_required' });
        return;
      }
      const idempotencyKey = String(req.body?.idempotencyKey || randomUUID());
      const order = await telephony.purchaseNumber({
        e164Number,
        idempotencyKey,
      });
      // Best-effort sync after purchase so UI can assign immediately.
      try {
        await telephony.syncTelnyxOwnedNumbers();
      } catch {
        /* ignore */
      }
      const managed = asList(await telephony.listManagedPhoneNumbers());
      res.status(201).json({ order, managed });
    } catch (err) {
      sendError(res, err, 'telephony_purchase_failed');
    }
  });

  app.post('/api/telephony/import', async (req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const e164Number = String(req.body?.e164Number || '').trim();
      if (!e164Number) {
        res.status(400).json({ error: 'e164_required' });
        return;
      }
      const existing = asList(await telephony.listManagedPhoneNumbers());
      const alreadyManaged = existing.find(number => number.e164_number === e164Number);
      if (alreadyManaged) {
        res.json({ imported: alreadyManaged, managed: existing, alreadyManaged: true });
        return;
      }
      const imported = await telephony.importTelnyxNumber({ e164Number });
      const managed = asList(await telephony.listManagedPhoneNumbers());
      res.json({ imported, managed });
    } catch (err) {
      sendError(res, err, 'telephony_import_failed');
    }
  });

  app.post('/api/telephony/assign', async (req, res) => {
    let telephony;
    const numberId = String(req.body?.numberId || '').trim();
    const agentId = String(req.body?.agentId || '').trim();
    try {
      if (!numberId || !agentId) {
        res.status(400).json({ error: 'numberId_and_agentId_required' });
        return;
      }
      telephony = await createTelephonyClient(config);
      const current = await telephony.getManagedPhoneNumber(numberId);
      // The public assignment operation already binds Telnyx and configures
      // LiveKit routing. Do not provision the same route twice on every click.
      const assigned = current.assigned_agent_id === agentId && current.routing_status === 'ready'
        ? current : await telephony.assignAgentToNumber(numberId, agentId);
      if (assigned.assigned_agent_id !== agentId || assigned.routing_status !== 'ready') {
        const err = new Error('Agent assignment is saved, but phone routing is not ready. Refresh the lists and resolve routing before calling.');
        err.status = 409;
        err.code = 'number_not_routing_ready';
        throw err;
      }
      res.json({ assigned, routing: { routing_status: 'ready' } });
    } catch (err) {
      // Assignment can commit before provider routing fails. Return verified
      // partial state instead of claiming rollback or swallowing routing errors.
      let current = null;
      if (telephony) {
        try { current = await telephony.getManagedPhoneNumber(numberId); } catch { /* outcome remains unknown */ }
      }
      const status = Number(err?.status || 502);
      res.status(status >= 400 && status < 600 ? status : 502).json({
        error: err?.code || 'telephony_assign_failed',
        message: err instanceof Error ? err.message : String(err),
        assignmentSaved: current ? current.assigned_agent_id === agentId : null,
        routingStatus: current?.routing_status || 'unknown',
      });
    }
  });

  app.post('/api/telephony/prepare-outbound', async (_req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const steps = {};
      try {
        steps.outboundTrunk = await telephony.configureOutboundTrunk();
      } catch (err) {
        steps.outboundTrunk = { error: err instanceof Error ? err.message : String(err) };
      }
      if (config.telnyxSipFqdn || config.telnyxSipUsername || config.telnyxSipSecret) {
        try {
          steps.sip = await telephony.upsertTelnyxSipConnection({
            sipFqdn: config.telnyxSipFqdn || undefined,
            sipUsername: config.telnyxSipUsername || undefined,
            sipSecret: config.telnyxSipSecret || undefined,
          });
        } catch (err) {
          steps.sip = { error: err instanceof Error ? err.message : String(err) };
        }
      }
      try {
        const allowed = (config.telnyxOutboundAllowedDestinations || 'US')
          .split(',')
          .map((v) => v.trim())
          .filter(Boolean);
        steps.outboundProfile = await telephony.upsertTelnyxOutboundVoiceProfile({
          allowedDestinations: allowed,
        });
      } catch (err) {
        steps.outboundProfile = { error: err instanceof Error ? err.message : String(err) };
      }
      const readiness = await telephony.getOutboundReadiness();
      res.json({ steps, readiness });
    } catch (err) {
      sendError(res, err, 'telephony_prepare_failed');
    }
  });

  app.post('/api/telephony/outbound', async (req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const agentId = String(req.body?.agentId || '').trim();
      const fromNumberId = String(req.body?.fromNumberId || '').trim();
      const toNumber = String(req.body?.toNumber || '').trim();
      if (!agentId || !fromNumberId || !toNumber) {
        res.status(400).json({ error: 'agentId_fromNumberId_toNumber_required' });
        return;
      }
      const idempotencyKey = String(req.body?.idempotencyKey || randomUUID());
      const call = await telephony.createOutboundCall({
        agentId,
        fromNumberId,
        toNumber,
        idempotencyKey,
      });
      res.status(201).json({ call });
    } catch (err) {
      sendError(res, err, 'telephony_outbound_failed');
    }
  });

  app.get('/api/telephony/calls/:callId', async (req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const callId = String(req.params.callId || '').trim();
      const status = await telephony.getCallStatus(callId);
      res.json({ status });
    } catch (err) {
      sendError(res, err, 'telephony_call_status_failed');
    }
  });

  app.get('/api/telephony/calls', async (_req, res) => {
    try {
      const telephony = await createTelephonyClient(config);
      const records = await telephony.listCallRecords({ limit: 20 });
      res.json({ calls: asList(records) });
    } catch (err) {
      sendError(res, err, 'telephony_calls_failed');
    }
  });
}
