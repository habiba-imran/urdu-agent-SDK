const API_BASE = process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL;
const TOKEN_KEY = "uva_tenant_portal_token";

export type PortalLoginResponse = {
  token: string;
  tenant_id: string;
  tenant_name: string;
  expires_in: number;
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

export async function loginTenantPortal(body: {
  tenant_id: string;
  tenant_secret: string;
}): Promise<PortalLoginResponse> {
  if (!API_BASE) {
    throw new PortalAuthError(
      "Missing NEXT_PUBLIC_TENANT_PORTAL_API_URL in dashboard/.env.local",
    );
  }

  const response = await fetch(`${API_BASE}/portal/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const json = (await response.json()) as { detail?: string };
      if (json.detail) {
        detail = json.detail;
      }
    } catch {}
    throw new PortalAuthError(detail);
  }

  return (await response.json()) as PortalLoginResponse;
}
