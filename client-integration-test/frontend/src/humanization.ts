export type Humanization = {
  enabled?: boolean; warmth?: 'reserved' | 'balanced' | 'warm';
  formality?: 'casual' | 'balanced' | 'formal'; energy?: 'calm' | 'balanced' | 'lively';
  pace?: 'slower' | 'normal' | 'slightly_fast'; expressiveness?: 'subtle' | 'balanced'; adaptivePace?: boolean;
};
export const defaultHumanization: Required<Humanization> = {
  enabled: false, warmth: 'warm', formality: 'balanced', energy: 'balanced',
  pace: 'normal', expressiveness: 'subtle', adaptivePace: true,
};
export const normalizedHumanization = (value?: Humanization | null) => ({ ...defaultHumanization, ...value });
export function humanizationMarkup(prefix: string) {
  const fields = [
    ['enabled', 'Humanized speech', [['false', 'Off'], ['true', 'On']]],
    ['warmth', 'Warmth', [['reserved', 'Reserved'], ['balanced', 'Balanced'], ['warm', 'Warm']]],
    ['formality', 'Formality', [['casual', 'Casual'], ['balanced', 'Balanced'], ['formal', 'Formal']]],
    ['energy', 'Energy', [['calm', 'Calm'], ['balanced', 'Balanced'], ['lively', 'Lively']]],
    ['pace', 'Base pace', [['slower', 'Slower'], ['normal', 'Normal'], ['slightly_fast', 'Slightly faster']]],
    ['expressiveness', 'Expression', [['subtle', 'Subtle'], ['balanced', 'Balanced']]],
    ['adaptivePace', 'Adapt pace to the conversation', [['true', 'On'], ['false', 'Keep configured pace']]],
  ] as const;
  return `<fieldset class="speech-persona"><legend>Speech persona</legend><p class="hint">Save a consistent speaking style for web tests, inbound and outbound calls using this agent. Voices differ in how much expression they support.</p><div class="pipeline-grid">${fields.map(([key, label, values]) =>
    `<label for="${prefix}-${key}">${label}<select id="${prefix}-${key}" data-persona="${key}" disabled>${values.map(([value, title]) => `<option value="${value}">${title}</option>`).join('')}</select></label>`).join('')}</div></fieldset>`;
}
export function personaControls(root: HTMLElement) {
  const fields = [...root.querySelectorAll<HTMLSelectElement>('[data-persona]')];
  return {
    set(value?: Humanization | null) {
      const settings = normalizedHumanization(value);
      for (const field of fields) field.value = String(settings[field.dataset.persona as keyof Humanization]);
    },
    value(): Humanization {
      return Object.fromEntries(fields.map(field => [field.dataset.persona!,
        ['enabled', 'adaptivePace'].includes(field.dataset.persona!) ? field.value === 'true' : field.value])) as Humanization;
    },
    lock(disabled: boolean) { for (const field of fields) field.disabled = disabled; },
    onChange(callback: () => void) { for (const field of fields) field.addEventListener('change', callback); },
  };
}
