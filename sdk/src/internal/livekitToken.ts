/**
 * Apply a host-refreshed LiveKit JWT onto an already-connected Room (F-H12).
 *
 * livekit-client does not expose Room.updateToken. Reconnect / full-reconnect
 * reads RTCEngine's private `token`, and LiveKit Cloud region selection reads
 * RegionUrlProvider's token. Mirror the SDK's own TokenRefreshed path:
 * write engine.token, emit `tokenRefreshed` so Room updates regionUrlProvider,
 * and also call regionUrlProvider.updateToken directly when reachable.
 */

import type { Room } from 'livekit-client';

/** LiveKit EngineEvent.TokenRefreshed — keep as string to avoid tight coupling. */
const TOKEN_REFRESHED_EVENT = 'tokenRefreshed';

/** Minimal surface we write — avoids depending on private class field types. */
export type LiveKitTokenSink = {
  engine?: {
    token?: string;
    /** EventEmitter-style; Room listens for TokenRefreshed to sync regionUrlProvider. */
    emit?: (event: string, token: string) => void;
  };
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
    // Prefer Room's official TokenRefreshed path so regionUrlProvider stays in sync
    // even if the private field is renamed or inaccessible in a future livekit-client.
    if (typeof sink.engine.emit === 'function') {
      try {
        sink.engine.emit(TOKEN_REFRESHED_EVENT, token);
      } catch {
        // Best-effort; direct updateToken below still runs.
      }
    }
  }

  const provider = sink.regionUrlProvider;
  if (provider && typeof provider.updateToken === 'function') {
    provider.updateToken(token);
  }
}
