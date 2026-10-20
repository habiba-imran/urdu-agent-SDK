import { defineConfig, mergeConfig } from 'vitest/config';
import base from './vite.config';

export default mergeConfig(base, defineConfig({
  test: { environment: 'happy-dom', include: ['test/**/*.test.ts'], restoreMocks: true },
}));
