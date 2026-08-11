import { getStoredTenantToken, clearStoredTenantToken } from '@/lib/portalAuth';

const API_BASE = process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL;

export type TelnyxConnectionStatus = {
  connected?: boolean;
  platform_status?: string | null;
  provider_status?: string | null;
  tenant_id: string;
  label?: string | null;
  status?: string | null;
  key_mask?: string | null;
  key_fingerprint?: string | null;
  verified_at?: string | null;
  last_verified_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
};

export type ManagedPhoneNumber = {
  id: string;
  e164_number: string;
  country?: string | null;
  locality?: string | null;
  assigned_agent_id?: string | null;
  assigned_agent_name?: string | null;
  status?: string | null;
  telnyx_phone_number_id?: string | null;
  external_customer_ref?: string | null;
  created_at?: string | null;
};

export type AvailablePhoneNumber = {
  e164_number: string;
  country: string;
  region?: string | null;
  locality?: string | null;
  number_type?: string | null;
  monthly_cost?: string | number | null;
  upfront_cost?: string | number | null;
  features?: string[] | null;
};

export type NumberDriftReport = {
  drift_detected: boolean;
  managed_count: number;
  provider_count: number;
  unmapped_in_provider: string[];
  missing_in_provider: string[];
};

export type TelephonyReadiness = {
  is_ready?: boolean;
  ready?: boolean;
  connection_status?: string;
  sip_status?: string;
  outbound_profile_status?: string;
  active_numbers_count?: number;
  reasons?: string[];
  missing_steps?: string[];
  has_connection?: boolean;
  has_managed_numbers?: boolean;
  has_sip_connection?: boolean;
  has_outbound_profile?: boolean;
  has_outbound_trunk?: boolean;
};

export type TelephonyHealth = {
  status: 'ok' | 'degraded' | 'error';
  database: boolean;
  timestamp: string;
  details?: Record<string, any>;
};

export class TelephonyApiError extends Error {
  status?: number;
  code?: string;
  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function telephonyRequest<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) {
    throw new TelephonyApiError('Missing NEXT_PUBLIC_TENANT_PORTAL_API_URL in dashboard/.env.local');
  }

  const token = getStoredTenantToken();
  if (!token) {
    throw new TelephonyApiError('Missing tenant session. Please sign in again.', 401);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    if (response.status === 401) {
      clearStoredTenantToken();
      throw new TelephonyApiError('Session expired. Please sign in again.', 401);
    }

    let detail = `${response.status} ${response.statusText}`;
    let code: string | undefined = undefined;
    try {
      const json = await response.json();
      if (json.detail?.error?.message) {
        detail = json.detail.error.message;
        code = json.detail.error.code;
      } else if (json.detail?.message) {
        detail = json.detail.message;
      } else if (typeof json.detail === 'string') {
        detail = json.detail;
      }
    } catch {}

    throw new TelephonyApiError(detail, response.status, code);
  }

  return (await response.json()) as T;
}

// -------------------------------------------------------------
// Provider & Account Connection APIs
// -------------------------------------------------------------
export async function getTelnyxConnection(): Promise<TelnyxConnectionStatus> {
  return telephonyRequest<TelnyxConnectionStatus>('/portal/telephony/telnyx/connection');
}

export async function connectTelnyx(apiKey: string, label?: string): Promise<TelnyxConnectionStatus> {
  return telephonyRequest<TelnyxConnectionStatus>('/portal/telephony/telnyx/connect', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey, label }),
  });
}

