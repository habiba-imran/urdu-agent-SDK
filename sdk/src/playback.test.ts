import { describe, expect, it, vi } from 'vitest';
import { RoomEvent } from 'livekit-client';
import { AwaazLabsUvaVoice } from './index.js';

function setup(ready = false) {
  const client = new AwaazLabsUvaVoice({ publishableKey: 'pk_test', sessionEndpoint: 'https://host.example/v1/session' });
  const events = new Map<string, (...args: any[]) => void>();
  const room = {
    canPlaybackAudio: ready,
    localParticipant: { publishData: vi.fn(async () => {}) },
    startAudio: vi.fn(async () => { room.canPlaybackAudio = true; }),
    on: vi.fn((event: string, cb: (...args: any[]) => void) => events.set(event, cb)),
  };
  const internals = client as any;
  internals.room = room;
  internals.state = 'connected';
  internals.wireRoomEvents(room);
  return { client, room, events, internals };
}

describe('P0 browser playback readiness', () => {
  it('keeps connected separate from blocked playback, then startAudio unlocks', async () => {
    const { client, room, events } = setup();
    const ready = vi.fn(), blocked = vi.fn();
    client.on('audio_ready', ready).on('audio_blocked', blocked);
    expect(client.isConnected).toBe(true);
    expect(client.isAudioReady).toBe(false);
    events.get(RoomEvent.AudioPlaybackStatusChanged)!();
    expect(blocked).toHaveBeenCalledWith(true);
    await client.startAudio();
    expect(client.isAudioReady).toBe(true);
    expect(ready).toHaveBeenCalledWith(true);
    const packet = JSON.parse(new TextDecoder().decode(room.localParticipant.publishData.mock.calls.at(-1)![0]));
    expect(packet).toEqual({ type: 'awaaz_playback_state', ready: true });
  });

  it('answers a late worker readiness request without claiming heard speech', () => {
    const { client, room, events } = setup(true);
    events.get(RoomEvent.DataReceived)!(new TextEncoder().encode('{"type":"awaaz_playback_request"}'));
    expect(client.isAudioReady).toBe(true);
    const packet = JSON.parse(new TextDecoder().decode(room.localParticipant.publishData.mock.calls[0]![0]));
    expect(packet).toEqual({ type: 'awaaz_playback_state', ready: true });
    expect(packet.callerHeard).toBeUndefined();
  });

  it('surfaces worker failure with no fabricated fallback speech', () => {
    const { client, events } = setup(true);
    const error = vi.fn(); client.on('error', error);
    const packet = new TextEncoder().encode('{"type":"awaaz_session_failure","stage":"TTS","spokenFallback":false}');
    events.get(RoomEvent.DataReceived)!(packet, { isAgent: true });
    expect(error).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ code: 'session_failed' }));
  });

  it('clears readiness on room disconnect', () => {
    const { client, events, internals } = setup(true);
    internals.updatePlaybackReady(internals.room);
    expect(client.isAudioReady).toBe(true);
    events.get(RoomEvent.Disconnected)!('ended');
    expect(client.isAudioReady).toBe(false);
  });
});
