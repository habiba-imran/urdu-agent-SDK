/**
 * Apply a host-refreshed LiveKit JWT onto an already-connected Room (F-H12).
 *
 * livekit-client does not expose Room.updateToken. Reconnect / full-reconnect
 * reads RTCEngine's private `token`, and LiveKit Cloud region selection reads
 * RegionUrlProvider's token. Mirror the SDK's own TokenRefreshed path.
 */

import type { Room } from 'livekit-client';

/** Minimal surface we write — avoids depending on private class field types. */
export type LiveKitTokenSink = {
  engine?: { token?: string };
  regionUrlProvider?: { updateToken?: (token: string) => void };
  /** Hypothetical future / alternate SDK surface — call if present. */
  updateToken?: (token: string) => void | Promise<void>;
};

export async function applyRefreshedLiveKitToken(
  room: Room | LiveKitTokenSink | null | undefined,
  token: string,
): Promise<void> {
  if (!room || !token) return;

  const sink = room as LiveKitTokenSink;

  if (typeof sink.updateToken === 'function') {
    await sink.updateToken(token);
  }

  if (sink.engine && typeof sink.engine === 'object') {
    sink.engine.token = token;
  }

  const provider = sink.regionUrlProvider;
  if (provider && typeof provider.updateToken === 'function') {
    provider.updateToken(token);
  }
}
