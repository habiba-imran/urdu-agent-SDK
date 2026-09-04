export interface AwaazLabsUvaAgentsClientOptions {
    /** The tenant UUID this client acts as. */
    tenantId: string;
    /** The tenant's raw HMAC secret - SERVER-SIDE SECRET, never expose it to a browser. */
    tenantSecret: string;
    /** Base URL of the tenant_portal_api deployment, e.g. https://portal-api.example.com */
    baseUrl: string;
    /** Optional non-auth headers for local tunnels/proxies. Auth headers cannot be overridden. */
    extraHeaders?: Record<string, string>;
}
export type UvaAgentsClientOptions = AwaazLabsUvaAgentsClientOptions;
export type FirstSpeaker = 'agent' | 'user';
export interface AgentRecord {
    id: string;
    name: string;
    prompt: string;
    voice_id: string;
    llm_model: string;
    created_at: string | null;
    total_agent_sec?: number;
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
export declare class AwaazLabsUvaAgentsError extends Error {
    readonly status: number;
    /** Stable machine-readable code from tenant_portal_api's ProviderValidationError, e.g.
     * `unsupported_provider_for_language`, `provider_not_enabled`, `unsupported_model_for_provider`,
     * `unsupported_voice_for_provider`. Undefined for non-provider-validation errors (auth
     * failures, 404s, etc.), which only ever carry a plain string detail. */
    readonly code?: string | undefined;
    constructor(status: number, message: string, 
    /** Stable machine-readable code from tenant_portal_api's ProviderValidationError, e.g.
     * `unsupported_provider_for_language`, `provider_not_enabled`, `unsupported_model_for_provider`,
     * `unsupported_voice_for_provider`. Undefined for non-provider-validation errors (auth
     * failures, 404s, etc.), which only ever carry a plain string detail. */
    code?: string | undefined);
}
export { AwaazLabsUvaAgentsError as UvaAgentsError };
export declare class AwaazLabsUvaAgentsClient {
    private readonly options;
    constructor(options: AwaazLabsUvaAgentsClientOptions);
    createAgent(params: CreateAgentParams): Promise<AgentRecord>;
    listAgents(): Promise<AgentRecord[]>;
    updateAgent(agentId: string, params: UpdateAgentParams): Promise<AgentRecord>;
    private request;
    /** GET /machine/provider-capabilities (Phase 4, ADR-036) - which (language, layer, provider)
     * combinations are currently `enabled` and selectable, plus each TTS provider's own voice IDs.
     * Use this to build cascading provider/model/voice pickers instead of hardcoding options. */
    getProviderCapabilities(): Promise<ProviderCapabilities>;
    listManagedNumbers(params?: {
        assignedAgentId?: string;
    }): Promise<ManagedNumberRecord[]>;
    assignAgentToNumber(numberId: string, agentId: string | null): Promise<ManagedNumberRecord>;
    unassignAgentFromNumber(numberId: string): Promise<ManagedNumberRecord>;
}
export { AwaazLabsUvaAgentsClient as UvaAgentsClient };
