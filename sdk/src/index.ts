// UrduVoiceAgent client SDK — PUBLIC SURFACE STUB (Phase 4 scaffold, docs/24-PHASE-4-CLIENT-SDK.md).
//
// This bundle ships into a THIRD-PARTY app and is assumed fully decompiled on day one, so it holds
// ZERO secrets (no API key, no HMAC secret, no LiveKit secret). It talks only to the HOST platform's
// own session endpoint (which holds THEIR HMAC secret and calls our mint) and then to LiveKit.
//
// Only the public TYPE surface + exact event/error names are defined here (per docs/24). The actual
// transport/session wiring (livekit-client) is Phase-4 real work, done AFTER Phase 3's Gate-3
// confirms the session/token contract — hence the not-implemented throws. Nothing here depends on
// Phase 3 internals.

export interface UrduVoiceAgentOptions {
  /** Identifies the tenant/app; never authorises. Safe to ship in a public bundle. */
  publishableKey: string;
  /** The HOST platform's OWN server (holds their HMAC secret, calls our mint). NOT our server. */
  sessionEndpoint: string;
}

export interface ConnectOptions {
  agentId: string;
}

/** Typed events (docs/24) — exact names, do not rename. */
export type UvaEvent = 'transcript' | 'speaking' | 'error' | 'ended';

/** Error taxonomy (docs/24) — public codes only; never leak internal detail. */
export type UvaErrorCode = 'quota_exceeded' | 'agent_not_found' | 'session_failed';

export class UvaError extends Error {
  constructor(
    public readonly code: UvaErrorCode,
    message?: string,
  ) {
    super(message ?? code);
    this.name = 'UvaError';
  }
}

export class UrduVoiceAgent {
  constructor(private readonly options: UrduVoiceAgentOptions) {}

  /**
   * Phase 4 (P4-T01/T02, post-Gate-3): POST `options.sessionEndpoint` (the host server) to obtain
   * `{ token, wsUrl, roomName }`, then connect via livekit-client. The SDK never calls a provider
   * and never holds a secret.
   */
  async connect(_opts: ConnectOptions): Promise<void> {
    throw new Error('not implemented — Phase 4 (P4-T01/T02), pending Phase-3 Gate-3');
  }

  /** Phase 4 (P4-T03): typed event subscription. */
  on(_event: UvaEvent, _cb: (...args: unknown[]) => void): this {
    throw new Error('not implemented — Phase 4 (P4-T03)');
  }

  /** Phase 4 (P4-T02): tear down the LiveKit connection. */
  async disconnect(): Promise<void> {
    throw new Error('not implemented — Phase 4 (P4-T02)');
  }
}
