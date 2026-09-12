import type { JsonInputValue, JsonValue, TelephonyErrorCode } from './types.js';

const SENSITIVE_KEY_PARTS = [
  'api_key',
  'apikey',
  'authorization',
  'credential',
  'password',
  'payload',
  'secret',
  'signature',
  'token',
];

export class AwaazLabsUvaTelephonyError extends Error {
  readonly status: number;
  readonly code: TelephonyErrorCode;
  readonly detail?: JsonValue;

  constructor(
    status: number,
    code: TelephonyErrorCode,
    message: string,
    detail?: JsonValue,
  ) {
    super(redactMessage(message));
    this.name = 'AwaazLabsUvaTelephonyError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export function createNetworkError(): AwaazLabsUvaTelephonyError {
  return new AwaazLabsUvaTelephonyError(
    0,
    'telephony_request_failed',
    'Telephony API request failed.',
  );
}

export function createInvalidResponseError(): AwaazLabsUvaTelephonyError {
  return new AwaazLabsUvaTelephonyError(
    502,
    'telephony_invalid_response',
    'Telephony API returned an invalid response.',
  );
}

type ErrorEnvelope = {
  error: { code?: unknown; message?: unknown; status?: unknown; detail?: unknown };
};

export function errorFromResponse(
  status: number,
  statusText: string | undefined,
  body: unknown,
): AwaazLabsUvaTelephonyError {
  const fallbackMessage = statusText?.trim() || 'Telephony API request failed.';
  const envelope = resolveErrorEnvelope(body);
  if (!envelope) {
    return new AwaazLabsUvaTelephonyError(status, 'telephony_request_failed', fallbackMessage);
  }

  const code = isErrorCode(envelope.error.code) ? envelope.error.code : 'telephony_request_failed';
  const message = typeof envelope.error.message === 'string' ? envelope.error.message : fallbackMessage;
  const errorStatus = typeof envelope.error.status === 'number' ? envelope.error.status : status;
  const detail = sanitizeErrorDetail(envelope.error.detail);

  return new AwaazLabsUvaTelephonyError(errorStatus, code, message, detail);
}

function resolveErrorEnvelope(value: unknown): ErrorEnvelope | null {
  if (isErrorEnvelope(value)) return value;
  if (!isRecord(value)) return null;
  return isErrorEnvelope(value.detail) ? value.detail : null;
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!isRecord(value)) return false;
  return isRecord(value.error);
}
function isErrorCode(value: unknown): value is TelephonyErrorCode {
  return typeof value === 'string' && value.trim().length > 0;
}

function sanitizeErrorDetail(value: unknown): JsonValue | undefined {
  if (value === undefined) return undefined;
  return sanitizeValue(value as JsonInputValue, '');
}

function sanitizeValue(value: JsonInputValue, key: string): JsonValue {
  if (isSensitiveKey(key)) return '[REDACTED]';
  if (value === undefined) return null;
  if (value === null || typeof value === 'boolean' || typeof value === 'number') return value;
  if (typeof value === 'string') return redactMessage(value);
  if (Array.isArray(value)) return value.map((item) => sanitizeValue(item, key));

  const output: { [key: string]: JsonValue } = {};
  for (const childKey of Object.keys(value).sort()) {
    output[childKey] = sanitizeValue(value[childKey], childKey);
  }
  return output;
}

function isSensitiveKey(key: string): boolean {
  const normalized = key.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
  return SENSITIVE_KEY_PARTS.some((part) => normalized.includes(part.replace('_', '')));
}

function redactMessage(message: string): string {
  return message
    .replace(/sk_[a-zA-Z0-9_-]+/g, '[REDACTED]')
    .replace(/[a-fA-F0-9]{64}/g, '[REDACTED]');
}

function isRecord(value: unknown): value is { [key: string]: unknown } {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
