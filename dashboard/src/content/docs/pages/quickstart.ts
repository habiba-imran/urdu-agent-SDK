export const meta = {
  slug: 'quickstart',
  title: 'Quickstart',
  eyebrow: 'Get started',
  description: 'Shortest path to a first browser call — five steps.',
};

export const markdown = `
## 1. Get your keys

Open **[API Keys](/credentials)** and copy:

- \`UVA_CONTROL_PLANE_URL\`
- \`UVA_TENANT_ID\`
- \`UVA_HMAC_SECRET\` (reveal once — backend only)
- \`UVA_PUBLISHABLE_KEY\` / \`NEXT_PUBLIC_UVA_PUBLISHABLE_KEY\` (or \`VITE_UVA_PUBLISHABLE_KEY\`)

Create an agent with \`@awaazlabs-uva/agents\` on your backend, then open **[Agents](/agents)** to copy its \`agentId\`.

## 2. Install packages

:::tabs
=== Backend
\`\`\`bash title=terminal
npm install
# Use host-backend-starter, or add agents/telephony when you need them:
# npm install @awaazlabs-uva/agents@0.1.0 @awaazlabs-uva/telephony@0.1.0
\`\`\`
=== Frontend
\`\`\`bash title=terminal
npm install @awaazlabs-uva/voice@1.1.0
\`\`\`
:::

## 3. Add a token endpoint on your backend

Expose \`POST /api/voice/session\` on **your** host. It validates the publishable key, HMAC-mints against the control plane, and returns \`{ token, wsUrl, roomName, refreshUrl, expiresIn? }\`.

Also expose \`POST /api/voice/session/refresh\` for mid-call refresh.

Full NestJS walkthrough + signing: [Backend setup](/docs/backend-setup). Or run the included \`host-backend-starter\`.

## 4. Connect from the frontend

\`\`\`ts title=app.ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voice = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
  sessionEndpoint: 'http://localhost:3000/api/voice/session',
  refreshEndpoint: 'http://localhost:3000/api/voice/session/refresh',
});

voice.on('transcript', (entry) => {
  console.log(entry.speaker, entry.text, entry.final);
});

voice.on('error', (error) => {
  console.error(error.code, error.message);
});

await voice.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
\`\`\`

The SDK POSTs \`{ publishableKey, agentId }\` to your \`sessionEndpoint\` — never to the control plane.

## 5. Make a call and verify in Sessions

Grant mic permission when asked, speak after the agent greets you (if configured), then hang up with \`disconnect()\`.

Open **[Sessions](/sessions)** — you should see duration, status, and transcript when available.

Stuck? See [Errors and troubleshooting](/docs/errors-and-troubleshooting).
`;
