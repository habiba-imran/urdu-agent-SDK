/**
 * Fetch helpers with AbortController timeout (F-M14).
 * Kept under `internal/` so unit tests can import without expanding package `exports`.
 */

import { AwaazLabsUvaVoiceError } from './errors.js';

/** Default fetch timeout for F-M14 (plan-locked; audit requires configurable timeout). */
export const DEFAULT_FETCH_TIMEOUT_MS = 15_000;

export async function fetchWithTimeout(
  input: string,
  init: RequestInit | undefined,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new AwaazLabsUvaVoiceError('timeout', `request timed out after ${timeoutMs}ms`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
