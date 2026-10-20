import { config as loadEnv } from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
loadEnv({ path: path.resolve(__dirname, '../.env') });

function requireEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function optionalEnv(name, fallback = '') {
  const value = process.env[name]?.trim();
  return value || fallback;
}

function optionalNumberEnv(name, fallback) {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive number of milliseconds, got ${raw}`);
  }
  return value;
}

function parseOrigins(raw) {
  return raw
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

export function loadConfig() {
  const portalApiUrl = optionalEnv('UVA_API_BASE_URL').replace(/\/$/, '');
  const telephonyApiUrl =
    optionalEnv('UVA_TELEPHONY_API_URL').replace(/\/$/, '') || portalApiUrl;

  return {
    port: Number(process.env.PORT || 3100),
    controlPlaneUrl: requireEnv('UVA_CONTROL_PLANE_URL').replace(/\/$/, ''),
    portalApiUrl,
    telephonyApiUrl,
    tenantId: requireEnv('UVA_TENANT_ID'),
    hmacSecret: requireEnv('UVA_HMAC_SECRET'),
    publishableKey: requireEnv('UVA_PUBLISHABLE_KEY'),
    telnyxApiKey: optionalEnv('TELNYX_API_KEY'),
    telnyxSipFqdn: optionalEnv('TELNYX_SIP_FQDN'),
    telnyxSipUsername: optionalEnv('TELNYX_SIP_USERNAME'),
    telnyxSipSecret: optionalEnv('TELNYX_SIP_SECRET'),
    telnyxOutboundAllowedDestinations: optionalEnv(
      'TELNYX_OUTBOUND_ALLOWED_DESTINATIONS',
      'US',
    ),
    // telephonyRoutes reads both with `??` fallbacks, so leaving them out of the config
    // made them test-only injections rather than anything an operator could tune.
    telephonyOperationTimeoutMs: optionalNumberEnv(
      'TELEPHONY_OPERATION_TIMEOUT_MS',
      120000,
    ),
    telephonyReadTimeoutMs: optionalNumberEnv('TELEPHONY_READ_TIMEOUT_MS', 10000),
    allowedOrigins: parseOrigins(
      process.env.HOST_ALLOWED_ORIGINS || 'http://localhost:5174',
    ),
    publicBaseUrl: optionalEnv('HOST_PUBLIC_BASE_URL').replace(/\/$/, ''),
  };
}
