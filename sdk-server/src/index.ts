// AwaazLabs-UVA-Agents server-side agent-management client (docs/MACHINE_AGENT_API_CONTRACT.md).
//
// SERVER-SIDE ONLY. This package holds the tenant's raw HMAC secret to sign requests. It must
// NEVER be imported into browser code - that is the entire point of @awaazlabs-uva/voice being a separate
// package. If your app is a browser SPA, this client belongs in your own backend, which then hands
// the resulting agentId to the browser for @awaazlabs-uva/voice to connect with.
//
// Existing-tenant scope only: this client assumes tenantId + tenantSecret are already provisioned
// (see the tenant portal or your platform contact). It has no tenant-signup capability.

import { createHmac, randomUUID } from 'node:crypto';

export interface AwaazLabsUvaAgentsClientOptions {
  /** The tenant UUID this client acts as. */
  tenantId: string;
  /** The tenant's raw HMAC secret - SERVER-SIDE SECRET, never expose it to a browser. */
  tenantSecret: string;
  /** Base URL of the tenant_portal_api deployment, e.g. https://portal-api.example.com */
  baseUrl: string;
  /** Optional non-auth headers for local tunnels/proxies. Auth headers cannot be overridden. */
  extraHeaders?: Record<string, string>;
  /** Opt into exact wire-byte signing after deploying a raw-body-v1 portal. */
  signatureVersion?: 'canonical-json-v1' | 'raw-body-v1';
}

export type UvaAgentsClientOptions = AwaazLabsUvaAgentsClientOptions;

export type FirstSpeaker = 'agent' | 'user';

/** Saved on the agent; applies to web sessions and both phone-call directions. */
export interface HumanizationOptions {
  enabled?: boolean;
  warmth?: 'reserved' | 'balanced' | 'warm';
  formality?: 'casual' | 'balanced' | 'formal';
  energy?: 'calm' | 'balanced' | 'lively';
  pace?: 'slower' | 'normal' | 'slightly_fast';
  expressiveness?: 'subtle' | 'balanced';
  /** Treat saved TTS speed as the base for bounded contextual pace adjustments. */
  adaptivePace?: boolean;
}

export function validateHumanization(value: unknown): HumanizationOptions {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('humanization must be an object');
  const enums: Record<string, readonly string[]> = {
    warmth: ['reserved', 'balanced', 'warm'], formality: ['casual', 'balanced', 'formal'],
    energy: ['calm', 'balanced', 'lively'], pace: ['slower', 'normal', 'slightly_fast'],
    expressiveness: ['subtle', 'balanced'],
  };
  for (const [key, entry] of Object.entries(value)) {
    if (key === 'enabled' || key === 'adaptivePace') {
      if (typeof entry !== 'boolean') throw new Error(`humanization.${key} must be a boolean`);
    } else if (!enums[key] || typeof entry !== 'string' || !enums[key].includes(entry)) {
      throw new Error(`invalid humanization.${key}`);
    }
  }
  return { ...value };
}

export interface AgentRecord {
  id: string;
  name: string;
  prompt: string;
  voice_id: string;
  llm_model: string;
  created_at: string | null;
  total_agent_sec?: number;
  // Provider/language fields are additive and optional for existing tenants.
  agent_language: string;
  stt_provider: string;
  stt_model: string;
  stt_options: Record<string, unknown>;
  llm_provider: string;
  llm_options: Record<string, unknown>;
  tts_provider: string;
  tts_voice_id: string | null;
  tts_options: Record<string, unknown>;
  greeting: string | null;
  first_speaker: FirstSpeaker;
  /** Client tool gateway base URL (no trailing slash). */
  tools_base_url: string | null;
  /** True when a tools auth secret is stored (raw secret is never returned). */
  tools_auth_secret_configured: boolean;
}

