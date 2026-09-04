import {
  createInvalidResponseError,
  createNetworkError,
  errorFromResponse,
} from './errors.js';
import { TELEPHONY_MACHINE_OPERATIONS } from './routes.js';
import { createNonce, createSignedHeaders } from './signing.js';
import {
  assertBackendRuntime,
  assertNonEmpty,
  buildUrl,
  fillPath,
  isJsonResponse,
  makeRequestInit,
  readJsonBody,
  resolveFetch,
  sanitizePublicResponse,
  sanitizeExtraHeaders,
  toSnakeCaseBody,
} from './transport.js';
import type { OperationName } from './routes.js';
import type {
  AvailableNumber,
  ConnectTelnyxAccountParams,
  CreateOutboundCallParams,
  ImportTelnyxNumberParams,
  JsonInputObject,
  JsonObject,
  JsonResponse,
  ListTelephonyFilters,
  MachineOperation,
  NumberOrderResponse,
  OutboundCallResponse,
  PurchaseNumberParams,
  ReserveNumberParams,
  RotateTelnyxAccountKeyParams,
  SearchAvailableNumbersParams,
  TelephonyClientOptions,
  TelephonyFetch,
  TelephonyFetchResponse,
  TelnyxConnectionResponse,
  UpsertTelnyxOutboundVoiceProfileParams,
  UpsertTelnyxSipConnectionParams,
} from './types.js';

export { AwaazLabsUvaTelephonyError } from './errors.js';
export { TELEPHONY_MACHINE_OPERATIONS } from './routes.js';
export {
  AUTH_HEADER_NAMES,
  canonicalJson,
  createNonce,
  createPayloadHash,
  createRequestSignature,
  createSignedHeaders,
} from './signing.js';
export type { OperationName } from './routes.js';
export type * from './types.js';

export class TelephonyClient {
  readonly #tenantId: string;
  readonly #tenantSecret: string;
  readonly #baseUrl: string;
  readonly #extraHeaders: Record<string, string>;
  readonly #fetcher: TelephonyFetch;
  readonly #nowSeconds: () => number;
  readonly #nonceFactory: () => string;

  constructor(options: TelephonyClientOptions) {
    assertBackendRuntime();
    assertNonEmpty(options.tenantId, 'tenantId');
    assertNonEmpty(options.tenantSecret, 'tenantSecret');
    assertNonEmpty(options.baseUrl, 'baseUrl');

    this.#tenantId = options.tenantId;
    this.#tenantSecret = options.tenantSecret;
    this.#baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.#extraHeaders = sanitizeExtraHeaders(options.extraHeaders);
    this.#fetcher = resolveFetch(options.fetch);
    this.#nowSeconds = options.nowSeconds ?? (() => Math.floor(Date.now() / 1000));
    this.#nonceFactory = options.nonceFactory ?? createNonce;
  }

  connectTelnyxAccount(params: ConnectTelnyxAccountParams): Promise<TelnyxConnectionResponse> {
    assertNonEmpty(params.apiKey, 'apiKey');
    return this.request<TelnyxConnectionResponse>('connectTelnyxAccount', toSnakeCaseBody(params));
  }

  rotateTelnyxAccountKey(params: RotateTelnyxAccountKeyParams): Promise<TelnyxConnectionResponse> {
    assertNonEmpty(params.apiKey, 'apiKey');
    return this.request<TelnyxConnectionResponse>('rotateTelnyxAccountKey', toSnakeCaseBody(params));
  }

  reverifyTelnyxAccount(): Promise<TelnyxConnectionResponse> {
    return this.request<TelnyxConnectionResponse>('reverifyTelnyxAccount');
  }

  disconnectTelnyxAccount(): Promise<JsonObject> {
    return this.request('disconnectTelnyxAccount');
  }

  getConnectionStatus(): Promise<TelnyxConnectionResponse> {
    return this.request<TelnyxConnectionResponse>('getConnectionStatus');
  }

  listTelnyxOwnedNumbers(filters: ListTelephonyFilters = {}): Promise<JsonResponse> {
    return this.request('listTelnyxOwnedNumbers', toSnakeCaseBody(filters));
  }

  listManagedPhoneNumbers(filters: ListTelephonyFilters = {}): Promise<JsonResponse> {
    return this.request('listManagedPhoneNumbers', toSnakeCaseBody(filters));
  }

  getManagedPhoneNumber(numberId: string): Promise<JsonObject> {
    assertNonEmpty(numberId, 'numberId');
    return this.request('getManagedPhoneNumber', { number_id: numberId });
  }

  importTelnyxNumber(params: ImportTelnyxNumberParams): Promise<JsonObject> {
    assertNonEmpty(params.e164Number, 'e164Number');
    return this.request('importTelnyxNumber', toSnakeCaseBody(params));
  }

  syncTelnyxOwnedNumbers(): Promise<JsonObject> {
    return this.request('syncTelnyxOwnedNumbers');
  }

  getTelnyxNumberDrift(): Promise<JsonObject> {
    return this.request('getTelnyxNumberDrift');
  }

  searchAvailableNumbers(params: SearchAvailableNumbersParams): Promise<AvailableNumber[]> {
    assertNonEmpty(params.country, 'country');
    return this.request<AvailableNumber[]>('searchAvailableNumbers', toSnakeCaseBody(params));
  }

