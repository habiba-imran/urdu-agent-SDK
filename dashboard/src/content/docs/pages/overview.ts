export const meta = {
  slug: 'overview',
  title: 'Overview',
  eyebrow: 'Get started',
  description: 'What the AwaazLabs voice SDK does, and how it fits in your product.',
};

export const markdown = `
## What this SDK does

AwaazLabs UVA lets you add a real-time voice agent to **your** app. Callers talk over WebRTC (browser) or the phone network (Telnyx). Your product stays in control of UX, auth, and business logic — we run the voice runtime.

You integrate with three npm packages:

| Package | Where it runs | Role |
|---------|---------------|------|
| \`@awaazlabs-uva/voice\` | Browser only | Connect, speak, receive transcripts and lifecycle events |
| \`@awaazlabs-uva/agents\` | Your backend only | Create and update agents (HMAC-signed) |
| \`@awaazlabs-uva/telephony\` | Your backend only | Telnyx connect, numbers, routing, outbound (HMAC-signed) |

Never put \`agents\` or \`telephony\` in a frontend bundle — they need your tenant HMAC secret.

## What AwaazLabs runs vs what you build

| AwaazLabs (platform) | You (host product) |
|----------------------|--------------------|
| Voice runtime (STT → LLM → TTS) | UX, auth, business logic |
| Control plane \`/v1/session\` mint + refresh | \`POST /api/voice/session\` (+ refresh) that HMAC-signs to us |
| Tenant HMAC, publishable key, quotas | Secret store + env; never ship HMAC to browsers |
| Agent / telephony **APIs** | Call \`@awaazlabs-uva/agents\` and \`@awaazlabs-uva/telephony\` from **your backend** |
| This console (read-only) | Inspect agents, sessions, keys; follow **/docs** to integrate |

Agents and phone routing are **not** edited in this console. Empty Agents / no numbers means configure via your host SDKs (or ask AwaazLabs to provision), then refresh [Agents](/agents).

## Architecture (one picture)

\`\`\`text
User browser / phone
        │
        ▼
Your host backend  ←── holds HMAC secret, mints sessions
        │
        ▼
AwaazLabs control plane  (/v1/session)
        │
        ▼
Voice agent runtime (LiveKit)
        │
        ▼
Telnyx (optional PSTN)
\`\`\`

The browser talks only to **your** session endpoints. Your backend signs requests to AwaazLabs. The secret never reaches the client.

## Where to work in this console

| Task | Where |
|------|--------|
| Inspect agents & assigned numbers | [Agents](/agents) (**read-only**) |
| Create / update agents | \`@awaazlabs-uva/agents\` on your backend |
| Connect Telnyx, numbers, routing | \`@awaazlabs-uva/telephony\` on your backend |
| Copy env / HMAC / set origins | [API Keys](/credentials) (masked metadata; permitted owner reveal or secure operator delivery; rotate disabled) |
| Inspect calls | [Sessions](/sessions) |
| STT / LLM / TTS matrix | [Providers](/docs/providers) |
| Operator smoke call | [Test Studio](/test-studio) — **not** your customers' mint path |
| This guide | **/docs** (you are here) |

## Suggested reading order

1. [How integration works](/docs/how-integration-works) — trust boundary and who does what
2. [Quickstart](/docs/quickstart) — first call in five steps
3. [What to expect](/docs/what-to-expect) — lifecycle, limits, end reasons
4. [Providers](/docs/providers) — English and Urdu STT / LLM / TTS (configured providers stick)
5. [Backend setup](/docs/backend-setup) → [Frontend setup](/docs/frontend-setup) → [Telephony](/docs/telephony) → [Going live](/docs/going-live)
6. [Security](/docs/security) · [Errors](/docs/errors-and-troubleshooting) · [Legal and trust](/docs/legal-and-trust)

## Version note

Published packages used in this guide:

- \`@awaazlabs-uva/voice@1.1.0\`
- \`@awaazlabs-uva/agents@0.1.0\`
- \`@awaazlabs-uva/telephony@0.1.0\`

Pin versions in production. Breaking changes are called out in package changelogs and release notes.
`;
