import { Room, RoomEvent, Track } from 'livekit-client';
import type { Participant, TranscriptionSegment } from 'livekit-client';

export interface AwaazLabsUvaVoiceOptions {
  /** Identifies the tenant/app; never authorises. Safe to ship in a public bundle. */
  publishableKey: string;
  /** The HOST platform's OWN server. It returns the short-lived session payload. */
  sessionEndpoint: string;
  /** Optional direct refresh endpoint; falls back to `<sessionEndpoint>/refresh` convention. */
  refreshEndpoint?: string;
}

export type UrduVoiceAgentOptions = AwaazLabsUvaVoiceOptions;

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

export type AwaazLabsUvaVoiceEvent =
  | 'transcript'
  | 'speaking'
  | 'error'
  | 'ended'
  | 'connected'
  | 'disconnected'
  | 'agent_speaking'
  | 'metrics_updated'
  | 'audio_blocked';

export type UvaEvent = AwaazLabsUvaVoiceEvent;

export type AwaazLabsUvaVoiceErrorCode = 'quota_exceeded' | 'agent_not_found' | 'session_failed';

export type UvaErrorCode = AwaazLabsUvaVoiceErrorCode;

export interface TranscriptEvent {
  /** Stable per-segment id from LiveKit — the same id recurs with updated `text`/`final` as a
   *  segment goes from interim to final. Use it to replace, not append, matching updates. */
  id: string;
  text: string;
  final: boolean;
  /** 'user' for the local mic's own transcript, 'agent' for anything from a remote participant. */
  speaker: 'user' | 'agent';
}

export interface MetricsEvent {
  type: 'metrics_updated' | 'turn_latency';
  [key: string]: unknown;
}

export class AwaazLabsUvaVoiceError extends Error {
  constructor(
    public readonly code: AwaazLabsUvaVoiceErrorCode,
    message?: string,
  ) {
    super(message ?? code);
    this.name = 'AwaazLabsUvaVoiceError';
  }
}

export { AwaazLabsUvaVoiceError as UvaError };

interface SessionResponse {
  token: string;
  wsUrl: string;
  roomName: string;
  refreshUrl?: string;
  expiresIn?: number;
}

export interface AwaazLabsUvaVoiceEventMap {
  transcript: [TranscriptEvent];
  speaking: [boolean];
  error: [AwaazLabsUvaVoiceError];
  ended: [unknown];
  connected: [];
  disconnected: [unknown];
  agent_speaking: [boolean];
  metrics_updated: [MetricsEvent];
  /** Per-turn stage breakdown emitted by the worker on every user turn (UVA-5). */
  turn_latency: [MetricsEvent];
  /**
   * Fired when the browser blocks audio autoplay (canPlaybackAudio=false) or
   * unblocks it (canPlaybackAudio=true). When blocked=true, show a user-visible
   * button and call agent.startAudio() inside its click handler.
   */
  audio_blocked: [boolean];
}

export type UvaEventMap = AwaazLabsUvaVoiceEventMap;

type Listener<TArgs extends unknown[] = unknown[]> = (...args: TArgs) => void;

export class AwaazLabsUvaVoice {
  private room: Room | null = null;
  private readonly listeners = new Map<AwaazLabsUvaVoiceEvent, Set<Listener>>();
  private readonly remoteAudioElements = new Map<string, HTMLMediaElement>();
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private session: SessionResponse | null = null;
  private state: ConnectionState = 'idle';

  static async listVoices(endpointUrl: string): Promise<Voice[]> {
    if (!endpointUrl.trim()) {
      throw new AwaazLabsUvaVoiceError('session_failed', 'voice catalog endpoint is required');
    }
    try {
      const res = await fetch(endpointUrl);
      if (!res.ok) {
        throw new AwaazLabsUvaVoiceError('session_failed', `Failed to fetch voices catalog: ${res.statusText}`);
      }
      return (await res.json()) as Voice[];
    } catch (e) {
      if (e instanceof AwaazLabsUvaVoiceError) throw e;
      throw new AwaazLabsUvaVoiceError('session_failed', `Failed to reach voices endpoint: ${String(e)}`);
    }
  }

  constructor(private readonly options: AwaazLabsUvaVoiceOptions) {

    if (!options.publishableKey.trim()) {
      throw new AwaazLabsUvaVoiceError('session_failed', 'publishableKey is required');
    }
    if (!options.sessionEndpoint.trim()) {
      throw new AwaazLabsUvaVoiceError('session_failed', 'sessionEndpoint is required');
    }
  }

  get connectionState(): ConnectionState {
    return this.state;
  }

  get isConnected(): boolean {
    return this.state === 'connected';
  }

