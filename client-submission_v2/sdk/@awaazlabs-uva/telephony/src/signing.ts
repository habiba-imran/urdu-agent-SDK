import { createHash, createHmac, randomUUID } from 'node:crypto';

import type { JsonInputObject, JsonInputValue, JsonValue } from './types.js';

export const AUTH_HEADER_NAMES = [
  'X-Tenant-Id',
  'X-Timestamp',
  'X-Nonce',
  'X-Signature',
] as const;

export interface CreateRequestSignatureOptions {
  tenantId: string;
  tenantSecret: string;
  timestamp: string;
  nonce: string;
  action: string;
  body?: JsonInputObject;
}

export interface CreateSignedHeadersOptions {
  tenantId: string;
  tenantSecret: string;
  action: string;
  body?: JsonInputObject;
  timestamp?: string;
  nonce?: string;
}

export interface SignedHeaders {
  headers: Record<string, string>;
  canonicalBody: string;
  payloadHash: string;
}

export function canonicalJson(value?: JsonInputValue): string {
  const normalized = value === undefined ? {} : normalizeJson(value);
  return JSON.stringify(normalized);
}

export function createPayloadHash(body?: JsonInputObject): string {
  return createHash('sha256').update(canonicalJson(body)).digest('hex');
}

export function createRequestSignature(options: CreateRequestSignatureOptions): string {
  const payloadHash = createPayloadHash(options.body);
  const message = [
    options.tenantId,
    options.timestamp,
    options.nonce,
    options.action,
    payloadHash,
  ].join('.');

  return createHmac('sha256', options.tenantSecret).update(message).digest('hex');
}

export function createSignedHeaders(options: CreateSignedHeadersOptions): SignedHeaders {
  const timestamp = options.timestamp ?? String(Math.floor(Date.now() / 1000));
  const nonce = options.nonce ?? createNonce();
  const signature = createRequestSignature({ ...options, timestamp, nonce });

  return {
    canonicalBody: canonicalJson(options.body),
    payloadHash: createPayloadHash(options.body),
    headers: {
      'X-Tenant-Id': options.tenantId,
      'X-Timestamp': timestamp,
      'X-Nonce': nonce,
      'X-Signature': signature,
    },
  };
}

export function createNonce(): string {
  return randomUUID();
}

function normalizeJson(value: JsonInputValue): JsonValue {
  if (value === undefined) return null;
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError('JSON numbers must be finite.');
    return value;
  }
  if (Array.isArray(value)) return value.map((item) => normalizeJson(item));

  const output: { [key: string]: JsonValue } = {};
  for (const key of Object.keys(value).sort()) {
    const item = value[key];
    if (item !== undefined) output[key] = normalizeJson(item);
  }
  return output;
}
