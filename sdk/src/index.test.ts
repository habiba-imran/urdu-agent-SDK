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
  room: {
    engine?: { token?: string; emit?: (event: string, token: string) => void };
    regionUrlProvider?: { updateToken?: (token: string) => void };
    updateToken?: (token: string) => Promise<void>;
    disconnect?: () => Promise<void>;
  } | null;
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

describe('AwaazLabsUvaVoice.listVoices (F-M16)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('maps distinguishable 429 bodies instead of collapsing to session_failed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ error: 'rate limited' }), { status: 429 })),
    );

    await expect(
      AwaazLabsUvaVoice.listVoices('https://host.example/v1/voices'),
    ).rejects.toMatchObject({ code: 'rate_limit' });
  });

  it('maps 404 to agent_not_found', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('missing', { status: 404 })),
    );

    await expect(
      AwaazLabsUvaVoice.listVoices('https://host.example/v1/voices'),
    ).rejects.toMatchObject({ code: 'agent_not_found' });
  });
});

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

    const regionUpdate = vi.fn();
    access.room = {
      engine: { token: 'tok_old' },
      regionUrlProvider: { updateToken: regionUpdate },
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
    expect(access.room?.engine?.token).toBe('tok_new');
    expect(regionUpdate).toHaveBeenCalledWith('tok_new');
    expect(access.refreshTimer).not.toBeNull();
    access.refreshTimer && clearTimeout(access.refreshTimer);
  });

  it('emits token_refresh_failed once when past deadline', async () => {
    vi.useFakeTimers();
    const agent = makeAgent();
    const access = internals(agent);
    const errors: AwaazLabsUvaVoiceError[] = [];
    const ended: unknown[] = [];
    agent.on('error', (e) => errors.push(e));
    agent.on('ended', (reason) => ended.push(reason));

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
    expect(access.room).toBeNull();
    expect(access.session).toBeNull();
    expect(ended).toEqual(['token_refresh_failed']);
  });

  it('emits token_refresh_failed immediately on 401', async () => {
    const agent = makeAgent();
    const access = internals(agent);
    const errors: AwaazLabsUvaVoiceError[] = [];
    const ended: unknown[] = [];
    agent.on('error', (e) => errors.push(e));
    agent.on('ended', (reason) => ended.push(reason));

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
    expect(access.room).toBeNull();
    expect(access.session).toBeNull();
    expect(ended).toEqual(['token_refresh_failed']);
  });

  it('does not burn the retry budget in a single tick (backoff sleeps)', async () => {
    vi.useFakeTimers();
    const agent = makeAgent();
    const access = internals(agent);
    const errors: AwaazLabsUvaVoiceError[] = [];
    agent.on('error', (e) => errors.push(e));

    access.room = { engine: { token: 'tok_old' } };
    access.session = {
      token: 'tok_old',
      wsUrl: 'wss://lk.example',
      roomName: 'room_1',
      expiresIn: 120,
    };
    access.sessionReceivedAt = Date.now();

    const fetchMock = vi.fn(async () => new Response('fail', { status: 500 }));
    vi.stubGlobal('fetch', fetchMock);

    const pending = access.refreshToken();

    // First attempt runs immediately; backoff before attempt 2 is 1s.
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(500);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(500);
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Still inside the 2s backoff before attempt 3 — must not have spammed.
    await vi.advanceTimersByTimeAsync(1_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Cancel the long retry loop so the test can finish cleanly.
    access.room = null;
    access.session = null;
    await vi.runAllTimersAsync();
    await pending;
    expect(errors).toHaveLength(0);
  });
});
