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
export declare class AwaazLabsUvaAgentsError extends Error {
    readonly status: number;
    constructor(status: number, message: string);
}
export { AwaazLabsUvaAgentsError as UvaAgentsError };
export declare class AwaazLabsUvaAgentsClient {
    private readonly options;
    constructor(options: AwaazLabsUvaAgentsClientOptions);
    createAgent(params: CreateAgentParams): Promise<AgentRecord>;
    listAgents(): Promise<AgentRecord[]>;
    updateAgent(agentId: string, params: UpdateAgentParams): Promise<AgentRecord>;
    private request;
}
export { AwaazLabsUvaAgentsClient as UvaAgentsClient };
