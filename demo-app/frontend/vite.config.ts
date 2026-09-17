import { createRequire } from 'node:module';
import { defineConfig } from 'vite';

const require = createRequire(import.meta.url);

function resolveVoiceVersion(): string {
  try {
    return String(require('@awaazlabs-uva/voice/package.json').version || '0.1.0');
  } catch {
    return '0.1.0';
  }
}

export default defineConfig({
  server: {
    port: 5173,
  },
  define: {
    __UVA_VOICE_VERSION__: JSON.stringify(resolveVoiceVersion()),
  },
  // Installed via npm (registry or packed tarball) — allow Vite to prebundle.
  optimizeDeps: {
    include: ['@awaazlabs-uva/voice'],
  },
  resolve: {
    dedupe: ['@awaazlabs-uva/voice'],
  },
});
