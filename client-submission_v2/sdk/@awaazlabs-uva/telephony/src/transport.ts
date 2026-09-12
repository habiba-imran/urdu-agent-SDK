import { AwaazLabsUvaTelephonyError, createInvalidResponseError } from './errors.js';
import { AUTH_HEADER_NAMES, canonicalJson } from './signing.js';
import type {
  HttpMethod,
  JsonInputObject,
  JsonInputValue,
  JsonObject,
  JsonValue,
  JsonResponse,
  TelephonyFetch,
  TelephonyFetchInit,
  TelephonyFetchResponse,
} from './types.js';

const RESTRICTED_RESPONSE_KEYS = new Set([
  'api_key',
  'encrypted_api_key_ref',
  'encrypted_sip_secret_ref',
  'payload',
  'payload_access_scope',
  'provider_error_payload',
  'raw_livekit_sip_participant_status',
  'raw_provider_status',
  'request_hash',
  'response_body',
  'sip_secret',
  'tenant_secret',
  'x_signature',
]);

export function makeRequestInit(
  method: HttpMethod,
  body: JsonInputObject,
  extraHeaders: Record<string, string>,
  authHeaders: Record<string, string>,
): TelephonyFetchInit {
  const headers = { ...extraHeaders, Accept: 'application/json', 'Content-Type': 'application/json', ...authHeaders };
  const init: TelephonyFetchInit = { method, headers };
  if (method !== 'GET') init.body = canonicalJson(body);
  return init;
}

export async function readJsonBody(response: TelephonyFetchResponse): Promise<unknown> {
  const text = await response.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw createInvalidResponseError();
  }
}

export function fillPath(path: string, params: Record<string, string>): `/machine/telephony/${string}` {
  let output = path;
  for (const key of Object.keys(params)) {
    output = output.replace(`{${key}}`, encodeURIComponent(params[key]));
  }
  if (!output.startsWith('/machine/telephony/')) throw createInvalidResponseError();
  return output as `/machine/telephony/${string}`;
}

export function buildUrl(baseUrl: string, path: string): string {
  return `${baseUrl}${path}`;
}

export function toSnakeCaseBody(value: JsonInputObject): JsonInputObject {
  return toSnakeCaseValue(value) as JsonInputObject;
}

export function sanitizeExtraHeaders(extraHeaders?: Record<string, string>): Record<string, string> {
  const output: Record<string, string> = {};
  const blocked = new Set([...AUTH_HEADER_NAMES.map((name) => name.toLowerCase()), 'content-type']);
  for (const [name, value] of Object.entries(extraHeaders ?? {})) {
    if (!blocked.has(name.toLowerCase())) output[name] = value;
  }
  return output;
}

export function resolveFetch(fetcher?: TelephonyFetch): TelephonyFetch {
  if (fetcher) return fetcher;
  const runtime = globalThis as typeof globalThis & { fetch?: TelephonyFetch };
  if (!runtime.fetch) throw createInvalidResponseError();
  return runtime.fetch.bind(globalThis) as TelephonyFetch;
}

export function assertBackendRuntime(): void {
  const runtime = globalThis as typeof globalThis & { process?: { versions?: { node?: string } } };
  if (!runtime.process?.versions?.node) {
    throw new AwaazLabsUvaTelephonyError(500, 'telephony_request_failed', 'Telephony SDK requires Node.js.');
  }
}

export function assertNonEmpty(value: string, name: string): void {
  if (!value.trim()) {
    throw new AwaazLabsUvaTelephonyError(400, 'telephony_request_failed', `${name} is required.`);
  }
}

export function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isJsonResponse(value: unknown): value is JsonResponse {
  return isJsonObject(value) || Array.isArray(value);
}

export function sanitizePublicResponse(value: JsonResponse): JsonResponse {
  if (Array.isArray(value)) return value.map((item) => sanitizePublicValue(item) ?? null);

  const output: JsonObject = {};
  for (const [key, item] of Object.entries(value)) {
    if (RESTRICTED_RESPONSE_KEYS.has(key)) continue;
    output[key] = sanitizePublicValue(item);
  }
  return output;
}

function toSnakeCaseValue(value: JsonInputValue): JsonInputValue {
  if (value === undefined || value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map((item) => toSnakeCaseValue(item));

  const output: JsonInputObject = {};
  for (const key of Object.keys(value)) {
    const item = value[key];
    if (item !== undefined) output[toSnakeCaseKey(key)] = toSnakeCaseValue(item);
  }
  return output;
}

function toSnakeCaseKey(key: string): string {
  return key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

function sanitizePublicValue(value: JsonValue | undefined): JsonValue | undefined {
  if (value === undefined || value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map((item) => sanitizePublicValue(item) ?? null);

  const output: JsonObject = {};
  for (const [key, item] of Object.entries(value)) {
    if (RESTRICTED_RESPONSE_KEYS.has(key)) continue;
    output[key] = sanitizePublicValue(item);
  }
  return output;
}
