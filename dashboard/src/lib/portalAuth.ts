import { getSupabaseBrowserClient } from "@/lib/supabaseBrowser";

const API_BASE = process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL;
const TOKEN_KEY = "uva_tenant_portal_token";

export type PortalLoginResponse = {
  token: string;
  tenant_id: string;
  tenant_name: string;
  expires_in: number;
  role?: string;
  email?: string | null;
};

export class PortalAuthError extends Error {}

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

export async function logoutPortalSession() {
  clearStoredTenantToken();
  try {
    const supabase = getSupabaseBrowserClient();
    await supabase.auth.signOut();
  } catch {
    /* env may be missing during teardown — portal token is already cleared */
  }
}
