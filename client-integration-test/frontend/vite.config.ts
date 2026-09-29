import { createRequire } from 'node:module';
import { defineConfig } from 'vite';

const require = createRequire(import.meta.url);

function resolveVoiceVersion(): string {
  try {
    return String(require('@awaazlabs-uva/voice/package.json').version || '1.1.0');
  } catch {
    return '1.1.0';
  }
}

export default defineConfig({
  server: {
    port: 5174,
    strictPort: true,
  },
  define: {
    __UVA_VOICE_VERSION__: JSON.stringify(resolveVoiceVersion()),
  },
  optimizeDeps: {
    include: ['@awaazlabs-uva/voice'],
  },
  resolve: {
    dedupe: ['@awaazlabs-uva/voice'],
  },
});
