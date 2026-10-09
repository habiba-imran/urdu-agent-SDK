import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { defineConfig } from 'vite';

const require = createRequire(import.meta.url);
// Resolve the installed package entry: package.json is not a public SDK export.
const voiceEntry = require.resolve('@awaazlabs-uva/voice');
const voiceVersion = JSON.parse(readFileSync(resolve(dirname(voiceEntry), '../package.json'), 'utf8')).version;

export default defineConfig({
  server: { port: 5174, strictPort: true },
  define: { __UVA_VOICE_VERSION__: JSON.stringify(voiceVersion) },
  optimizeDeps: { include: ['@awaazlabs-uva/voice'] },
  resolve: { dedupe: ['@awaazlabs-uva/voice'] },
});
