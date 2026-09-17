import express from 'express';
import { createControlPlaneHeaders } from './signing.js';

function readJsonSafely(response) {
  return response.text().then((text) => {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return { raw: text };
    }
  });
}

function resolveRefreshUrl(req, config) {
  if (config.publicBaseUrl) {
    return `${config.publicBaseUrl}/api/voice/session/refresh`;
  }
  return `${req.protocol}://${req.get('host')}/api/voice/session/refresh`;
}

/**
 * Map upstream failures to browser-safe statuses.
 * For 429, forward the upstream signal so the voice SDK (F-M16) can distinguish
 * rate_limit vs quota_exceeded when the control plane returns distinct text.
 */
function normalizeSessionFailure(upstreamStatus, payload) {
  const detail = String(payload?.detail || payload?.error || payload?.code || '');
  const lower = detail.toLowerCase();

  if (upstreamStatus === 429) {
    return {
      status: 429,
      body: { error: detail || 'quota_exceeded' },
    };
  }
  if (
    upstreamStatus === 404 ||
    lower.includes('agent') ||
    lower.includes('not found')
  ) {
    return { status: 404, body: { error: 'agent_not_found' } };
  }
  if (lower.includes('worker_not_ready') || lower.includes('worker not ready')) {
    return { status: 503, body: { error: detail || 'worker_not_ready' } };
  }
  if (lower.includes('provider_limit') || lower.includes('provider limit')) {
    return { status: 429, body: { error: detail || 'provider_limit' } };
  }
  return { status: 502, body: { error: 'session_failed', detail: detail || undefined } };
}

function addCorsHeaders(res, origin, config) {
  if (!origin) return;
  if (config.allowedOrigins.length === 0 || config.allowedOrigins.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
  }
}

async function createAgentsClient(config) {
  if (!config.portalApiUrl) {
    const err = new Error('UVA_API_BASE_URL not set — provider picker requires tenant portal API');
    err.code = 'portal_not_configured';
    throw err;
  }
  const { AwaazLabsUvaAgentsClient } = await import('@awaazlabs-uva/agents');
  return new AwaazLabsUvaAgentsClient({
    baseUrl: config.portalApiUrl,
    tenantId: config.tenantId,
    tenantSecret: config.hmacSecret,
  });
}

function pickDefaultModel(entry) {
  if (!entry) return undefined;
  if (entry.defaultModel) return entry.defaultModel;
  if (Array.isArray(entry.models) && entry.models.length > 0) return entry.models[0];
  return undefined;
}

function pickDefaultVoice(entry) {
  if (!entry) return undefined;
  if (entry.defaultVoice) return entry.defaultVoice;
  if (Array.isArray(entry.voices) && entry.voices.length > 0) return entry.voices[0];
  return undefined;
}

/** Process-local capabilities cache — avoids a portal round-trip on every Connect. */
let _capsCache = { at: 0, value: null };
const CAPS_TTL_MS = 60_000;

async function getCapabilitiesCached(client) {
  const now = Date.now();
  if (_capsCache.value && now - _capsCache.at < CAPS_TTL_MS) {
    return _capsCache.value;
  }
  const capabilities = await client.getProviderCapabilities();
  _capsCache = { at: now, value: capabilities };
  return capabilities;
}

function agentPipelineMatches(agent, applied) {
  if (!agent || !applied) return false;
  const lang = agent.agent_language || agent.agentLanguage;
  const stt = agent.stt_provider || agent.sttProvider;
  const llm = agent.llm_provider || agent.llmProvider;
  const tts = agent.tts_provider || agent.ttsProvider;
  const sttModel = agent.stt_model || agent.sttModel;
  const llmModel = agent.llm_model || agent.llmModel;
  const voice = agent.tts_voice_id || agent.ttsVoiceId || agent.voice_id || agent.voiceId;
  return (
    lang === applied.agentLanguage &&
    stt === applied.sttProvider &&
    llm === applied.llmProvider &&
    tts === applied.ttsProvider &&
    (!applied.sttModel || sttModel === applied.sttModel) &&
    (!applied.llmModel || llmModel === applied.llmModel) &&
    (!applied.ttsVoiceId || voice === applied.ttsVoiceId)
  );
}

/**
 * Resolve language/STT/LLM/TTS against live capabilities and PATCH the agent
 * so the next mint/worker session uses that pipeline.
 * Skips the portal PATCH when the agent already matches (demo Connect hot path).
 */
