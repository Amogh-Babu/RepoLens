/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "http" (default) or "mock". See src/api/createApiClient.ts. */
  readonly VITE_API_MODE?: string;
  /** Base URL of the backend API in http mode. Defaults to "/api". */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
