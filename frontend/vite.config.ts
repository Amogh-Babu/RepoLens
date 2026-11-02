import react from '@vitejs/plugin-react';
import {loadEnv} from 'vite';
import {defineConfig} from 'vitest/config';

// Vite requires a default export from its config file.
// eslint-disable-next-line import-x/no-default-export
export default defineConfig(({mode}) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    server: {
      // In http mode the client calls /api/...; forward those requests to the
      // backend with the /api prefix removed.
      proxy: {
        '/api': {
          target: env['API_PROXY_TARGET'] || 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api/, ''),
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      // Tests never talk to a real backend, whatever .env.local says.
      env: {VITE_API_MODE: 'mock'},
    },
  };
});
