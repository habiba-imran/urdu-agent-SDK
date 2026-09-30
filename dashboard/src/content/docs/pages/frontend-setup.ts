export const meta = {
  slug: 'frontend-setup',
  title: 'Frontend setup',
  eyebrow: 'Integrate',
  description: 'Install the voice client, connect, and handle call states.',
};

export const markdown = `
## Install

\`\`\`bash title=terminal
npm install @awaazlabs-uva/voice@1.1.0
\`\`\`

Browser / bundler only. Safe to import at module scope in Next.js — DOM access happens on connect.

## Connect

\`\`\`ts title=voice.ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

export const voice = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT,
  refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT,
});

export async function startCall(agentId: string) {
  await voice.connect({ agentId });
}

export async function endCall() {
  await voice.disconnect();
}
\`\`\`

Frontend env (from **[API Keys](/credentials)** + your host URL):

\`\`\`bash title=.env
VITE_UVA_PUBLISHABLE_KEY=uva_pk_xxxxxxxx
VITE_UVA_SESSION_ENDPOINT=http://localhost:3000/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3000/api/voice/session/refresh
VITE_UVA_AGENT_ID=agt_xxxxxxxx
\`\`\`

## States to handle in UI

| State | Signal | UX tip |
|-------|--------|--------|
| Idle | Before \`connect\` | Show Start call |
| Connecting | Awaiting \`connect\` promise | Spinner; disable double-tap |
| Connected | \`connected\` event / \`isConnected\` | Show mute / end |
| Agent speaking | \`agent_speaking\` → \`true\` | Optional waveform |
| User speaking | \`speaking\` → \`true\` | Optional mic indicator |
| Audio blocked | \`audio_blocked\` → \`true\` | Button that calls \`startAudio()\` |
| Ended | \`disconnected\` / \`ended\` | Reset UI |
| Failed | \`error\` | Map \`error.code\` — see troubleshooting |

Full event table: [Events and lifecycle](/docs/events-and-lifecycle).

## Microphone permission

Call \`connect\` from a **user gesture** (button click). Mic needs a secure context (\`https://\` or \`localhost\`).

If permission is denied, show a clear message and link to site settings — do not retry in a loop.

## Autoplay / audio blocked

Browsers may block playback until a gesture. Listen for \`audio_blocked\` and call \`voice.startAudio()\` from a button click.

## Minimal React example

\`\`\`tsx title=CallButton.tsx
'use client';
import { useEffect, useState } from 'react';
import { voice, startCall, endCall } from './voice';

export function CallButton({ agentId }: { agentId: string }) {
  const [status, setStatus] = useState<'idle' | 'live' | 'busy'>('idle');
  const [needAudio, setNeedAudio] = useState(false);

  useEffect(() => {
    const onConnected = () => setStatus('live');
    const onEnded = () => setStatus('idle');
    const onBlocked = (blocked: boolean) => setNeedAudio(blocked);
    voice.on('connected', onConnected);
    voice.on('disconnected', onEnded);
    voice.on('audio_blocked', onBlocked);
    return () => {
      voice.off('connected', onConnected);
      voice.off('disconnected', onEnded);
      voice.off('audio_blocked', onBlocked);
    };
  }, []);

  async function onStart() {
    setStatus('busy');
    try {
      await startCall(agentId);
    } catch (e) {
      console.error(e);
      setStatus('idle');
      alert('Could not start call — check mic permission and session endpoint.');
    }
  }

  return (
    <div>
      {needAudio ? (
        <button type="button" onClick={() => voice.startAudio()}>
          Enable audio
        </button>
      ) : null}
      {status === 'live' ? (
        <button type="button" onClick={() => endCall()}>End call</button>
      ) : (
        <button type="button" disabled={status === 'busy'} onClick={onStart}>
          {status === 'busy' ? 'Connecting…' : 'Start call'}
        </button>
      )}
    </div>
  );
}
\`\`\`

## After you connect

Verify the call in **[Sessions](/sessions)**. Inspect agent config on **[Agents](/agents)** (read-only; edit via the agents SDK).

Mint through **your** \`sessionEndpoint\` — [Test Studio](/test-studio) is an operator smoke path only ([Security](/docs/security)).
`;
