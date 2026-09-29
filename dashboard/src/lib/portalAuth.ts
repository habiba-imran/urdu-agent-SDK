import { getSupabaseBrowserClient } from "@/lib/supabaseBrowser";

const API_BASE = process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL;
const TOKEN_KEY = "uva_tenant_portal_token";

/** Must match ``tenant_portal_api.auth.TENANT_JWT_TTL_SEC`` (8 hours). */
export const PORTAL_SESSION_TTL_SEC = 8 * 3600;
export const PORTAL_SESSION_TTL_HOURS = PORTAL_SESSION_TTL_SEC / 3600;

export type PortalLoginResponse = {
  token: string;
  tenant_id: string;
  tenant_name: string;
  expires_in: number;
  role?: string;
  email?: string | null;
};

export class PortalAuthError extends Error {}

type JwtPayload = {
  exp?: number;
  iat?: number;
  sub?: string;
  role?: string;
  auth_user_id?: string;
};

function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) {
      return null;
    }
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const json = atob(padded);
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function getStoredTenantToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setStoredTenantToken(token: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredTenantToken() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(TOKEN_KEY);
}

/** True if the portal JWT exists and ``exp`` is still in the future (small skew). */
export function isPortalTokenValid(
  token: string | null | undefined,
  skewSec = 30,
): boolean {
  if (!token) {
    return false;
  }
  const payload = decodeJwtPayload(token);
  if (!payload?.exp || typeof payload.exp !== "number") {
    return false;
  }
  return payload.exp * 1000 > Date.now() + skewSec * 1000;
}

/** Return stored token only if not expired; clear stale tokens. */
export function getStoredValidTenantToken(): string | null {
  const token = getStoredTenantToken();
  if (!token) {
    return null;
  }
  if (!isPortalTokenValid(token)) {
    clearStoredTenantToken();
    return null;
  }
  return token;
}

/** Role claim from the current portal JWT (`owner` | `member`), or null if logged out. */
export function getPortalRole(): string | null {
  const token = getStoredValidTenantToken();
  if (!token) {
    return null;
  }
  const payload = decodeJwtPayload(token);
  const role = payload?.role;
  return typeof role === "string" && role.length > 0 ? role : null;
}

let refreshInFlight: Promise<string | null> | null = null;

/**
 * Ensure a valid portal JWT. If the stored one expired, silently re-exchange
 * using the Supabase session (when still signed in). Returns null if the user
 * must sign in again.
 */
export async function ensurePortalSession(): Promise<string | null> {
  const existing = getStoredValidTenantToken();
  if (existing) {
    return existing;
  }

  if (refreshInFlight) {
    return refreshInFlight;
  }

  refreshInFlight = (async () => {
    try {
      if (!API_BASE) {
        return null;
      }
      const supabase = getSupabaseBrowserClient();
      const { data, error } = await supabase.auth.getSession();
      if (error || !data.session?.access_token) {
        clearStoredTenantToken();
        return null;
      }
      const portal = await exchangeSupabaseAccessToken(data.session.access_token);
      setStoredTenantToken(portal.token);
      return portal.token;
    } catch {
      clearStoredTenantToken();
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

const PUBLIC_AUTH_PATHS = new Set(["/login", "/invite", "/claim"]);

/** Hard redirect to login after clearing portal token (avoids sticky error banners). */
export function redirectToLogin(): void {
  if (typeof window === "undefined") {
    return;
  }
  clearStoredTenantToken();
  const path = window.location.pathname;
  if (PUBLIC_AUTH_PATHS.has(path)) {
    return;
  }
  window.location.replace("/login");
}

/** Exchange a Supabase access_token for the tenant portal JWT used by /portal/*. */
export async function exchangeSupabaseAccessToken(
  accessToken: string,
): Promise<PortalLoginResponse> {
  if (!API_BASE) {
    throw new PortalAuthError(
      "Missing NEXT_PUBLIC_TENANT_PORTAL_API_URL in dashboard/.env.local",
    );
  }

  const response = await fetch(`${API_BASE}/portal/auth/supabase`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ access_token: accessToken }),
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const json = (await response.json()) as { detail?: string };
      if (json.detail) {
        detail = typeof json.detail === "string" ? json.detail : detail;
      }
    } catch {
      /* ignore */
    }
    throw new PortalAuthError(detail);
  }

  return (await response.json()) as PortalLoginResponse;
}

/** Email/password via Supabase Auth, then bind to tenant via portal exchange. */
export async function loginWithEmailPassword(
  email: string,
  password: string,
): Promise<PortalLoginResponse> {
  const supabase = getSupabaseBrowserClient();
  const { data, error } = await supabase.auth.signInWithPassword({
    email: email.trim(),
    password,
  });

  if (error) {
    throw new PortalAuthError(error.message);
  }

  const accessToken = data.session?.access_token;
  if (!accessToken) {
    throw new PortalAuthError("Supabase login succeeded but no session was returned");
  }

  return exchangeSupabaseAccessToken(accessToken);
}

/** After email/password Auth exists: attach this user to a pre-email tenant via HMAC. */
export async function claimExistingTenant(input: {
  tenantId: string;
  tenantSecret: string;
}): Promise<PortalLoginResponse> {
  if (!API_BASE) {
    throw new PortalAuthError(
      "Missing NEXT_PUBLIC_TENANT_PORTAL_API_URL in dashboard/.env.local",
    );
  }

  const supabase = getSupabaseBrowserClient();
  const { data, error } = await supabase.auth.getSession();
  if (error) {
    throw new PortalAuthError(error.message);
  }
  const accessToken = data.session?.access_token;
  if (!accessToken) {
    throw new PortalAuthError(
      "Sign in with email and password first, then claim your existing tenant.",
    );
  }

  const response = await fetch(`${API_BASE}/portal/auth/claim-tenant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      access_token: accessToken,
      tenant_id: input.tenantId.trim(),
      tenant_secret: input.tenantSecret,
    }),
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const json = (await response.json()) as { detail?: string };
      if (json.detail) {
        detail = typeof json.detail === "string" ? json.detail : detail;
      }
    } catch {
      /* ignore */
    }
    throw new PortalAuthError(detail);
  }

  return (await response.json()) as PortalLoginResponse;
}

export async function logoutPortalSession() {
  clearStoredTenantToken();
  try {
    const supabase = getSupabaseBrowserClient();
    await supabase.auth.signOut();
  } catch {
    /* env may be missing during teardown — portal token is already cleared */
  }
}

/** True when an API/SWR error is an auth failure (pages should not show it as a backend banner). */
export function isPortalAuthFailure(error: unknown): boolean {
  if (!error) {
    return false;
  }
  if (error instanceof PortalAuthError) {
    return true;
  }
  const msg = error instanceof Error ? error.message : String(error);
  return /session expired|missing tenant session|sign in again|unauthorized|401/i.test(
    msg,
  );
}
