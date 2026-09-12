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
};

export type PortalUsageSummary = {
  /** Inclusive start of the current calendar month, e.g. "2026-07-01". */
  period_start: string;
  /** Exclusive — the 1st of NEXT month, e.g. "2026-08-01". Not "the last day": avoids any
   *  ambiguity about whether the final instant of the month is included. */
  period_end: string;
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

export function getSessions(limit = 50) {
  return request<PortalSession[]>(`/portal/sessions?limit=${limit}`);
}

export function getUsageSummary() {
  return request<PortalUsageSummary>("/portal/usage-summary");
}
