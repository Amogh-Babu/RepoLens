import type {StoreApi} from 'zustand/vanilla';
import {createStore} from 'zustand/vanilla';
import type {ApiClient} from '../api/client.ts';
import type {ErrorDescription} from '../api/describeError.ts';
import {describeError} from '../api/describeError.ts';
import {toApiError} from '../api/errors.ts';
import type {Analysis, AnalysisStatus} from '../api/types.ts';

/** How often to ask for the status of a running analysis. */
export const DEFAULT_POLL_INTERVAL_MS = 1_000;

/** A request failure, ready to show in an ErrorBanner. */
export interface RequestFailure {
  code: string;
  error: ErrorDescription;
}

export interface AnalysisState {
  analysisId: string;
  /** Latest status from the backend; null until the first response. */
  analysis: Analysis | null;
  /** Set when asking for the status failed. Polling stops until retried. */
  loadFailure: RequestFailure | null;
  /** True while a cancel request is in flight. */
  cancelling: boolean;
  cancelFailure: RequestFailure | null;
}

export interface AnalysisActions {
  /** Fetches the status now, then keeps polling while the analysis runs. */
  startPolling(): void;
  stopPolling(): void;
  /** Asks the backend to cancel, then refreshes the status. */
  cancel(): Promise<void>;
}

export type AnalysisStore = StoreApi<AnalysisState & AnalysisActions>;

export interface AnalysisStoreOptions {
  pollIntervalMs?: number;
}

/** Whether the analysis is still in progress and worth polling. */
export function isInProgress(status: AnalysisStatus): boolean {
  return status === 'queued' || status === 'running';
}

/**
 * Creates the client-side state for one analysis. Later PRs add the graph,
 * selection and search results here.
 */
export function createAnalysisStore(
  api: ApiClient,
  analysisId: string,
  options: AnalysisStoreOptions = {},
): AnalysisStore {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  return createStore<AnalysisState & AnalysisActions>()((set, get) => {
    async function poll(signal: AbortSignal) {
      try {
        const analysis = await api.getAnalysis(analysisId, {signal});
        if (signal.aborted) return;
        set({analysis, loadFailure: null});
        if (isInProgress(analysis.status)) {
          timer = setTimeout(() => void poll(signal), pollIntervalMs);
        }
      } catch (error: unknown) {
        const apiError = toApiError(error);
        if (signal.aborted || apiError.code === 'ABORTED') return;
        set({
          loadFailure: {code: apiError.code, error: describeError(apiError)},
        });
      }
    }

    return {
      analysisId,
      analysis: null,
      loadFailure: null,
      cancelling: false,
      cancelFailure: null,

      startPolling() {
        get().stopPolling();
        controller = new AbortController();
        set({loadFailure: null});
        void poll(controller.signal);
      },

      stopPolling() {
        controller?.abort();
        controller = null;
        if (timer !== null) {
          clearTimeout(timer);
          timer = null;
        }
      },

      async cancel() {
        set({cancelling: true, cancelFailure: null});
        try {
          await api.cancelAnalysis(analysisId);
          get().startPolling();
        } catch (error: unknown) {
          const apiError = toApiError(error);
          set({
            cancelFailure: {
              code: apiError.code,
              error: describeError(apiError),
            },
          });
        } finally {
          set({cancelling: false});
        }
      },
    };
  });
}
