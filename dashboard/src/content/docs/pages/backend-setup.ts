export const meta = {
  slug: 'backend-setup',
  title: 'Backend setup',
  eyebrow: 'Integrate',
  description: 'Env vars, HMAC session mint, and a NestJS token endpoint.',
};

export const markdown = `
## Environment

Copy values from **[API Keys](/credentials)** (never commit secrets):

Copy the combined block from **[API Keys](/credentials)** (preferred). Shape:

\`\`\`bash title=.env
UVA_TENANT_ID=ten_xxxxxxxx
UVA_HMAC_SECRET=uva_sk_xxxxxxxx
UVA_PUBLISHABLE_KEY=uva_pk_xxxxxxxx
UVA_CONTROL_PLANE_URL=https://your-control-plane.example
UVA_API_BASE_URL=https://your-portal-api.example
UVA_TELEPHONY_API_URL=https://your-portal-api.example
HOST_ALLOWED_ORIGINS=http://localhost:5173,https://your-app.example.com
HOST_PUBLIC_BASE_URL=https://your-api.example.com
PORT=3000
\`\`\`

Platform URLs above are prefilled to Render staging on the API Keys page.

## Browser-facing contract

Your frontend only knows these routes on **your** host:

| Route | Body / auth | Success body |
|-------|-------------|--------------|
| \`POST /api/voice/session\` | \`{ publishableKey, agentId }\` | \`{ token, wsUrl, roomName, refreshUrl?, expiresIn? }\` |
| \`POST /api/voice/session/refresh\` | \`Authorization: Bearer <token>\` (or \`{ token }\`) | same shape |

Rewrite any upstream refresh URL to **your** \`/api/voice/session/refresh\` before returning to the browser.

## HMAC mint to the control plane

Your backend calls \`POST {UVA_CONTROL_PLANE_URL}/v1/session\` with:

**Canonical string** (HMAC-SHA256 → hex):

\`\`\`text
{tenantId}.{timestamp}.{nonce}.{agentId}
\`\`\`

**Headers:**

- \`Content-Type: application/json\`
- \`X-Tenant-Id\`
- \`X-Timestamp\` (unix seconds)
- \`X-Nonce\` (UUID)
- \`X-Signature\` (hex digest)
- Forward browser \`Origin\` when present

**Body:** \`{ "agent_id": "<agentId>", "verified_caller_phone"?: "+92300…" }\`

When scheduling write tools (book / cancel / reschedule) are enabled, your host **must** assert \`verified_caller_phone\` from a trusted identity (logged-in account, OTP, carrier ANI) — never from an untrusted browser field alone. Without it, ownership-bound writes are rejected.

## NestJS example

\`\`\`ts title=voice-session.controller.ts
import {
  Body, Controller, Headers, HttpException, Post, Req, UnauthorizedException, BadRequestException,
} from '@nestjs/common';
import { createHmac, randomUUID } from 'crypto';
import type { Request } from 'express';

type SessionBody = {
  publishableKey?: string;
  agentId?: string;
  /** Host-asserted caller phone for write-tool ownership. */
  verifiedCallerPhone?: string;
  verified_caller_phone?: string;
};

function mapMintFailure(upstreamStatus: number, payload: Record<string, unknown>) {
  // Preserve status + short reason so @awaazlabs-uva/voice can map agent_not_found / quota / rate_limit.
  const detail = String(payload?.detail || payload?.error || payload?.code || '');
  const lower = detail.toLowerCase();
  if (upstreamStatus === 429) {
    return { status: 429, body: { error: detail || 'quota_exceeded' } };
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

@Controller('api/voice')
export class VoiceSessionController {
  @Post('session')
  async createSession(
    @Body() body: SessionBody,
    @Headers('origin') origin: string | undefined,
    @Req() req: Request,
  ) {
    const { publishableKey, agentId } = body;
    if (!publishableKey || !agentId) {
      throw new BadRequestException('publishableKey and agentId are required');
    }
    if (publishableKey !== process.env.UVA_PUBLISHABLE_KEY) {
      throw new UnauthorizedException('unknown publishable key');
    }

    const tenantId = process.env.UVA_TENANT_ID!;
    const secret = process.env.UVA_HMAC_SECRET!;
    const controlPlane = process.env.UVA_CONTROL_PLANE_URL!;
    const timestamp = String(Math.floor(Date.now() / 1000));
    const nonce = randomUUID();
    const signature = createHmac('sha256', secret)
      .update(\`\${tenantId}.\${timestamp}.\${nonce}.\${agentId}\`)
      .digest('hex');

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Tenant-Id': tenantId,
      'X-Timestamp': timestamp,
      'X-Nonce': nonce,
      'X-Signature': signature,
    };
    if (origin) headers.Origin = origin;

    const mintBody: Record<string, string> = { agent_id: agentId };
    const phone = (body.verifiedCallerPhone || body.verified_caller_phone || '').trim();
    if (phone) mintBody.verified_caller_phone = phone;

    const upstream = await fetch(\`\${controlPlane}/v1/session\`, {
      method: 'POST',
      headers,
      body: JSON.stringify(mintBody),
    });
    const payload = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      const failure = mapMintFailure(upstream.status, payload);
      throw new HttpException(failure.body, failure.status);
    }

    const publicBase =
      process.env.HOST_PUBLIC_BASE_URL ||
      \`\${req.protocol}://\${req.get('host')}\`;

    return {
      token: payload.token,
      wsUrl: payload.wsUrl,
      roomName: payload.roomName,
      refreshUrl: \`\${publicBase}/api/voice/session/refresh\`,
      expiresIn: payload.expiresIn ?? 120,
    };
  }

  @Post('session/refresh')
  async refreshSession(
    @Body() body: { token?: string },
    @Headers('authorization') authorization: string | undefined,
    @Req() req: Request,
  ) {
    const bearer = authorization?.startsWith('Bearer ')
      ? authorization.slice(7).trim()
      : '';
    const token = bearer || (body.token || '').trim();
    if (!token) {
      throw new UnauthorizedException('missing bearer token');
    }

    const controlPlane = process.env.UVA_CONTROL_PLANE_URL!;
    const headers: Record<string, string> = {};
    if (bearer) {
      headers.Authorization = \`Bearer \${bearer}\`;
    } else {
      headers['Content-Type'] = 'application/json';
    }

    const upstream = await fetch(\`\${controlPlane}/v1/session/refresh\`, {
      method: 'POST',
      headers,
      body: bearer ? undefined : JSON.stringify({ token }),
    });
    const payload = await upstream.json().catch(() => ({}));
    if (!upstream.ok || !payload?.token || !payload?.wsUrl || !payload?.roomName) {
      throw new HttpException(
        { error: payload?.detail || payload?.error || 'token_refresh_failed' },
        upstream.status >= 400 ? upstream.status : 502,
      );
    }

    const publicBase =
      process.env.HOST_PUBLIC_BASE_URL ||
      \`\${req.protocol}://\${req.get('host')}\`;

    return {
      token: payload.token,
      wsUrl: payload.wsUrl,
      roomName: payload.roomName,
      refreshUrl: \`\${publicBase}/api/voice/session/refresh\`,
      expiresIn: payload.expiresIn ?? 120,
    };
  }
}
\`\`\`

Forward \`verifiedCallerPhone\` when write tools are enabled. Set \`HOST_ALLOWED_ORIGINS\` on your host (an empty allowlist must not reflect arbitrary Origins).

## Agents SDK

Create and update agents from your **backend** (this console does not edit agents):

\`\`\`ts title=agents.ts
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

const agents = new AwaazLabsUvaAgentsClient({
  baseUrl: process.env.UVA_API_BASE_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});

const agent = await agents.createAgent({
  name: 'Support Agent',
  prompt: 'Answer customer questions concisely.',
  voiceId: 'cartesia-sonic-default', // required — or pick from getProviderCapabilities()
  agentLanguage: 'en', // or 'ur'
  // Optional: sttProvider, llmProvider, ttsProvider, ttsVoiceId — see Providers
  firstSpeaker: 'agent',
  greeting: 'Hi, thanks for calling. How can I help?',
});
// Use agent.id as VITE_UVA_AGENT_ID / connect({ agentId })
\`\`\`

Configured STT / LLM / TTS **stick at runtime** (no silent vendor remap). Matrix: [Providers](/docs/providers).

Inspect the result on **[Agents](/agents)** (read-only).
`;