  /** Whether the local microphone track is currently enabled. `false` when not connected. */
  get isMicMuted(): boolean {
    return this.room ? !this.room.localParticipant.isMicrophoneEnabled : false;
  }

  /** Enable/disable the local microphone track. No-op if not connected. */
  async setMicMuted(muted: boolean): Promise<void> {
    if (!this.room) return;
    await this.room.localParticipant.setMicrophoneEnabled(!muted);
  }

  async connect(opts: ConnectOptions): Promise<void> {
    if (this.room) {
      throw new AwaazLabsUvaVoiceError('session_failed', 'already connected - call disconnect() first');
    }
    if (!opts.agentId.trim()) {
      throw new AwaazLabsUvaVoiceError('session_failed', 'agentId is required');
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
        throw new AwaazLabsUvaVoiceError('quota_exceeded');
      }
      if (res.status === 404) {
        throw new AwaazLabsUvaVoiceError('agent_not_found');
      }
      if (!res.ok) {
        throw new AwaazLabsUvaVoiceError('session_failed');
      }
      const parsed = (await res.json()) as Partial<SessionResponse>;
      if (!parsed.token || !parsed.wsUrl || !parsed.roomName) {
        throw new AwaazLabsUvaVoiceError('session_failed', 'session endpoint returned an incomplete response');
      }
      body = parsed as SessionResponse;
    } catch (err) {
      this.state = 'idle';
      if (err instanceof AwaazLabsUvaVoiceError) throw err;
      throw new AwaazLabsUvaVoiceError('session_failed', 'could not reach sessionEndpoint');
    }

    const room = new Room();
    this.wireRoomEvents(room);

    try {
      await room.connect(body.wsUrl, body.token);
    } catch {
      this.state = 'idle';
      throw new AwaazLabsUvaVoiceError('session_failed', 'LiveKit connection failed');
    }

    try {
      await room.localParticipant.setMicrophoneEnabled(true);
    } catch {
      await room.disconnect();
      this.state = 'idle';
      throw new AwaazLabsUvaVoiceError('session_failed', 'microphone permission denied or unavailable');
    }