export interface CreateAgentParams {
  name: string;
  prompt: string;
  voiceId: string;
  llmModel?: string;
  /** Optional provider/language fields. Omitting them keeps the hosted platform defaults.
   * ttsVoiceId takes priority over voiceId when both are given. */
  agentLanguage?: string;
  sttProvider?: string;
  sttModel?: string;
  sttOptions?: Record<string, unknown>;
  llmProvider?: string;
  llmOptions?: Record<string, unknown>;
  /** Replaces the saved profile. Omit to preserve; enabled:false disables it. */
  humanization?: HumanizationOptions;
  ttsProvider?: string;
  ttsVoiceId?: string;
  ttsOptions?: Record<string, unknown>;
  /** Exact opening line when firstSpeaker is 'agent'. Omit for a generated greeting. Empty string on update clears it. */
  greeting?: string;
  /** Who speaks first. Default 'agent'. 'user' waits for the caller. */
  firstSpeaker?: FirstSpeaker;
  /**
   * HTTPS (or http for local) base URL of THIS client's tool gateway.
   * Worker POSTs RAG/FAQ/scheduling to `{toolsBaseUrl}/api/tools/*`.
   * Per-agent so one UVA worker can serve many client backends.
   */
  toolsBaseUrl?: string;
  /** Shared secret sent as x-tool-gateway-secret. Must match the client backend TOOL_GATEWAY_SECRET. */
  toolsAuthSecret?: string;
}

export interface UpdateAgentParams {
  name?: string;
  prompt?: string;
  voiceId?: string;
  llmModel?: string;
  agentLanguage?: string;
  sttProvider?: string;
  sttModel?: string;
  sttOptions?: Record<string, unknown>;
  llmProvider?: string;
  llmOptions?: Record<string, unknown>;
  humanization?: HumanizationOptions;
  ttsProvider?: string;
  ttsVoiceId?: string;
  ttsOptions?: Record<string, unknown>;
  /** Exact opening line when firstSpeaker is 'agent'. Empty string clears it. */
  greeting?: string;
  firstSpeaker?: FirstSpeaker;
  toolsBaseUrl?: string;
  toolsAuthSecret?: string;
}

/** Shape returned by GET /machine/provider-capabilities (== GET /portal/provider-capabilities),
 * see tenant_portal_api/provider_capabilities.py::get_public_capabilities. Only ever contains
 * `enabled` combinations - a provider absent from a language's entry is either unsupported for
 * that language or not yet enabled; both cases are represented the same way here (absence), so
 * always check for key presence before offering it as an option. */
export interface ProviderCapabilityEntry {
  state: 'enabled';
  models?: string[];
  defaultModel?: string;
  voices?: string[];
  defaultVoice?: string | null;
}

export interface LanguageCapabilities {
  label: string;
  stt?: Record<string, ProviderCapabilityEntry>;
  llm?: Record<string, ProviderCapabilityEntry>;
  tts?: Record<string, ProviderCapabilityEntry>;
}

export interface ProviderCapabilities {
  languages: Record<string, LanguageCapabilities>;
}

export interface ManagedNumberRecord {
  id: string;
  tenant_id: string;
  provider_number_id: string | null;
  e164_number: string;
  country: string;
  number_type: string;
  features: string[];
  provisioning_status: string;
  routing_status: string;
  assigned_agent_id: string | null;
  external_customer_ref: string | null;
}

export class AwaazLabsUvaAgentsError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    /** Stable machine-readable code from tenant_portal_api's ProviderValidationError, e.g.
     * `unsupported_provider_for_language`, `provider_not_enabled`, `unsupported_model_for_provider`,
     * `unsupported_voice_for_provider`. Undefined for non-provider-validation errors (auth
     * failures, 404s, etc.), which only ever carry a plain string detail. */
    public readonly code?: string,
  ) {
    super(message);
    this.name = 'AwaazLabsUvaAgentsError';
  }
}

export { AwaazLabsUvaAgentsError as UvaAgentsError };

