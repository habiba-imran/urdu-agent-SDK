/** Public agent configuration used by this demo; tool credentials stay server-side. */
export function publicAgentConfig(agent) {
  return {
    id: agent.id,
    name: agent.name,
    prompt: agent.prompt ?? '',
    firstSpeaker: agent.first_speaker ?? 'agent',
    greeting: agent.greeting ?? '',
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
    const { prompt, firstSpeaker, greeting } = req.body ?? {};
    if (typeof prompt !== 'string' || !prompt.trim() || prompt.length > 24000 ||
        !['agent', 'user'].includes(firstSpeaker) || typeof greeting !== 'string' || greeting.trim().length > 500) {
      return res.status(400).json({ error: 'invalid_agent_config', message: 'Use a non-empty prompt (up to 24,000 characters), firstSpeaker (agent/user), and greeting (up to 500 characters).' });
    }
    try {
      const client = await getClient();
      const agent = await client.updateAgent(req.params.agentId, { prompt, firstSpeaker, greeting });
      res.json(publicAgentConfig(agent));
    } catch (error) {
      res.status(502).json({ error: 'agent_save_failed', message: error.message });
    }
  });
}