    this.room = room;
    this.session = body;
    this.scheduleTokenRefresh(body);
  }

  on<K extends AwaazLabsUvaVoiceEvent>(event: K, cb: Listener<AwaazLabsUvaVoiceEventMap[K]>): this {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(cb as Listener);
    return this;
  }

  off<K extends AwaazLabsUvaVoiceEvent>(event: K, cb: Listener<AwaazLabsUvaVoiceEventMap[K]>): this {
    this.listeners.get(event)?.delete(cb as Listener);
    return this;
  }

  async disconnect(): Promise<void> {
    this.clearRefreshTimer();
    if (!this.room) return;
    this.state = 'disconnecting';
    await this.room.disconnect();
    this.detachAllRemoteAudio();
    this.room = null;
    this.session = null;
    this.state = 'idle';
  }

  /**
   * Call this inside a user-gesture event handler (e.g. button click) when the
   * 'audio_blocked' event fires with blocked=true.
   * Browsers require a user interaction before they allow audio playback, so
   * the LiveKit Room's internal AudioContext must be resumed explicitly here.
   */
  async startAudio(): Promise<void> {
    if (this.room) {
      await this.room.startAudio();
    }
  }

  private emit<K extends AwaazLabsUvaVoiceEvent>(event: K, ...args: AwaazLabsUvaVoiceEventMap[K]): void {
    for (const cb of this.listeners.get(event) ?? []) {
      (cb as Listener<AwaazLabsUvaVoiceEventMap[K]>)(...args);
    }
  }

  private wireRoomEvents(room: Room): void {
    room.on(RoomEvent.Connected, () => {
      this.state = 'connected';
      this.emit('connected');
    });

    room.on(RoomEvent.Disconnected, (reason) => {
      this.clearRefreshTimer();
      this.detachAllRemoteAudio();
      this.room = null;
      this.session = null;
      this.state = 'idle';
      this.emit('disconnected', reason);
      this.emit('ended', reason);
    });

    room.on(
      RoomEvent.TranscriptionReceived,
      (segments: TranscriptionSegment[], participant?: Participant) => {
        const speaker: 'user' | 'agent' = participant?.isLocal ? 'user' : 'agent';
        for (const seg of segments) {
          this.emit('transcript', { id: seg.id, text: seg.text, final: seg.final, speaker });
        }
      },
    );

    room.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
      const agentSpeaking = speakers.some((speaker) => !speaker.isLocal);
      this.emit('speaking', speakers.length > 0);
      this.emit('agent_speaking', agentSpeaking);
    });

    // --- AUDIO PLAYBACK FIX ---
    // Explicitly subscribe to remote audio tracks and attach them to audio
    // elements. Without this, LiveKit's default audio playback relies on the
    // browser's AudioContext which is suspended until a user gesture.
    room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
      if (track.kind !== Track.Kind.Audio || participant.isLocal) {
        return;
      }
      const trackSid = track.sid ?? publication.trackSid;
      // track.attach() creates an <audio> element and pipes the MediaStream
      // into it. We then force .play() inside a try/catch so we always
      // attempt playback even if autoplay policy fires first.
      const el = track.attach();
      this.attachRemoteAudio(trackSid, el);
    });

    room.on(RoomEvent.TrackUnsubscribed, (track, publication) => {
      if (track.kind !== Track.Kind.Audio) {
        return;
      }
      const trackSid = track.sid ?? publication.trackSid;
      this.detachRemoteAudio(trackSid);
    });

    room.on(RoomEvent.MediaDevicesError, (error: Error) => {
      this.emit('error', new AwaazLabsUvaVoiceError('session_failed', error.message));
    });

    room.on(RoomEvent.RoomMetadataChanged, (metadata?: string) => {
      const metrics = this.tryParseMetrics(metadata);
      if (metrics) this.emitLatencyEvents(metrics);
    });

    room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
      const metrics = this.tryParseMetrics(this.decodePayload(payload));
      if (metrics) this.emitLatencyEvents(metrics);
    });

    // Browsers block audio autoplay without a prior user gesture.
    // LiveKit signals this via AudioPlaybackStatusChanged when its internal
    // HTMLAudioElement.play() promise rejects (NotAllowedError).
    // We forward it as 'audio_blocked' so the host app can show an
    // "Unlock Audio" button and call agent.startAudio() on click.
    room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      const blocked = !room.canPlaybackAudio;
      this.emit('audio_blocked', blocked);
    });
  }

  private attachRemoteAudio(trackSid: string, element: HTMLMediaElement): void {
    this.detachRemoteAudio(trackSid); // clean up any previous element for this sid
    element.autoplay = true;
    element.setAttribute('playsinline', 'true');
    element.style.display = 'none';
    document.body.appendChild(element);
    this.remoteAudioElements.set(trackSid, element);
    // Attempt .play() eagerly. If the browser blocks it (NotAllowedError),
    // LiveKit will fire AudioPlaybackStatusChanged, which we relay as 'audio_blocked'.
    void element.play().catch(() => {
      // Silently ignore — AudioPlaybackStatusChanged will handle the blocked state.
    });
  }

  private detachRemoteAudio(trackSid: string): void {
    const element = this.remoteAudioElements.get(trackSid);
    if (!element) return;
    try {
      element.pause();
      element.removeAttribute('src');
      element.load();
    } catch {
      // Best-effort cleanup.
    }
    element.remove();
    this.remoteAudioElements.delete(trackSid);
  }

  private detachAllRemoteAudio(): void {
    for (const trackSid of [...this.remoteAudioElements.keys()]) {
      this.detachRemoteAudio(trackSid);
    }
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
      this.emit('error', new AwaazLabsUvaVoiceError('session_failed', 'token refresh failed'));
    }
  }

  private resolveRefreshEndpoint(): string {
    if (this.session?.refreshUrl) {
      // A relative refreshUrl (e.g. control_plane's own "/v1/session/refresh", meant to be
      // rewritten by a proxying host backend before it ever reaches a browser — see
      // examples/host-backend's resolveRefreshUrl()) must resolve against the endpoint that
      // actually served it (sessionEndpoint), not the current page's origin. A bare
      // fetch('/v1/session/refresh') from the browser would otherwise hit the PAGE's own
      // origin, which has no such route. Already-absolute URLs pass through `new URL()`
      // unchanged regardless of the base, so this is a no-op for well-behaved host backends
      // that already rewrite it themselves.
      try {
        return new URL(this.session.refreshUrl, this.options.sessionEndpoint).toString();
      } catch {
        return this.session.refreshUrl;
      }
    }
    if (this.options.refreshEndpoint) return this.options.refreshEndpoint;
    if (this.options.sessionEndpoint.endsWith('/v1/session')) {
      return `${this.options.sessionEndpoint}/refresh`;
    }
    return `${this.options.sessionEndpoint.replace(/\/$/, '')}/refresh`;
  }

  private emitLatencyEvents(metrics: MetricsEvent): void {
    if (metrics.type === 'turn_latency') {
      this.emit('turn_latency', metrics);
    }
    if (metrics.type === 'metrics_updated' || metrics.type === 'turn_latency') {
      this.emit('metrics_updated', metrics);
    }
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

export { AwaazLabsUvaVoice as UrduVoiceAgent };
