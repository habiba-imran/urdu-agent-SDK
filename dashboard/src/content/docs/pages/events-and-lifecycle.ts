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
| \`metrics_updated\` | metrics object from the runtime |
| \`turn_latency\` | per-turn timing from the runtime |
| \`connect_timing\` | session-mint vs LiveKit-join ms (diagnostics) |
| \`error\` | \`AwaazLabsUvaVoiceError\` with a public \`code\` |

A throwing listener does not stop other listeners.

## Public error codes

| Code | Meaning |
|------|---------|
| \`quota_exceeded\` | Plan concurrency or monthly minutes (or opaque \`429\`) |
| \`rate_limit\` | Platform rate limit — back off |
| \`provider_limit\` | Upstream voice/LLM provider limit |
| \`worker_not_ready\` | Session not ready yet — retry shortly |
| \`agent_not_found\` | Wrong or missing \`agentId\` |
| \`timeout\` | Host session endpoint exceeded \`fetchTimeoutMs\` |
| \`token_refresh_failed\` | Refresh rejected or retries exhausted |
| \`session_failed\` | Other session failure |

## Mapping to Sessions

Successful connects appear under **[Sessions](/sessions)**. Use Sessions when UI events and the console disagree.

## Related

- [What to expect](/docs/what-to-expect)
- [Frontend setup](/docs/frontend-setup)

## Current humanization SDK snapshot

The published voice \`1.1.0\` baseline does not contain the new \`audio_ready\` event. The independent client ships an unpublished \`1.1.1-humanization.0\` snapshot; Test Studio uses the current repository SDK. With that build, \`audio_ready: boolean\` reports browser playback readiness. \`connected\` reports room connection. Neither proves a specific utterance was heard. Continue to handle \`audio_blocked\` and unlock via \`startAudio()\` from a gesture.

Per-turn metrics are also forwarded to \`metrics_updated\` for legacy compatibility. If subscribing to both, handle a turn once:

\`\`\`ts
voice.on('turn_latency', (metrics) => {
  // Save outcome and correlation/version fields, when supplied.
  // Only completed outcomes belong in a completed-turn latency summary.
});
voice.on('metrics_updated', (metrics) => {
  if (metrics.type !== 'metrics_updated') return;
  // Update aggregate diagnostics.
});
\`\`\`

Current metrics can include policy/component identities, session/user-turn/assistant-turn/generation IDs and outcome. Fields are optional and arrive only when the runtime supplies them. A provider failure can emit \`session_failed\` after connection, followed by session closure. Keep error handlers active for the whole call. Full matrix: [Humanization testing](/docs/humanization-testing).
`;
