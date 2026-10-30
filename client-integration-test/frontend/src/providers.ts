export type PipelineAgent = {
  id: string; name?: string; agent_language?: string; stt_provider?: string;
  stt_model?: string; llm_provider?: string; llm_model?: string;
  tts_provider?: string; tts_voice_id?: string; voice_id?: string;
};

export function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!));
}

export function providerName(value?: string): string {
  const names: Record<string, string> = { deepgram: 'Deepgram', openai: 'OpenAI', anthropic: 'Anthropic',
    gemini: 'Gemini', groq: 'Groq', cartesia: 'Cartesia', elevenlabs: 'ElevenLabs', sarvam: 'Sarvam',
    azure: 'Azure', google: 'Google', rime: 'Rime', assemblyai: 'AssemblyAI' };
  return value ? names[value] || value : 'Not configured';
}

export function providerCards(agent?: Partial<PipelineAgent>): string {
  const paths: Record<string, string> = {
    STT: '<path d="M4 10v4m4-8v12m4-15v18m4-15v12m4-8v4"/>',
    LLM: '<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7Z"/>',
    TTS: '<path d="m11 5-6 4H2v6h3l6 4Zm4 3a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
  };
  return `<div class="provider-cards">${([
    ['STT', 'Listening', agent?.stt_provider, agent?.stt_model],
    ['LLM', 'Reasoning', agent?.llm_provider, agent?.llm_model],
    ['TTS', 'Speaking', agent?.tts_provider, agent?.tts_voice_id || agent?.voice_id],
  ] as const).map(([layer, title, provider, model]) => `<article class="provider-card" data-layer="${layer.toLowerCase()}">
    <div class="provider-card-heading"><svg class="provider-symbol" aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${paths[layer]}</svg><span>${title}</span><span class="provider-layer">${layer}</span></div>
    <strong>${escapeHtml(providerName(provider))}</strong><span class="provider-model" title="${escapeHtml(model)}">${escapeHtml(model || 'No model selected')}</span>
  </article>`).join('')}</div>`;
}
