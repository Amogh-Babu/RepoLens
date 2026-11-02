import type {ApiClient} from './client.ts';
import {HttpApiClient} from './client.ts';
import {MockApiClient} from './mock/mockClient.ts';

/** The environment variables that choose and configure the client. */
export interface ApiEnv {
  VITE_API_MODE?: string;
  VITE_API_BASE_URL?: string;
}

/**
 * Builds the ApiClient selected by the environment:
 *
 * - VITE_API_MODE=http (the default): the real backend at VITE_API_BASE_URL,
 *   which defaults to "/api" (proxied to the backend by the Vite dev server).
 * - VITE_API_MODE=mock: in-memory fixture data, no backend needed. Tests
 *   always use this mode.
 */
export function createApiClient(env: ApiEnv = import.meta.env): ApiClient {
  const mode = env.VITE_API_MODE || 'http';
  switch (mode) {
    case 'http':
      return new HttpApiClient(env.VITE_API_BASE_URL || '/api');
    case 'mock':
      return new MockApiClient();
    default:
      throw new Error(
        `Unknown VITE_API_MODE "${mode}"; expected "http" or "mock".`,
      );
  }
}
