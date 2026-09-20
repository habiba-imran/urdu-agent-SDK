import { describe, expect, it, vi } from 'vitest';
import { applyRefreshedLiveKitToken } from './livekitToken.js';

describe('applyRefreshedLiveKitToken (F-H12)', () => {
  it('writes token onto engine and regionUrlProvider (real livekit-client shape)', async () => {
    const updateToken = vi.fn();
    const emit = vi.fn();
    const room = {
      engine: { token: 'old', emit },
      regionUrlProvider: { updateToken },
    };

    await applyRefreshedLiveKitToken(room, 'new-jwt');

    expect(room.engine.token).toBe('new-jwt');
    expect(emit).toHaveBeenCalledWith('tokenRefreshed', 'new-jwt');
    expect(updateToken).toHaveBeenCalledWith('new-jwt');
  });

  it('also awaits Room.updateToken when a host/mock provides it', async () => {
    const updateToken = vi.fn(async () => undefined);
    const room = {
      engine: { token: 'old' },
      updateToken,
    };

    await applyRefreshedLiveKitToken(room, 'new-jwt');

    expect(updateToken).toHaveBeenCalledWith('new-jwt');
    expect(room.engine.token).toBe('new-jwt');
  });

  it('no-ops on null room', async () => {
    await expect(applyRefreshedLiveKitToken(null, 'x')).resolves.toBeUndefined();
  });
});
