import type { HttpMethod, MachineOperation } from './types.js';

export const TELEPHONY_MACHINE_OPERATIONS = {
  connectTelnyxAccount: route('POST', '/machine/telephony/telnyx/connect', 'telephony.telnyx_connection.connect'),
  rotateTelnyxAccountKey: route('POST', '/machine/telephony/telnyx/rotate', 'telephony.telnyx_connection.rotate'),
  reverifyTelnyxAccount: route('POST', '/machine/telephony/telnyx/reverify', 'telephony.telnyx_connection.reverify'),
  disconnectTelnyxAccount: route('DELETE', '/machine/telephony/telnyx/connection', 'telephony.telnyx_connection.disconnect'),
  getConnectionStatus: route('GET', '/machine/telephony/telnyx/connection', 'telephony.telnyx_connection.status'),
  listTelnyxOwnedNumbers: route('POST', '/machine/telephony/telnyx/owned-numbers/list', 'telephony.telnyx_owned_numbers.list'),
  listManagedPhoneNumbers: route('POST', '/machine/telephony/numbers/list', 'telephony.managed_numbers.list'),
  getManagedPhoneNumber: route('POST', '/machine/telephony/numbers/get', 'telephony.managed_numbers.get'),
  importTelnyxNumber: route('POST', '/machine/telephony/numbers/import', 'telephony.managed_numbers.import'),
  syncTelnyxOwnedNumbers: route('POST', '/machine/telephony/numbers/sync', 'telephony.managed_numbers.sync'),
  getTelnyxNumberDrift: route('POST', '/machine/telephony/numbers/drift', 'telephony.managed_numbers.drift'),
  searchAvailableNumbers: route('POST', '/machine/telephony/available-numbers/search', 'telephony.available_numbers.search'),
  reserveNumber: route('POST', '/machine/telephony/number-reservations', 'telephony.number_reservations.create'),
  purchaseNumber: route('POST', '/machine/telephony/number-orders', 'telephony.number_orders.create'),
  getNumberOrderStatus: route('POST', '/machine/telephony/number-orders/get', 'telephony.number_orders.get'),
  assignAgentToNumber: route('PATCH', '/machine/telephony/numbers/{number_id}/assignment', 'telephony.numbers.assign_agent'),
  unassignAgentFromNumber: route('PATCH', '/machine/telephony/numbers/{number_id}/assignment', 'telephony.numbers.assign_agent'),
  upsertTelnyxSipConnection: route('POST', '/machine/telephony/telnyx/sip-connection', 'telephony.telnyx_sip_connection.upsert'),
  verifyTelnyxSipConnection: route('POST', '/machine/telephony/telnyx/sip-connection/test', 'telephony.telnyx_sip_connection.test'),
  upsertTelnyxOutboundVoiceProfile: route('POST', '/machine/telephony/telnyx/outbound-voice-profile', 'telephony.telnyx_outbound_voice_profile.upsert'),
  verifyTelnyxOutboundVoiceProfile: route('POST', '/machine/telephony/telnyx/outbound-voice-profile/reverify', 'telephony.telnyx_outbound_voice_profile.reverify'),
  configureNumberRouting: route('POST', '/machine/telephony/numbers/{number_id}/routing/configure', 'telephony.number_routing.configure'),
  configureOutboundTrunk: route('POST', '/machine/telephony/telnyx/outbound-trunk/configure', 'telephony.outbound_trunk.configure'),
  getOutboundReadiness: route('GET', '/machine/telephony/outbound-readiness', 'telephony.outbound_readiness.get'),
  createOutboundCall: route('POST', '/machine/telephony/outbound-calls', 'telephony.outbound_calls.create'),
  getCallStatus: route('POST', '/machine/telephony/calls/get', 'telephony.calls.get'),
  listCallRecords: route('POST', '/machine/telephony/calls/list', 'telephony.calls.list'),
  disableNumber: route('POST', '/machine/telephony/numbers/{number_id}/disable', 'telephony.numbers.disable'),
} as const;

export type OperationName = keyof typeof TELEPHONY_MACHINE_OPERATIONS;

function route(method: HttpMethod, path: MachineOperation['path'], action: MachineOperation['action']): MachineOperation {
  return { method, path, action };
}
