import { defineConfig } from 'vitest/config';

/** Local / Ehsan-wired runner. Habiba does not add vitest to package.json (Wave 1 freeze). */
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