async function applyPipelineSelection(client, agentId, selection, { force = false } = {}) {
  const language = String(selection.agentLanguage || '').trim();
  const sttProvider = String(selection.sttProvider || '').trim();
  const llmProvider = String(selection.llmProvider || '').trim();
  const ttsProvider = String(selection.ttsProvider || '').trim();

  if (!language || !sttProvider || !llmProvider || !ttsProvider) {
    const err = new Error('agentLanguage, sttProvider, llmProvider, and ttsProvider are required');
    err.code = 'pipeline_incomplete';
    throw err;
  }

  const caps = await getCapabilitiesCached(client);
  const langCaps = caps?.languages?.[language];
  if (!langCaps) {
    const err = new Error(`language ${language} is not enabled`);
    err.code = 'unsupported_language';
    throw err;
  }

  const sttEntry = langCaps.stt?.[sttProvider];
  const llmEntry = langCaps.llm?.[llmProvider];
  const ttsEntry = langCaps.tts?.[ttsProvider];
  if (!sttEntry) {
    const err = new Error(`STT ${sttProvider} is not enabled for ${language}`);
    err.code = 'unsupported_stt';
    throw err;
  }
  if (!llmEntry) {
    const err = new Error(`LLM ${llmProvider} is not enabled for ${language}`);
    err.code = 'unsupported_llm';
    throw err;
  }
  if (!ttsEntry) {
    const err = new Error(`TTS ${ttsProvider} is not enabled for ${language}`);
    err.code = 'unsupported_tts';
    throw err;
  }

  const sttModel =
    String(selection.sttModel || '').trim() || pickDefaultModel(sttEntry) || 'default';
  const llmModel =
    String(selection.llmModel || '').trim() || pickDefaultModel(llmEntry);
  const ttsVoiceId =
    String(selection.ttsVoiceId || '').trim() || pickDefaultVoice(ttsEntry);

  if (!llmModel) {
    const err = new Error(`no default model for LLM ${llmProvider}/${language}`);
    err.code = 'missing_llm_model';
    throw err;
  }
  if (!ttsVoiceId) {
    const err = new Error(
      `no enabled voice for TTS ${ttsProvider}/${language} — seed voices or pick another TTS`,
    );
    err.code = 'missing_tts_voice';
    throw err;
  }

  if (Array.isArray(sttEntry.models) && sttEntry.models.length > 0 && !sttEntry.models.includes(sttModel)) {
    const err = new Error(`STT model ${sttModel} is not valid for ${sttProvider}`);
    err.code = 'unsupported_stt_model';
    throw err;
  }
  if (Array.isArray(llmEntry.models) && !llmEntry.models.includes(llmModel)) {
    const err = new Error(`LLM model ${llmModel} is not valid for ${llmProvider}`);
    err.code = 'unsupported_llm_model';
    throw err;
  }
  if (Array.isArray(ttsEntry.voices) && !ttsEntry.voices.includes(ttsVoiceId)) {
    const err = new Error(`voice ${ttsVoiceId} is not valid for ${ttsProvider}/${language}`);
    err.code = 'unsupported_voice';
    throw err;
  }

  const applied = {
    agentLanguage: language,
    sttProvider,
    sttModel,
    llmProvider,
    llmModel,
    ttsProvider,
    ttsVoiceId,
  };

  if (!force) {
    try {
      const agents = await client.listAgents();
      const current = Array.isArray(agents)
        ? agents.find((a) => a.id === agentId || a.agent_id === agentId)
        : null;
      if (agentPipelineMatches(current, applied)) {
        return { agent: current, applied, skipped: true };
      }
    } catch {
      // Fall through to PATCH if list fails.
    }
  }

  const agent = await client.updateAgent(agentId, {
    agentLanguage: language,
    sttProvider,
    sttModel,
    llmProvider,
    llmModel,
    ttsProvider,
    ttsVoiceId,
    voiceId: ttsVoiceId,
  });

  return {
    agent,
    applied,
    skipped: false,
  };
}

