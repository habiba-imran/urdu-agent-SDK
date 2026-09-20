import { defineConfig } from 'vitest/config';

/** Runs via `npm test` (`vitest` is a package.json devDependency). */
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