/**
 * Stable JavaScript wire JSON: sort keys and keep non-ASCII text as UTF-8.
 * Legacy Python canonicalization can differ for number formatting and Unicode key order;
 * raw-body-v1 verifies these exact transmitted bytes instead of reserializing them.
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

export class AwaazLabsUvaAgentsClient {
  constructor(private readonly options: AwaazLabsUvaAgentsClientOptions) {
    if (!options.tenantId.trim()) throw new Error('tenantId is required');
    if (!options.tenantSecret.trim()) throw new Error('tenantSecret is required');
    if (!options.baseUrl.trim()) throw new Error('baseUrl is required');
  }

  async createAgent(params: CreateAgentParams): Promise<AgentRecord> {
    const body: Record<string, unknown> = {
      name: params.name,
      prompt: params.prompt,
      voice_id: params.voiceId,
      llm_model: params.llmModel ?? 'gemini-2.5-flash',
    };
    if (params.agentLanguage !== undefined) body.agent_language = params.agentLanguage;
    if (params.sttProvider !== undefined) body.stt_provider = params.sttProvider;
    if (params.sttModel !== undefined) body.stt_model = params.sttModel;
    if (params.sttOptions !== undefined) body.stt_options = params.sttOptions;
    if (params.llmProvider !== undefined) body.llm_provider = params.llmProvider;
    if (params.llmOptions !== undefined) body.llm_options = params.llmOptions;
    if (params.humanization !== undefined) body.llm_options = { ...params.llmOptions, humanization: validateHumanization(params.humanization) };
    if (params.ttsProvider !== undefined) body.tts_provider = params.ttsProvider;
    if (params.ttsVoiceId !== undefined) body.tts_voice_id = params.ttsVoiceId;
    if (params.ttsOptions !== undefined) body.tts_options = params.ttsOptions;
    if (params.greeting !== undefined) body.greeting = params.greeting;
    if (params.firstSpeaker !== undefined) body.first_speaker = params.firstSpeaker;
    if (params.toolsBaseUrl !== undefined) body.tools_base_url = params.toolsBaseUrl;
    if (params.toolsAuthSecret !== undefined) body.tools_auth_secret = params.toolsAuthSecret;
    return this.request<AgentRecord>('POST', '/machine/agents', 'agent.create', body);
  }

  async listAgents(): Promise<AgentRecord[]> {
    return this.request<AgentRecord[]>('GET', '/machine/agents', 'agent.list', {});
  }

  async updateAgent(agentId: string, params: UpdateAgentParams): Promise<AgentRecord> {
    const body: Record<string, unknown> = {};
    if (params.name !== undefined) body.name = params.name;
    if (params.prompt !== undefined) body.prompt = params.prompt;
    if (params.voiceId !== undefined) body.voice_id = params.voiceId;
    if (params.llmModel !== undefined) body.llm_model = params.llmModel;
    if (params.agentLanguage !== undefined) body.agent_language = params.agentLanguage;
    if (params.sttProvider !== undefined) body.stt_provider = params.sttProvider;
    if (params.sttModel !== undefined) body.stt_model = params.sttModel;
    if (params.sttOptions !== undefined) body.stt_options = params.sttOptions;
    if (params.llmProvider !== undefined) body.llm_provider = params.llmProvider;
    if (params.llmOptions !== undefined) body.llm_options = params.llmOptions;
    if (params.humanization !== undefined) body.llm_options = { ...params.llmOptions, humanization: validateHumanization(params.humanization) };
    if (params.ttsProvider !== undefined) body.tts_provider = params.ttsProvider;
    if (params.ttsVoiceId !== undefined) body.tts_voice_id = params.ttsVoiceId;
    if (params.ttsOptions !== undefined) body.tts_options = params.ttsOptions;
    if (params.greeting !== undefined) body.greeting = params.greeting;
    if (params.firstSpeaker !== undefined) body.first_speaker = params.firstSpeaker;
    if (params.toolsBaseUrl !== undefined) body.tools_base_url = params.toolsBaseUrl;
    if (params.toolsAuthSecret !== undefined) body.tools_auth_secret = params.toolsAuthSecret;
    return this.request<AgentRecord>('PATCH', `/machine/agents/${agentId}`, 'agent.update', body);
  }

  private async request<TResponse>(
    method: 'GET' | 'POST' | 'PATCH',
    path: string,
    action: string,
    body: Record<string, unknown>,
  ): Promise<TResponse> {
    const ts = Math.floor(Date.now() / 1000).toString();
    const nonce = randomUUID();
    const canonicalBody = canonicalJson(body);
    const bodyHash = await sha256Hex(canonicalBody);
    const message = `${this.options.tenantId}.${ts}.${nonce}.${action}.${bodyHash}`;
    const signature = createHmac('sha256', this.options.tenantSecret).update(message).digest('hex');

    const headers: Record<string, string> = {
      ...Object.fromEntries(Object.entries(this.options.extraHeaders ?? {})
        .filter(([name]) => name.toLowerCase() !== 'x-signature-version')),
      'Content-Type': 'application/json',
      'X-Tenant-Id': this.options.tenantId,
      'X-Timestamp': ts,
      'X-Nonce': nonce,
      'X-Signature': signature,
      'X-Signature-Version': this.options.signatureVersion ?? 'canonical-json-v1',
    };

    const hasBody = method !== 'GET';
    const res = await fetch(`${this.options.baseUrl.replace(/\/$/, '')}${path}`, {
      method,
      headers,
      body: hasBody ? canonicalBody : undefined,
    });

    const text = await res.text();
    const parsed = text ? JSON.parse(text) : null;
    if (!res.ok) {
      const detail = parsed?.detail;
      // tenant_portal_api's ProviderValidationError path raises HTTPException(detail={"code":
      // ..., "reason": ...}) (app.py::_resolve_provider_fields) - every other error path (auth
      // failures, 404s) raises a plain string detail. Without this branch, `String(detail)` on
      // the object case produced the literal text "[object Object]", silently discarding the
      // one piece of information (the stable `code`) API consumers need to branch on.
      if (detail && typeof detail === 'object' && typeof detail.reason === 'string') {
        throw new AwaazLabsUvaAgentsError(res.status, detail.reason, detail.code);
      }
      throw new AwaazLabsUvaAgentsError(res.status, String(detail ?? res.statusText));
    }
    return parsed as TResponse;
  }

  /** GET /machine/provider-capabilities (Phase 4, ADR-036) - which (language, layer, provider)
   * combinations are currently `enabled` and selectable, plus each TTS provider's own voice IDs.
   * Use this to build cascading provider/model/voice pickers instead of hardcoding options. */
  async getProviderCapabilities(): Promise<ProviderCapabilities> {
    return this.request<ProviderCapabilities>(
      'GET',
      '/machine/provider-capabilities',
      'provider_capabilities.get',
      {},
    );
  }

  async listManagedNumbers(params?: { assignedAgentId?: string }): Promise<ManagedNumberRecord[]> {
    const body: Record<string, unknown> = {};
    if (params?.assignedAgentId) body.assigned_agent_id = params.assignedAgentId;
    return this.request<ManagedNumberRecord[]>('POST', '/machine/telephony/numbers/list', 'telephony.managed_numbers.list', body);
  }

  async assignAgentToNumber(numberId: string, agentId: string | null): Promise<ManagedNumberRecord> {
    const body: Record<string, unknown> = { agent_id: agentId };
    return this.request<ManagedNumberRecord>('PATCH', `/machine/telephony/numbers/${numberId}/assignment`, 'telephony.numbers.assign_agent', body);
  }

  async unassignAgentFromNumber(numberId: string): Promise<ManagedNumberRecord> {
    return this.assignAgentToNumber(numberId, null);
  }
}

export { AwaazLabsUvaAgentsClient as UvaAgentsClient };
