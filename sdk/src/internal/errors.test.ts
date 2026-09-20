import { describe, expect, it } from 'vitest';
import { mapSessionHttpError } from './errors.js';

/** F-M16: status + body → distinct SDK error codes (audit §9). */
describe('mapSessionHttpError (F-M16)', () => {
  it.each([
    { status: 404, body: '', code: 'agent_not_found' },
    { status: 500, body: 'boom', code: 'session_failed' },
    { status: 429, body: '', code: 'quota_exceeded' },
    { status: 429, body: '{}', code: 'quota_exceeded' },
    { status: 429, body: JSON.stringify({ error: 'rate limited' }), code: 'rate_limit' },
    { status: 429, body: JSON.stringify({ detail: 'rate_limit' }), code: 'rate_limit' },
    {
      status: 429,
      body: JSON.stringify({ error: 'concurrent cap exceeded' }),
      code: 'quota_exceeded',
    },
    {
      status: 429,
      body: JSON.stringify({ error: 'monthly minutes exceeded' }),
      code: 'quota_exceeded',
    },
    { status: 503, body: JSON.stringify({ code: 'worker_not_ready' }), code: 'worker_not_ready' },
    { status: 503, body: 'worker not ready', code: 'worker_not_ready' },
    { status: 429, body: JSON.stringify({ error: 'provider_limit' }), code: 'provider_limit' },
    { status: 502, body: 'provider limit hit', code: 'provider_limit' },
  ] as const)('HTTP $status body=$body → $code', ({ status, body, code }) => {
    const err = mapSessionHttpError(status, body);
    expect(err.code).toBe(code);
  });
});
