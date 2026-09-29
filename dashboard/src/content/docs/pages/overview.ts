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
Voice agent runtime (LiveKit room + worker)
        │
        ▼
Telnyx (optional PSTN)
\`\`\`

The browser talks only to **your** session endpoints. Your backend signs requests to AwaazLabs. The secret never reaches the client.

## Where to work in this console

This console is **read-only** for agents and phone routing. Create and change configuration from your host codebase.

| Task | Where |
|------|--------|
| Inspect agents & assigned numbers | [Agents](/agents) |
| Create / update agents | \`@awaazlabs-uva/agents\` (backend) |
| Connect Telnyx, numbers, routing | \`@awaazlabs-uva/telephony\` (backend) |
| Copy env / keys | [API Keys](/credentials) |
| Inspect calls | [Sessions](/sessions) |
| This guide | Docs (you are here) |

## Suggested reading order

1. [How integration works](/docs/how-integration-works) — trust boundary and who does what  
2. [Quickstart](/docs/quickstart) — first call in five steps  
3. [What to expect](/docs/what-to-expect) — lifecycle, limits, end reasons  
4. Backend → Frontend → Telephony → Going live  

## Version note

Published packages used in this guide:

- \`@awaazlabs-uva/voice@1.1.0\`
- \`@awaazlabs-uva/agents@0.1.0\`
- \`@awaazlabs-uva/telephony@0.1.0\`

Pin versions in production. Breaking changes are called out in package changelogs and release notes.
`;
