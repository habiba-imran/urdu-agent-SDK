import { Room, RoomEvent, Track } from 'livekit-client';
import type { AudioCaptureOptions, Participant, TranscriptionSegment } from 'livekit-client';
import {
  AwaazLabsUvaVoiceError,
  mapSessionHttpError,
  type AwaazLabsUvaVoiceErrorCode,
} from './internal/errors.js';
import { DEFAULT_FETCH_TIMEOUT_MS, fetchTextWithTimeout, withDeadline } from './internal/http.js';
import { applyRefreshedLiveKitToken } from './internal/livekitToken.js';

/**
 * Prefer browser AEC/NS so agent TTS on speakers is less likely to re-enter the mic
 * and trip worker-side Silero barge-in (mid-reply flicker / stuck speech).
 */
const MIC_CAPTURE_OPTIONS: AudioCaptureOptions = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

export type { AwaazLabsUvaVoiceErrorCode };
export { AwaazLabsUvaVoiceError };
export { AwaazLabsUvaVoiceError as UvaError };
export type UvaErrorCode = AwaazLabsUvaVoiceErrorCode;

export interface AwaazLabsUvaVoiceOptions {
  /** Identifies the tenant/app; never authorises. Safe to ship in a public bundle. */
  publishableKey: string;
  /** The HOST platform's OWN server. It returns the short-lived session payload. */
  sessionEndpoint: string;
  /** Optional direct refresh endpoint; falls back to `<sessionEndpoint>/refresh` convention. */
  refreshEndpoint?: string;
  /**
   * Extra headers on session mint (and merged into refresh). Use for dashboard Test Studio
   * portal JWT — production hosts should not need this; auth belongs on your session endpoint.
   */
  sessionHeaders?: HeadersInit | (() => HeadersInit | Promise<HeadersInit>);
  /**
   * Fetch credentials for session mint/refresh. Portal Test Studio should use ``include``
   * so the HttpOnly portal cookie is sent (P1-H6). Default ``same-origin``.
   */
  sessionCredentials?: RequestCredentials;
  /**
   * Max wait for session / refresh / voice-catalog `fetch` (F-M14).
   * Default: 15000 ms.
   */
  fetchTimeoutMs?: number;
  /** Maximum wait for the worker to start its pipeline (default 30 seconds). */
  agentReadyTimeoutMs?: number;
}

export type UrduVoiceAgentOptions = AwaazLabsUvaVoiceOptions;

export interface ConnectOptions {
  agentId: string;
  voiceId?: string;
}

/** Browser-side split of room_connected: session mint HTTP vs LiveKit room.connect. */
export interface ConnectTiming {
  mintMs: number;
  livekitConnectMs: number;
  /** Hostname from session wsUrl — use to spot far LiveKit regions. */
  livekitUrlHost?: string;
  /** Local participant connection quality right after join, when available. */
  connectionQuality?: string;
}

export interface Voice {
  id: string;
  displayName: string;
  gender: 'male' | 'female' | 'unspecified';
  previewUrl?: string | null;
  artworkUrl?: string | null;
  enabled: boolean;
}


export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'disconnecting';

export type AwaazLabsUvaVoiceEvent =
  | 'transcript'
  | 'speaking'
  | 'error'
  | 'ended'
  | 'connected'
  | 'connect_timing'
  | 'disconnected'
  | 'agent_speaking'
  | 'metrics_updated'
  | 'audio_blocked'
  | 'audio_ready'
  | 'turn_latency'
  | 'connection_state_changed'
  | 'session_outcome';

export type UvaEvent = AwaazLabsUvaVoiceEvent;

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
  /** Stable structural correlation, added by Phase 1 workers. Older workers omit it. */
  session_id?: string;
  user_turn_id?: string | null;
  assistant_turn_id?: string;
  generation_id?: string;
  humanization_policy_version?: string;
  outcome?: 'completed' | 'interrupted' | 'cancelled' | 'cancelled_speculation'
    | 'provider_error' | 'tool_error' | 'tool_timeout' | 'tool_outcome_unknown'
    | 'false_interruption' | 'stale';
  sequence?: number;
  monotonicAt?: number;
  latencyKind?: 'server_diagnostic_proxy';
  stages?: Record<string, number | null>;
  providerSnapshot?: Record<string, unknown>;
  tools?: Array<Record<string, unknown>>;
  generations?: Array<Record<string, unknown>>;
  sampleCounts?: Record<string, number>;
  percentiles?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface SessionOutcome {
  type: string;
  reason?: string;
  stage?: string;
  code?: string;
  session_id?: string;
}

