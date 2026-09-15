/**
 * SDK error types + session HTTP mapping (F-M16).
 * Kept under `internal/` so unit tests can import without expanding package `exports`.
 */

/**
 * Error codes thrown / emitted by `@awaazlabs-uva/voice`.
 *
 * - `quota_exceeded` — plan concurrent/monthly cap (or unknown 429 with no distinguishable body)
 * - `agent_not_found` — HTTP 404 from the session endpoint
 * - `session_failed` — generic connect / session failure
 * - `rate_limit` — platform rate limit (e.g. control-plane "rate limited")
 * - `worker_not_ready` — host/control-plane signals worker not ready
 * - `provider_limit` — upstream provider limit (distinct from plan quota)
 * - `timeout` — request aborted by client timeout (wired in F-M14 / Phase 4)
 * - `token_refresh_failed` — LiveKit token refresh failed permanently or until token expiry (F-H12)
 */
export type AwaazLabsUvaVoiceErrorCode =
  | 'quota_exceeded'
  | 'agent_not_found'
  | 'session_failed'
  | 'rate_limit'
  | 'worker_not_ready'
  | 'provider_limit'
  | 'timeout'
  | 'token_refresh_failed';

export class AwaazLabsUvaVoiceError extends Error {
  constructor(
    public readonly code: AwaazLabsUvaVoiceErrorCode,
    message?: string,
  ) {
    super(message ?? code);
    this.name = 'AwaazLabsUvaVoiceError';
  }
}

/** Pull a string signal from common host / FastAPI error JSON shapes. */
export function sessionErrorSignal(bodyText: string): string {
  const raw = bodyText.trim();
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    for (const key of ['error', 'detail', 'code'] as const) {
      const value = parsed[key];
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
  } catch {
    // Non-JSON body — use raw text.
  }
  return raw;
}

/**
 * Map session-endpoint HTTP status + body to an SDK error (F-M16).
 * Unknown / empty 429 bodies stay `quota_exceeded` for backward compatibility.
 */
export function mapSessionHttpError(status: number, bodyText: string): AwaazLabsUvaVoiceError {
  const signal = sessionErrorSignal(bodyText).toLowerCase();

  if (signal.includes('worker_not_ready') || signal.includes('worker-not-ready') || signal.includes('worker not ready')) {
    return new AwaazLabsUvaVoiceError('worker_not_ready', bodyText.trim() || 'worker not ready');
  }
  if (signal.includes('provider_limit') || signal.includes('provider-limit') || signal.includes('provider limit')) {
    return new AwaazLabsUvaVoiceError('provider_limit', bodyText.trim() || 'provider limit');
  }

  if (status === 404) {
    return new AwaazLabsUvaVoiceError('agent_not_found');
  }

  if (status === 429) {
    if (signal.includes('rate limited') || signal.includes('rate_limit') || signal.includes('rate-limit')) {
      return new AwaazLabsUvaVoiceError('rate_limit', bodyText.trim() || 'rate limited');
    }
    if (
      signal.includes('concurrent cap') ||
      signal.includes('monthly minutes') ||
      signal.includes('quota')
    ) {
      return new AwaazLabsUvaVoiceError('quota_exceeded', bodyText.trim() || 'quota exceeded');
    }
    // Opaque 429 — preserve prior SDK behaviour.
    return new AwaazLabsUvaVoiceError('quota_exceeded');
  }

  return new AwaazLabsUvaVoiceError('session_failed', bodyText.trim() || `HTTP ${status}`);
}
