import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
  },
  // Always pick up local file:../../sdk rebuilds (avoid stale optimizeDeps cache).
  optimizeDeps: {
    exclude: ['@awaazlabs-uva/voice'],
  },
  resolve: {
    dedupe: ['@awaazlabs-uva/voice'],
  },
});
