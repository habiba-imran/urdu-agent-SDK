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

/** Bound the entire operation, including response bodies and asynchronous host auth. */
export async function withDeadline<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  timeoutMs: number,
  parent?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let abort: () => void = () => {};
  const cancelled = new Promise<never>((_, reject) => {
    abort = () => {
      controller.abort();
      reject(parent?.reason instanceof Error ? parent.reason : new AwaazLabsUvaVoiceError('session_failed', 'Connection cancelled'));
    };
    if (parent?.aborted) { abort(); return; }
    parent?.addEventListener('abort', abort, { once: true });
    timer = setTimeout(() => {
      controller.abort();
      reject(new AwaazLabsUvaVoiceError('timeout', `Operation timed out after ${timeoutMs}ms`));
    }, Math.max(1, timeoutMs));
  });
  try {
    if (parent?.aborted) return await cancelled;
    return await Promise.race([operation(controller.signal), cancelled]);
  } finally {
    clearTimeout(timer);
    parent?.removeEventListener('abort', abort);
  }
}

export async function fetchTextWithTimeout(input: string, init: RequestInit | undefined, timeoutMs: number,
  parent?: AbortSignal): Promise<{ response: Response; text: string }> {
  return withDeadline(async (signal) => {
    const response = await fetch(input, { ...init, signal });
    return { response, text: await response.text() };
  }, timeoutMs, parent);
}
