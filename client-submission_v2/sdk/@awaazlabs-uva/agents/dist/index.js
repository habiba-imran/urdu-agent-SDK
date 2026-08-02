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
export class AwaazLabsUvaAgentsError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
        this.name = 'AwaazLabsUvaAgentsError';
    }
}
export { AwaazLabsUvaAgentsError as UvaAgentsError };
/**
 * Canonical JSON: recursively sort object keys, no whitespace. Must match the server's
 * `json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` byte-for-byte,
 * including leaving non-ASCII (Urdu-script) text unescaped - see machine_auth.py::payload_hash.
 */
function canonicalJson(value) {
    if (value === null || typeof value !== 'object') {
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return `[${value.map(canonicalJson).join(',')}]`;
    }
    const obj = value;
    const keys = Object.keys(obj).sort();
    const parts = keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`);
    return `{${parts.join(',')}}`;
}
async function sha256Hex(input) {
    const data = new TextEncoder().encode(input);
    const digest = await crypto.subtle.digest('SHA-256', data);
    return Buffer.from(digest).toString('hex');
}
export class AwaazLabsUvaAgentsClient {
    constructor(options) {
        this.options = options;
        if (!options.tenantId.trim())
            throw new Error('tenantId is required');
        if (!options.tenantSecret.trim())
            throw new Error('tenantSecret is required');
        if (!options.baseUrl.trim())
            throw new Error('baseUrl is required');
    }
    async createAgent(params) {
        const body = {
            name: params.name,
            prompt: params.prompt,
            voice_id: params.voiceId,
            llm_model: params.llmModel ?? 'gemini-2.5-flash',
        };
        if (params.agentLanguage !== undefined)
            body.agent_language = params.agentLanguage;
        if (params.sttProvider !== undefined)
            body.stt_provider = params.sttProvider;
        if (params.sttModel !== undefined)
            body.stt_model = params.sttModel;
        if (params.sttOptions !== undefined)
            body.stt_options = params.sttOptions;
        if (params.llmProvider !== undefined)
            body.llm_provider = params.llmProvider;
        if (params.llmOptions !== undefined)
            body.llm_options = params.llmOptions;
        if (params.ttsProvider !== undefined)
            body.tts_provider = params.ttsProvider;
        if (params.ttsVoiceId !== undefined)
            body.tts_voice_id = params.ttsVoiceId;
        if (params.ttsOptions !== undefined)
            body.tts_options = params.ttsOptions;
        return this.request('POST', '/machine/agents', 'agent.create', body);
    }
    async listAgents() {
        return this.request('GET', '/machine/agents', 'agent.list', {});
    }
    async updateAgent(agentId, params) {
        const body = {};
        if (params.name !== undefined)
            body.name = params.name;
        if (params.prompt !== undefined)
            body.prompt = params.prompt;
        if (params.voiceId !== undefined)
            body.voice_id = params.voiceId;
        if (params.llmModel !== undefined)
            body.llm_model = params.llmModel;
        if (params.agentLanguage !== undefined)
            body.agent_language = params.agentLanguage;
        if (params.sttProvider !== undefined)
            body.stt_provider = params.sttProvider;
        if (params.sttModel !== undefined)
            body.stt_model = params.sttModel;
        if (params.sttOptions !== undefined)
            body.stt_options = params.sttOptions;
        if (params.llmProvider !== undefined)
            body.llm_provider = params.llmProvider;
        if (params.llmOptions !== undefined)
            body.llm_options = params.llmOptions;
        if (params.ttsProvider !== undefined)
            body.tts_provider = params.ttsProvider;
        if (params.ttsVoiceId !== undefined)
            body.tts_voice_id = params.ttsVoiceId;
        if (params.ttsOptions !== undefined)
            body.tts_options = params.ttsOptions;
        return this.request('PATCH', `/machine/agents/${agentId}`, 'agent.update', body);
    }
    async request(method, path, action, body) {
        const ts = Math.floor(Date.now() / 1000).toString();
        const nonce = randomUUID();
        const bodyHash = await sha256Hex(canonicalJson(body));
        const message = `${this.options.tenantId}.${ts}.${nonce}.${action}.${bodyHash}`;
        const signature = createHmac('sha256', this.options.tenantSecret).update(message).digest('hex');
        const headers = {
            ...(this.options.extraHeaders ?? {}),
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
            throw new AwaazLabsUvaAgentsError(res.status, String(detail));
        }
        return parsed;
    }
}
export { AwaazLabsUvaAgentsClient as UvaAgentsClient };
