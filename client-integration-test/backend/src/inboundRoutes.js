import { createTelephonyClient } from './telephonyRoutes.js';
import { publicAgentConfig } from './agentConfig.js';

const fields = ['agent_language', 'stt_provider', 'stt_model', 'llm_provider', 'llm_model', 'tts_provider', 'tts_voice_id', 'voice_id'];
function publicAgent(agent) {
  return { ...publicAgentConfig(agent), ...Object.fromEntries(fields.map(key => [key, agent[key]])) };
}
function fail(message, code, status = 409) {
  throw Object.assign(new Error(message), { code, status });
}
function assignedAgent(number) {
  if (number.disabled_at) fail('This number is disabled.', 'inbound_number_disabled');
  const id = number.assigned_agent_id || number.agent_id;
  if (!id) fail('Assign an agent to this number first.', 'inbound_agent_missing');
  return id;
}
function sendError(res, error) {
  res.status(error.status || error.statusCode || 422).json({ error: error.code || 'inbound_setup_failed', message: error.message });
}

/** Provider edits target the number's assigned agent, never a browser-supplied agent ID. */
export function mountInboundRoutes(app, config, getAgents, applyPipeline, matches,
  getTelephony = () => createTelephonyClient(config)) {
  app.get('/api/inbound/setup', async (_req, res) => {
    try {
      const [client, telephony] = await Promise.all([getAgents(), getTelephony()]);
      const [agents, capabilities, numbers] = await Promise.all([
        client.listAgents(), client.getProviderCapabilities(), telephony.listManagedPhoneNumbers(),
      ]);
      res.json({ tenantId: config.tenantId, agents: agents.map(publicAgent), capabilities,
        numbers: Array.isArray(numbers) ? numbers : numbers.items || numbers.numbers || numbers.data || [] });
    } catch (error) { sendError(res, error); }
  });

  app.post('/api/inbound/numbers/:numberId/pipeline', async (req, res) => {
    try {
      const [client, telephony] = await Promise.all([getAgents(), getTelephony()]);
      const number = await telephony.getManagedPhoneNumber(req.params.numberId);
      const agentId = assignedAgent(number);
      // Verify visibility in this tenant before any write. Do not trust an ID from the form.
      const before = (await client.listAgents()).find(agent => agent.id === agentId);
      if (!before) fail('The assigned agent is unavailable in this tenant.', 'inbound_agent_missing', 404);
      const result = await applyPipeline(client, agentId, req.body ?? {}, { force: true });
      const [agents, current] = await Promise.all([client.listAgents(), telephony.getManagedPhoneNumber(req.params.numberId)]);
      if (assignedAgent(current) !== agentId) fail('Number assignment changed while saving. Refresh and review its settings.', 'inbound_assignment_changed');
      const saved = agents.find(agent => agent.id === agentId);
      if (!matches(saved, result.applied)) fail('The saved providers could not be confirmed. Refresh before calling.', 'inbound_save_unverified', 502);
      res.json({ tenantId: config.tenantId, number: current, routingReady: current.routing_status === 'ready', agent: publicAgent(saved), applied: result.applied,
        message: 'Saved and verified. Allow 30 seconds before calling for cached settings to expire. Future calls using this agent will load these settings. Existing calls keep their current settings.' });
    } catch (error) { sendError(res, error); }
  });
}
