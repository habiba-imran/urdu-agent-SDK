export const meta = {
  slug: 'what-to-expect',
  title: 'What to expect',
  eyebrow: 'Get started',
  description: 'Lifecycle, timing, ownership, limits, and how sessions end.',
};

export const markdown = `
## Call lifecycle

| Stage | What happens | Typical events |
|-------|----------------|----------------|
| Connect | Your host mints; SDK joins LiveKit | \`connected\` (or \`error\`) |
| Greeting | Agent speaks first if \`firstSpeaker: 'agent'\` | \`agent_speaking\` |
| Conversation | Turn-taking + optional transcripts | \`speaking\`, \`agent_speaking\`, \`transcript\` |
| End | Hangup, timeout, or error | \`disconnected\` / \`ended\` |

Catalog: [Events and lifecycle](/docs/events-and-lifecycle).

## Timing

We do not publish hard SLAs here. Expect:

- **Connection** (click → \`connected\`): usually a few seconds (network + region)  
- **First agent audio**: follows your agent greeting settings  

Use **[Sessions](/sessions)** on test calls to set your own baselines before launch. The SDK also emits \`turn_latency\` / \`metrics_updated\` when the worker provides them.

## What you handle vs. what the SDK handles

| Topic | You | SDK / runtime |
|-------|-----|----------------|
| Mic permission UX | Yes | Fails connect if denied |
| Token refresh | Host \`/api/voice/session/refresh\` | Retries with backoff until expiry |
| Reconnect after blip | Optional product UX | LiveKit best-effort |
| Autoplay block | \`startAudio()\` from a click | Emits \`audio_blocked\` |
| Interruptions | Product / agent config | Runtime barge-in support |
| Silence / max duration | Product policy | Runtime may end; see Sessions |
| HMAC signing | Your backend | Control plane verifies |

## Limits

Concurrency, max session length, and mint rate limits are tenant / plan specific. Numbers are intentionally omitted so this page stays accurate — check your agreement or support for higher caps. \`quota_exceeded\` and \`rate_limit\` surface in the browser SDK when caps hit.

## Session end reasons

Open **[Sessions](/sessions)** after a call. Common meanings:

| Status / reason | Meaning |
|-----------------|---------|
| Completed / ended normally | Clean hangup |
| Error / failed | Mint, media, or worker failure |
| Timeout / silence | Idle or max-length policy |
| Cancelled / early disconnect | Client left early |

Treat Sessions as source of truth for a given call.

## Versioning

- Pin npm versions in lockfiles.  
- Breaking API changes ship as major bumps with changelog notes.  
- After upgrading voice or your host starter, re-run Quickstart mint + connect.
`;