interface SessionResponse {
  sessionId?: string;
  token: string;
  wsUrl: string;
  roomName: string;
  refreshUrl?: string;
  expiresIn?: number;
}

export interface AwaazLabsUvaVoiceEventMap {
  connection_state_changed: [ConnectionState];
  session_outcome: [SessionOutcome];
  transcript: [TranscriptEvent];
  speaking: [boolean];
  error: [AwaazLabsUvaVoiceError];
  ended: [unknown];
  connected: [];
  /** Fired just before `connected` with mint vs LiveKit join split (room_connected diagnosis). */
  connect_timing: [ConnectTiming];
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
  /** Playback permission, independent of room connection; not proof a phrase was heard. */
  audio_ready: [boolean];
}

export type UvaEventMap = AwaazLabsUvaVoiceEventMap;

type Listener<TArgs extends unknown[] = unknown[]> = (...args: TArgs) => void;

/** Coerce session expiresIn to a positive second count (default 120). */
function normalizeExpiresInSec(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n) || n <= 0) return 120;
  // Guard against hosts that accidentally send milliseconds (e.g. 120000).
  if (n > 10_000) return Math.round(n / 1000);
  return Math.round(n);
}

export class AwaazLabsUvaVoice {
  private room: Room | null = null;
  private generation = 0;
  private connectController: AbortController | null = null;
  private refreshController: AbortController | null = null;
  private readyRoom: Room | null = null;
  private readyResolve: (() => void) | null = null;
  private terminalOutcome: SessionOutcome | null = null;
  private disconnectReason: unknown;
  private metricSequences = new Map<string, number>();

  private setState(state: ConnectionState): void {
    if (this.state === state) return;
    this.state = state;
    this.emit('connection_state_changed', state);
  }

  private owns(room: Room, generation: number): boolean {
    return this.room === room && this.generation === generation;
  }

  private observeAgent(room: Room): void {
    // Native agent state can be "listening" before its provider handshake finishes.
    // Only the worker's authenticated awaaz_agent_ready packet establishes readiness.
    void room;
  }

  private markAgentReady(room: Room): void {
    if (this.room !== room) return;
    this.readyRoom = room;
    this.readyResolve?.();
  }

  private readonly listeners = new Map<AwaazLabsUvaVoiceEvent, Set<Listener>>();
  private readonly remoteAudioElements = new Map<string, HTMLMediaElement>();
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  /** Prevents overlapping refresh loops (timer + retry must not stack). */
  private refreshInFlight = false;
  private session: SessionResponse | null = null;
  /** Wall clock when `session` was last received (connect or successful refresh). */
  private sessionReceivedAt: number | null = null;
  private state: ConnectionState = 'idle';
  /** Last emitted speaking flags — skip no-op ActiveSpeakersChanged churn. */
  private lastCallerSpeaking: boolean | null = null;
  private lastAgentSpeaking: boolean | null = null;
  private lastConnectTiming: ConnectTiming | null = null;
  private playbackReady = false;
  private readonly blockedRemoteAudio = new Set<string>();

  static async listVoices(endpointUrl: string, timeoutMs: number = DEFAULT_FETCH_TIMEOUT_MS): Promise<Voice[]> {
    if (!endpointUrl.trim()) {
      throw new AwaazLabsUvaVoiceError('session_failed', 'voice catalog endpoint is required');
    }
    try {
      const { response, text } = await fetchTextWithTimeout(endpointUrl, undefined, timeoutMs);
      if (!response.ok) throw mapSessionHttpError(response.status, text || response.statusText);
      return JSON.parse(text) as Voice[];
    } catch (e) {
      if (e instanceof AwaazLabsUvaVoiceError) throw e;
      throw new AwaazLabsUvaVoiceError('session_failed', `Failed to reach voices endpoint: ${String(e)}`);
    }
  }

  constructor(private readonly options: AwaazLabsUvaVoiceOptions) {

    for (const value of [options.fetchTimeoutMs, options.agentReadyTimeoutMs]) {
      if (value !== undefined && (!Number.isFinite(value) || value <= 0)) {
        throw new AwaazLabsUvaVoiceError('session_failed', 'Timeouts must be positive finite milliseconds');
      }
    }
    if (!options.publishableKey.trim()) {
      throw new AwaazLabsUvaVoiceError('session_failed', 'publishableKey is required');
    }
    if (!options.sessionEndpoint.trim()) {
      throw new AwaazLabsUvaVoiceError('session_failed', 'sessionEndpoint is required');
    }
  }

