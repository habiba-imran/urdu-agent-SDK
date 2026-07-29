# AwaazLabs-UVA-Voice SDK - Integration Guide

Version 1.0, July 2026. Confidential client onboarding documentation from Finova Solutions.

This package contains private SDK tarballs. It does not contain a test frontend/backend. Integrate
the packages into the client's own application.

## 1. What The Client Must Build

The integration has two sides:

1. Frontend/browser
   - Installs `@awaazlabs-uva/voice`
   - Holds only `VITE_UVA_PUBLISHABLE_KEY` or the framework equivalent
   - Calls the client's own backend at `/api/voice/session`
   - Connects to LiveKit using the short-lived token returned by the backend

2. Backend/server
   - Installs `@awaazlabs-uva/agents`
   - Holds `UVA_TENANT_ID`, `UVA_HMAC_SECRET`, `UVA_PORTAL_API_URL`, and session upstream config
   - Provides browser-facing session, refresh, voices, and agent-management routes
   - Never exposes HMAC secrets or backend-only upstream URLs to the browser

## 2. Install Packages

Run these commands from the client's project roots. Adjust the path to wherever the unzipped
`client-submission_v2` folder is located.

Frontend:

```bash
npm install /path/to/client-submission_v2/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz livekit-client@^2.0.0
```

Backend:

```bash
npm install /path/to/client-submission_v2/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
```

`@awaazlabs-uva/agents` is ESM and backend-only. Do not install it in the frontend package.

## 3. Environment Files

Backend `.env`:

```env
PORT=3100
HOST_ALLOWED_ORIGINS=http://localhost:5174
HOST_PUBLIC_BASE_URL=http://localhost:3100

UVA_SESSION_UPSTREAM_URL=[BACKEND_ONLY_SESSION_UPSTREAM_URL]
UVA_SESSION_REFRESH_UPSTREAM_URL=[OPTIONAL_BACKEND_ONLY_REFRESH_UPSTREAM_URL]
UVA_VOICE_CATALOG_URL=[VOICE_CATALOG_URL]

UVA_PORTAL_API_URL=[PORTAL_API_URL]
UVA_TENANT_ID=[TENANT_ID]
UVA_HMAC_SECRET=[HMAC_SECRET]
UVA_PUBLISHABLE_KEY=[PUBLISHABLE_KEY]
```

Frontend `.env` for Vite:

```env
VITE_UVA_PUBLISHABLE_KEY=[PUBLISHABLE_KEY]
VITE_UVA_SESSION_ENDPOINT=http://localhost:3100/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3100/api/voice/session/refresh
VITE_UVA_VOICE_CATALOG_ENDPOINT=http://localhost:3100/api/voices
VITE_UVA_AGENT_ID=[AGENT_ID]
```

For Next.js, rename public frontend variables to `NEXT_PUBLIC_UVA_*`. Never prefix backend secrets
with `NEXT_PUBLIC_`.

## 4. Backend Routes

The browser should call only the client's backend. The backend may then call Finova/AwaazLabs-UVA
upstream services using backend-only credentials.

### Express Example

