/** @type {import('next').NextConfig} */

// F-M10: the dashboard shipped with no security headers. It is the surface that holds tenant
// session tokens (localStorage, F-C6), so CSP here is the main mitigation for the XSS chain
// that turns one injected script into a stolen tenant signing secret.
//
// connect-src has to allow the browser to reach the control plane and portal API, whose
// origins differ per environment — hence the env vars, with localhost defaults for dev.
const CONTROL_PLANE = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL || 'http://localhost:8000';
const PORTAL_API = process.env.NEXT_PUBLIC_PORTAL_API_URL || 'http://localhost:8002';
// LiveKit is reached over WebSocket from the Test Studio.
const LIVEKIT = process.env.NEXT_PUBLIC_LIVEKIT_URL || 'wss://*.livekit.cloud';

const isProd = process.env.NODE_ENV === 'production';

const connectSrc = ["'self'", CONTROL_PLANE, PORTAL_API, LIVEKIT, 'https://*.livekit.cloud', 'wss://*.livekit.cloud']
  .filter(Boolean)
  .join(' ');

// Next.js injects inline bootstrap scripts, and in development also uses eval for HMR.
const scriptSrc = isProd
  ? "'self' 'unsafe-inline'"
  : "'self' 'unsafe-inline' 'unsafe-eval'";

const csp = [
  "default-src 'self'",
  `script-src ${scriptSrc}`,
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
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

module.exports = nextConfig;