export async function rotateTelnyxKey(apiKey: string): Promise<TelnyxConnectionStatus> {
  return telephonyRequest<TelnyxConnectionStatus>('/portal/telephony/telnyx/rotate', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function reverifyTelnyx(): Promise<TelnyxConnectionStatus> {
  return telephonyRequest<TelnyxConnectionStatus>('/portal/telephony/telnyx/reverify', {
    method: 'POST',
  });
}

export async function disconnectTelnyx(): Promise<{ success: boolean }> {
  return telephonyRequest<{ success: boolean }>('/portal/telephony/telnyx/connection', {
    method: 'DELETE',
  });
}

// -------------------------------------------------------------
// Managed Phone Numbers APIs
// -------------------------------------------------------------
export async function getManagedNumbers(assignedAgentId?: string): Promise<ManagedPhoneNumber[]> {
  const query = assignedAgentId ? `?assigned_agent_id=${encodeURIComponent(assignedAgentId)}` : '';
  return telephonyRequest<ManagedPhoneNumber[]>(`/portal/telephony/numbers${query}`);
}

export async function syncManagedNumbers(): Promise<{ synced_count: number; drift_count?: number; items?: ManagedPhoneNumber[] }> {
  return telephonyRequest<{ synced_count: number; drift_count?: number; items?: ManagedPhoneNumber[] }>('/portal/telephony/numbers/sync', {
    method: 'POST',
  });
}

export async function getNumberDrift(): Promise<NumberDriftReport> {
  return telephonyRequest<NumberDriftReport>('/portal/telephony/numbers/drift');
}

export async function assignAgentToNumber(numberId: string, agentId: string | null): Promise<ManagedPhoneNumber> {
  return telephonyRequest<ManagedPhoneNumber>(`/portal/telephony/numbers/${numberId}/assignment`, {
    method: 'PATCH',
    body: JSON.stringify({ agent_id: agentId }),
  });
}

export async function importTelnyxNumber(e164Number: string, externalCustomerRef?: string): Promise<ManagedPhoneNumber> {
  return telephonyRequest<ManagedPhoneNumber>('/portal/telephony/numbers/import', {
    method: 'POST',
    body: JSON.stringify({ e164_number: e164Number, external_customer_ref: externalCustomerRef }),
  });
}

// -------------------------------------------------------------
// Available Numbers Search & Purchase
// -------------------------------------------------------------
export async function searchAvailableNumbers(params: {
  country?: string;
  area_code?: string;
  number_type?: string;
  features?: string[];
}): Promise<AvailablePhoneNumber[]> {
  return telephonyRequest<AvailablePhoneNumber[]>('/portal/telephony/available-numbers/search', {
    method: 'POST',
    body: JSON.stringify({
      country: params.country || 'US',
      area_code: params.area_code,
      number_type: params.number_type || 'local',
      features: params.features,
    }),
  });
}

export async function reserveNumber(e164Number: string, idempotencyKey?: string): Promise<{ reservation_id: string; expires_at: string }> {
  return telephonyRequest<{ reservation_id: string; expires_at: string }>('/portal/telephony/number-reservations', {
    method: 'POST',
    body: JSON.stringify({
      e164_number: e164Number,
      idempotency_key: idempotencyKey || `res_${Date.now()}`,
    }),
  });
}

export async function purchaseNumber(params: {
  e164_number: string;
  idempotency_key?: string;
  external_customer_ref?: string;
}): Promise<{ order_id: string; status: string; number: ManagedPhoneNumber }> {
  return telephonyRequest<{ order_id: string; status: string; number: ManagedPhoneNumber }>('/portal/telephony/number-orders', {
    method: 'POST',
    body: JSON.stringify({
      e164_number: params.e164_number,
      idempotency_key: params.idempotency_key || `ord_${Date.now()}`,
      external_customer_ref: params.external_customer_ref,
    }),
  });
}

// -------------------------------------------------------------
// SIP Trunking & Outbound Profiles
// -------------------------------------------------------------
export async function upsertSipConnection(body: {
  sip_fqdn: string;
  sip_username?: string;
  sip_secret?: string;
}): Promise<{ connection_id: string; sip_fqdn: string; status: string }> {
  return telephonyRequest<{ connection_id: string; sip_fqdn: string; status: string }>('/portal/telephony/telnyx/sip-connection', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function testSipConnection(): Promise<{ verified: boolean; message: string }> {
  return telephonyRequest<{ verified: boolean; message: string }>('/portal/telephony/telnyx/sip-connection/test', {
    method: 'POST',
  });
}

export async function upsertOutboundVoiceProfile(body: {
  profile_name: string;
  traffic_type?: string;
  service_plan?: string;
}): Promise<{ profile_id: string; profile_name: string }> {
  return telephonyRequest<{ profile_id: string; profile_name: string }>('/portal/telephony/telnyx/outbound-voice-profile', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function upsertOutboundTrunk(body: {
  connection_name: string;
}): Promise<{ trunk_id: string; connection_name: string }> {
  return telephonyRequest<{ trunk_id: string; connection_name: string }>('/portal/telephony/telnyx/outbound-trunk', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// -------------------------------------------------------------
// Diagnostics & Outbound Calls
// -------------------------------------------------------------
export async function getTelephonyReadiness(): Promise<TelephonyReadiness> {
  return telephonyRequest<TelephonyReadiness>('/portal/telephony/outbound-readiness');
}

export async function getTelephonyHealth(): Promise<TelephonyHealth> {
  if (!API_BASE) {
    throw new TelephonyApiError('Missing NEXT_PUBLIC_TENANT_PORTAL_API_URL in dashboard/.env.local');
  }
  const res = await fetch(`${API_BASE}/portal/telephony/health`, { cache: 'no-store' });
  if (!res.ok) throw new TelephonyApiError(`Health check failed: ${res.statusText}`);
  return (await res.json()) as TelephonyHealth;
}

export async function createOutboundCall(body: {
  agent_id: string;
  to_e164: string;
  from_number_id?: string;
}): Promise<{ call_id: string; status: string; room_name: string }> {
  return telephonyRequest<{ call_id: string; status: string; room_name: string }>('/portal/telephony/outbound-calls', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
