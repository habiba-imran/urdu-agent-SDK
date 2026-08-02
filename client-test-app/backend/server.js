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

import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { randomUUID, createHmac } from 'crypto';
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';
import { TelephonyClient, AwaazLabsUvaTelephonyError } from '@awaazlabs-uva/telephony';

const app = express();
app.use(cors({ origin: '*' }));
app.use(express.json());

// ─── Runtime config (can be overridden via POST /api/config) ────────────────
let config = {
  apiBaseUrl: process.env.UVA_API_BASE_URL || 'http://localhost:8000',
  telephonyApiUrl: process.env.UVA_TELEPHONY_API_URL || 'http://localhost:8000',
  tenantId: process.env.UVA_TENANT_ID || '',
  hmacSecret: process.env.UVA_HMAC_SECRET || '',
  telnyxApiKey: process.env.TELNYX_API_KEY || '',
};

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

// ─── Error helpers ───────────────────────────────────────────────────────────
function handleError(res, error) {
  console.error('[UVA Test App Error]', error?.message || error);
  if (error instanceof AwaazLabsUvaTelephonyError) {
    return res.status(error.status || 500).json({
      ok: false,
      code: error.code,
      message: error.message,
      detail: error.detail,
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
  });
});

// ────────────────────────────────────────────────────────────────────────────
// CONFIG
// ────────────────────────────────────────────────────────────────────────────
app.get('/api/config', (_req, res) => {
  res.json({
    apiBaseUrl: config.apiBaseUrl,
    telephonyApiUrl: config.telephonyApiUrl,
    tenantId: config.tenantId,
    // Never return secrets — just presence flags
    hmacSecretSet: !!config.hmacSecret,
    telnyxApiKeySet: !!config.telnyxApiKey,
  });
});

app.post('/api/config', (req, res) => {
  const { apiBaseUrl, telephonyApiUrl, tenantId, hmacSecret, telnyxApiKey } = req.body;
  if (apiBaseUrl) config.apiBaseUrl = apiBaseUrl;
  if (telephonyApiUrl) config.telephonyApiUrl = telephonyApiUrl;
  if (tenantId) config.tenantId = tenantId;
  if (hmacSecret) config.hmacSecret = hmacSecret;
  if (telnyxApiKey) config.telnyxApiKey = telnyxApiKey;
  console.log('[Config] Updated:', {
    apiBaseUrl: config.apiBaseUrl,
    tenantId: config.tenantId ? `${config.tenantId.slice(0, 8)}...` : '(not set)',
    hmacSecretSet: !!config.hmacSecret,
    telnyxApiKeySet: !!config.telnyxApiKey,
  });
  res.json({ ok: true, message: 'Configuration saved (in-memory only).' });
});

// ────────────────────────────────────────────────────────────────────────────
// PROVIDER CAPABILITIES
// ────────────────────────────────────────────────────────────────────────────
app.get('/api/capabilities', async (_req, res) => {
  try {
    // Fetch directly from the portal API (no SDK wrapper needed for this public endpoint)
    const agents = getAgentsClient();
    // Use the agents client's underlying fetch or call the portal directly
    const response = await fetch(`${config.apiBaseUrl}/portal/provider-capabilities`, {
      headers: {
        'Content-Type': 'application/json',
        // We piggyback on portal login token if we had one, but machine auth also works
        // For simplicity in test app: use a portal login if credentials allow, otherwise
        // fall back to direct call (the server may accept it in dev mode)
      },
    });
    if (!response.ok) {
      // Try machine auth path
      const telephony = getTelephonyClient();
      const caps = await telephony.getProviderCapabilities?.();
      return res.json(caps || { languages: {} });
    }
    const data = await response.json();
    return res.json(data);
  } catch (error) {
    // Return a minimal fallback so the UI still loads
    console.warn('[Capabilities] Could not fetch from API, using fallback:', error.message);
    return res.json({
      languages: {
        ur: {
          label: 'Urdu',
          stt: { gladia: { state: 'enabled', models: ['solaria-1'], defaultModel: 'solaria-1' } },
          llm: { gemini: { state: 'enabled', models: ['gemini-2.5-flash', 'gemini-2.0-flash'], defaultModel: 'gemini-2.5-flash' } },
          tts: { uplift: { state: 'enabled', voices: [], defaultVoice: null }, rime: { state: 'enabled', voices: [], defaultVoice: null } },
        },
        en: {
          label: 'English',
          stt: { gladia: { state: 'enabled', models: ['solaria-1'], defaultModel: 'solaria-1' } },
          llm: { gemini: { state: 'enabled', models: ['gemini-2.5-flash'], defaultModel: 'gemini-2.5-flash' } },
          tts: { uplift: { state: 'enabled', voices: [], defaultVoice: null } },
        },
      },
      _fallback: true,
    });
  }
});

