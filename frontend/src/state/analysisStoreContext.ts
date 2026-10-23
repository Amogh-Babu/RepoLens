import {createContext, useContext} from 'react';
import {useStore} from 'zustand';
import type {
  AnalysisActions,
  AnalysisState,
  AnalysisStore,
} from './analysisStore.ts';

/** The store for the analysis shown on the current page. */
export const AnalysisStoreContext = createContext<AnalysisStore | null>(null);

/**
 * Reads from the current analysis store. Select single values (or use
 * zustand's useShallow) so components re-render only when those change.
 */
export function useAnalysisStore<T>(
  selector: (state: AnalysisState & AnalysisActions) => T,
): T {
  const store = useContext(AnalysisStoreContext);
  if (store === null) {
    throw new Error(
      'useAnalysisStore must be used inside AnalysisStoreContext',
    );
  }
  return useStore(store, selector);
}
