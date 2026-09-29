export const meta = {
  slug: 'how-integration-works',
  title: 'How integration works',
  eyebrow: 'Get started',
  description: 'The request flow, who owns which keys, and the trust boundary.',
};

export const markdown = `
## The flow

Every browser voice session follows the same path:

1. \`AwaazLabsUvaVoice\` calls **your** \`sessionEndpoint\`: \`POST /api/voice/session\` with \`publishableKey\` + \`agentId\`.
2. Your backend HMAC-signs a mint to AwaazLabs: \`POST {UVA_CONTROL_PLANE_URL}/v1/session\`.
3. Control plane returns a short-lived LiveKit join token (+ \`wsUrl\`, \`roomName\`).
4. Your backend returns that payload to the browser (and a \`refreshUrl\` that points at **you**, not us).
5. The voice SDK joins the LiveKit room and starts the mic.

Phone (PSTN) skips the browser SDK for the media path: Telnyx → our telephony webhook → same worker runtime. Configure numbers and agents with \`@awaazlabs-uva/agents\` / \`@awaazlabs-uva/telephony\` on your backend; this console is read-only for inspection.

\`\`\`text
┌─────────────┐     POST /api/voice/session      ┌────────────────┐
│   Browser   │ ───────────────────────────────► │  Your backend  │
│ voice SDK   │ ◄─────────────────────────────── │  (HMAC here)   │
└─────────────┘   token, wsUrl, refreshUrl       └───────┬────────┘
                                                         │ signed mint
                                                         ▼
                                                 ┌────────────────┐
                                                 │ Control plane  │
                                                 │  /v1/session   │
                                                 └───────┬────────┘
                                                         │
                                                         ▼
                                                 LiveKit + agent worker
\`\`\`

## Who does what

| Concern | Your backend | Your frontend | AwaazLabs |
|---------|--------------|---------------|-----------|
| Hold HMAC secret | Yes | Never | Verifies signature |
| Hold publishable key | Yes (check it) | Yes (identify only) | Maps to tenant |
| Mint LiveKit token | Via our control plane | No | Issues token |
| Agent prompt / voice | Optional (agents SDK) | No | Runs agent |
| UI / business logic | As you need | Yes | No |
| Telnyx API key | Yes (telephony SDK) | Never | Uses key you connect |
| Session debug | — | — | [Sessions](/sessions) in console |

## Trust boundary (plain words)

- **Secret HMAC key** stays on your server (and in [API Keys](/credentials) reveal for operators). If it appears in a browser bundle, the integration is wrong.
- **Publishable key** is safe to embed. It identifies your tenant; it does not authorize minting by itself.
- **LiveKit join token** is short-lived. The browser may hold it only after your backend returns it.
- **Control plane URL** is used by your backend only — not by the voice SDK as a signing target.

## Console deep links

- Copy ready \`.env\` blocks: [API Keys](/credentials)  
- Inspect agent ids / assigned numbers: [Agents](/agents) (create via agents SDK)  

- After a test call, open [Sessions](/sessions) for duration, transcript, and end reason  
`;
