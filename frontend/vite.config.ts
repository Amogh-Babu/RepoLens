import react from '@vitejs/plugin-react';
import {defineConfig} from 'vitest/config';

// Vite requires a default export from its config file.
// eslint-disable-next-line import-x/no-default-export
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