```ts
import cors from 'cors';
import dotenv from 'dotenv';
import express from 'express';
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

dotenv.config();

const app = express();
app.use(express.json());

const allowedOrigins = (process.env.HOST_ALLOWED_ORIGINS ?? '')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);

app.use(cors({
  origin(origin, cb) {
    if (!origin || allowedOrigins.includes(origin)) return cb(null, true);
    return cb(new Error('CORS origin not allowed'));
  },
  credentials: false,
}));

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

async function postJson(url: string, body: unknown, headers: Record<string, string> = {}) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });

  const text = await response.text();
  let payload: any = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { error: text };
    }
  }

  if (!response.ok) {
    const error: any = new Error(payload?.message || payload?.error || response.statusText);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

function sendError(res: express.Response, error: any, fallback = 'request_failed') {
  const status = Number(error?.status) || 500;
  const code =
    status === 429 ? 'quota_exceeded' :
    status === 404 ? 'agent_not_found' :
    error?.payload?.error || fallback;

  res.status(status).json({ error: code, message: error?.message || fallback });
}

const agents = new AwaazLabsUvaAgentsClient({
  tenantId: requireEnv('UVA_TENANT_ID'),
  tenantSecret: requireEnv('UVA_HMAC_SECRET'),
  baseUrl: requireEnv('UVA_PORTAL_API_URL'),
});

app.get('/api/health', (_req, res) => {
  res.json({ ok: true });
});

app.post('/api/voice/session', async (req, res) => {
  try {
    const publishableKey = String(req.body?.publishableKey ?? '');
    const agentId = String(req.body?.agentId ?? '');

    if (!publishableKey || !agentId) {
      return res.status(400).json({ error: 'publishableKey and agentId are required' });
    }
    if (publishableKey !== requireEnv('UVA_PUBLISHABLE_KEY')) {
      return res.status(401).json({ error: 'unknown_publishable_key' });
    }

    const origin = req.get('origin');
    const session = await postJson(
      requireEnv('UVA_SESSION_UPSTREAM_URL'),
      { publishableKey, agentId, origin },
      origin ? { origin } : {},
    );

    if (!session.token || !session.wsUrl || !session.roomName) {
      return res.status(502).json({ error: 'invalid_session_response' });
    }

    res.json({
      ...session,
      refreshUrl: session.refreshUrl ?? `${requireEnv('HOST_PUBLIC_BASE_URL')}/api/voice/session/refresh`,
    });
  } catch (error) {
    sendError(res, error, 'session_failed');
  }
});

app.post('/api/voice/session/refresh', async (req, res) => {
  try {
    const refreshUrl =
      process.env.UVA_SESSION_REFRESH_UPSTREAM_URL ||
      `${requireEnv('UVA_SESSION_UPSTREAM_URL').replace(/\/$/, '')}/refresh`;

    const origin = req.get('origin');
    const auth = req.get('authorization');
    const session = await postJson(
      refreshUrl,
      req.body ?? {},
      {
        ...(origin ? { origin } : {}),
        ...(auth ? { authorization: auth } : {}),
      },
    );

    res.json(session);
  } catch (error) {
    sendError(res, error, 'refresh_failed');
  }
});

app.get('/api/voices', async (_req, res) => {
  try {
    const response = await fetch(requireEnv('UVA_VOICE_CATALOG_URL'));
    if (!response.ok) throw Object.assign(new Error('voice catalog failed'), { status: response.status });
    const payload = await response.json();
    res.json(Array.isArray(payload) ? payload : payload.voices ?? []);
  } catch (error) {
    sendError(res, error, 'voices_failed');
  }
});

app.get('/api/agents', async (_req, res) => {
  try {
    res.json(await agents.listAgents());
  } catch (error) {
    sendError(res, error, 'agents_failed');
  }
});

app.post('/api/agents', async (req, res) => {
  try {
    const { name, prompt, voiceId, llmModel } = req.body ?? {};
    if (!name || !prompt || !voiceId) {
      return res.status(400).json({ error: 'name, prompt, and voiceId are required' });
    }
    const agent = await agents.createAgent({ name, prompt, voiceId, llmModel });
    res.status(201).json(agent);
  } catch (error) {
    sendError(res, error, 'create_agent_failed');
  }
});

app.patch('/api/agents/:agentId', async (req, res) => {
  try {
    res.json(await agents.updateAgent(req.params.agentId, req.body ?? {}));
  } catch (error) {
    sendError(res, error, 'update_agent_failed');
  }
});

app.listen(Number(process.env.PORT ?? 3100), () => {
  console.log(`AwaazLabs-UVA backend listening on ${process.env.PORT ?? 3100}`);
});
```

Adapt this shape to Fastify, NestJS, Next.js API routes, or any other server framework. Preserve
the same security boundary.

## 5. Frontend Voice Session

React/Vite example:

```tsx
import { useEffect, useMemo, useState } from 'react';
import { AwaazLabsUvaVoice, type TranscriptEvent } from '@awaazlabs-uva/voice';

export function VoiceWidget({ agentId }: { agentId: string }) {
  const [status, setStatus] = useState('idle');
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [transcripts, setTranscripts] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const voice = useMemo(() => new AwaazLabsUvaVoice({
    publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
    sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT,
    refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT,
  }), []);

  useEffect(() => {
    const onTranscript = (entry: TranscriptEvent) => {
      if (entry.final) setTranscripts((items) => [...items, entry.text]);
    };

    voice.on('connected', () => setStatus('connected'));
    voice.on('disconnected', () => setStatus('idle'));
    voice.on('transcript', onTranscript);
    voice.on('audio_blocked', setAudioBlocked);
    voice.on('error', (err) => setError(`${err.code}: ${err.message}`));

    return () => {
      voice.off('transcript', onTranscript);
      voice.disconnect();
    };
  }, [voice]);

  async function connect() {
    setError(null);
    setStatus('connecting');
    try {
      await voice.connect({ agentId });
    } catch (err) {
      setStatus('idle');
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section>
      <p>Status: {status}</p>
      {error && <p role="alert">{error}</p>}
      {audioBlocked && <button onClick={() => voice.startAudio()}>Unlock Audio</button>}
      <button onClick={connect} disabled={status === 'connecting' || status === 'connected'}>
        Connect
      </button>
      <button onClick={() => voice.disconnect()} disabled={status !== 'connected'}>
        Disconnect
      </button>
      <ul>{transcripts.map((text, index) => <li key={index}>{text}</li>)}</ul>
    </section>
  );
}
```

