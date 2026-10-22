import {createContext, useContext} from 'react';
import type {ApiClient} from './client.ts';

/** The ApiClient the app uses. Provided once in main.tsx; tests swap it. */
export const ApiClientContext = createContext<ApiClient | null>(null);

/** Returns the ApiClient from the nearest ApiClientContext provider. */
export function useApiClient(): ApiClient {
  const client = useContext(ApiClientContext);
  if (client === null) {
    throw new Error('useApiClient must be used inside ApiClientContext');
  }
  return client;
}
