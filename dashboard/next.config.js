/** @type {import('next').NextConfig} */

// F-M10: the dashboard shipped with no security headers. It is the surface that holds tenant
// session tokens (localStorage, F-C6), so CSP here is the main mitigation for the XSS chain
// that turns one injected script into a stolen tenant signing secret.
//
// connect-src has to allow the browser to reach the control plane and portal API, whose
// origins differ per environment — hence the env vars, with localhost defaults for dev.
const CONTROL_PLANE = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL || 'http://localhost:8000';
const PORTAL_API =
  process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL || 'http://localhost:8002';
// LiveKit is reached over WebSocket from the Test Studio.
const LIVEKIT = process.env.NEXT_PUBLIC_LIVEKIT_URL || 'wss://*.livekit.cloud';
// Phase 1: browser signs in via Supabase Auth (email/password → /auth/v1/token).
const SUPABASE = process.env.NEXT_PUBLIC_SUPABASE_URL || '';

const isProd = process.env.NODE_ENV === 'production';

/** localhost and 127.0.0.1 are different CSP hosts — allow both for local HTTP APIs. */
function localHostAliases(url) {
  const raw = (url || '').trim();
  if (!raw) return [];
  const out = [raw];
  try {
    const u = new URL(raw);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return out;
    if (u.hostname === 'localhost') {
      const alt = new URL(raw);
      alt.hostname = '127.0.0.1';
      out.push(alt.origin);
    } else if (u.hostname === '127.0.0.1') {
      const alt = new URL(raw);
      alt.hostname = 'localhost';
      out.push(alt.origin);
    }
  } catch {
    /* keep raw */
  }
  return out;
}

const connectSrc = [
  "'self'",
  ...localHostAliases(CONTROL_PLANE),
  ...localHostAliases(PORTAL_API),
  LIVEKIT,
  SUPABASE,
  'https://*.supabase.co',
  'wss://*.supabase.co',
  'https://*.livekit.cloud',
  'wss://*.livekit.cloud',
]
  .filter(Boolean)
  .filter((v, i, arr) => arr.indexOf(v) === i)
  .join(' ');

// Next.js injects inline bootstrap scripts, and in development also uses eval for HMR.
// Wave 2 / P1-H6: block inline event-handler attributes; keep 'unsafe-inline' for Next
// hydration until a nonce-based CSP is wired. Prefer HttpOnly portal cookies so XSS
// cannot read the session JWT from storage even if script-src stays imperfect.
const scriptSrc = isProd
  ? "'self' 'unsafe-inline'"
  : "'self' 'unsafe-inline' 'unsafe-eval'";

const csp = [
  "default-src 'self'",
  `script-src ${scriptSrc}`,
  "script-src-attr 'none'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "media-src 'self' blob: https:",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  "form-action 'self'",
  "object-src 'none'",
].join('; ');

const securityHeaders = [
  { key: 'Content-Security-Policy', value: csp },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'geolocation=(), camera=(), microphone=(self)' },
];

if (isProd) {
  // Only in production: a year-long HSTS pin against localhost is painful to undo.
  securityHeaders.push({
    key: 'Strict-Transport-Security',
    value: 'max-age=31536000; includeSubDomains',
  });
}

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // This repo has lockfiles at the root and in dashboard/, and Next 15 otherwise guesses the
  // workspace root (it picked the repo root, which would trace far more than this app).
  outputFileTracingRoot: __dirname,
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

module.exports = nextConfig;
