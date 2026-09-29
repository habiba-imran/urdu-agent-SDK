export const meta = {
  slug: 'events-and-lifecycle',
  title: 'Events and lifecycle',
  eyebrow: 'Reference',
  description: 'Browser SDK events from connect through disconnect.',
};

export const markdown = `
## Lifecycle sketch

\`\`\`text
idle → connect() → connected → (speaking turns) → disconnected / ended
\`\`\`

Subscribe before \`connect\` so you do not miss early events:

\`\`\`ts
voice.on('connected', () => {});
voice.on('disconnected', (reason) => {});
voice.on('ended', (reason) => {});
voice.on('error', (error) => {});
\`\`\`

## Supported events

| Event | Payload |
|-------|---------|
| \`connected\` | none |
| \`disconnected\` | LiveKit reason when available |
| \`ended\` | same reason (convenience) |
| \`transcript\` | \`{ id, text, final, speaker }\` — replace earlier entries with the same \`id\` |
| \`speaking\` | \`boolean\` caller / room speaking |
| \`agent_speaking\` | \`boolean\` agent active speaker |
| \`audio_blocked\` | \`boolean\` — call \`startAudio()\` from a click when \`true\` |
| \`metrics_updated\` | metrics object from the worker |
| \`turn_latency\` | per-turn timing from the worker |
| \`error\` | \`AwaazLabsUvaVoiceError\` with a public \`code\` |

A throwing listener does not stop other listeners.

## Public error codes

| Code | Meaning |
|------|---------|
| \`quota_exceeded\` | Plan concurrency or monthly minutes (or opaque \`429\`) |
| \`rate_limit\` | Platform rate limit — back off |
| \`provider_limit\` | Upstream voice/LLM provider limit |
| \`worker_not_ready\` | Worker not ready yet |
| \`agent_not_found\` | Wrong or missing \`agentId\` |
| \`timeout\` | Host session endpoint exceeded \`fetchTimeoutMs\` |
| \`token_refresh_failed\` | Refresh rejected or retries exhausted |
| \`session_failed\` | Other session failure |

## Mapping to Sessions

Successful connects that reach the worker appear under **[Sessions](/sessions)**. Use Sessions when UI events and the console disagree.

## Related

- [What to expect](/docs/what-to-expect)  
- [Frontend setup](/docs/frontend-setup)  
`;
