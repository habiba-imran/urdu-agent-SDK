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
| Empty tenant \`allowed_origins\` (hosted) | [API Keys](/credentials) — mint fails closed until you set origins |
| Origin not on the allowlist | Browser \`Origin\` must match an entry on the tenant |

Re-read signing in [Backend setup](/docs/backend-setup) and origins in [Security](/docs/security).

## Browser SDK error codes

| Code | Likely cause |
|------|----------------|
| \`agent_not_found\` | Bad \`agentId\` or wrong tenant — confirm on [Agents](/agents) |
| \`quota_exceeded\` | Concurrency or monthly minutes |
| \`rate_limit\` | Back off and retry |
| \`provider_limit\` | Upstream STT/LLM/TTS provider limit (not your plan quota) |
| \`timeout\` | Host \`sessionEndpoint\` too slow / down |
| \`token_refresh_failed\` | Your refresh route failing (not Test Studio) |
| \`worker_not_ready\` | Retry shortly |
| \`session_failed\` | Catch-all — check host logs + [Sessions](/sessions) |

## Browser connects but no audio

- Mic permission denied or insecure origin  
- \`audio_blocked\` — show a button that calls \`startAudio()\`  
- Wrong \`agentId\` — [Agents](/agents)  
- Mute via \`setMicMuted\`  
- Check [Sessions](/sessions) for session-side errors  

## Connect hangs

- Your \`/api/voice/session\` is slow or CORS-blocked (\`HOST_ALLOWED_ORIGINS\` on **your** host)  
- LiveKit \`wsUrl\` unreachable from the client network  
- Ad blockers interfering with WebRTC  
- UVA \`allowed_origins\` empty or mismatched (hosted fail-closed)  

## Telephony: ring then silence

- Number not assigned to an agent — check [Agents](/agents); assign via \`@awaazlabs-uva/telephony\`  
- Telnyx connection incomplete  
- Confirm inbound session row in [Sessions](/sessions)  

## Telephony: outbound rejected

| Code / signal | Likely cause |
|---------------|----------------|
| \`outbound_destination_disabled\` | Destination country not on the platform outbound whitelist |
| \`outbound_not_ready\` / readiness reasons | Run \`getOutboundReadiness()\` — connect Telnyx, number, SIP profile first |
| Regulatory / KYC / balance errors | Complete requirements in Telnyx Mission Control, then retry purchase |

See [Telephony](/docs/telephony).

## Test Studio vs host mint

| Symptom | Meaning |
|---------|---------|
| Test Studio works; your app fails | Host signing, origins, or \`sessionEndpoint\` — not the platform |
| Both fail | Keys, agent id, quotas, or control plane URL — check [API Keys](/credentials) |

Test Studio is an **operator** smoke path. Customer apps must mint from **their** backend ([Frontend setup](/docs/frontend-setup)).

## Still stuck

1. Reproduce once and note timestamps.  
2. Open the matching row in Sessions.  
3. Confirm env against API Keys (no trailing spaces / wrong tenant).  
4. See [Security](/docs/security) if you suspect a leaked secret (ask AwaazLabs to rotate via admin — not the console).
`;
