// UrduVoiceAgent SERVER-SIDE agent-management client (docs/MACHINE_AGENT_API_CONTRACT.md).
//
// SERVER-SIDE ONLY. This package holds the tenant's raw HMAC secret to sign requests. It must
// NEVER be imported into browser code — that is the entire point of @uva/voice being a separate
// package. If your app is a browser SPA, this client belongs in your own backend, which then hands
// the resulting agentId to the browser for @uva/voice to connect with.
//
// Existing-tenant scope only: this client assumes tenantId + tenantSecret are already provisioned
// (see the tenant portal or your platform contact). It has no tenant-signup capability.

import { createHmac, randomUUID } from 'node:crypto';

export interface UvaAgentsClientOptions {
  /** The tenant UUID this client acts as. */
  tenantId: string;
  /** The tenant's raw HMAC secret — SERVER-SIDE SECRET, never expose it to a browser. */
  tenantSecret: string;
  /** Base URL of the tenant_portal_api deployment, e.g. https://portal-api.example.com */
  baseUrl: string;
}

export interface AgentRecord {
  id: string;
  name: string;
  prompt: string;
  voice_id: string;
  llm_model: string;
  created_at: string | null;
  total_agent_sec?: number;
}

export interface CreateAgentParams {
  name: string;
  prompt: string;
  voiceId: string;
  llmModel?: string;
}

export interface UpdateAgentParams {
  name?: string;
  prompt?: string;
  voiceId?: string;
  llmModel?: string;
}

export class UvaAgentsError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'UvaAgentsError';
  }
}

/**
 * Canonical JSON: recursively sort object keys, no whitespace. Must match the server's
 * `json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` byte-for-byte,
 * including leaving non-ASCII (Urdu-script) text unescaped — see machine_auth.py::payload_hash.
 */
function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(',')}]`;
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  const parts = keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`);
  return `{${parts.join(',')}}`;
}

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return Buffer.from(digest).toString('hex');
}

export class UvaAgentsClient {
  constructor(private readonly options: UvaAgentsClientOptions) {
    if (!options.tenantId.trim()) throw new Error('tenantId is required');
    if (!options.tenantSecret.trim()) throw new Error('tenantSecret is required');
    if (!options.baseUrl.trim()) throw new Error('baseUrl is required');
  }

  async createAgent(params: CreateAgentParams): Promise<AgentRecord> {
    const body = {
      name: params.name,
      prompt: params.prompt,
      voice_id: params.voiceId,
      llm_model: params.llmModel ?? 'gemini-2.5-flash',
    };
    return this.request('POST', '/machine/agents', 'agent.create', body);
  }

  async listAgents(): Promise<AgentRecord[]> {
    return this.request('GET', '/machine/agents', 'agent.list', {});
  }

  async updateAgent(agentId: string, params: UpdateAgentParams): Promise<AgentRecord> {
    const body: Record<string, string> = {};
    if (params.name !== undefined) body.name = params.name;
    if (params.prompt !== undefined) body.prompt = params.prompt;
    if (params.voiceId !== undefined) body.voice_id = params.voiceId;
    if (params.llmModel !== undefined) body.llm_model = params.llmModel;
    return this.request('PATCH', `/machine/agents/${agentId}`, 'agent.update', body);
  }

  private async request(
    method: 'GET' | 'POST' | 'PATCH',
    path: string,
    action: string,
    body: Record<string, unknown>,
  ): Promise<any> {
    const ts = Math.floor(Date.now() / 1000).toString();
    const nonce = randomUUID();
    const bodyHash = await sha256Hex(canonicalJson(body));
    const message = `${this.options.tenantId}.${ts}.${nonce}.${action}.${bodyHash}`;
    const signature = createHmac('sha256', this.options.tenantSecret).update(message).digest('hex');

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Tenant-Id': this.options.tenantId,
      'X-Timestamp': ts,
      'X-Nonce': nonce,
      'X-Signature': signature,
    };

    const hasBody = method !== 'GET';
    const res = await fetch(`${this.options.baseUrl.replace(/\/$/, '')}${path}`, {
      method,
      headers,
      body: hasBody ? JSON.stringify(body) : undefined,
    });

    const text = await res.text();
    const parsed = text ? JSON.parse(text) : null;
    if (!res.ok) {
      const detail = parsed?.detail ?? res.statusText;
      throw new UvaAgentsError(res.status, String(detail));
    }
    return parsed;
  }
}
