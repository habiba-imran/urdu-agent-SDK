// UrduVoiceAgent client SDK (docs/24-PHASE-4-CLIENT-SDK.md).
//
// This bundle ships into a THIRD-PARTY app and is assumed fully decompiled on day one, so it holds
// ZERO secrets (no API key, no HMAC secret, no LiveKit secret). It talks only to the HOST
// platform's own session endpoint (which holds THEIR HMAC secret and calls our control-plane mint)
// and then to LiveKit directly via livekit-client. It never calls Uplift/Gladia/Gemini/Supabase.
//
// Session contract (this SDK's own public contract for `sessionEndpoint` — the host's server is
// expected to call our control plane's `POST /v1/session` (control_plane/app.py) and relay its
// JSON response verbatim): on success, `{ token: string, wsUrl: string, roomName: string }`
// (exactly what `control_plane.mint.mint_session` returns); on failure, any non-2xx status.
//
// API verified against installed livekit-client 2.x source (sdk/node_modules/livekit-client):
//   Room.connect(url, token, opts)               — dist/livekit-client.esm.mjs L16405-16408
//   RoomEvent.Connected = "connected"             — L12103
//   RoomEvent.Disconnected = "disconnected"       — L12130
//   RoomEvent.TranscriptionReceived (segments, participant, publication) — L30465-30467
//   RoomEvent.ActiveSpeakersChanged (Array<Participant>), loudest-first  — L12238-12245
//   RoomEvent.MediaDevicesError (error: Error)    — L12360-12364
//   LocalParticipant.setMicrophoneEnabled(enabled, opts?, publishOpts?)
//     — dist/src/room/participant/LocalParticipant.d.ts L95-100

import { Room, RoomEvent } from 'livekit-client';
import type { Participant, TranscriptionSegment } from 'livekit-client';

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

interface SessionResponse {
  token: string;
  wsUrl: string;
  roomName: string;
}

type Listener = (...args: unknown[]) => void;

export class UrduVoiceAgent {
  private room: Room | null = null;
  private readonly listeners = new Map<UvaEvent, Set<Listener>>();

  constructor(private readonly options: UrduVoiceAgentOptions) {}

  /**
   * POSTs `options.sessionEndpoint` (the HOST's own server) for a scoped join token, then connects
   * via livekit-client. Never calls a provider directly; never holds or transmits a secret of ours.
   */
  async connect(opts: ConnectOptions): Promise<void> {
    if (this.room) {
      throw new UvaError('session_failed', 'already connected — call disconnect() first');
    }

    let body: SessionResponse;
    try {
      const res = await fetch(this.options.sessionEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          publishableKey: this.options.publishableKey,
          agentId: opts.agentId,
        }),
      });
      if (res.status === 429) {
        throw new UvaError('quota_exceeded');
      }
      if (res.status === 404) {
        throw new UvaError('agent_not_found');
      }
      if (!res.ok) {
        throw new UvaError('session_failed');
      }
      const parsed = (await res.json()) as Partial<SessionResponse>;
      if (!parsed.token || !parsed.wsUrl || !parsed.roomName) {
        throw new UvaError('session_failed', 'session endpoint returned an incomplete response');
      }
      body = parsed as SessionResponse;
    } catch (err) {
      if (err instanceof UvaError) throw err;
      // Network failure, JSON parse failure, etc. — never leak the raw error into the public
      // taxonomy; the internal `err` is intentionally dropped, not attached to UvaError.
      throw new UvaError('session_failed', 'could not reach sessionEndpoint');
    }

    const room = new Room();
    this.wireRoomEvents(room);

    try {
      await room.connect(body.wsUrl, body.token);
    } catch {
      throw new UvaError('session_failed', 'LiveKit connection failed');
    }

    try {
      // A voice agent that can't hear the caller isn't a working session — fail connect()
      // outright rather than leaving a silent, half-open room.
      await room.localParticipant.setMicrophoneEnabled(true);
    } catch {
      await room.disconnect();
      throw new UvaError('session_failed', 'microphone permission denied or unavailable');
    }

    this.room = room;
  }

  /** Typed event subscription. */
  on(event: UvaEvent, cb: Listener): this {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(cb);
    return this;
  }

  /** Tear down the LiveKit connection. */
  async disconnect(): Promise<void> {
    if (!this.room) return;
    await this.room.disconnect();
    this.room = null;
  }

  private emit(event: UvaEvent, ...args: unknown[]): void {
    for (const cb of this.listeners.get(event) ?? []) {
      cb(...args);
    }
  }

  private wireRoomEvents(room: Room): void {
    room.on(RoomEvent.Disconnected, (reason) => {
      this.room = null;
      this.emit('ended', reason);
    });

    room.on(
      RoomEvent.TranscriptionReceived,
      (segments: TranscriptionSegment[]) => {
        for (const seg of segments) {
          this.emit('transcript', { text: seg.text, final: seg.final });
        }
      },
    );

    room.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
      this.emit('speaking', speakers.length > 0);
    });

    room.on(RoomEvent.MediaDevicesError, (error: Error) => {
      // Post-connect device failures (mic unplugged mid-call, permission revoked, etc.) surface
      // as an 'error' event rather than throwing — the session may still be partially usable.
      this.emit('error', new UvaError('session_failed', error.message));
    });
  }
}
