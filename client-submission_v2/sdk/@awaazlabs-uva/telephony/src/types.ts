export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | JsonObject;
export type JsonInputValue =
  | JsonPrimitive
  | undefined
  | JsonInputValue[]
  | { [key: string]: JsonInputValue };

export interface JsonObject {
  [key: string]: JsonValue | undefined;
}

export interface JsonInputObject {
  [key: string]: JsonInputValue;
}

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE';

export interface TelephonyFetchInit {
  method: HttpMethod;
  headers: Record<string, string>;
  body?: string;
}

export interface TelephonyFetchResponse {
  ok: boolean;
  status: number;
  statusText?: string;
  text(): Promise<string>;
}

export type TelephonyFetch = (
  url: string,
  init: TelephonyFetchInit,
) => Promise<TelephonyFetchResponse>;

export interface TelephonyClientOptions {
  tenantId: string;
  tenantSecret: string;
  baseUrl: string;
  extraHeaders?: Record<string, string>;
  fetch?: TelephonyFetch;
  nowSeconds?: () => number;
  nonceFactory?: () => string;
}

export interface MachineOperation {
  method: HttpMethod;
  path: `/machine/telephony/${string}`;
  action: `telephony.${string}`;
}

export type TelephonyErrorCode =
  | 'telephony_auth_failed'
  | 'tenant_not_active'
  | 'tenant_not_found'
  | 'telnyx_connection_missing'
  | 'telnyx_key_invalid'
  | 'telnyx_key_unauthorized'
  | 'telnyx_key_permission_failed'
  | 'telnyx_key_compromised'
  | 'provider_credentials_missing'
  | 'agent_not_found'
  | 'number_not_found'
  | 'number_not_owned_by_tenant'
  | 'number_not_assigned'
  | 'number_not_routing_ready'
  | 'outbound_voice_profile_missing'
  | 'outbound_destination_disabled'
  | 'outbound_spending_limit_reached'
  | 'outbound_concurrency_limit_reached'
  | 'outbound_verification_required'
  | 'invalid_to_number'
  | 'unsupported_number_feature'
  | 'outbound_not_ready'
  | 'duplicate_idempotency_key'
  | 'idempotency_payload_mismatch'
  | 'telnyx_api_error'
  | 'telnyx_rate_limited'
  | 'number_not_available'
  | 'insufficient_telnyx_balance'
  | 'number_order_action_required'
  | 'regulatory_action_required'
  | 'provider_timeout'
  | 'livekit_inbound_trunk_failed'
  | 'livekit_outbound_trunk_failed'
  | 'livekit_sip_dispatch_rule_failed'
  | 'livekit_agent_dispatch_failed'
  | 'sip_verification_failed'
  | 'sip_media_failed'
  | 'call_setup_failed'
  | 'call_state_conflict'
  | 'quota_reservation_failed'
  | 'quota_release_failed'
  | 'unknown_inbound_number'
  | 'routing_identifier_mismatch'
  | 'assigned_agent_load_failed'
  | 'provider_pipeline_start_failed'
  | 'worker_metadata_missing'
  | 'worker_session_failed'
  | 'webhook_signature_invalid'
  | 'webhook_duplicate'
  | 'webhook_unmapped_provider_id'
  | 'retention_policy_violation'
  | 'export_not_authorized'
  | 'restricted_payload_access_denied'
  | 'telephony_request_failed'
  | 'telephony_invalid_response';

export interface ConnectTelnyxAccountParams extends JsonInputObject {
  apiKey: string;
  label?: string;
}

export interface RotateTelnyxAccountKeyParams extends JsonInputObject {
  apiKey: string;
}

export interface ListTelephonyFilters extends JsonInputObject {
  cursor?: string;
  limit?: number;
  platformStatus?: string;
  providerStatus?: string;
}

export interface ImportTelnyxNumberParams extends JsonInputObject {
  e164Number: string;
  externalCustomerRef?: string;
}

export interface SearchAvailableNumbersParams extends JsonInputObject {
  country: string;
  areaCode?: string;
  numberType?: string;
  features?: string[];
}

export interface ReserveNumberParams extends JsonInputObject {
  e164Number: string;
  idempotencyKey: string;
}

export interface PurchaseNumberParams extends JsonInputObject {
  e164Number: string;
  externalCustomerRef?: string;
  idempotencyKey: string;
}

export interface UpsertTelnyxSipConnectionParams extends JsonInputObject {
  sipFqdn?: string;
  sipUsername?: string;
  sipSecret?: string;
  providerSipConnectionId?: string;
}

export interface UpsertTelnyxOutboundVoiceProfileParams extends JsonInputObject {
  providerOutboundVoiceProfileId?: string;
  telnyxSipConnectionId?: string;
  allowedDestinations?: string[];
  concurrencyLimit?: number;
  channelLimit?: number;
  dailySpendingLimit?: number;
}

export interface CreateOutboundCallParams extends JsonInputObject {
  agentId: string;
  fromNumberId: string;
  toNumber: string;
  recipient?: string;
  context?: JsonInputObject;
  externalCustomerRef?: string;
  externalWorkflowRef?: string;
  idempotencyKey: string;
}

export interface TelnyxConnectionResponse extends JsonObject {
  id: string;
  tenant_id: string;
  platform_status: string;
  provider_status?: string | null;
  key_fingerprint?: string | null;
  telnyx_account_id?: string | null;
}

export interface OutboundCallResponse extends JsonObject {
  telephony_call_id: string;
  session_id?: string | null;
  room_name?: string | null;
  platform_status: string;
  direction: 'outbound';
  error_code?: string | null;
  error_message?: string | null;
}
