import { clearStoredTenantToken, getStoredTenantToken } from '@/lib/portalAuth';

const API_BASE = process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL;

export type PortalAgent = {
  id: string;
  name: string;
  prompt: string;
  voice_id: string;
  llm_model: string;
  created_at: string | null;
  total_agent_sec?: number;
};

export type PortalCredentials = {
  publishable_key: string;
  tenant_id: string;
  name: string;
  allowed_origins: string[];
  hmac_secret_hash: string;
  secret_masked: string;
  status: string;
};

export type PortalSession = {
  id: string;
  agent_id: string;
  agent_name: string;
  room_name: string;
  started_at: string | null;
  ended_at: string | null;
  duration_sec: number | null;
  end_reason: string | null;
  live: boolean;
};

export type PortalUsageSummary = {
  window_days: number;
  quota: {
    max_concurrent: number;
    max_minutes_month: number;
    concurrent_now: number;
    minutes_this_month: number;
  };
  totals: Array<{
    kind: string;
    total_qty: number;
  }>;
  daily: Array<{
    day: string;
    kind: string;
    total_qty: number;
  }>;
};

export class PortalApiConfigError extends Error {}
export class PortalApiAuthError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) {
    throw new PortalApiConfigError(
      "Missing NEXT_PUBLIC_TENANT_PORTAL_API_URL in dashboard/.env.local",
    );
  }

  const token = getStoredTenantToken();
  if (!token) {
    throw new PortalApiAuthError("Missing tenant session. Please sign in again.");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    if (response.status === 401) {
      clearStoredTenantToken();
      throw new PortalApiAuthError("Session expired. Please sign in again.");
    }

    let detail = `${response.status} ${response.statusText}`;

    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) {
        detail = body.detail;
      }
    } catch {}

    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function getAgents() {
  return request<PortalAgent[]>("/portal/agents");
}

export function createAgent(body: {
  name: string;
  prompt: string;
  voice_id: string;
  llm_model: string;
}) {
  return request<PortalAgent>("/portal/agents", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateAgent(
  agentId: string,
  body: {
    name?: string;
    prompt?: string;
    voice_id?: string;
    llm_model?: string;
  },
) {
  return request<PortalAgent>(`/portal/agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function getCredentials() {
  return request<PortalCredentials>("/portal/credentials");
}

export function getSessions(limit = 50) {
  return request<PortalSession[]>(`/portal/sessions?limit=${limit}`);
}

export function getUsageSummary(days = 30) {
  return request<PortalUsageSummary>(`/portal/usage-summary?days=${days}`);
}