  reserveNumber(params: ReserveNumberParams): Promise<JsonObject> {
    assertNonEmpty(params.e164Number, 'e164Number');
    assertNonEmpty(params.idempotencyKey, 'idempotencyKey');
    return this.request('reserveNumber', toSnakeCaseBody(params));
  }

  purchaseNumber(params: PurchaseNumberParams): Promise<NumberOrderResponse> {
    assertNonEmpty(params.e164Number, 'e164Number');
    assertNonEmpty(params.idempotencyKey, 'idempotencyKey');
    return this.request<NumberOrderResponse>('purchaseNumber', toSnakeCaseBody(params));
  }

  getNumberOrderStatus(orderId: string): Promise<NumberOrderResponse> {
    assertNonEmpty(orderId, 'orderId');
    return this.request<NumberOrderResponse>('getNumberOrderStatus', { order_id: orderId });
  }

  assignAgentToNumber(numberId: string, agentId: string): Promise<JsonObject> {
    assertNonEmpty(numberId, 'numberId');
    assertNonEmpty(agentId, 'agentId');
    return this.request(
      'assignAgentToNumber',
      { number_id: numberId, agent_id: agentId },
      { number_id: numberId },
    );
  }

  unassignAgentFromNumber(numberId: string): Promise<JsonObject> {
    assertNonEmpty(numberId, 'numberId');
    return this.request(
      'unassignAgentFromNumber',
      { number_id: numberId, agent_id: null },
      { number_id: numberId },
    );
  }

  upsertTelnyxSipConnection(params: UpsertTelnyxSipConnectionParams): Promise<JsonObject> {
    return this.request('upsertTelnyxSipConnection', toSnakeCaseBody(params));
  }

  verifyTelnyxSipConnection(): Promise<JsonObject> {
    return this.request('verifyTelnyxSipConnection');
  }

  upsertTelnyxOutboundVoiceProfile(params: UpsertTelnyxOutboundVoiceProfileParams): Promise<JsonObject> {
    return this.request('upsertTelnyxOutboundVoiceProfile', toSnakeCaseBody(params));
  }

  verifyTelnyxOutboundVoiceProfile(): Promise<JsonObject> {
    return this.request('verifyTelnyxOutboundVoiceProfile');
  }

  configureNumberRouting(numberId: string): Promise<JsonObject> {
    assertNonEmpty(numberId, 'numberId');
    return this.request('configureNumberRouting', { number_id: numberId }, { number_id: numberId });
  }

  configureOutboundTrunk(): Promise<JsonObject> {
    return this.request('configureOutboundTrunk');
  }

  getOutboundReadiness(): Promise<JsonObject> {
    return this.request('getOutboundReadiness');
  }

  createOutboundCall(params: CreateOutboundCallParams): Promise<OutboundCallResponse> {
    assertNonEmpty(params.agentId, 'agentId');
    assertNonEmpty(params.fromNumberId, 'fromNumberId');
    assertNonEmpty(params.toNumber, 'toNumber');
    assertNonEmpty(params.idempotencyKey, 'idempotencyKey');
    return this.request<OutboundCallResponse>('createOutboundCall', toSnakeCaseBody(params));
  }

  getCallStatus(telephonyCallId: string): Promise<JsonObject> {
    assertNonEmpty(telephonyCallId, 'telephonyCallId');
    return this.request('getCallStatus', { telephony_call_id: telephonyCallId });
  }

  listCallRecords(filters: ListTelephonyFilters = {}): Promise<JsonResponse> {
    return this.request('listCallRecords', toSnakeCaseBody(filters));
  }

  disableNumber(numberId: string): Promise<JsonObject> {
    assertNonEmpty(numberId, 'numberId');
    return this.request('disableNumber', { number_id: numberId }, { number_id: numberId });
  }

  private async request<TResponse extends JsonResponse>(
    name: OperationName,
    body: JsonInputObject = {},
    pathParams: Record<string, string> = {},
  ): Promise<TResponse> {
    const operation = TELEPHONY_MACHINE_OPERATIONS[name];
    const signed = createSignedHeaders({
      tenantId: this.#tenantId,
      tenantSecret: this.#tenantSecret,
      action: operation.action,
      body,
      timestamp: String(this.#nowSeconds()),
      nonce: this.#nonceFactory(),
    });
    const response = await this.send(operation, body, pathParams, signed.headers);
    return parseTelephonyResponse<TResponse>(response);
  }

  private async send(
    operation: MachineOperation,
    body: JsonInputObject,
    pathParams: Record<string, string>,
    authHeaders: Record<string, string>,
  ): Promise<TelephonyFetchResponse> {
    const init = makeRequestInit(operation.method, body, this.#extraHeaders, authHeaders);
    const url = buildUrl(this.#baseUrl, fillPath(operation.path, pathParams));
    try {
      return await this.#fetcher(url, init);
    } catch {
      throw createNetworkError();
    }
  }
}

async function parseTelephonyResponse<TResponse extends JsonResponse>(
  response: TelephonyFetchResponse,
): Promise<TResponse> {
  const body = await readJsonBody(response);
  if (!response.ok) throw errorFromResponse(response.status, response.statusText, body);
  if (!isJsonResponse(body)) throw createInvalidResponseError();
  return sanitizePublicResponse(body) as TResponse;
}