  private get fetchTimeoutMs(): number {
    return this.options.fetchTimeoutMs ?? DEFAULT_FETCH_TIMEOUT_MS;
  }

  private async resolveSessionHeaders(): Promise<Record<string, string>> {
    const raw = this.options.sessionHeaders;
    if (!raw) return {};
    const resolved = typeof raw === 'function' ? await raw() : raw;
    if (resolved instanceof Headers) {
      const out: Record<string, string> = {};
      resolved.forEach((value, key) => {
        out[key] = value;
      });
      return out;
    }
    if (Array.isArray(resolved)) {
      return Object.fromEntries(resolved);
    }
    return { ...resolved };
  }

  get connectionState(): ConnectionState {
    return this.state;
  }

  get isAudioReady(): boolean {
    return this.state === 'connected' && this.playbackReady;
  }

  get isConnected(): boolean {
    return this.state === 'connected';
  }

  /** Last successful connect() mint vs LiveKit join timings, or null before first connect. */
  get connectTiming(): ConnectTiming | null {
    return this.lastConnectTiming;
  }

  /** Whether the local microphone track is currently enabled. `false` when not connected. */
  get isMicMuted(): boolean {
    return this.room ? !this.room.localParticipant.isMicrophoneEnabled : false;
  }

  /** Enable/disable the local microphone track. No-op if not connected. */
  async setMicMuted(muted: boolean): Promise<void> {
    const room = this.room;
    const generation = this.generation;
    if (!room) return;
    try {
      await room.localParticipant.setMicrophoneEnabled(!muted, MIC_CAPTURE_OPTIONS);
    } finally {
      if (!this.owns(room, generation)) {
        await room.localParticipant.setMicrophoneEnabled(false).catch(() => {});
      }
    }
  }

