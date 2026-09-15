import { afterEach, describe, expect, it, vi } from 'vitest';
import { AwaazLabsUvaVoice, AwaazLabsUvaVoiceError } from './index.js';
import type { AwaazLabsUvaVoiceEvent, AwaazLabsUvaVoiceEventMap } from './index.js';

type EmitAccess = {
  emit: <K extends AwaazLabsUvaVoiceEvent>(
    event: K,
    ...args: AwaazLabsUvaVoiceEventMap[K]
  ) => void;
  attachRemoteAudio: (trackSid: string, element: HTMLMediaElement) => void;
  refreshToken: () => Promise<void>;
  session: {
    token: string;
    wsUrl: string;
    roomName: string;
    refreshUrl?: string;
    expiresIn?: number;
  } | null;
  sessionReceivedAt: number | null;
  room: { updateToken?: (token: string) => Promise<void> } | null;
  refreshTimer: ReturnType<typeof setTimeout> | null;
};

function internals(agent: AwaazLabsUvaVoice): EmitAccess {
  return agent as unknown as EmitAccess;
}

function makeAgent(): AwaazLabsUvaVoice {
  return new AwaazLabsUvaVoice({
    publishableKey: 'pk_test',
    sessionEndpoint: 'https://host.example/v1/session',
  });
}

describe('AwaazLabsUvaVoice emit (F-L8)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('continues to later listeners when one throws', () => {
    const agent = makeAgent();
    const second = vi.fn();
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    agent.on('error', () => {
      throw new Error('host listener boom');
    });
    agent.on('error', second);

    const payload = new AwaazLabsUvaVoiceError('session_failed', 'x');
    internals(agent).emit('error', payload);

    expect(second).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledWith(payload);
    expect(errSpy).toHaveBeenCalled();
  });
});

describe('AwaazLabsUvaVoice attachRemoteAudio (F-L7)', () => {
  it('does not throw when document is undefined', () => {
    const agent = makeAgent();
    const el = {
      autoplay: false,
      setAttribute: vi.fn(),
      style: { display: '' },
      play: vi.fn(() => Promise.resolve()),
    } as unknown as HTMLMediaElement;

    expect(() => internals(agent).attachRemoteAudio('trk_1', el)).not.toThrow();
  });

  it('does not throw when document.body is missing', () => {
    const agent = makeAgent();
    vi.stubGlobal('document', { body: null });
    const el = {
      autoplay: false,
      setAttribute: vi.fn(),
      style: { display: '' },
      play: vi.fn(() => Promise.resolve()),
    } as unknown as HTMLMediaElement;

    expect(() => internals(agent).attachRemoteAudio('trk_2', el)).not.toThrow();
    vi.unstubAllGlobals();
  });
});

describe('AwaazLabsUvaVoice refreshToken (F-H12)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('retries once then succeeds without terminal error', async () => {
    vi.useFakeTimers();
    const agent = makeAgent();
    const access = internals(agent);
    const errors: AwaazLabsUvaVoiceError[] = [];
    agent.on('error', (e) => errors.push(e));

    access.room = {
      updateToken: vi.fn(async () => undefined),
    };
    access.session = {
      token: 'tok_old',
      wsUrl: 'wss://lk.example',
      roomName: 'room_1',
      expiresIn: 120,
    };
    access.sessionReceivedAt = Date.now();

    let calls = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        calls += 1;
        if (calls === 1) {
          return new Response('fail', { status: 500 });
        }
        return new Response(
          JSON.stringify({
            token: 'tok_new',
            wsUrl: 'wss://lk.example',
            roomName: 'room_1',
            expiresIn: 120,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }),
    );

    const pending = access.refreshToken();
    await vi.advanceTimersByTimeAsync(1_000);
    await pending;

    expect(calls).toBe(2);
    expect(errors).toHaveLength(0);
    expect(access.session?.token).toBe('tok_new');
    expect(access.refreshTimer).not.toBeNull();
    access.refreshTimer && clearTimeout(access.refreshTimer);
  });

  it('emits token_refresh_failed once when past deadline', async () => {
    vi.useFakeTimers();
    const agent = makeAgent();
    const access = internals(agent);
    const errors: AwaazLabsUvaVoiceError[] = [];
    agent.on('error', (e) => errors.push(e));

    access.room = {};
    access.session = {
      token: 'tok_old',
      wsUrl: 'wss://lk.example',
      roomName: 'room_1',
      expiresIn: 2,
    };
    access.sessionReceivedAt = Date.now();

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('fail', { status: 500 })),
    );

    const pending = access.refreshToken();
    await vi.runAllTimersAsync();
    await pending;

    expect(errors).toHaveLength(1);
    expect(errors[0]?.code).toBe('token_refresh_failed');
    expect(access.refreshTimer).toBeNull();
  });

  it('emits token_refresh_failed immediately on 401', async () => {
    const agent = makeAgent();
    const access = internals(agent);
    const errors: AwaazLabsUvaVoiceError[] = [];
    agent.on('error', (e) => errors.push(e));

    access.room = {};
    access.session = {
      token: 'tok_old',
      wsUrl: 'wss://lk.example',
      roomName: 'room_1',
      expiresIn: 120,
    };
    access.sessionReceivedAt = Date.now();

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('nope', { status: 401 })),
    );

    await access.refreshToken();

    expect(errors).toHaveLength(1);
    expect(errors[0]?.code).toBe('token_refresh_failed');
  });
});
