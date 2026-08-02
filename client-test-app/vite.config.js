import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: 'frontend',
  server: {
    port: 3000,
    open: true
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true
  },
  envDir: 'frontend'
});