  async connect(opts: ConnectOptions): Promise<void> {
    if (this.room || this.state !== 'idle') {
      throw new AwaazLabsUvaVoiceError('session_failed', 'already connecting or connected - call disconnect() first');
    }
    if (!opts.agentId.trim()) throw new AwaazLabsUvaVoiceError('session_failed', 'agentId is required');
    const generation = ++this.generation;
    const controller = new AbortController();
    this.connectController = controller;
    const room = new Room({ audioCaptureDefaults: MIC_CAPTURE_OPTIONS });
    this.room = room;
    this.terminalOutcome = null;
    this.disconnectReason = undefined;
    this.readyRoom = null;
    this.metricSequences.clear();
    this.wireRoomEvents(room);
    this.setState('connecting');
    const assertCurrent = () => {
      if (!this.owns(room, generation) || controller.signal.aborted) {
        throw new AwaazLabsUvaVoiceError('session_failed', 'Connection cancelled');
      }
    };
    // Browser permissions can resolve after cancellation. Always stop those late tracks.
    const micPromise = room.localParticipant.setMicrophoneEnabled(true, MIC_CAPTURE_OPTIONS)
      .catch(() => {}).then(async () => {
        if (!this.owns(room, generation)) await room.localParticipant.setMicrophoneEnabled(false).catch(() => {});
      });
    try {
      const mintStarted = performance.now();
      const body = await withDeadline(async signal => {
        const headers = await this.resolveSessionHeaders();
        if (signal.aborted) throw new Error('Connection cancelled');
        const { response, text } = await fetchTextWithTimeout(this.options.sessionEndpoint, {
          method: 'POST', credentials: this.options.sessionCredentials ?? 'same-origin',
          headers: { 'Content-Type': 'application/json', ...headers },
          body: JSON.stringify({ publishableKey: this.options.publishableKey, agentId: opts.agentId }),
        }, this.fetchTimeoutMs, signal);
        if (!response.ok) throw mapSessionHttpError(response.status, text);
        const parsed = JSON.parse(text) as SessionResponse;
        if (!parsed.token || !parsed.wsUrl || !parsed.roomName) {
          throw new AwaazLabsUvaVoiceError('session_failed', 'session endpoint returned an incomplete response');
        }
        return parsed;
      }, this.fetchTimeoutMs, controller.signal);
      assertCurrent();
      this.session = body;
      this.sessionReceivedAt = Date.now();
      const mintMs = Math.round(performance.now() - mintStarted);
      const connectStarted = performance.now();
      await withDeadline(async () => {
        await room.connect(body.wsUrl, body.token, {
          peerConnectionTimeout: this.fetchTimeoutMs, websocketTimeout: this.fetchTimeoutMs,
        });
        if (!this.owns(room, generation)) await room.disconnect();
      }, this.fetchTimeoutMs, controller.signal);
      assertCurrent();
      const livekitConnectMs = Math.round(performance.now() - connectStarted);
      await withDeadline(async () => {
        await micPromise;
        assertCurrent();
        if (!room.localParticipant.isMicrophoneEnabled) {
          await room.localParticipant.setMicrophoneEnabled(true, MIC_CAPTURE_OPTIONS);
          if (!this.owns(room, generation)) await room.localParticipant.setMicrophoneEnabled(false);
        }
      }, this.fetchTimeoutMs, controller.signal);
      assertCurrent();
      if (!room.localParticipant.isMicrophoneEnabled) {
        throw new AwaazLabsUvaVoiceError('session_failed', 'microphone permission denied or unavailable');
      }
      this.updatePlaybackReady(room);
      this.observeAgent(room);
      // Data can arrive before the waiter is installed; readyRoom retains that edge.
      await withDeadline(async () => {
        const ready = new Promise<void>(resolve => {
          this.readyResolve = resolve;
          if (this.readyRoom === room) resolve();
        });
        void room.localParticipant.publishData(new TextEncoder().encode(JSON.stringify({
          type: 'awaaz_lifecycle_request',
        })), { reliable: true }).catch(() => {});
        await ready;
      }, this.options.agentReadyTimeoutMs ?? 30_000, controller.signal);
      assertCurrent();
      this.readyResolve = null;
      let livekitUrlHost: string | undefined;
      try { livekitUrlHost = new URL(body.wsUrl).host; } catch { /* optional diagnostic */ }
      this.lastConnectTiming = { mintMs, livekitConnectMs, livekitUrlHost,
        connectionQuality: String(room.localParticipant.connectionQuality ?? 'unknown') };
      this.emit('connect_timing', this.lastConnectTiming);
      this.setState('connected');
      this.updatePlaybackReady(room);
      this.scheduleTokenRefresh(body);
      this.emit('connected');
    } catch (error) {
      if (this.owns(room, generation)) {
        this.finishDisconnect(room, this.terminalOutcome ?? 'connection_failed');
      }
      void room.localParticipant.setMicrophoneEnabled(false).catch(() => {});
      void room.disconnect().catch(() => {});
      if (error instanceof AwaazLabsUvaVoiceError) throw error;
      throw new AwaazLabsUvaVoiceError('session_failed', 'Connection establishment failed');
    } finally {
      if (this.connectController === controller) this.connectController = null;
    }
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

  async disconnect(reason?: unknown): Promise<void> {
    this.disconnectReason = reason;
    this.connectController?.abort();
    this.refreshController?.abort();
    this.refreshController = null;
    this.refreshInFlight = false;
    this.generation++;
    this.clearRefreshTimer();
    this.playbackReady = false;
    const room = this.room;
    if (!room) {
      this.session = null;
      this.sessionReceivedAt = null;
      this.lastCallerSpeaking = null;
      this.lastAgentSpeaking = null;
      this.setState('idle');
      return;
    }
    this.setState('disconnecting');
    const canDisconnect = typeof (room as { disconnect?: unknown }).disconnect === 'function';
    if (canDisconnect) {
      await withDeadline(() => (room as { disconnect: () => Promise<void> }).disconnect(), this.fetchTimeoutMs).catch(() => {});
    }
    // Real LiveKit Room fires RoomEvent.Disconnected, which already clears state + emits.
    // Stubs / failed-refresh paths still need local cleanup when that event never runs.
    this.finishDisconnect(room, reason);
  }

  /**
   * Call this inside a user-gesture event handler (e.g. button click) when the
   * 'audio_blocked' event fires with blocked=true.
   * Browsers require a user interaction before they allow audio playback, so
   * the LiveKit Room's internal AudioContext must be resumed explicitly here.
   */
  async startAudio(): Promise<void> {
    const room = this.room;
    if (room) {
      await room.startAudio();
      if (this.room !== room) return;
      await Promise.all([...this.remoteAudioElements].map(async ([sid, element]) => {
        try {
          await element.play();
          if (this.room === room && this.remoteAudioElements.get(sid) === element) this.blockedRemoteAudio.delete(sid);
        } catch {
          if (this.room === room && this.remoteAudioElements.get(sid) === element) this.blockedRemoteAudio.add(sid);
        }
      }));
      this.updatePlaybackReady(room);
    }
  }

  private emit<K extends AwaazLabsUvaVoiceEvent>(event: K, ...args: AwaazLabsUvaVoiceEventMap[K]): void {
    for (const cb of this.listeners.get(event) ?? []) {
      try {
        (cb as Listener<AwaazLabsUvaVoiceEventMap[K]>)(...args);
      } catch (err) {
        // F-L8: one throwing host listener must not block later listeners for the same event.
        console.error(`[AwaazLabsUvaVoice] listener for "${event}" threw:`, err);
      }
    }
  }

  private updatePlaybackReady(room: Room): void {
    if (this.room !== room) return;
    const ready = ['connecting', 'connected'].includes(this.state) && room.canPlaybackAudio === true && this.blockedRemoteAudio.size === 0;
    if (this.playbackReady !== ready) {
      this.playbackReady = ready;
      this.emit('audio_ready', ready);
    }
    // A host may manually attach media elements; a rejected play() below also
    // reports blocked readiness. This packet contains no provider/policy controls.
    if (typeof room.localParticipant.publishData === 'function') {
      void room.localParticipant.publishData(new TextEncoder().encode(JSON.stringify({
        type: 'awaaz_playback_state', ready,
      })), { reliable: true }).catch(() => {});
    }
  }

  private wireRoomEvents(room: Room): void {
    room.on(RoomEvent.Reconnecting, () => {
      if (this.room !== room || this.state !== 'connected') return;
      this.setState('reconnecting');
      this.updatePlaybackReady(room);
    });
    room.on(RoomEvent.SignalReconnecting, () => {
      if (this.room !== room || this.state !== 'connected') return;
      this.setState('reconnecting');
    });
    room.on(RoomEvent.Reconnected, () => {
      if (this.room !== room || this.state !== 'reconnecting') return;
      this.setState('connected');
      this.updatePlaybackReady(room);
    });
    room.on(RoomEvent.ParticipantAttributesChanged, () => this.observeAgent(room));
    room.on(RoomEvent.ParticipantDisconnected, participant => {
      if (this.room !== room || !participant.isAgent) return;
      this.emit('error', new AwaazLabsUvaVoiceError('session_failed', 'Voice worker disconnected'));
      void this.disconnect(this.terminalOutcome ?? 'worker_disconnected');
    });

    room.on(RoomEvent.Disconnected, (reason) => {
      this.finishDisconnect(room, reason);
    });

    room.on(RoomEvent.ConnectionQualityChanged, (quality, participant) => {
      if (this.room !== room || !participant?.isLocal || !this.lastConnectTiming) return;
      // Refresh quality on the last timing snapshot for hosts that re-read connectTiming.
      this.lastConnectTiming = {
        ...this.lastConnectTiming,
        connectionQuality: String(quality),
      };
    });

    room.on(
      RoomEvent.TranscriptionReceived,
      (segments: TranscriptionSegment[], participant?: Participant) => {
        if (this.room !== room) return;
        const speaker: 'user' | 'agent' = participant?.isLocal ? 'user' : 'agent';
        for (const seg of segments) {
          this.emit('transcript', { id: seg.id, text: seg.text, final: seg.final, speaker });
        }
      },
    );

    room.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
      if (this.room !== room) return;
      // Local mic only — do not treat remote/agent speakers as "caller speaking"
      // (that false positive made demos look like VAD barge-in when the agent talked).
      const callerSpeaking = speakers.some((speaker) => speaker.isLocal);
      const agentSpeaking = speakers.some((speaker) => !speaker.isLocal);
      // Emit only on edge changes — LiveKit often re-fires the same speaker set.
      if (callerSpeaking !== this.lastCallerSpeaking) {
        this.lastCallerSpeaking = callerSpeaking;
        this.emit('speaking', callerSpeaking);
      }
      if (agentSpeaking !== this.lastAgentSpeaking) {
        this.lastAgentSpeaking = agentSpeaking;
        this.emit('agent_speaking', agentSpeaking);
      }
    });

