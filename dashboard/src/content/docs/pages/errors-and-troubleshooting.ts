export const meta = {
  slug: 'errors-and-troubleshooting',
  title: 'Errors and troubleshooting',
  eyebrow: 'Reference',
  description: 'Common failures when minting, connecting, or going live.',
};

export const markdown = `
## Session mint fails (4xx / 401)

| Check | Where |
|-------|--------|
| HMAC secret / tenant id mismatch | [API Keys](/credentials) vs backend env |
| Clock skew on \`X-Timestamp\` | Server NTP |
| Wrong nonce / agentId in canonical string | Must be \`{tenantId}.{timestamp}.{nonce}.{agentId}\` |
| Wrong control plane URL | API Keys → \`UVA_CONTROL_PLANE_URL\` |
| Publishable key rejected | Keys tab + request body |

Re-read signing in [Backend setup](/docs/backend-setup), or run \`host-backend-starter\` unchanged.

## Browser SDK error codes

| Code | Likely cause |
|------|----------------|
| \`agent_not_found\` | Bad \`agentId\` or wrong tenant |
| \`quota_exceeded\` | Concurrency or monthly minutes |
| \`rate_limit\` | Back off and retry |
| \`timeout\` | Host \`sessionEndpoint\` too slow / down |
| \`token_refresh_failed\` | Refresh route failing |
| \`worker_not_ready\` | Retry shortly |
| \`session_failed\` | Catch-all — check host logs |

## Browser connects but no audio

- Mic permission denied or insecure origin  
- \`audio_blocked\` — show a button that calls \`startAudio()\`  
- Wrong \`agentId\` — [Agents](/agents)  
- Mute via \`setMicMuted\`  
- Check [Sessions](/sessions) for worker-side errors  

## Connect hangs

- Your \`/api/voice/session\` is slow or CORS-blocked (\`HOST_ALLOWED_ORIGINS\`)  
- LiveKit \`wsUrl\` unreachable from the client network  
- Ad blockers interfering with WebRTC  

## Telephony: ring then silence

- Number not assigned to an agent — check [Agents](/agents); assign via \`@awaazlabs-uva/telephony\`  

- Telnyx connection incomplete  
- Confirm inbound session row in [Sessions](/sessions)  

## Still stuck

1. Reproduce once and note timestamps.  
2. Open the matching row in Sessions.  
3. Confirm env against API Keys (no trailing spaces / wrong tenant).  
4. See [Security](/docs/security) if you suspect a leaked secret (rotate immediately).
`;
