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

function normalizeSessionFailure(upstreamStatus, payload) {
  const detail = String(payload?.detail || payload?.error || payload?.code || '');
  const lower = detail.toLowerCase();

  if (upstreamStatus === 429) {
    return {
      status: 429,
      body: { error: detail || 'quota_exceeded' },
    };
  }
  if (upstreamStatus === 404 || lower.includes('agent') || lower.includes('not found')) {
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

/**
 * @param {object} config
 * @param {{ fetchImpl?: typeof fetch }} [options]
 */
export function createApp(config, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const app = express();
  app.use(express.json({ limit: '32kb' }));

  app.use((req, res, next) => {
    const origin = req.get('origin');
    addCorsHeaders(res, origin, config);
    if (req.method === 'OPTIONS') {
      res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
      res.setHeader(
        'Access-Control-Allow-Headers',
        'Content-Type, Authorization',
      );
      res.status(204).end();
      return;
    }
    next();
  });

  app.get('/healthz', (_req, res) => {
    res.json({ ok: true });
  });

  app.post('/api/voice/session', async (req, res) => {
    const { publishableKey, agentId } = req.body ?? {};
    if (!publishableKey || !agentId) {
      res.status(400).json({ error: 'publishableKey and agentId are required' });
      return;
    }
    if (publishableKey !== config.publishableKey) {
      res.status(401).json({ error: 'unknown publishable key' });
      return;
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