    // --- AUDIO PLAYBACK FIX ---
    // Explicitly subscribe to remote audio tracks and attach them to audio
    // elements. Without this, LiveKit's default audio playback relies on the
    // browser's AudioContext which is suspended until a user gesture.
    room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
      if (this.room !== room) return;
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
      if (this.room !== room) return;
      if (track.kind !== Track.Kind.Audio) {
        return;
      }
      const trackSid = track.sid ?? publication.trackSid;
      this.detachRemoteAudio(trackSid);
    });

    room.on(RoomEvent.MediaDevicesError, (error: Error) => {
      if (this.room !== room) return;
      this.emit('error', new AwaazLabsUvaVoiceError('session_failed', error.message));
    });

    room.on(RoomEvent.RoomMetadataChanged, (metadata?: string) => {
      // Room metadata is not an authenticated worker message. Metrics use agent data packets.
      void metadata;
    });

    room.on(RoomEvent.DataReceived, (payload: Uint8Array, participant?: Participant) => {
      if (this.room !== room) return;
      const text = this.decodePayload(payload);
      try {
        const packet = JSON.parse(text);
        if (packet?.type === 'awaaz_playback_request' && participant?.isAgent) this.updatePlaybackReady(room);
        if (!participant?.isAgent) return;
        if (this.session?.sessionId && packet.type !== 'awaaz_playback_request' && packet.session_id !== this.session.sessionId) return;
        if (packet?.type === 'awaaz_agent_ready') this.markAgentReady(room);
        if (['awaaz_session_failure', 'awaaz_session_ended'].includes(packet?.type)) {
          this.terminalOutcome = packet as SessionOutcome;
          this.emit('session_outcome', this.terminalOutcome);
          if (packet.type === 'awaaz_session_failure') {
            this.emit('error', new AwaazLabsUvaVoiceError('session_failed',
              'Voice session unavailable: ' + String(packet.stage ?? packet.reason ?? 'provider')));
          }
        }
        const metrics = this.tryParseMetrics(text);
        if (metrics) {
          if (metrics.sequence !== undefined) {
            if (!Number.isSafeInteger(metrics.sequence) || metrics.sequence < 0) return;
            const key = metrics.type;
            if (metrics.sequence <= (this.metricSequences.get(key) ?? -1)) return;
            this.metricSequences.set(key, metrics.sequence);
          }
          this.emitLatencyEvents(metrics);
        }
      } catch { /* Ignore unrelated/malformed packets. */ }
    });

    // Browsers block audio autoplay without a prior user gesture.
    // LiveKit signals this via AudioPlaybackStatusChanged when its internal
    // HTMLAudioElement.play() promise rejects (NotAllowedError).
    // We forward it as 'audio_blocked' so the host app can show an
    // "Unlock Audio" button and call agent.startAudio() on click.
    room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      if (this.room !== room) return;
      const blocked = !room.canPlaybackAudio;
      this.emit('audio_blocked', blocked);
      this.updatePlaybackReady(room);
    });
  }

  private finishDisconnect(room: Room, reason?: unknown): void {
    // Ignore duplicate/late events, including an old room closing after reconnect.
    if (this.room !== room) return;
    this.connectController?.abort();
    this.refreshController?.abort();
    this.refreshController = null;
    this.refreshInFlight = false;
    this.readyResolve = null;
    this.readyRoom = null;
    const outcome = this.terminalOutcome ?? this.disconnectReason ?? reason;
    this.terminalOutcome = null;
    this.disconnectReason = undefined;
    this.clearRefreshTimer();
    this.detachAllRemoteAudio();
    this.room = null;
    this.session = null;
    this.sessionReceivedAt = null;
    this.lastCallerSpeaking = null;
    this.lastAgentSpeaking = null;
    this.setState('idle');
    this.playbackReady = false;
    this.emit('audio_ready', false);
    this.emit('disconnected', outcome);
    this.emit('ended', outcome);
  }

  private attachRemoteAudio(trackSid: string, element: HTMLMediaElement): void {
    this.detachRemoteAudio(trackSid); // clean up any previous element for this sid
    element.autoplay = true;
    element.setAttribute('playsinline', 'true');
    element.style.display = 'none';
    // F-L7: no `document` / `document.body` under Next.js SSR (or non-DOM runtimes).
    // Still track the element so TrackUnsubscribed cleanup works if attach raced hydration.
    this.remoteAudioElements.set(trackSid, element);
    if (typeof document !== 'undefined' && document.body) {
      document.body.appendChild(element);
    }
    // Attempt .play() eagerly. If the browser blocks it (NotAllowedError),
    // LiveKit will fire AudioPlaybackStatusChanged, which we relay as 'audio_blocked'.
    void element.play().then(() => {
      if (this.remoteAudioElements.get(trackSid) !== element) return;
      this.blockedRemoteAudio.delete(trackSid);
      if (this.room) this.updatePlaybackReady(this.room);
    }).catch(() => {
      if (this.remoteAudioElements.get(trackSid) !== element) return;
      this.blockedRemoteAudio.add(trackSid);
      this.playbackReady = false;
      this.emit('audio_ready', false);
      this.emit('audio_blocked', true);
      if (this.room) {
        void this.room.localParticipant.publishData(new TextEncoder().encode(
          '{"type":"awaaz_playback_state","ready":false}'), { reliable: true }).catch(() => {});
      }
    });
  }

  private detachRemoteAudio(trackSid: string): void {
    this.blockedRemoteAudio.delete(trackSid);
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
    const ttlSeconds = normalizeExpiresInSec(session.expiresIn);
    // Refresh 60s before expiry, but never sooner than 5s after mint/refresh.
    // Leave a wide retry window before the JWT deadline (F-H12).
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
    if (this.refreshInFlight || !this.room || !this.session) return;
    const room = this.room;
    const generation = this.generation;
    const session = this.session;
    const controller = new AbortController();
    this.refreshController = controller;
    this.refreshInFlight = true;
    const current = () => this.owns(room, generation) && !controller.signal.aborted;
    const endpoint = this.resolveRefreshEndpoint();
    const deadline = (this.sessionReceivedAt ?? Date.now()) + normalizeExpiresInSec(session.expiresIn) * 1000;
    let backoffMs = 1000;
    try {
      for (let attempt = 0; attempt < 20 && current() && Date.now() < deadline; attempt++) {
        let terminal = false;
        try {
          const result = await withDeadline(async signal => {
            const headers = await this.resolveSessionHeaders();
            if (signal.aborted) throw new Error('Refresh cancelled');
            return fetchTextWithTimeout(endpoint, { method: 'POST',
              credentials: this.options.sessionCredentials ?? 'same-origin',
              headers: { ...headers, Authorization: 'Bearer ' + session.token },
            }, this.fetchTimeoutMs, signal);
          }, Math.min(this.fetchTimeoutMs, Math.max(1, deadline - Date.now())), controller.signal);
          if (!current()) return;
          terminal = [400, 401, 403, 404, 409, 429].includes(result.response.status);
          if (result.response.ok) {
            const parsed = JSON.parse(result.text) as SessionResponse;
            if (!parsed.token || parsed.roomName !== session.roomName || parsed.wsUrl !== session.wsUrl ||
                (session.sessionId && parsed.sessionId && parsed.sessionId !== session.sessionId)) {
              terminal = true;
            } else {
              await applyRefreshedLiveKitToken(room, parsed.token);
              if (!current()) return;
              this.session = { ...session, ...parsed };
              this.sessionReceivedAt = Date.now();
              this.scheduleTokenRefresh(this.session);
              return;
            }
          }
        } catch { /* A bounded transient failure can retry until the original JWT expires. */ }
        if (!current()) return;
        if (terminal) break;
        await withDeadline(() => new Promise<void>(resolve => {
          const timer = setTimeout(resolve, Math.min(backoffMs, Math.max(1, deadline - Date.now())));
          controller.signal.addEventListener('abort', () => { clearTimeout(timer); resolve(); }, { once: true });
        }), Math.max(1, deadline - Date.now()), controller.signal).catch(() => {});
        backoffMs = Math.min(8000, backoffMs * 2);
      }
      if (!current()) return;
      this.emit('error', new AwaazLabsUvaVoiceError('token_refresh_failed', 'token refresh failed'));
      await this.disconnect('token_refresh_failed');
    } finally {
      if (this.refreshController === controller) {
        this.refreshController = null;
        this.refreshInFlight = false;
      }
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
    // Historical compatibility: per-turn events also reach metrics_updated.
    // Consumers subscribing to both should process turns only on turn_latency,
    // and accept only type=metrics_updated on the aggregate subscription.
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
