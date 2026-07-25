import express from 'express';
import { createControlPlaneHeaders } from './signing.js';

function readJsonSafely(response) {
  return response.text().then((text) => {
    if (!text) {
      return null;
    }
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
  const detail = String(payload?.detail || payload?.error || '').toLowerCase();
  if (upstreamStatus === 429) {
    return { status: 429, body: { error: 'quota_exceeded' } };
  }
  if (upstreamStatus === 404 || detail.includes('agent') || detail.includes('not found')) {
    return { status: 404, body: { error: 'agent_not_found' } };
  }
  return { status: 502, body: { error: 'session_failed' } };
}

function addCorsHeaders(res, origin, config) {
  if (!origin) {
    return;
  }
  if (config.allowedOrigins.length === 0 || config.allowedOrigins.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
  }
}

export function createApp(config, fetchImpl = fetch) {
  const app = express();
  app.use(express.json());

  app.use((req, res, next) => {
    const origin = req.get('origin');
    addCorsHeaders(res, origin, config);
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    if (req.method === 'OPTIONS') {
      res.status(204).end();
      return;
    }
    next();
  });

  app.get('/healthz', (_req, res) => {
    res.json({ status: 'ok', service: 'uva-host-backend-starter' });
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

    const upstream = await fetchImpl(`${config.sessionUpstreamUrl}/v1/session`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ agent_id: agentId }),
    });

    const payload = await readJsonSafely(upstream);
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

    const upstream = await fetchImpl(`${config.sessionUpstreamUrl}/v1/session/refresh`, {
      method: 'POST',
      headers,
      body: bearer?.startsWith('Bearer ') ? undefined : JSON.stringify({ token }),
    });

    const payload = await readJsonSafely(upstream);
    if (!upstream.ok || !payload?.token || !payload?.wsUrl || !payload?.roomName) {
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

  return app;
}
