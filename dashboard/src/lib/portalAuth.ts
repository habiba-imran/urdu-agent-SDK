import { getSupabaseBrowserClient } from "@/lib/supabaseBrowser";

const API_BASE = process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL;
/** Legacy key — cleared on load; JWT must not live in localStorage (P1-H6). */
const LEGACY_TOKEN_KEY = "uva_tenant_portal_token";
const ROLE_KEY = "uva_portal_role";

/**
 * In-tab memory only (not localStorage). Needed when the dashboard origin and
 * portal API host differ (e.g. localhost:3000 → 127.0.0.1:8002): browsers treat
 * that as cross-site, so SameSite=Lax HttpOnly cookies are set but not sent on
 * ``fetch``. Bearer from memory keeps the session alive; HttpOnly cookie still
 * works when both sides share a site (localhost↔localhost or hosted SameSite=None).
 */
let memoryPortalToken: string | null = null;

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

export type PortalWhoami = {
  tenant_id: string;
  role?: string | null;
  auth_user_id?: string | null;
  tenant_name?: string | null;
};

export class PortalAuthError extends Error {}

function clearLegacyLocalStorageToken() {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

function setMemoryPortalToken(token: string | null | undefined) {
  memoryPortalToken =
    typeof token === "string" && token.trim().length > 0 ? token.trim() : null;
}

/** Authorization header value when an in-memory portal JWT is available. */
export function portalAuthHeaders(): Record<string, string> {
  if (!memoryPortalToken) {
    return {};
  }
  return { Authorization: `Bearer ${memoryPortalToken}` };
}

export function setPortalRole(role: string | null | undefined) {
  if (typeof window === "undefined") {
    return;
  }
  if (role && role.length > 0) {
    window.sessionStorage.setItem(ROLE_KEY, role);
  } else {
    window.sessionStorage.removeItem(ROLE_KEY);
  }
}

export function getPortalRole(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const role = window.sessionStorage.getItem(ROLE_KEY);
  return role && role.length > 0 ? role : null;
}

/** True when the cached portal role is owner (UI gate — API still enforces). */
export function isPortalOwner(): boolean {
  return getPortalRole() === "owner";
}

/** In-memory portal JWT if present (never reads localStorage). */
export function getStoredTenantToken(): string | null {
  clearLegacyLocalStorageToken();
  return memoryPortalToken;
}

/** Keep JWT in tab memory only — cookie is still set by the portal API. */
export function setStoredTenantToken(token: string) {
  clearLegacyLocalStorageToken();
  setMemoryPortalToken(token);
}

export function clearStoredTenantToken() {
  clearLegacyLocalStorageToken();
  setMemoryPortalToken(null);
  setPortalRole(null);
}

/** @deprecated Prefer ensurePortalSession / whoami. */
export function isPortalTokenValid(
  _token: string | null | undefined,
  _skewSec = 30,
): boolean {
  return Boolean(memoryPortalToken);
}

/** @deprecated Prefer ensurePortalSession / whoami. */
export function getStoredValidTenantToken(): string | null {
  return getStoredTenantToken();
}

let refreshInFlight: Promise<boolean> | null = null;

async function fetchWhoami(): Promise<PortalWhoami | null> {
  if (!API_BASE) {
    return null;
  }
  try {
    const response = await fetch(`${API_BASE}/portal/whoami`, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: {
        ...portalAuthHeaders(),
      },
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as PortalWhoami;
  } catch {
    return null;
  }
}

/**
 * Ensure a valid portal session (HttpOnly cookie and/or in-memory Bearer).
 * Re-exchanges via Supabase when both are missing/expired.
 */
export async function ensurePortalSession(): Promise<string | null> {
  clearLegacyLocalStorageToken();

  const existing = await fetchWhoami();
  if (existing?.tenant_id) {
    if (existing.role) {
      setPortalRole(existing.role);
    }
    return memoryPortalToken ?? "cookie";
  }

  if (refreshInFlight) {
    const ok = await refreshInFlight;
    return ok ? memoryPortalToken ?? "cookie" : null;
  }

  refreshInFlight = (async () => {
    try {
      if (!API_BASE) {
        return false;
      }
      const supabase = getSupabaseBrowserClient();
      const { data, error } = await supabase.auth.getSession();
      if (error || !data.session?.access_token) {
        clearStoredTenantToken();
        return false;
      }
      const portal = await exchangeSupabaseAccessToken(data.session.access_token);
      setPortalRole(portal.role ?? null);
      return true;
    } catch {
      clearStoredTenantToken();
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  const ok = await refreshInFlight;
  return ok ? memoryPortalToken ?? "cookie" : null;
}

const PUBLIC_AUTH_PATHS = new Set(["/login", "/invite", "/claim"]);

/** Hard redirect to login after clearing portal session. */
export function redirectToLogin(): void {
  if (typeof window === "undefined") {
    return;
  }
  void logoutPortalSession().finally(() => {
    const path = window.location.pathname;
    if (PUBLIC_AUTH_PATHS.has(path)) {
      return;
    }
    window.location.replace("/login");
  });
}

/** Exchange a Supabase access_token for the tenant portal JWT (sets HttpOnly cookie). */
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
    credentials: "include",
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

  const portal = (await response.json()) as PortalLoginResponse;
  setStoredTenantToken(portal.token);
  setPortalRole(portal.role ?? null);
  return portal;
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
    credentials: "include",
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

  const portal = (await response.json()) as PortalLoginResponse;
  setStoredTenantToken(portal.token);
  setPortalRole(portal.role ?? null);
  return portal;
}

export async function logoutPortalSession() {
  clearStoredTenantToken();
  if (API_BASE) {
    try {
      await fetch(`${API_BASE}/portal/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      /* ignore */
    }
  }
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
