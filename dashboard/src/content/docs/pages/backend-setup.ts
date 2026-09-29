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

**Body:** \`{ "agent_id": "<agentId>" }\`

This matches \`host-backend-starter/src/signing.js\`. Prefer copying that starter rather than re-deriving the algorithm.

## NestJS example

\`\`\`ts title=voice-session.controller.ts
import {
  Body, Controller, Headers, Post, Req, UnauthorizedException, BadRequestException,
} from '@nestjs/common';
import { createHmac, randomUUID } from 'crypto';
import type { Request } from 'express';

type SessionBody = { publishableKey?: string; agentId?: string };

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

    const upstream = await fetch(\`\${controlPlane}/v1/session\`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ agent_id: agentId }),
    });
    const payload = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      throw new UnauthorizedException(payload?.detail || payload?.error || 'session_failed');
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

Add a matching \`POST session/refresh\` that proxies to the control plane refresh path (see \`host-backend-starter\`).

## Express starter

Runnable reference: \`host-backend-starter\` in the deliverables (\`createApp\` + \`signing.js\`). Same contract as above.

## Agents SDK (optional)

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
  firstSpeaker: 'agent',
  greeting: 'Hi, thanks for calling. How can I help?',
});
// Use agent.id as VITE_UVA_AGENT_ID / connect({ agentId })
\`\`\`

Day-to-day edits stay in your codebase via this SDK. Inspect the result on **[Agents](/agents)** (read-only).
`;
