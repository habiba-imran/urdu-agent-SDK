/**
 * UVA Client Test App — Express Backend
 *
 * Acts as a real client integration. Uses:
 *   @awaazlabs-uva/agents   — createAgent, listAgents, updateAgent
 *   @awaazlabs-uva/telephony — full telephony lifecycle
 *
 * All secrets (Tenant ID, HMAC Secret, Telnyx API Key) stay here.
 * The frontend only calls this local server on port 3001.
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';
import express from 'express';
import cors from 'cors';
import { randomUUID, createHmac, createHash } from 'crypto';
import { AwaazLabsUvaAgentsClient, AwaazLabsUvaAgentsError } from '@awaazlabs-uva/agents';
import { TelephonyClient, AwaazLabsUvaTelephonyError } from '@awaazlabs-uva/telephony';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.join(__dirname, '.env') });

function csv(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

// ─── Runtime config (can be overridden via POST /api/config) ────────────────
let config = {
  apiBaseUrl: process.env.UVA_API_BASE_URL || 'http://localhost:8000',
  telephonyApiUrl: process.env.UVA_TELEPHONY_API_URL || 'http://localhost:8000',
  sessionUpstreamUrl: process.env.UVA_SESSION_UPSTREAM_URL || process.env.UVA_API_BASE_URL || 'http://localhost:7860',
  publicBaseUrl: process.env.PUBLIC_BASE_URL || '',
  publishableKey: process.env.UVA_PUBLISHABLE_KEY || '',
  allowedOrigins: csv(process.env.ALLOWED_ORIGINS || 'http://localhost:3000'),
  tenantId: process.env.UVA_TENANT_ID || '',
  hmacSecret: process.env.UVA_HMAC_SECRET || '',
  telnyxApiKey: '',  // entered at runtime only - never in .env
  allowPaidTelephonyActions: process.env.ALLOW_PAID_TELEPHONY_ACTIONS === '1',
};

const app = express();
app.use(cors({
  origin(origin, cb) {
    const allowed = !origin || config.allowedOrigins.length === 0 || config.allowedOrigins.includes(origin);
    cb(null, allowed);
  },
}));
app.use(express.json());

// ─── SDK client factory helpers ─────────────────────────────────────────────
function getAgentsClient() {
  if (!config.tenantId || !config.hmacSecret) {
    throw new Error('Tenant ID and HMAC Secret are required. Configure them via POST /api/config or backend/.env.');
  }
  return new AwaazLabsUvaAgentsClient({
    baseUrl: config.apiBaseUrl,
    tenantId: config.tenantId,
    tenantSecret: config.hmacSecret,
  });
}

function getTelephonyClient() {
  if (!config.tenantId || !config.hmacSecret) {
    throw new Error('Tenant ID and HMAC Secret are required. Configure them via POST /api/config or backend/.env.');
  }
  return new TelephonyClient({
    baseUrl: config.telephonyApiUrl,
    tenantId: config.tenantId,
    tenantSecret: config.hmacSecret,
  });
}

function createControlPlaneHeaders(tenantId, secret, agentId) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID();
  const signature = createHmac('sha256', secret)
    .update(`${tenantId}.${timestamp}.${nonce}.${agentId}`)
    .digest('hex');

  return {
    'Content-Type': 'application/json',
    'X-Tenant-Id': tenantId,
    'X-Timestamp': timestamp,
    'X-Nonce': nonce,
    'X-Signature': signature,
  };
}

function canonicalJson(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
}

function createMachineHeaders(action, body = {}) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID();
  const payloadHash = createHash('sha256').update(canonicalJson(body)).digest('hex');
  const signature = createHmac('sha256', config.hmacSecret)
    .update(`${config.tenantId}.${timestamp}.${nonce}.${action}.${payloadHash}`)
    .digest('hex');

  return {
    'Content-Type': 'application/json',
    'X-Tenant-Id': config.tenantId,
    'X-Timestamp': timestamp,
    'X-Nonce': nonce,
    'X-Signature': signature,
  };
}

async function readJsonSafely(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function normalizeSessionFailure(upstreamStatus, payload) {
  const detail = String(payload?.detail || payload?.error || '').toLowerCase();
  if (upstreamStatus === 429) return { status: 429, body: { error: 'quota_exceeded' } };
  if (upstreamStatus === 404 || detail.includes('agent') || detail.includes('not found')) {
    return { status: 404, body: { error: 'agent_not_found' } };
  }
  return { status: 502, body: { error: 'session_failed' } };
}

function resolveRefreshUrl(req) {
  if (config.publicBaseUrl) return `${config.publicBaseUrl.replace(/\/$/, '')}/api/voice/session/refresh`;
  return `${req.protocol}://${req.get('host')}/api/voice/session/refresh`;
}

function requirePaidTelephonyActions(res) {
  if (config.allowPaidTelephonyActions) return false;
  res.status(403).json({
    ok: false,
    code: 'paid_action_disabled',
    message: 'Set ALLOW_PAID_TELEPHONY_ACTIONS=1 in backend/.env before purchase or outbound-call tests.',
  });
  return true;
}

function normalizeCollection(result, fallbackKeys = []) {
  if (Array.isArray(result)) return result;
  for (const key of fallbackKeys) {
    if (Array.isArray(result?.[key])) return result[key];
  }
  return [];
}

async function listManagedNumbers() {
  const telephony = getTelephonyClient();
  const result = await telephony.listManagedPhoneNumbers();
  return normalizeCollection(result, ['data', 'numbers', 'items']);
}

async function recoverAlreadyOwnedNumber(e164Number) {
  const telephony = getTelephonyClient();

  try {
    const imported = await telephony.importTelnyxNumber({ e164Number });
    return {
      recovered: true,
      source: 'import',
      managedNumber: imported,
    };
  } catch {
    // Ignore and fall through to sync/list checks below.
  }

  try {
    await telephony.syncTelnyxOwnedNumbers();
  } catch {
    // Sync can fail for transient reasons; still try current managed inventory.
  }

  const managedNumbers = await listManagedNumbers();
  const managedNumber = managedNumbers.find((item) => item?.e164_number === e164Number) || null;
  if (managedNumber) {
    return {
      recovered: true,
      source: 'managed_inventory',
      managedNumber,
    };
  }

  return {
    recovered: false,
    source: null,
    managedNumber: null,
  };
}

async function listAgents() {
  const agents = getAgentsClient();
  const result = await agents.listAgents();
  return normalizeCollection(result, ['agents', 'data', 'items']);
}

function toSnakeCaseValue(value) {
  if (value === null || value === undefined || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map((item) => toSnakeCaseValue(item));
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`),
      toSnakeCaseValue(item),
    ]),
  );
}

function previewText(value, limit = 360) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function detectResponseKind(contentType, text) {
  const normalizedType = String(contentType || '').toLowerCase();
  const trimmed = String(text || '').trim().toLowerCase();
  if (normalizedType.includes('application/json')) return 'json';
  if (trimmed.startsWith('<!doctype') || trimmed.startsWith('<html')) return 'html';
  if (!trimmed) return 'empty';
  return 'text';
}

function inferLikelyCauses({ responseKind, status, payloadPreview, parsedBody }) {
  const hints = [];
  const detailText = JSON.stringify(parsedBody || payloadPreview || '').toLowerCase();
  if (responseKind === 'html' && status === 502) {
    hints.push('The hosted telephony API or its upstream service returned an HTML 502 page.');
  }
  if (detailText.includes('insufficient') || detailText.includes('balance')) {
    hints.push('The upstream response mentions balance or insufficient funds.');
  }
  if (detailText.includes('verified number') || detailText.includes('trial')) {
    hints.push('The upstream response mentions trial-account or verified-number restrictions.');
  }
  if (detailText.includes('caller') || detailText.includes('origination') || detailText.includes('d35')) {
    hints.push('The upstream response suggests caller ID / origination number validation failed.');
  }
  if (detailText.includes('livekit') || detailText.includes('sip')) {
    hints.push('The upstream response points at LiveKit or SIP setup.');
  }
  if (!hints.length) {
    hints.push('No structured provider error was returned; inspect the hosted telephony API logs for the same timestamp.');
  }
  return hints;
}

async function probeTelephonyUpstream({ action, path, body = {}, method = 'POST' }) {
  const url = `${config.telephonyApiUrl.replace(/\/$/, '')}${path}`;
  const response = await fetch(url, {
    method,
    headers: createMachineHeaders(action, body),
    body: method === 'GET' ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  const contentType = response.headers.get('content-type') || '';
  let parsedBody = null;
  try {
    parsedBody = text ? JSON.parse(text) : null;
  } catch {
    parsedBody = null;
  }
  const payloadPreview = previewText(text);
  const responseKind = detectResponseKind(contentType, text);
  return {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    url,
    contentType,
    responseKind,
    payloadPreview,
    parsedBody,
    likelyCauses: inferLikelyCauses({ responseKind, status: response.status, payloadPreview, parsedBody }),
  };
}

async function collectTelephonyDiagnostics({ fromNumberId = '', requestedAgentId = '', toNumber = '' }) {
  const [numbers, agents, readiness, connectionProbe] = await Promise.all([
    listManagedNumbers(),
    listAgents(),
    getTelephonyClient().getOutboundReadiness().catch((error) => ({
      ok: false,
      error: error?.message || String(error),
      code: error?.code || null,
    })),
    probeTelephonyUpstream({
      action: 'telephony.telnyx_connection.status',
      path: '/machine/telephony/telnyx/connection',
      body: {},
      method: 'GET',
    }).catch((error) => ({
      ok: false,
      status: 0,
      statusText: 'probe_failed',
      responseKind: 'text',
      payloadPreview: previewText(error?.message || String(error)),
      parsedBody: null,
      likelyCauses: ['The local backend could not complete a signed probe to the telephony API.'],
    })),
  ]);

  const selectedNumber = numbers.find((item) => item.id === fromNumberId) || null;
  const assignedAgent = selectedNumber
    ? agents.find((item) => item.id === selectedNumber.assigned_agent_id) || null
    : null;

  return {
    telephonyApiUrl: config.telephonyApiUrl,
    paidTelephonyActionsEnabled: config.allowPaidTelephonyActions,
    readiness,
    connectionProbe,
    requested: {
      fromNumberId,
      requestedAgentId,
      toNumber,
    },
    selectedNumber: selectedNumber
      ? {
          id: selectedNumber.id,
          e164Number: selectedNumber.e164_number || selectedNumber.phone_number || null,
          assignedAgentId: selectedNumber.assigned_agent_id || null,
          routingStatus: selectedNumber.routing_status || null,
          provisioningStatus: selectedNumber.provisioning_status || null,
        }
      : null,
    assignedAgent: assignedAgent
      ? {
          id: assignedAgent.id,
          name: assignedAgent.name || null,
        }
      : null,
    notes: [
      'Inbound simulation only proves assignment and routing state inside the platform.',
      'Real PSTN inbound/outbound still depends on the hosted telephony API, LiveKit, and Telnyx provider behavior.',
      'Trial-account or verified-number restrictions can only be confirmed when the upstream provider returns a structured error.',
    ],
  };
}

// ─── Error helpers ───────────────────────────────────────────────────────────
function handleError(res, error) {
  console.error('[UVA Test App Error]', error?.message || error);
  if (error instanceof AwaazLabsUvaTelephonyError) {
    const signatureMessage = String(error.message || '').toLowerCase().includes('bad signature')
      ? 'Bad signature: the Tenant ID and HMAC Secret loaded in this local backend do not match the target API.'
      : error.message;
    const providerMessage = typeof error.detail?.provider_message === 'string'
      ? error.detail.provider_message
      : '';
    const message = providerMessage && !signatureMessage.includes(providerMessage)
      ? `${signatureMessage} Telnyx said: ${providerMessage}`
      : signatureMessage;
    return res.status(error.status || 500).json({
      ok: false,
      code: error.code,
      message,
      detail: error.detail,
    });
  }
  if (error instanceof AwaazLabsUvaAgentsError) {
    return res.status(error.status || 500).json({
      ok: false,
      code: 'agents_request_failed',
      message: error.message,
    });
  }
  const status = error?.status || 500;
  return res.status(status).json({
    ok: false,
    message: error?.message || 'Internal server error',
  });
}

// ────────────────────────────────────────────────────────────────────────────
// HEALTH
// ────────────────────────────────────────────────────────────────────────────
app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    service: 'uva-client-test-app-backend',
    configuredTenantId: config.tenantId ? `${config.tenantId.slice(0, 8)}...` : '(not set)',
    apiBaseUrl: config.apiBaseUrl,
    telephonyApiUrl: config.telephonyApiUrl,
    sessionUpstreamUrl: config.sessionUpstreamUrl,
    paidTelephonyActionsEnabled: config.allowPaidTelephonyActions,
  });
});

// ────────────────────────────────────────────────────────────────────────────
// CONFIG
// ────────────────────────────────────────────────────────────────────────────
app.get('/api/config', (_req, res) => {
  res.json({
    apiBaseUrl: config.apiBaseUrl,
    telephonyApiUrl: config.telephonyApiUrl,
    sessionUpstreamUrl: config.sessionUpstreamUrl,
    tenantId: config.tenantId,
    allowedOrigins: config.allowedOrigins,
    hmacSecretSet: !!config.hmacSecret,
    telnyxApiKeySet: !!config.telnyxApiKey,
    publishableKeySet: !!config.publishableKey,
    paidTelephonyActionsEnabled: config.allowPaidTelephonyActions,
  });
});

app.post('/api/config', (req, res) => {
  const {
    apiBaseUrl,
    telephonyApiUrl,
    sessionUpstreamUrl,
    publishableKey,
    tenantId,
    hmacSecret,
    telnyxApiKey,
    allowPaidTelephonyActions,
  } = req.body;
  if (apiBaseUrl) config.apiBaseUrl = apiBaseUrl;
  if (telephonyApiUrl) config.telephonyApiUrl = telephonyApiUrl;
  if (sessionUpstreamUrl) config.sessionUpstreamUrl = sessionUpstreamUrl;
  if (publishableKey) config.publishableKey = publishableKey;
  if (tenantId) config.tenantId = tenantId;
  if (hmacSecret) config.hmacSecret = hmacSecret;
  if (telnyxApiKey) config.telnyxApiKey = telnyxApiKey;
  if (allowPaidTelephonyActions !== undefined) {
    config.allowPaidTelephonyActions = allowPaidTelephonyActions === true || allowPaidTelephonyActions === '1';
  }
  console.log('[Config] Updated:', {
    apiBaseUrl: config.apiBaseUrl,
    telephonyApiUrl: config.telephonyApiUrl,
    sessionUpstreamUrl: config.sessionUpstreamUrl,
    tenantId: config.tenantId ? `${config.tenantId.slice(0, 8)}...` : '(not set)',
    hmacSecretSet: !!config.hmacSecret,
    telnyxApiKeySet: !!config.telnyxApiKey,
    publishableKeySet: !!config.publishableKey,
    paidTelephonyActionsEnabled: config.allowPaidTelephonyActions,
  });
  res.json({ ok: true, message: 'Configuration saved (in-memory only).' });
});

// Provider capabilities
app.get('/api/capabilities', async (_req, res) => {
  try {
    if (!config.tenantId || !config.hmacSecret) {
      return res.status(401).json({ ok: false, message: 'Tenant ID and HMAC Secret are required.' });
    }
    const response = await fetch(`${config.apiBaseUrl.replace(/\/$/, '')}/machine/provider-capabilities`, {
      method: 'GET',
      headers: createMachineHeaders('provider_capabilities.get', {}),
    });
    const data = await readJsonSafely(response);
    if (!response.ok) {
      return res.status(response.status).json({ ok: false, message: data?.detail || data?.error || response.statusText });
    }
    return res.json(data);
  } catch (error) {
    handleError(res, error);
  }
});

// Agents
app.get('/api/agents', async (_req, res) => {
  try {
    const agents = getAgentsClient();
    const result = await agents.listAgents();
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/agents', async (req, res) => {
  try {
    const agents = getAgentsClient();
    const {
      name, prompt, voiceId, llmModel,
      agentLanguage, sttProvider, sttModel,
      llmProvider, ttsProvider, ttsVoiceId,
    } = req.body;

    if (!name || !prompt || !voiceId) {
      return res.status(400).json({ ok: false, message: 'name, prompt, and voiceId are required' });
    }

    const agent = await agents.createAgent({
      name,
      prompt,
      voiceId,
      llmModel: llmModel || 'gemini-2.5-flash',
      agentLanguage,
      sttProvider,
      sttModel,
      llmProvider,
      ttsProvider,
      ttsVoiceId,
    });
    res.json(agent);
  } catch (error) {
    handleError(res, error);
  }
});

app.patch('/api/agents/:agentId', async (req, res) => {
  try {
    const agents = getAgentsClient();
    const { agentId } = req.params;
    const {
      name, prompt, voiceId, llmModel,
      agentLanguage, sttProvider, sttModel,
      llmProvider, ttsProvider, ttsVoiceId,
    } = req.body;

    const updated = await agents.updateAgent(agentId, {
      name, prompt, voiceId, llmModel,
      agentLanguage, sttProvider, sttModel,
      llmProvider, ttsProvider, ttsVoiceId,
    });
    res.json(updated);
  } catch (error) {
    handleError(res, error);
  }
});

// ─── BROWSER VOICE SESSION ENDPOINTS ──────────────────────────────────────────

app.post('/api/voice/session', async (req, res) => {
  const { publishableKey, agentId } = req.body || {};
  if (!publishableKey || !agentId) return res.status(400).json({ error: 'publishableKey and agentId are required' });
  if (!config.publishableKey) return res.status(500).json({ error: 'publishable_key_not_configured' });
  if (publishableKey !== config.publishableKey) return res.status(401).json({ error: 'unknown publishable key' });
  if (!config.tenantId || !config.hmacSecret) return res.status(401).json({ error: 'Tenant credentials not set' });

  try {
    const headers = createControlPlaneHeaders(config.tenantId, config.hmacSecret, agentId);
    if (req.get('origin')) headers.Origin = req.get('origin');
    const upstream = await fetch(`${config.sessionUpstreamUrl.replace(/\/$/, '')}/v1/session`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ agent_id: agentId }),
    });

    const payload = await readJsonSafely(upstream);

    if (!upstream.ok) {
      const failure = normalizeSessionFailure(upstream.status, payload);
      return res.status(failure.status).json(failure.body);
    }

    if (!payload?.token || !payload?.wsUrl || !payload?.roomName) {
      return res.status(502).json({ error: 'session_failed' });
    }

    res.json({
      token: payload.token,
      wsUrl: payload.wsUrl,
      roomName: payload.roomName,
      refreshUrl: resolveRefreshUrl(req),
      expiresIn: payload.expiresIn || 120,
    });
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/voice/session/refresh', async (req, res) => {
  const bearer = req.get('authorization');
  const bodyToken = req.body?.token;
  const token = bearer?.startsWith('Bearer ') ? bearer.slice(7).trim() : bodyToken;
  if (!token) return res.status(401).json({ error: 'missing token' });

  try {
    const headers = {};
    if (bearer?.startsWith('Bearer ')) {
      headers.Authorization = bearer;
    } else {
      headers['Content-Type'] = 'application/json';
    }

    const upstream = await fetch(`${config.sessionUpstreamUrl.replace(/\/$/, '')}/v1/session/refresh`, {
      method: 'POST',
      headers,
      body: bearer?.startsWith('Bearer ') ? undefined : JSON.stringify({ token }),
    });

    const payload = await readJsonSafely(upstream);

    if (!upstream.ok || !payload?.token || !payload?.wsUrl || !payload?.roomName) {
      return res.status(502).json({ error: 'session_failed' });
    }

    res.json({
      token: payload.token,
      wsUrl: payload.wsUrl,
      roomName: payload.roomName,
      refreshUrl: resolveRefreshUrl(req),
      expiresIn: payload.expiresIn || 120,
    });
  } catch (error) {
    handleError(res, error);
  }
});

// ────────────────────────────────────────────────────────────────────────────
// TELNYX — CONNECTION
// ────────────────────────────────────────────────────────────────────────────
app.get('/api/telnyx/status', async (_req, res) => {
  try {
    const telephony = getTelephonyClient();
    const status = await telephony.getConnectionStatus();
    res.json(status);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/connect', async (req, res) => {
  try {
    if (!config.telnyxApiKey) {
      return res.status(400).json({ ok: false, message: 'Telnyx API key not set. Use POST /api/config first.' });
    }
    const telephony = getTelephonyClient();
    const connection = await telephony.connectTelnyxAccount({
      apiKey: config.telnyxApiKey,
      label: 'primary',
    });
    res.json(connection);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/rotate-key', async (req, res) => {
  try {
    const { apiKey } = req.body;
    if (!apiKey) return res.status(400).json({ ok: false, message: 'apiKey required' });
    const telephony = getTelephonyClient();
    const result = await telephony.rotateTelnyxAccountKey({ apiKey });
    // Update stored key too
    config.telnyxApiKey = apiKey;
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

// ────────────────────────────────────────────────────────────────────────────
// TELNYX — PHONE NUMBERS
// ────────────────────────────────────────────────────────────────────────────
app.get('/api/telnyx/numbers/available', async (req, res) => {
  try {
    const { country = 'US', areaCode, limit = 10 } = req.query;
    const telephony = getTelephonyClient();
    const numbers = await telephony.searchAvailableNumbers({
      country,
      ...(areaCode ? { areaCode } : {}),
      limit: parseInt(limit, 10),
    });
    res.json(numbers);
  } catch (error) {
    handleError(res, error);
  }
});

app.get('/api/telnyx/numbers/managed', async (req, res) => {
  try {
    const { limit = 25 } = req.query;
    const telephony = getTelephonyClient();
    const numbers = await telephony.listManagedPhoneNumbers({ limit: parseInt(limit, 10) });
    res.json(numbers);
  } catch (error) {
    handleError(res, error);
  }
});

app.get('/api/telnyx/numbers/owned', async (req, res) => {
  try {
    const { limit = 25 } = req.query;
    const telephony = getTelephonyClient();
    const numbers = await telephony.listTelnyxOwnedNumbers({ limit: parseInt(limit, 10) });
    res.json(numbers);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/numbers/sync', async (_req, res) => {
  try {
    const telephony = getTelephonyClient();
    const result = await telephony.syncTelnyxOwnedNumbers();
    res.json({ ok: true, ...result });
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/numbers/reserve', async (req, res) => {
  try {
    if (requirePaidTelephonyActions(res)) return;
    const { e164Number, idempotencyKey } = req.body;
    if (!e164Number) return res.status(400).json({ ok: false, message: 'e164Number required' });
    const telephony = getTelephonyClient();
    const result = await telephony.reserveNumber({
      e164Number,
      idempotencyKey: idempotencyKey || randomUUID(),
    });
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/numbers/purchase', async (req, res) => {
  try {
    if (requirePaidTelephonyActions(res)) return;
    const { e164Number, idempotencyKey } = req.body;
    if (!e164Number) return res.status(400).json({ ok: false, message: 'e164Number required' });
    const telephony = getTelephonyClient();
    const result = await telephony.purchaseNumber({
      e164Number,
      idempotencyKey: idempotencyKey || randomUUID(),
    });
    res.json(result);
  } catch (error) {
    if (error instanceof AwaazLabsUvaTelephonyError && error.code === 'number_not_available') {
      try {
        const recovery = await recoverAlreadyOwnedNumber(req.body?.e164Number);
        if (recovery.recovered && recovery.managedNumber) {
          return res.json({
            ok: true,
            recovered: true,
            recovery_source: recovery.source,
            platform_status: 'purchased',
            provider_status: 'already_owned',
            selected_e164_number: req.body.e164Number,
            managed_number_id: recovery.managedNumber.id || null,
            message: 'That number was already purchased or already present in your Telnyx inventory, so the test app recovered it instead of placing another paid order.',
          });
        }
      } catch (recoveryError) {
        console.warn('[UVA Test App Recovery] Could not verify already-owned number:', recoveryError?.message || recoveryError);
      }
    }
    handleError(res, error);
  }
});

app.post('/api/telnyx/numbers/import', async (req, res) => {
  try {
    const { e164Number } = req.body;
    if (!e164Number) return res.status(400).json({ ok: false, message: 'e164Number required' });
    const telephony = getTelephonyClient();
    const result = await telephony.importTelnyxNumber({ e164Number });
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.get('/api/telnyx/numbers/order/:orderId', async (req, res) => {
  try {
    const telephony = getTelephonyClient();
    const result = await telephony.getNumberOrderStatus(req.params.orderId);
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/numbers/:numberId/disable', async (req, res) => {
  try {
    const telephony = getTelephonyClient();
    const result = await telephony.disableNumber(req.params.numberId);
    res.json({ ok: true, ...result });
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/numbers/:numberId/assign-agent', async (req, res) => {
  try {
    const { agentId } = req.body;
    if (!agentId) return res.status(400).json({ ok: false, message: 'agentId required' });
    const telephony = getTelephonyClient();
    const result = await telephony.assignAgentToNumber(req.params.numberId, agentId);
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/numbers/:numberId/configure-routing', async (req, res) => {
  try {
    const telephony = getTelephonyClient();
    const { agentId } = req.body || {};
    if (agentId) {
      await telephony.assignAgentToNumber(req.params.numberId, agentId);
    }
    const result = await telephony.configureNumberRouting(req.params.numberId);
    res.json({ ok: true, ...result });
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/inbound/simulate', async (req, res) => {
  try {
    const { numberId, agentId } = req.body || {};
    if (!numberId) {
      return res.status(400).json({ ok: false, message: 'numberId is required' });
    }

    const [numbers, agents] = await Promise.all([listManagedNumbers(), listAgents()]);
    const number = numbers.find((item) => item.id === numberId);
    if (!number) {
      return res.status(404).json({ ok: false, message: `Managed number ${numberId} was not found.` });
    }

    if (!number.assigned_agent_id) {
      return res.status(409).json({ ok: false, code: 'number_not_assigned', message: 'Assign this number to an agent before simulating inbound.' });
    }

    if (agentId && number.assigned_agent_id !== agentId) {
      return res.status(409).json({
        ok: false,
        code: 'number_not_assigned',
        message: 'This number is currently attached to a different agent.',
        assignedAgentId: number.assigned_agent_id,
      });
    }

    if (number.routing_status !== 'ready') {
      return res.status(409).json({
        ok: false,
        code: 'number_not_routing_ready',
        message: 'Configure routing before simulating inbound.',
        routingStatus: number.routing_status,
      });
    }

    const agent = agents.find((item) => item.id === number.assigned_agent_id) || null;
    res.json({
      ok: true,
      mode: 'simulated_inbound_dispatch',
      message: 'Inbound dispatch would resolve to the assigned agent.',
      numberId: number.id,
      e164Number: number.e164_number || number.phone_number || null,
      agentId: number.assigned_agent_id,
      agentName: agent?.name || null,
      routingStatus: number.routing_status,
      providerStatus: number.provider_status || null,
    });
  } catch (error) {
    handleError(res, error);
  }
});

// ────────────────────────────────────────────────────────────────────────────
// TELNYX — SIP / OUTBOUND PROFILE
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/telnyx/sip-connection', async (req, res) => {
  try {
    const { sipFqdn, sipUsername, sipSecret } = req.body;
    const telephony = getTelephonyClient();
    const result = await telephony.upsertTelnyxSipConnection({ sipFqdn, sipUsername, sipSecret });
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/sip-connection/verify', async (_req, res) => {
  try {
    const telephony = getTelephonyClient();
    const result = await telephony.verifyTelnyxSipConnection();
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/outbound-voice-profile', async (req, res) => {
  try {
    const { allowedDestinations, concurrencyLimit, channelLimit, dailySpendingLimit } = req.body;
    const telephony = getTelephonyClient();
    const result = await telephony.upsertTelnyxOutboundVoiceProfile({
      allowedDestinations: allowedDestinations || ['US'],
      concurrencyLimit: concurrencyLimit || 2,
      ...(channelLimit ? { channelLimit } : {}),
      ...(dailySpendingLimit ? { dailySpendingLimit } : {}),
    });
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/outbound-voice-profile/verify', async (_req, res) => {
  try {
    const telephony = getTelephonyClient();
    const result = await telephony.verifyTelnyxOutboundVoiceProfile();
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/outbound-trunk', async (_req, res) => {
  try {
    const telephony = getTelephonyClient();
    const result = await telephony.configureOutboundTrunk();
    res.json({ ok: true, ...result });
  } catch (error) {
    handleError(res, error);
  }
});

// ────────────────────────────────────────────────────────────────────────────
// OUTBOUND CALLS
// ────────────────────────────────────────────────────────────────────────────
app.get('/api/readiness', async (_req, res) => {
  try {
    const telephony = getTelephonyClient();
    const readiness = await telephony.getOutboundReadiness();
    res.json(readiness);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/outbound-call', async (req, res) => {
  try {
    if (requirePaidTelephonyActions(res)) return;
    const { agentId, fromNumberId, toNumber, recipient, context } = req.body;
    if (!agentId || !fromNumberId || !toNumber) {
      return res.status(400).json({ ok: false, message: 'agentId, fromNumberId, and toNumber are required' });
    }
    if (!/^\+[1-9]\d{6,14}$/.test(toNumber)) {
      return res.status(400).json({ ok: false, message: 'toNumber must be in E.164 format (e.g. +12125551234)' });
    }

    const [numbers, agents] = await Promise.all([listManagedNumbers(), listAgents()]);
    const selectedNumber = numbers.find((item) => item.id === fromNumberId);
    if (!selectedNumber) {
      return res.status(404).json({ ok: false, code: 'number_not_found', message: `Managed number ${fromNumberId} was not found.` });
    }
    if (!selectedNumber.assigned_agent_id) {
      return res.status(409).json({
        ok: false,
        code: 'number_not_assigned',
        message: 'Attach this managed number to an agent before placing an outbound call.',
      });
    }

    const effectiveAgentId = selectedNumber.assigned_agent_id;
    const selectedAgent = agents.find((item) => item.id === effectiveAgentId) || null;
    if (agentId !== effectiveAgentId) {
      console.warn('[Outbound Call] Overriding stale agent selection', {
        requestedAgentId: agentId,
        effectiveAgentId,
        fromNumberId,
      });
    }

    const telephony = getTelephonyClient();
    const call = await telephony.createOutboundCall({
      agentId: effectiveAgentId,
      fromNumberId,
      toNumber,
      recipient: recipient || 'Test Recipient',
      context: context || { source: 'uva-client-test-app' },
      idempotencyKey: randomUUID(),
    });
    res.json({
      ...call,
      agentId: effectiveAgentId,
      agentName: selectedAgent?.name || null,
      requestedAgentId: agentId,
    });
  } catch (error) {
    if (error instanceof AwaazLabsUvaTelephonyError && (error.code === 'telephony_invalid_response' || error.status === 502)) {
      const diagnosticBody = {
        agent_id: req.body?.agentId || '',
        from_number_id: req.body?.fromNumberId || '',
        to_number: req.body?.toNumber || '',
        recipient: req.body?.recipient || 'Test Recipient',
        context: toSnakeCaseValue(req.body?.context || { source: 'uva-client-test-app' }),
        idempotency_key: randomUUID(),
      };
      const [upstreamProbe, diagnostics] = await Promise.all([
        probeTelephonyUpstream({
          action: 'telephony.outbound_calls.create',
          path: '/machine/telephony/outbound-calls',
          body: diagnosticBody,
          method: 'POST',
        }).catch((probeError) => ({
          ok: false,
          status: 0,
          statusText: 'probe_failed',
          responseKind: 'text',
          payloadPreview: previewText(probeError?.message || String(probeError)),
          parsedBody: null,
          likelyCauses: ['The local backend could not complete the raw outbound diagnostic probe.'],
        })),
        collectTelephonyDiagnostics({
          fromNumberId: req.body?.fromNumberId || '',
          requestedAgentId: req.body?.agentId || '',
          toNumber: req.body?.toNumber || '',
        }).catch(() => null),
      ]);
      return res.status(502).json({
        ok: false,
        code: error.code,
        message: 'Telephony API returned a non-JSON or gateway response during outbound call setup.',
        detail: {
          diagnostics,
          upstreamProbe,
        },
      });
    }
    handleError(res, error);
  }
});

app.get('/api/telephony/diagnostics', async (req, res) => {
  try {
    const diagnostics = await collectTelephonyDiagnostics({
      fromNumberId: String(req.query.numberId || ''),
      requestedAgentId: String(req.query.agentId || ''),
      toNumber: String(req.query.toNumber || ''),
    });
    res.json({ ok: true, diagnostics });
  } catch (error) {
    handleError(res, error);
  }
});

app.get('/api/calls', async (req, res) => {
  try {
    const { limit = 25 } = req.query;
    const telephony = getTelephonyClient();
    const calls = await telephony.listCallRecords({ limit: parseInt(limit, 10) });
    res.json(calls);
  } catch (error) {
    handleError(res, error);
  }
});

app.get('/api/calls/:callId', async (req, res) => {
  try {
    const telephony = getTelephonyClient();
    const call = await telephony.getCallStatus(req.params.callId);
    res.json(call);
  } catch (error) {
    handleError(res, error);
  }
});

app.get('/api/telnyx/drift', async (_req, res) => {
  try {
    const telephony = getTelephonyClient();
    const drift = await telephony.getTelnyxNumberDrift();
    res.json(drift);
  } catch (error) {
    handleError(res, error);
  }
});

// ────────────────────────────────────────────────────────────────────────────
// START
// ────────────────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`\n🚀 UVA Client Test App Backend running on http://localhost:${PORT}`);
  console.log(`   API Base URL: ${config.apiBaseUrl}`);
  console.log(`   Telephony URL: ${config.telephonyApiUrl}`);
  console.log(`   Session URL:   ${config.sessionUpstreamUrl}`);
  console.log(`   Tenant ID:    ${config.tenantId ? config.tenantId.slice(0, 8) + '...' : '(not set - use /api/config or Setup tab)'}`);
  console.log(`   Paid actions: ${config.allowPaidTelephonyActions ? 'enabled' : 'disabled'}`);
  console.log(`
   Open the frontend at http://localhost:3000
`);
});
