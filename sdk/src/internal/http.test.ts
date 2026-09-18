import { afterEach, describe, expect, it, vi } from 'vitest';
import { AwaazLabsUvaVoiceError } from './errors.js';
import { fetchWithTimeout } from './http.js';

/** F-M14: AbortController timeout on hung fetch. */
describe('fetchWithTimeout (F-M14)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('throws timeout when fetch never resolves', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: string, init?: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            const err = new Error('aborted');
            err.name = 'AbortError';
            reject(err);
          });
        });
      }),
    );

    const pending = fetchWithTimeout('https://example.test/session', { method: 'POST' }, 1_000);
    const assertion = expect(pending).rejects.toMatchObject({
      name: 'AwaazLabsUvaVoiceError',
      code: 'timeout',
    } satisfies Partial<AwaazLabsUvaVoiceError>);

    await vi.advanceTimersByTimeAsync(1_000);
    await assertion;
  });

  it('returns response when fetch completes before timeout', async () => {
    const ok = new Response('{}', { status: 200 });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ok),
    );

    const res = await fetchWithTimeout('https://example.test/voices', undefined, 5_000);
    expect(res).toBe(ok);
  });
});
