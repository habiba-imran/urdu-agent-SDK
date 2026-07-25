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
export type AwaazLabsUvaVoiceEvent = 'transcript' | 'speaking' | 'error' | 'ended' | 'connected' | 'disconnected' | 'agent_speaking' | 'metrics_updated' | 'audio_blocked';
export type UvaEvent = AwaazLabsUvaVoiceEvent;
export type AwaazLabsUvaVoiceErrorCode = 'quota_exceeded' | 'agent_not_found' | 'session_failed';
export type UvaErrorCode = AwaazLabsUvaVoiceErrorCode;
export interface TranscriptEvent {
    text: string;
    final: boolean;
}
export interface MetricsEvent {
    type: 'metrics_updated' | 'turn_latency';
    [key: string]: unknown;
}
export declare class AwaazLabsUvaVoiceError extends Error {
    readonly code: AwaazLabsUvaVoiceErrorCode;
    constructor(code: AwaazLabsUvaVoiceErrorCode, message?: string);
}
export { AwaazLabsUvaVoiceError as UvaError };
export interface AwaazLabsUvaVoiceEventMap {
    transcript: [TranscriptEvent];
    speaking: [boolean];
    error: [AwaazLabsUvaVoiceError];
    ended: [unknown];
    connected: [];
    disconnected: [unknown];
    agent_speaking: [boolean];
    metrics_updated: [MetricsEvent];
    /**
     * Fired when the browser blocks audio autoplay (canPlaybackAudio=false) or
     * unblocks it (canPlaybackAudio=true). When blocked=true, show a user-visible
     * button and call agent.startAudio() inside its click handler.
     */
    audio_blocked: [boolean];
}
export type UvaEventMap = AwaazLabsUvaVoiceEventMap;
type Listener<TArgs extends unknown[] = unknown[]> = (...args: TArgs) => void;
export declare class AwaazLabsUvaVoice {
    private readonly options;
    private room;
    private readonly listeners;
    private readonly remoteAudioElements;
    private refreshTimer;
    private session;
    private state;
    static listVoices(endpointUrl: string): Promise<Voice[]>;
    constructor(options: AwaazLabsUvaVoiceOptions);
    get connectionState(): ConnectionState;
    get isConnected(): boolean;
    connect(opts: ConnectOptions): Promise<void>;
    on<K extends AwaazLabsUvaVoiceEvent>(event: K, cb: Listener<AwaazLabsUvaVoiceEventMap[K]>): this;
    off<K extends AwaazLabsUvaVoiceEvent>(event: K, cb: Listener<AwaazLabsUvaVoiceEventMap[K]>): this;
    disconnect(): Promise<void>;
    /**
     * Call this inside a user-gesture event handler (e.g. button click) when the
     * 'audio_blocked' event fires with blocked=true.
     * Browsers require a user interaction before they allow audio playback, so
     * the LiveKit Room's internal AudioContext must be resumed explicitly here.
     */
    startAudio(): Promise<void>;
    private emit;
    private wireRoomEvents;
    private attachRemoteAudio;
    private detachRemoteAudio;
    private detachAllRemoteAudio;
    private scheduleTokenRefresh;
    private clearRefreshTimer;
    private refreshToken;
    private resolveRefreshEndpoint;
    private decodePayload;
    private tryParseMetrics;
}
export { AwaazLabsUvaVoice as UrduVoiceAgent };