Important browser audio rule: if the SDK emits `audio_blocked: true`, show a button and call
`startAudio()` inside that button click. Browsers may block autoplay until a user gesture occurs.

## 6. Agent Management

Create agents from the backend, then pass the returned `id` to the frontend.

```ts
const agent = await agents.createAgent({
  name: 'Support Agent',
  prompt: 'You are a helpful Urdu support assistant.',
  voiceId: 'v_meklc281',
  llmModel: 'gemini-2.5-flash',
});

console.log(agent.id);
```

Voice catalog flow:

1. Backend exposes `GET /api/voices`.
2. Backend fetches `UVA_VOICE_CATALOG_URL`.
3. Frontend calls only `VITE_UVA_VOICE_CATALOG_ENDPOINT`.
4. Frontend filters for `enabled === true`.
5. User chooses `voice.id` and backend uses it as `voiceId` when creating an agent.

## 7. Event Reference

| Event | Payload | Meaning |
|---|---|---|
| `connected` | none | Room joined and microphone started |
| `disconnected` | optional reason | Room left or connection closed |
| `ended` | optional reason | Alias for final session end |
| `transcript` | `{ text, final }` | Partial/final transcript |
| `speaking` | boolean | Any room participant speaking |
| `agent_speaking` | boolean | Agent participant speaking |
| `metrics_updated` | object | Worker metrics when available |
| `audio_blocked` | boolean | Browser requires user gesture before audio playback |
| `error` | `AwaazLabsUvaVoiceError` | SDK-level error |

## 8. Error Reference

| Error code | Common cause |
|---|---|
| `quota_exceeded` | Tenant quota or concurrency limit reached |
| `agent_not_found` | Wrong agent ID or wrong tenant |
| `session_failed` | Backend/session upstream/network/LiveKit setup failed |

`@awaazlabs-uva/agents` throws `AwaazLabsUvaAgentsError` with an HTTP `status`. Common statuses:

| Status | Meaning |
|---|---|
| 401 | Bad HMAC secret, replayed nonce, or clock drift |
| 403 | Tenant suspended |
| 404 | Agent not found |
| 429 | Rate limited |

## 9. Validation Checklist

- [ ] Backend starts without missing environment variables.
- [ ] `GET /api/health` returns `{ "ok": true }`.
- [ ] `GET /api/voices` returns an array of enabled/disabled voice records.
- [ ] `GET /api/agents` returns a JSON array.
- [ ] `POST /api/agents` creates an agent and returns a UUID `id`.
- [ ] Frontend bundle contains `@awaazlabs-uva/voice`.
- [ ] Frontend bundle does not contain `@awaazlabs-uva/agents`.
- [ ] Browser DevTools shows `/api/voice/session` going to the client's backend only.
- [ ] Browser request body contains only `{ publishableKey, agentId }`.
- [ ] Browser request/response/logs do not contain `UVA_HMAC_SECRET` or `UVA_TENANT_ID`.
- [ ] Voice session connects, microphone prompt appears, and transcripts appear.
- [ ] Agent response audio is audible after `audio_blocked` handling if required.

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `session_failed` before connecting | Backend env or session upstream is wrong | Check backend logs and `UVA_SESSION_UPSTREAM_URL` |
| `agent_not_found` | Agent ID does not belong to the tenant | Create/list agents from the backend and use returned `id` |
| `quota_exceeded` | Tenant quota hit | Contact Finova |
| Transcript appears but no agent audio | TTS/provider/voice issue or browser audio blocked | Check worker/provider logs and handle `audio_blocked` |
| Browser calls Finova/AwaazLabs-UVA URL directly | Frontend configured with upstream URL | Point frontend env to client's backend routes only |
| `401` from agent API | Bad HMAC secret or server clock drift | Verify `UVA_HMAC_SECRET` and sync server clock |
| `ERR_REQUIRE_ESM` | Backend used `require()` for agents SDK | Use ESM `import` or dynamic `import()` |

## 11. Production Notes

- Replace localhost origins and URLs with production origins.
- Set `HOST_ALLOWED_ORIGINS` exactly; no trailing slash mismatch.
- Keep `.env` files out of Git.
- Rotate `UVA_HMAC_SECRET` immediately if it is exposed.
- Do not ask a coding agent to invent HMAC/session-upstream logic. Use the provided backend-only
  upstream configuration and the `@awaazlabs-uva/agents` SDK.