export function createApp(config, fetchImpl = fetch) {
  const app = express();
  app.use(express.json());

  app.use((req, res, next) => {
    const origin = req.get('origin');
    addCorsHeaders(res, origin, config);
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    if (req.method === 'OPTIONS') {
      res.status(204).end();
      return;
    }
    next();
  });

  app.get('/healthz', (_req, res) => {
    res.json({ status: 'ok', service: 'uva-demo-backend' });
  });

  /** Never responds — use as sessionEndpoint to smoke-test F-M14 timeout (~15s). */
  app.post('/api/demo/hang', (_req, _res) => {
    // Intentionally leave the request open until the client aborts.
  });

  app.get('/api/demo/config', (_req, res) => {
    res.json({
      publishableKey: config.publishableKey,
      tenantId: config.tenantId,
      hasPortalApi: Boolean(config.portalApiUrl),
    });
  });

  app.get('/api/provider-capabilities', async (_req, res) => {
    try {
      const client = await createAgentsClient(config);
      const capabilities = await client.getProviderCapabilities();
      res.json(capabilities);
    } catch (err) {
      const status = err?.code === 'portal_not_configured' ? 501 : 502;
      res.status(status).json({
        error: err?.code || 'capabilities_failed',
        message: err instanceof Error ? err.message : String(err),
      });
    }
  });

  app.get('/api/agents', async (_req, res) => {
    try {
      const client = await createAgentsClient(config);
      const agents = await client.listAgents();
      res.json({ agents });
    } catch (err) {
      const status = err?.code === 'portal_not_configured' ? 501 : 502;
      res.status(status).json({
        error: err?.code || 'list_agents_failed',
        message: err instanceof Error ? err.message : String(err),
      });
    }
  });

  /** Apply language/STT/LLM/TTS to the agent before the browser SDK mints a session. */
  app.post('/api/agents/:agentId/pipeline', async (req, res) => {
    const agentId = String(req.params.agentId || '').trim();
    if (!agentId) {
      res.status(400).json({ error: 'agentId is required' });
      return;
    }
    try {
      const result = await applyPipelineSelection(await createAgentsClient(config), agentId, req.body ?? {});
      res.json(result);
    } catch (err) {
      const status =
        err?.code === 'portal_not_configured'
          ? 501
          : err?.code === 'pipeline_incomplete'
            ? 400
            : 422;
      res.status(status).json({
        error: err?.code || 'pipeline_update_failed',
        message: err instanceof Error ? err.message : String(err),
      });
    }
  });

  app.post('/api/voice/session', async (req, res) => {
    const {
      publishableKey,
      agentId,
      agentLanguage,
      sttProvider,
      llmProvider,
      ttsProvider,
      sttModel,
      llmModel,
      ttsVoiceId,
    } = req.body ?? {};
    if (!publishableKey || !agentId) {
      res.status(400).json({ error: 'publishableKey and agentId are required' });
      return;
    }
    if (publishableKey !== config.publishableKey) {
      res.status(401).json({ error: 'unknown publishable key' });
      return;
    }

    const wantsPipeline =
      agentLanguage || sttProvider || llmProvider || ttsProvider || sttModel || llmModel || ttsVoiceId;
    if (wantsPipeline) {
      try {
        await applyPipelineSelection(await createAgentsClient(config), agentId, {
          agentLanguage,
          sttProvider,
          llmProvider,
          ttsProvider,
          sttModel,
          llmModel,
          ttsVoiceId,
        });
      } catch (err) {
        const status =
          err?.code === 'portal_not_configured'
            ? 501
            : err?.code === 'pipeline_incomplete'
              ? 400
              : 422;
        res.status(status).json({
          error: err?.code || 'pipeline_update_failed',
          message: err instanceof Error ? err.message : String(err),
        });
        return;
      }
    }

    const headers = createControlPlaneHeaders({
      tenantId: config.tenantId,
      agentId,
      secret: config.hmacSecret,
      origin: req.get('origin'),
    });

    let upstream;
    let payload;
    try {
      upstream = await fetchImpl(`${config.controlPlaneUrl}/v1/session`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ agent_id: agentId }),
      });
      payload = await readJsonSafely(upstream);
    } catch (err) {
      res.status(502).json({
        error: 'session_failed',
        detail: `control plane unreachable at ${config.controlPlaneUrl}`,
        cause: err instanceof Error ? err.message : String(err),
      });
      return;
    }

    if (!upstream.ok) {
      const failure = normalizeSessionFailure(upstream.status, payload);
      res.status(failure.status).json(failure.body);
      return;
    }

    if (!payload?.token || !payload?.wsUrl || !payload?.roomName) {
      res.status(502).json({ error: 'session_failed' });
      return;
    }

    res.json({
      token: payload.token,
      wsUrl: payload.wsUrl,
      roomName: payload.roomName,
      refreshUrl: resolveRefreshUrl(req, config),
      expiresIn: payload.expiresIn ?? 120,
    });
  });

  app.post('/api/voice/session/refresh', async (req, res) => {
    const bearer = req.get('authorization');
    const bodyToken = req.body?.token;
    const token = bearer?.startsWith('Bearer ') ? bearer.slice(7).trim() : bodyToken;
    if (!token) {
      res.status(401).json({ error: 'missing bearer token' });
      return;
    }

    const headers = {};
    if (bearer?.startsWith('Bearer ')) {
      headers.Authorization = bearer;
    } else {
      headers['Content-Type'] = 'application/json';
    }

    let upstream;
    let payload;
    try {
      upstream = await fetchImpl(`${config.controlPlaneUrl}/v1/session/refresh`, {
        method: 'POST',
        headers,
        body: bearer?.startsWith('Bearer ') ? undefined : JSON.stringify({ token }),
      });
      payload = await readJsonSafely(upstream);
    } catch (err) {
      res.status(502).json({
        error: 'session_failed',
        detail: `control plane unreachable at ${config.controlPlaneUrl}`,
        cause: err instanceof Error ? err.message : String(err),
      });
      return;
    }

    if (!upstream.ok || !payload?.token || !payload?.wsUrl || !payload?.roomName) {
      const detail = String(payload?.detail || payload?.error || '');
      res.status(upstream.status === 401 || upstream.status === 403 ? upstream.status : 502).json({
        error: 'session_failed',
        detail: detail || undefined,
      });
      return;
    }

    res.json({
      token: payload.token,
      wsUrl: payload.wsUrl,
      roomName: payload.roomName,
      refreshUrl: resolveRefreshUrl(req, config),
      expiresIn: payload.expiresIn ?? 120,
    });
  });

  return app;
}

export { applyPipelineSelection };
