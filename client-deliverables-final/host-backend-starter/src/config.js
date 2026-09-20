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

function parseOrigins(raw) {
  return raw
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

export function loadConfig() {
  return {
    port: Number(process.env.PORT || 3000),
    controlPlaneUrl: requireEnv('UVA_CONTROL_PLANE_URL').replace(/\/$/, ''),
    tenantId: requireEnv('UVA_TENANT_ID'),
    hmacSecret: requireEnv('UVA_HMAC_SECRET'),
    publishableKey: requireEnv('UVA_PUBLISHABLE_KEY'),
    allowedOrigins: parseOrigins(
      process.env.HOST_ALLOWED_ORIGINS || 'http://localhost:5173',
    ),
    publicBaseUrl: process.env.HOST_PUBLIC_BASE_URL?.trim().replace(/\/$/, '') || '',
  };
}
