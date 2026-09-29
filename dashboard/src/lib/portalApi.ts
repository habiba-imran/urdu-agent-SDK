import {
  clearStoredTenantToken,
  ensurePortalSession,
  redirectToLogin,
} from '@/lib/portalAuth';

const API_BASE = process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL;

export type PortalAgent = {
  id: string;
  name: string;
  prompt: string;
  voice_id: string;
  llm_model: string;
  created_at: string | null;
  total_agent_sec?: number;
  // Advanced parameters
  top_p?: number;
  phone_number?: string | null;
  phone_number_id?: string | null;
  vad_sensitivity?: number;
  agent_description?: string;
  // Multi-provider / language (ADR-036) — see provider_capabilities.py for what's enabled.
  agent_language?: string;
  stt_provider?: string;
  stt_model?: string;
  stt_options?: Record<string, unknown>;
  llm_provider?: string;
  llm_options?: Record<string, unknown>;
  tts_provider?: string;
  tts_voice_id?: string | null;
  tts_options?: Record<string, unknown>;
  /** F-C4 — opt-in call recording (default false). */
  recording_enabled?: boolean;
};

// ── Provider capabilities (ADR-036) — which STT/LLM/TTS providers + models/voices are enabled
// per agent_language. Mirrors test-app/frontend/src/lib/api.ts's ProviderCapabilities exactly,
// since both consume the same tenant_portal_api response shape (machine vs portal auth only).
export type ProviderCapabilityEntry = {
  state: 'enabled';
  models?: string[];
  defaultModel?: string;
  voices?: string[];
  defaultVoice?: string | null;
};

export type LanguageCapabilities = {
  label: string;
  stt?: Record<string, ProviderCapabilityEntry>;
  llm?: Record<string, ProviderCapabilityEntry>;
  tts?: Record<string, ProviderCapabilityEntry>;
};

export type ProviderCapabilities = {
  languages: Record<string, LanguageCapabilities>;
};

export type PortalCredentials = {
  publishable_key: string;
  tenant_id: string;
  name: string;
  allowed_origins: string[];
  hmac_secret_hash: string;
  secret_masked: string;
  status: string;
  /** True when an HMAC secret hash exists for this tenant. */
  secret_provisioned?: boolean;
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
  /** Open AND started within the backend's staleness bound (LIVE_SESSION_MAX_AGE_MIN). */
  live: boolean;
  /** Open but past that bound — the session leaked and was never closed. */
  stale: boolean;
  /** One-sentence, agent-generated summary (worker/tools.py::end_conversation_summary).
   *  Null for any call that never reached that tool call. */
  summary: string | null;
  /** Real user/assistant turns only, in order. Null for any session that never reached a
   *  clean close (worker/main.py::_release_quota_slot). */
  transcript: Array<{ role: string; text: string | null; at: number }> | null;
  /**
   * Billable seconds from usage_events.agent_sec (source of truth for payment).
   * 0 when the session never wrote usage (reconciled/stale/no participant).
   */
  billable_agent_sec?: number;
};

export type PortalUsageSummary = {
  /** Inclusive start of the selected calendar month (UTC), e.g. "2026-07-01". */
  period_start: string;
  /** Exclusive — the 1st of NEXT month (UTC), e.g. "2026-08-01". */
  period_end: string;
  /** Server's current UTC calendar month as YYYY-MM. */
  current_month?: string;
  /** True when period_start is the current UTC calendar month. */
  is_current_period?: boolean;
  /** Always "UTC" — month boundaries for billing. */
  timezone?: string;
  /** Invoice figure: sum(agent_sec) / 60, half-up to 4 dp. */
  billable_minutes?: number;
  billable_agent_sec?: number;
  quota: {
    max_concurrent: number;
    max_minutes_month: number;
    concurrent_now: number;
    /** Same as billable_minutes (UI / Overview back-compat). */
    minutes_this_month: number;
    /** What the mint currently enforces (current month only); may briefly diverge. */
    enforced_minutes?: number | null;
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

  let token = await ensurePortalSession();
  if (!token) {
    redirectToLogin();
    throw new PortalApiAuthError("Missing tenant session. Please sign in again.");
  }

  const doFetch = (bearer: string) =>
    fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${bearer}`,
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });

  let response = await doFetch(token);

  if (response.status === 401) {
    // Portal JWT expired or rejected — try one silent re-exchange, then login.
    clearStoredTenantToken();
    token = await ensurePortalSession();
    if (token) {
      response = await doFetch(token);
    }
    if (!token || response.status === 401) {
      redirectToLogin();
      throw new PortalApiAuthError("Session expired. Please sign in again.");
    }
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;

    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body?.detail != null) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {}

    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function getAgents() {
  return request<PortalAgent[]>("/portal/agents");
}

export function getAgentById(agentId: string) {
  return request<PortalAgent>(`/portal/agents/${agentId}`);
}

export type AgentProviderFields = {
  agent_language?: string;
  stt_provider?: string;
  stt_model?: string;
  llm_provider?: string;
  tts_provider?: string;
  tts_voice_id?: string;
};

export function createAgent(
  body: {
    name: string;
    prompt: string;
    voice_id: string;
    llm_model: string;
    top_p?: number;
    agent_description?: string;
  } & AgentProviderFields,
) {
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
    top_p?: number;
    agent_description?: string;
    recording_enabled?: boolean;
  } & AgentProviderFields,
) {
  return request<PortalAgent>(`/portal/agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteAgent(agentId: string) {
  return request<{ success: boolean }>(`/portal/agents/${agentId}`, {
    method: "DELETE",
  });
}

export function getProviderCapabilities() {
  return request<ProviderCapabilities>("/portal/provider-capabilities");
}

export function getCredentials() {
  return request<PortalCredentials>("/portal/credentials");
}

export function getCredentialSecret() {
  return request<{ hmac_secret: string }>("/portal/credentials/secret");
}

export function rotateCredentialSecret() {
  return request<{ hmac_secret: string; warning: string }>(
    "/portal/credentials/rotate-secret",
    { method: "POST" },
  );
}

export function setAllowedOrigins(allowed_origins: string[]) {
  return request<{
    allowed_origins: string[];
    enforced: boolean;
    note: string;
  }>("/portal/credentials/allowed-origins", {
    method: "PUT",
    body: JSON.stringify({ allowed_origins }),
  });
}

export function getSessions(limit = 50) {
  return request<PortalSession[]>(`/portal/sessions?limit=${limit}`);
}

export function getSession(sessionId: string) {
  return request<PortalSession>(`/portal/sessions/${sessionId}`);
}

export type PortalMember = {
  auth_user_id: string;
  email: string | null;
  role: "owner" | "member" | string;
  status: "invited" | "active" | string;
  created_at: string | null;
};

export function getMembers() {
  return request<PortalMember[]>("/portal/members");
}

export function inviteMember(email: string) {
  return request<
    PortalMember & {
      tenant_id: string;
      existing_auth_user?: boolean;
      resent?: boolean;
    }
  >("/portal/members/invite", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function getUsageSummary(month?: string) {
  const q = month ? `?month=${encodeURIComponent(month)}` : "";
  return request<PortalUsageSummary>(`/portal/usage-summary${q}`);
}
