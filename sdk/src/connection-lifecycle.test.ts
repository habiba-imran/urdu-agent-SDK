import { afterEach, describe, expect, it, vi } from 'vitest';

const rooms = vi.hoisted(() => [] as any[]);
vi.mock('livekit-client', async importOriginal => {
  const original = await importOriginal<typeof import('livekit-client')>();
  class Room {
    handlers = new Map<string, (...args: any[]) => void>();
    remoteParticipants = new Map();
    canPlaybackAudio = true;
    localParticipant = {
      isMicrophoneEnabled: false, connectionQuality: 'excellent',
      setMicrophoneEnabled: vi.fn(async (enabled: boolean) => { this.localParticipant.isMicrophoneEnabled = enabled; }),
      publishData: vi.fn(async () => {}),
    };
    on(event: string, fn: (...args: any[]) => void) { this.handlers.set(event, fn); return this; }
    emit(event: string, ...args: any[]) { this.handlers.get(event)?.(...args); }
    connect = vi.fn(async () => {});
    disconnect = vi.fn(async () => { this.emit(original.RoomEvent.Disconnected, 'client'); });
    constructor() { rooms.push(this); }
  }
  return { ...original, Room };
});
import { RoomEvent } from 'livekit-client';
import { AwaazLabsUvaVoice } from './index.js';
import { fetchTextWithTimeout, withDeadline } from './internal/http.js';

const response = () => new Response(JSON.stringify({token: 't', wsUrl: 'wss://lk.test', roomName: 'r', sessionId: 's'}));
const client = () => new AwaazLabsUvaVoice({publishableKey: 'pk', sessionEndpoint: 'https://host.test/session', agentReadyTimeoutMs: 100});
const tick = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
afterEach(() => { rooms.length = 0; vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('connection lifecycle ownership', () => {
  it('rejects simultaneous connects during mint and cancels the pending operation', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const agent = client();
    const first = agent.connect({agentId: 'a'});
    const rejected = expect(first).rejects.toMatchObject({code: 'session_failed'});
    await expect(agent.connect({agentId: 'a'})).rejects.toThrow('already connecting');
    await agent.disconnect();
    await rejected;
    expect(rooms).toHaveLength(1);
    expect(agent.connectionState).toBe('idle');
    expect(rooms[0].localParticipant.isMicrophoneEnabled).toBe(false);
  });

  it('waits for worker readiness and microphone before reporting connected', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response()));
    const agent = client(), connected = vi.fn(); agent.on('connected', connected);
    const pending = agent.connect({agentId: 'a'});
    await tick();
    expect(connected).not.toHaveBeenCalled();
    rooms[0].emit(RoomEvent.DataReceived, new TextEncoder().encode('{"type":"awaaz_agent_ready","session_id":"s"}'), {isAgent: true});
    await pending;
    expect(agent.isConnected).toBe(true);
    expect(connected).toHaveBeenCalledTimes(1);
    await agent.disconnect();
  });

  it('bounds a missing worker and cleans up its room', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response()));
    const agent = client();
    await expect(agent.connect({agentId: 'a'})).rejects.toMatchObject({code: 'timeout'});
    expect(agent.connectionState).toBe('idle');
    expect(rooms[0].disconnect).toHaveBeenCalled();
  });

  it('rejects spoofed readiness and metrics, then reports reconnection state', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response()));
    const agent = client(), metrics = vi.fn(); agent.on('metrics_updated', metrics);
    const pending = agent.connect({agentId: 'a'});
    await tick();
    const room = rooms[0];
    room.emit(RoomEvent.DataReceived, new TextEncoder().encode('{"type":"awaaz_agent_ready"}'), {isAgent: false});
    room.emit(RoomEvent.DataReceived, new TextEncoder().encode('{"type":"metrics_updated"}'), {isAgent: false});
    expect(agent.isConnected).toBe(false); expect(metrics).not.toHaveBeenCalled();
    room.emit(RoomEvent.DataReceived, new TextEncoder().encode('{"type":"awaaz_agent_ready","session_id":"s"}'), {isAgent: true});
    await pending;
    room.emit(RoomEvent.Reconnecting); expect(agent.connectionState).toBe('reconnecting');
    room.emit(RoomEvent.Reconnected); expect(agent.isConnected).toBe(true);
    await agent.disconnect();
  });

  it('bounds a response body even after successful headers', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, text: () => new Promise(() => {})})));
    await expect(fetchTextWithTimeout('https://host.test', {}, 10)).rejects.toMatchObject({code: 'timeout'});
  });

  it('disables a microphone enablement that finishes after disconnect', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response()));
    const agent = client();
    const pending = agent.connect({agentId: 'a'});
    await tick();
    const room = rooms[0];
    room.emit(RoomEvent.DataReceived, new TextEncoder().encode('{"type":"awaaz_agent_ready","session_id":"s"}'), {isAgent: true});
    await pending;
    let finish!: () => void;
    room.localParticipant.setMicrophoneEnabled.mockImplementationOnce(async () => {
      await new Promise<void>(resolve => { finish = resolve; });
      room.localParticipant.isMicrophoneEnabled = true;
    });
    const enabling = agent.setMicMuted(false);
    await agent.disconnect();
    finish();
    await enabling;
    expect(room.localParticipant.isMicrophoneEnabled).toBe(false);
  });

  it('bounds asynchronous host authentication', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    const agent = new AwaazLabsUvaVoice({publishableKey: 'pk', sessionEndpoint: 'https://host.test', fetchTimeoutMs: 10,
      sessionHeaders: () => new Promise(() => {})});
    await expect(agent.connect({agentId: 'a'})).rejects.toMatchObject({code: 'timeout'});
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not invoke an operation whose parent was already cancelled', async () => {
    const controller = new AbortController(); controller.abort(); const operation = vi.fn();
    await expect(withDeadline(operation, 10, controller.signal)).rejects.toBeDefined();
    expect(operation).not.toHaveBeenCalled();
  });
});
