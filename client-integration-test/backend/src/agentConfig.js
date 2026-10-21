import { validateHumanization } from '@awaazlabs-uva/agents';
/** Public agent configuration used by this demo; tool credentials stay server-side. */
export function publicAgentConfig(agent) {
  return {
    id: agent.id,
    name: agent.name,
    prompt: agent.prompt ?? '',
    firstSpeaker: agent.first_speaker ?? 'agent',
    greeting: agent.greeting ?? '',
    ...(agent.llm_options?.humanization ? { humanization: agent.llm_options.humanization } : {}),
  };
}

export function mountAgentConfigRoutes(app, getClient) {
  app.get('/api/agents/:agentId/config', async (req, res) => {
    try {
      const client = await getClient();
      const agents = await client.listAgents();
      const agent = agents.find(item => item.id === req.params.agentId);
      if (!agent) return res.status(404).json({ error: 'agent_not_found' });
      res.json(publicAgentConfig(agent));
    } catch (error) {
      res.status(502).json({ error: 'agent_load_failed', message: error.message });
    }
  });

  app.post('/api/agents/:agentId/config', async (req, res) => {
    const { prompt, firstSpeaker, greeting, humanization } = req.body ?? {};
    if (typeof prompt !== 'string' || !prompt.trim() || prompt.length > 24000 ||
        !['agent', 'user'].includes(firstSpeaker) || typeof greeting !== 'string' || greeting.trim().length > 500) {
      return res.status(400).json({ error: 'invalid_agent_config', message: 'Use a non-empty prompt (up to 24,000 characters), firstSpeaker (agent/user), and greeting (up to 500 characters).' });
    }
    if (humanization !== undefined) {
      try { validateHumanization(humanization); }
      catch (error) { return res.status(400).json({ error: 'invalid_humanization', message: error.message }); }
    }
    try {
      const client = await getClient();
      const agent = await client.updateAgent(req.params.agentId, { prompt, firstSpeaker, greeting,
        ...(humanization === undefined ? {} : { humanization }) });
      res.json(publicAgentConfig(agent));
    } catch (error) {
      res.status(502).json({ error: 'agent_save_failed', message: error.message });
    }
  });
}
