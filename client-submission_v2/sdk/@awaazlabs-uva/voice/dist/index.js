import { Room, RoomEvent, Track } from 'livekit-client';
export class AwaazLabsUvaVoiceError extends Error {
    constructor(code, message) {
        super(message ?? code);
        this.code = code;
        this.name = 'AwaazLabsUvaVoiceError';
    }
}
export { AwaazLabsUvaVoiceError as UvaError };
export class AwaazLabsUvaVoice {
    static async listVoices(endpointUrl) {
        if (!endpointUrl.trim()) {
            throw new AwaazLabsUvaVoiceError('session_failed', 'voice catalog endpoint is required');
        }
        try {
            const res = await fetch(endpointUrl);
            if (!res.ok) {
                throw new AwaazLabsUvaVoiceError('session_failed', `Failed to fetch voices catalog: ${res.statusText}`);
            }
            return (await res.json());
        }
        catch (e) {
            if (e instanceof AwaazLabsUvaVoiceError)
                throw e;
            throw new AwaazLabsUvaVoiceError('session_failed', `Failed to reach voices endpoint: ${String(e)}`);
        }
    }
    constructor(options) {
        this.options = options;
        this.room = null;
        this.listeners = new Map();
        this.remoteAudioElements = new Map();
        this.refreshTimer = null;
        this.session = null;
        this.state = 'idle';
        if (!options.publishableKey.trim()) {
            throw new AwaazLabsUvaVoiceError('session_failed', 'publishableKey is required');
        }
        if (!options.sessionEndpoint.trim()) {
            throw new AwaazLabsUvaVoiceError('session_failed', 'sessionEndpoint is required');
        }
    }
    get connectionState() {
        return this.state;
    }
    get isConnected() {
        return this.state === 'connected';
    }
    async connect(opts) {
        if (this.room) {
            throw new AwaazLabsUvaVoiceError('session_failed', 'already connected - call disconnect() first');
        }
        if (!opts.agentId.trim()) {
            throw new AwaazLabsUvaVoiceError('session_failed', 'agentId is required');
        }
        this.state = 'connecting';
        let body;
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
            const parsed = (await res.json());
            if (!parsed.token || !parsed.wsUrl || !parsed.roomName) {
                throw new AwaazLabsUvaVoiceError('session_failed', 'session endpoint returned an incomplete response');
            }
            body = parsed;
        }
        catch (err) {
            this.state = 'idle';
            if (err instanceof AwaazLabsUvaVoiceError)
                throw err;
            throw new AwaazLabsUvaVoiceError('session_failed', 'could not reach sessionEndpoint');
        }
        const room = new Room();
        this.wireRoomEvents(room);
        try {
            await room.connect(body.wsUrl, body.token);
        }
        catch {
            this.state = 'idle';
            throw new AwaazLabsUvaVoiceError('session_failed', 'LiveKit connection failed');
        }
        try {
            await room.localParticipant.setMicrophoneEnabled(true);
        }
        catch {
            await room.disconnect();
            this.state = 'idle';
            throw new AwaazLabsUvaVoiceError('session_failed', 'microphone permission denied or unavailable');
        }
        this.room = room;
        this.session = body;
        this.scheduleTokenRefresh(body);
    }
    on(event, cb) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event).add(cb);
        return this;
    }
    off(event, cb) {
        this.listeners.get(event)?.delete(cb);
        return this;
    }
    async disconnect() {
        this.clearRefreshTimer();
        if (!this.room)
            return;
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
    async startAudio() {
        if (this.room) {
            await this.room.startAudio();
        }
    }
    emit(event, ...args) {
        for (const cb of this.listeners.get(event) ?? []) {
            cb(...args);
        }
    }
    wireRoomEvents(room) {
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
        room.on(RoomEvent.TranscriptionReceived, (segments) => {
            for (const seg of segments) {
                this.emit('transcript', { text: seg.text, final: seg.final });
            }
        });
        room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
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
        room.on(RoomEvent.MediaDevicesError, (error) => {
            this.emit('error', new AwaazLabsUvaVoiceError('session_failed', error.message));
        });
        room.on(RoomEvent.RoomMetadataChanged, (metadata) => {
            const metrics = this.tryParseMetrics(metadata);
            if (metrics)
                this.emit('metrics_updated', metrics);
        });
        room.on(RoomEvent.DataReceived, (payload) => {
            const metrics = this.tryParseMetrics(this.decodePayload(payload));
            if (metrics)
                this.emit('metrics_updated', metrics);
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
    attachRemoteAudio(trackSid, element) {
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
    detachRemoteAudio(trackSid) {
        const element = this.remoteAudioElements.get(trackSid);
        if (!element)
            return;
        try {
            element.pause();
            element.removeAttribute('src');
            element.load();
        }
        catch {
            // Best-effort cleanup.
        }
        element.remove();
        this.remoteAudioElements.delete(trackSid);
    }
    detachAllRemoteAudio() {
        for (const trackSid of [...this.remoteAudioElements.keys()]) {
            this.detachRemoteAudio(trackSid);
        }
    }
    scheduleTokenRefresh(session) {
        this.clearRefreshTimer();
        const ttlSeconds = session.expiresIn ?? 120;
        const refreshDelayMs = Math.max(5000, (ttlSeconds - 60) * 1000);
        this.refreshTimer = setTimeout(() => {
            void this.refreshToken();
        }, refreshDelayMs);
    }
    clearRefreshTimer() {
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
            this.refreshTimer = null;
        }
    }
    async refreshToken() {
        if (!this.room || !this.session)
            return;
        const refreshEndpoint = this.resolveRefreshEndpoint();
        try {
            const res = await fetch(refreshEndpoint, {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${this.session.token}`,
                },
            });
            if (!res.ok)
                throw new Error('refresh failed');
            const parsed = (await res.json());
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
            const tokenUpdater = this.room;
            if (typeof tokenUpdater.updateToken === 'function') {
                await tokenUpdater.updateToken(this.session.token);
            }
            this.scheduleTokenRefresh(this.session);
        }
        catch {
            this.emit('error', new AwaazLabsUvaVoiceError('session_failed', 'token refresh failed'));
        }
    }
    resolveRefreshEndpoint() {
        if (this.session?.refreshUrl)
            return this.session.refreshUrl;
        if (this.options.refreshEndpoint)
            return this.options.refreshEndpoint;
        if (this.options.sessionEndpoint.endsWith('/v1/session')) {
            return `${this.options.sessionEndpoint}/refresh`;
        }
        return `${this.options.sessionEndpoint.replace(/\/$/, '')}/refresh`;
    }
    decodePayload(payload) {
        try {
            return new TextDecoder().decode(payload);
        }
        catch {
            return '';
        }
    }
    tryParseMetrics(text) {
        if (!text)
            return null;
        try {
            const parsed = JSON.parse(text);
            if (parsed.type === 'metrics_updated' || parsed.type === 'turn_latency') {
                return parsed;
            }
            return null;
        }
        catch {
            return null;
        }
    }
}
export { AwaazLabsUvaVoice as UrduVoiceAgent };
