// UrduVoiceAgent client SDK (docs/24-PHASE-4-CLIENT-SDK.md).
//
// This bundle ships into a THIRD-PARTY app and is assumed fully decompiled on day one, so it holds
// ZERO secrets (no API key, no HMAC secret, no LiveKit secret). It talks only to the HOST
// platform's own session endpoint (which holds THEIR HMAC secret and calls our control-plane mint)
// and then to LiveKit directly via livekit-client. It never calls Uplift/Gladia/Gemini/Supabase.

import { Room, RoomEvent } from 'livekit-client';
import type { Participant, TranscriptionSegment } from 'livekit-client';

export interface UrduVoiceAgentOptions {
  /** Identifies the tenant/app; never authorises. Safe to ship in a public bundle. */
  publishableKey: string;
  /** The HOST platform's OWN server (holds their HMAC secret, calls our mint). NOT our server. */
  sessionEndpoint: string;
  /** Optional direct refresh endpoint; falls back to `<sessionEndpoint>/refresh` convention. */
  refreshEndpoint?: string;
}

export interface ConnectOptions {
  agentId: string;
  voiceId?: string;
}

export interface Voice {
  id: string;
  displayName: string;
  gender: 'male' | 'female' | 'unspecified';
  previewUrl?: string | null;
  artworkUrl?: string | null;
  enabled: boolean;
}


export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'disconnecting';

export type UvaEvent =
  | 'transcript'
  | 'speaking'
  | 'error'
  | 'ended'
  | 'connected'
  | 'disconnected'
  | 'agent_speaking'
  | 'metrics_updated';

export type UvaErrorCode = 'quota_exceeded' | 'agent_not_found' | 'session_failed';

export interface TranscriptEvent {
  text: string;
  final: boolean;
}

export interface MetricsEvent {
  type: 'metrics_updated' | 'turn_latency';
  [key: string]: unknown;
}

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
  refreshUrl?: string;
  expiresIn?: number;
}

export interface UvaEventMap {
  transcript: [TranscriptEvent];
  speaking: [boolean];
  error: [UvaError];
  ended: [unknown];
  connected: [];
  disconnected: [unknown];
  agent_speaking: [boolean];
  metrics_updated: [MetricsEvent];
}

type Listener<TArgs extends unknown[] = unknown[]> = (...args: TArgs) => void;

export class UrduVoiceAgent {
  private room: Room | null = null;
  private readonly listeners = new Map<UvaEvent, Set<Listener>>();
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private session: SessionResponse | null = null;
  private state: ConnectionState = 'idle';

  static async listVoices(
    endpointUrl = 'https://uva-control-plane.onrender.com/v1/voices'
  ): Promise<Voice[]> {
    try {
      const res = await fetch(endpointUrl);
      if (!res.ok) {
        throw new UvaError('session_failed', `Failed to fetch voices catalog: ${res.statusText}`);
      }
      return (await res.json()) as Voice[];
    } catch (e) {
      if (e instanceof UvaError) throw e;
      throw new UvaError('session_failed', `Failed to reach voices endpoint: ${String(e)}`);
    }
  }

  constructor(private readonly options: UrduVoiceAgentOptions) {

    if (!options.publishableKey.trim()) {
      throw new UvaError('session_failed', 'publishableKey is required');
    }
    if (!options.sessionEndpoint.trim()) {
      throw new UvaError('session_failed', 'sessionEndpoint is required');
    }
  }

  get connectionState(): ConnectionState {
    return this.state;
  }

  get isConnected(): boolean {
    return this.state === 'connected';
  }

  async connect(opts: ConnectOptions): Promise<void> {
    if (this.room) {
      throw new UvaError('session_failed', 'already connected - call disconnect() first');
    }
    if (!opts.agentId.trim()) {
      throw new UvaError('session_failed', 'agentId is required');
    }

    this.state = 'connecting';

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
      this.state = 'idle';
      if (err instanceof UvaError) throw err;
      throw new UvaError('session_failed', 'could not reach sessionEndpoint');
    }

    const room = new Room();
    this.wireRoomEvents(room);

    try {
      await room.connect(body.wsUrl, body.token);
    } catch {
      this.state = 'idle';
      throw new UvaError('session_failed', 'LiveKit connection failed');
    }

    try {
      await room.localParticipant.setMicrophoneEnabled(true);
    } catch {
      await room.disconnect();
      this.state = 'idle';
      throw new UvaError('session_failed', 'microphone permission denied or unavailable');
    }