// ────────────────────────────────────────────────────────────────────────────
// AGENTS
// ────────────────────────────────────────────────────────────────────────────
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

    if (!name || !prompt) {
      return res.status(400).json({ ok: false, message: 'name and prompt are required' });
    }

    const agent = await agents.createAgent({
      name,
      prompt,
      voiceId: voiceId || 'default',
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
  const { agentId } = req.body || {};
  if (!agentId) return res.status(400).json({ error: 'agentId is required' });
  if (!config.tenantId || !config.hmacSecret) return res.status(401).json({ error: 'Tenant credentials not set' });

  try {
    const headers = createControlPlaneHeaders(config.tenantId, config.hmacSecret, agentId);
    const upstream = await fetch(`${config.apiBaseUrl}/v1/session`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ agent_id: agentId }),
    });

    let payload;
    try { payload = await upstream.json(); } catch { payload = {}; }

    if (!upstream.ok || !payload?.token || !payload?.wsUrl || !payload?.roomName) {
      return res.status(502).json({ error: 'session_failed', detail: payload });
    }

    res.json({
      token: payload.token,
      wsUrl: payload.wsUrl,
      roomName: payload.roomName,
      refreshUrl: `http://localhost:${process.env.PORT || 3001}/api/voice/session/refresh`,
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

    const upstream = await fetch(`${config.apiBaseUrl}/v1/session/refresh`, {
      method: 'POST',
      headers,
      body: bearer?.startsWith('Bearer ') ? undefined : JSON.stringify({ token }),
    });

    let payload;
    try { payload = await upstream.json(); } catch { payload = {}; }

    if (!upstream.ok || !payload?.token || !payload?.wsUrl || !payload?.roomName) {
      return res.status(502).json({ error: 'session_failed', detail: payload });
    }

    res.json({
      token: payload.token,
      wsUrl: payload.wsUrl,
      roomName: payload.roomName,
      refreshUrl: `http://localhost:${process.env.PORT || 3001}/api/voice/session/refresh`,
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
    const { e164Number } = req.body;
    if (!e164Number) return res.status(400).json({ ok: false, message: 'e164Number required' });
    const telephony = getTelephonyClient();
    const result = await telephony.reserveNumber({
      e164Number,
      idempotencyKey: randomUUID(),
    });
    res.json(result);
  } catch (error) {
    handleError(res, error);
  }
});

app.post('/api/telnyx/numbers/purchase', async (req, res) => {
  try {
    const { e164Number } = req.body;
    if (!e164Number) return res.status(400).json({ ok: false, message: 'e164Number required' });
    const telephony = getTelephonyClient();
    const result = await telephony.purchaseNumber({
      e164Number,
      idempotencyKey: randomUUID(),
    });
    res.json(result);
  } catch (error) {
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
    const result = await telephony.configureNumberRouting(req.params.numberId);
    res.json({ ok: true, ...result });
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
    const { agentId, fromNumberId, toNumber, recipient, context } = req.body;
    if (!agentId || !fromNumberId || !toNumber) {
      return res.status(400).json({ ok: false, message: 'agentId, fromNumberId, and toNumber are required' });
    }
    // E.164 validation
    if (!/^\+[1-9]\d{6,14}$/.test(toNumber)) {
      return res.status(400).json({ ok: false, message: 'toNumber must be in E.164 format (e.g. +12125551234)' });
    }
    const telephony = getTelephonyClient();
    const call = await telephony.createOutboundCall({
      agentId,
      fromNumberId,
      toNumber,
      recipient: recipient || 'Test Recipient',
      context: context || { source: 'uva-client-test-app' },
      idempotencyKey: randomUUID(),
    });
    res.json(call);
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
  console.log(`   Tenant ID:    ${config.tenantId ? config.tenantId.slice(0, 8) + '...' : '(not set — use /api/config or Setup tab)'}`);
  console.log(`\n   Open the frontend at http://localhost:3000\n`);
});
