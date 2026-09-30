import { ensurePortalSession, portalAuthHeaders } from '@/lib/portalAuth';

const API_BASE = process.env.NEXT_PUBLIC_TENANT_PORTAL_API_URL;

/** Read-only managed number shape for Agents / Overview. */
export type ManagedPhoneNumber = {
  id: string;
  e164_number: string;
  country?: string | null;
  locality?: string | null;
  assigned_agent_id?: string | null;
  assigned_agent_name?: string | null;
  status?: string | null;
  provisioning_status?: string | null;
  routing_status?: string | null;
  telnyx_phone_number_id?: string | null;
  external_customer_ref?: string | null;
  created_at?: string | null;
};

export class TelephonyApiError extends Error {
  status?: number;
  code?: string;
  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = 'TelephonyApiError';
    this.status = status;
    this.code = code;
  }
}

async function telephonyRequest<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) {
    throw new TelephonyApiError(
      'Missing NEXT_PUBLIC_TENANT_PORTAL_API_URL in dashboard/.env.local',
    );
  }

  const sessionOk = await ensurePortalSession();
  if (!sessionOk) {
    throw new TelephonyApiError('Missing tenant session. Please sign in again.', 401);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...portalAuthHeaders(),
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    let code: string | undefined;
    try {
      const body = (await response.json()) as { detail?: unknown; code?: string };
      if (body?.code) code = body.code;
      if (body?.detail != null) {
        detail =
          typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* ignore */
    }
    throw new TelephonyApiError(detail, response.status, code);
  }

  return (await response.json()) as T;
}

/** List managed phone numbers for this tenant (read-only). */
export async function getManagedNumbers(
  assignedAgentId?: string,
): Promise<ManagedPhoneNumber[]> {
  const query = assignedAgentId
    ? `?assigned_agent_id=${encodeURIComponent(assignedAgentId)}`
    : '';
  return telephonyRequest<ManagedPhoneNumber[]>(`/portal/telephony/numbers${query}`);
}