    this.room = room;
    this.session = body;
    this.scheduleTokenRefresh(body);
  }

  on<K extends UvaEvent>(event: K, cb: Listener<UvaEventMap[K]>): this {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(cb as Listener);
    return this;
  }

  off<K extends UvaEvent>(event: K, cb: Listener<UvaEventMap[K]>): this {
    this.listeners.get(event)?.delete(cb as Listener);
    return this;
  }

  async disconnect(): Promise<void> {
    this.clearRefreshTimer();
    if (!this.room) return;
    this.state = 'disconnecting';
    await this.room.disconnect();
    this.room = null;
    this.session = null;
    this.state = 'idle';
  }

  private emit<K extends UvaEvent>(event: K, ...args: UvaEventMap[K]): void {
    for (const cb of this.listeners.get(event) ?? []) {
      (cb as Listener<UvaEventMap[K]>)(...args);
    }
  }

  private wireRoomEvents(room: Room): void {
    room.on(RoomEvent.Connected, () => {
      this.state = 'connected';
      this.emit('connected');
    });

    room.on(RoomEvent.Disconnected, (reason) => {
      this.clearRefreshTimer();
      this.room = null;
      this.session = null;
      this.state = 'idle';
      this.emit('disconnected', reason);
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
      const agentSpeaking = speakers.some((speaker) => !speaker.isLocal);
      this.emit('speaking', speakers.length > 0);
      this.emit('agent_speaking', agentSpeaking);
    });

    room.on(RoomEvent.MediaDevicesError, (error: Error) => {
      this.emit('error', new UvaError('session_failed', error.message));
    });

    room.on(RoomEvent.RoomMetadataChanged, (metadata?: string) => {
      const metrics = this.tryParseMetrics(metadata);
      if (metrics) this.emit('metrics_updated', metrics);
    });

    room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
      const metrics = this.tryParseMetrics(this.decodePayload(payload));
      if (metrics) this.emit('metrics_updated', metrics);
    });
  }

  private scheduleTokenRefresh(session: SessionResponse): void {
    this.clearRefreshTimer();
    const ttlSeconds = session.expiresIn ?? 120;
    const refreshDelayMs = Math.max(5_000, (ttlSeconds - 60) * 1000);
    this.refreshTimer = setTimeout(() => {
      void this.refreshToken();
    }, refreshDelayMs);
  }

  private clearRefreshTimer(): void {
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  private async refreshToken(): Promise<void> {
    if (!this.room || !this.session) return;
    const refreshEndpoint = this.resolveRefreshEndpoint();
    try {
      const res = await fetch(refreshEndpoint, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.session.token}`,
        },
      });
      if (!res.ok) throw new Error('refresh failed');
      const parsed = (await res.json()) as Partial<SessionResponse>;
      if (!parsed.token || !parsed.wsUrl || !parsed.roomName) {
        throw new Error('refresh response incomplete');
      }
      this.session = {
        token: parsed.token,
        wsUrl: parsed.wsUrl,
        roomName: parsed.roomName,
        refreshUrl: parsed.refreshUrl ?? this.session.refreshUrl,
        expiresIn: parsed.expiresIn ?? this.session.expiresIn,
      };
      const tokenUpdater = this.room as Room & { updateToken?: (token: string) => Promise<void> };
      if (typeof tokenUpdater.updateToken === 'function') {
        await tokenUpdater.updateToken(this.session.token);
      }
      this.scheduleTokenRefresh(this.session);
    } catch {
      this.emit('error', new UvaError('session_failed', 'token refresh failed'));
    }
  }

  private resolveRefreshEndpoint(): string {
    if (this.session?.refreshUrl) return this.session.refreshUrl;
    if (this.options.refreshEndpoint) return this.options.refreshEndpoint;
    if (this.options.sessionEndpoint.endsWith('/v1/session')) {
      return `${this.options.sessionEndpoint}/refresh`;
    }
    return `${this.options.sessionEndpoint.replace(/\/$/, '')}/refresh`;
  }

  private decodePayload(payload: Uint8Array): string {
    try {
      return new TextDecoder().decode(payload);
    } catch {
      return '';
    }
  }

  private tryParseMetrics(text?: string): MetricsEvent | null {
    if (!text) return null;
    try {
      const parsed = JSON.parse(text) as { type?: string };
      if (parsed.type === 'metrics_updated' || parsed.type === 'turn_latency') {
        return parsed as MetricsEvent;
      }
      return null;
    } catch {
      return null;
    }
  }
}
