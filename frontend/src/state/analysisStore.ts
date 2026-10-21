import type {StoreApi} from 'zustand/vanilla';
import {createStore} from 'zustand/vanilla';
import type {ApiClient} from '../api/client.ts';
import type {ErrorDescription} from '../api/describeError.ts';
import {describeError} from '../api/describeError.ts';
import {toApiError} from '../api/errors.ts';
import type {
  Analysis,
  AnalysisStatus,
  DependencyGraph,
  FileDetail,
} from '../api/types.ts';
import {ancestorDirs, topLevelDirs} from '../utils/fileTree.ts';

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

  /** Files, modules and import edges; loaded once the analysis completes. */
  graph: DependencyGraph | null;
  graphFailure: RequestFailure | null;

  /** Path of the selected file, shown in the detail panel. */
  selectedPath: string | null;
  /** File details fetched so far, by path. */
  fileDetails: Readonly<Record<string, FileDetail>>;
  /** Set when fetching the selected file's details failed. */
  fileFailure: RequestFailure | null;

  /** Directories expanded in the file explorer. */
  expandedDirs: ReadonlySet<string>;
  /** Modules expanded on the dependency map; the rest are collapsed. */
  expandedModules: ReadonlySet<string>;
}

export interface AnalysisActions {
  /** Fetches the status now, then keeps polling while the analysis runs. */
  startPolling(): void;
  stopPolling(): void;
  /** Asks the backend to cancel, then refreshes the status. */
  cancel(): Promise<void>;
  /** Fetches the graph. Called automatically when the analysis completes. */
  loadGraph(): void;
  /**
   * Selects a file (or clears the selection with null), expands its
   * directories in the explorer and fetches its details if needed.
   */
  selectFile(path: string | null): void;
  /** Expands or collapses a directory in the file explorer. */
  toggleDir(path: string, expanded?: boolean): void;
  /** Expands or collapses a module on the dependency map. */
  toggleModule(moduleId: string, expanded?: boolean): void;
  /** Collapses every module on the dependency map. */
  collapseAllModules(): void;
  /** Stops polling and cancels every in-flight request. */
  dispose(): void;
}

export type AnalysisStore = StoreApi<AnalysisState & AnalysisActions>;

export interface AnalysisStoreOptions {
  pollIntervalMs?: number;
}

/** Whether the analysis is still in progress and worth polling. */
export function isInProgress(status: AnalysisStatus): boolean {
  return status === 'queued' || status === 'running';
}

/** A copy of `set` with `item` added or removed (toggled if undefined). */
function toggled(
  set: ReadonlySet<string>,
  item: string,
  include?: boolean,
): ReadonlySet<string> {
  const shouldInclude = include ?? !set.has(item);
  if (shouldInclude === set.has(item)) return set;
  const next = new Set(set);
  if (shouldInclude) {
    next.add(item);
  } else {
    next.delete(item);
  }
  return next;
}

function failureFrom(error: unknown): RequestFailure | null {
  const apiError = toApiError(error);
  if (apiError.code === 'ABORTED') return null;
  return {code: apiError.code, error: describeError(apiError)};
}

/**
 * Creates the client-side state for one analysis: its status, graph, file
 * selection, explorer and map state. Later PRs add search state here.
 */
export function createAnalysisStore(
  api: ApiClient,
  analysisId: string,
  options: AnalysisStoreOptions = {},
): AnalysisStore {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  let pollController: AbortController | null = null;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let graphController: AbortController | null = null;
  let fileController: AbortController | null = null;

  return createStore<AnalysisState & AnalysisActions>()((set, get) => {
    async function poll(signal: AbortSignal) {
      try {
        const analysis = await api.getAnalysis(analysisId, {signal});
        if (signal.aborted) return;
        set({analysis, loadFailure: null});
        if (isInProgress(analysis.status)) {
          pollTimer = setTimeout(() => void poll(signal), pollIntervalMs);
        } else if (analysis.status === 'completed' && get().graph === null) {
          get().loadGraph();
        }
      } catch (error: unknown) {
        if (signal.aborted) return;
        const failure = failureFrom(error);
        if (failure !== null) set({loadFailure: failure});
      }
    }

    async function fetchGraph(signal: AbortSignal) {
      try {
        const graph = await api.getGraph(analysisId, {signal});
        if (signal.aborted) return;
        set({
          graph,
          graphFailure: null,
          expandedDirs: new Set(topLevelDirs(graph.files.map(f => f.path))),
          // Modules start collapsed, unless there is only one.
          expandedModules: new Set(
            graph.modules.length === 1 ? graph.modules.map(m => m.id) : [],
          ),
        });
      } catch (error: unknown) {
        if (signal.aborted) return;
        const failure = failureFrom(error);
        if (failure !== null) set({graphFailure: failure});
      }
    }

    async function fetchFile(path: string, signal: AbortSignal) {
      try {
        const detail = await api.getFile(analysisId, path, {signal});
        if (signal.aborted) return;
        set(state => ({
          fileDetails: {...state.fileDetails, [path]: detail},
        }));
      } catch (error: unknown) {
        if (signal.aborted) return;
        const failure = failureFrom(error);
        if (failure !== null) set({fileFailure: failure});
      }
    }

    return {
      analysisId,
      analysis: null,
      loadFailure: null,
      cancelling: false,
      cancelFailure: null,
      graph: null,
      graphFailure: null,
      selectedPath: null,
      fileDetails: {},
      fileFailure: null,
      expandedDirs: new Set(),
      expandedModules: new Set(),

      startPolling() {
        get().stopPolling();
        pollController = new AbortController();
        set({loadFailure: null});
        void poll(pollController.signal);
      },

      stopPolling() {
        pollController?.abort();
        pollController = null;
        if (pollTimer !== null) {
          clearTimeout(pollTimer);
          pollTimer = null;
        }
      },

      async cancel() {
        set({cancelling: true, cancelFailure: null});
        try {
          await api.cancelAnalysis(analysisId);
          get().startPolling();
        } catch (error: unknown) {
          set({cancelFailure: failureFrom(error)});
        } finally {
          set({cancelling: false});
        }
      },

      loadGraph() {
        graphController?.abort();
        graphController = new AbortController();
        set({graphFailure: null});
        void fetchGraph(graphController.signal);
      },

      selectFile(path) {
        fileController?.abort();
        fileController = null;
        if (path === null) {
          set({selectedPath: null, fileFailure: null});
          return;
        }
        set(state => {
          const moduleId = state.graph?.files.find(
            f => f.path === path,
          )?.module;
          return {
            selectedPath: path,
            fileFailure: null,
            expandedDirs: new Set([
              ...state.expandedDirs,
              ...ancestorDirs(path),
            ]),
            expandedModules:
              moduleId === undefined || state.expandedModules.has(moduleId)
                ? state.expandedModules
                : new Set([...state.expandedModules, moduleId]),
          };
        });
        if (get().fileDetails[path] === undefined) {
          fileController = new AbortController();
          void fetchFile(path, fileController.signal);
        }
      },

      toggleDir(path, expanded) {
        set(state => ({
          expandedDirs: toggled(state.expandedDirs, path, expanded),
        }));
      },

      toggleModule(moduleId, expanded) {
        set(state => ({
          expandedModules: toggled(state.expandedModules, moduleId, expanded),
        }));
      },

      collapseAllModules() {
        set({expandedModules: new Set()});
      },

      dispose() {
        get().stopPolling();
        graphController?.abort();
        fileController?.abort();
      },
    };
  });
}
