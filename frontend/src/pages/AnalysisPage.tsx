import {lazy, Suspense, useCallback, useEffect, useState} from 'react';
import {Link, useNavigate, useParams} from 'react-router';
import {useApiClient} from '../api/apiClientContext.ts';
import {describeError} from '../api/describeError.ts';
import {ApiError, toApiError} from '../api/errors.ts';
import type {Analysis, DependencyGraph} from '../api/types.ts';
import {ErrorBanner} from '../components/ErrorBanner.tsx';
import {FileDetailPanel} from '../components/FileDetailPanel.tsx';
import {FileExplorer} from '../components/FileExplorer.tsx';
import {ListFallback} from '../components/map/ListFallback.tsx';
import {MapErrorBoundary} from '../components/map/MapErrorBoundary.tsx';
import {ProgressIndicator} from '../components/ProgressIndicator.tsx';
import {SummaryBar} from '../components/SummaryBar.tsx';
import type {RequestFailure} from '../state/analysisStore.ts';
import {createAnalysisStore, isInProgress} from '../state/analysisStore.ts';
import {
  AnalysisStoreContext,
  useAnalysisStore,
} from '../state/analysisStoreContext.ts';
import './AnalysisPage.css';

interface AnalysisPageProps {
  /** Overrides how often a running analysis is polled. For tests. */
  pollIntervalMs?: number;
}

/**
 * Analysis page: progress while the analysis runs, then the summary, file
 * explorer, dependency map, search and reading list.
 */
export function AnalysisPage({pollIntervalMs}: AnalysisPageProps) {
  const {analysisId = ''} = useParams();
  // A new id gets a fresh store and polling loop.
  return (
    <AnalysisSession
      key={analysisId}
      analysisId={analysisId}
      pollIntervalMs={pollIntervalMs}
    />
  );
}

function AnalysisSession({
  analysisId,
  pollIntervalMs,
}: {
  analysisId: string;
  pollIntervalMs: number | undefined;
}) {
  const api = useApiClient();
  const [store] = useState(() =>
    createAnalysisStore(api, analysisId, {pollIntervalMs}),
  );

  // Leaving the page stops polling but does not cancel the analysis, so the
  // user can come back to it (and so React's development double-mount does
  // not cancel it).
  useEffect(() => {
    store.getState().startPolling();
    return () => store.getState().dispose();
  }, [store]);

  return (
    <AnalysisStoreContext value={store}>
      <AnalysisContent />
    </AnalysisStoreContext>
  );
}

function AnalysisContent() {
  const analysis = useAnalysisStore(state => state.analysis);
  const loadFailure = useAnalysisStore(state => state.loadFailure);

  return (
    <main className="page analysis">
      <header className="analysis__header">
        <Link to="/" className="analysis__back">
          ← Analyze another repository
        </Link>
        <h1>{analysis === null ? 'Analysis' : repoName(analysis.repoUrl)}</h1>
        {analysis !== null && (
          <a href={analysis.repoUrl} target="_blank" rel="noreferrer">
            {analysis.repoUrl}
          </a>
        )}
      </header>

      {loadFailure !== null ? (
        <LoadFailure failure={loadFailure} />
      ) : analysis === null ? (
        <p role="status">Loading the analysis…</p>
      ) : (
        <AnalysisBody analysis={analysis} />
      )}
    </main>
  );
}

function AnalysisBody({analysis}: {analysis: Analysis}) {
  const cancel = useAnalysisStore(state => state.cancel);
  const cancelling = useAnalysisStore(state => state.cancelling);
  const cancelFailure = useAnalysisStore(state => state.cancelFailure);

  if (isInProgress(analysis.status)) {
    return (
      <>
        <ProgressIndicator
          analysis={analysis}
          onCancel={() => void cancel()}
          cancelling={cancelling}
        />
        {cancelFailure !== null && (
          <ErrorBanner
            error={cancelFailure.error}
            onRetry={() => void cancel()}
          />
        )}
      </>
    );
  }

  switch (analysis.status) {
    case 'failed':
      return <FailedAnalysis analysis={analysis} />;
    case 'cancelled':
      return (
        <section className="analysis__ended">
          <p>This analysis was cancelled. Nothing was saved.</p>
          <ReanalyzeButton analysis={analysis} label="Analyze again" />
        </section>
      );
    default:
      return analysis.summary === null ? (
        <p role="status">Loading the analysis…</p>
      ) : (
        <>
          <SummaryBar analysis={analysis} summary={analysis.summary} />
          <Workspace analysis={analysis} />
        </>
      );
  }
}

/** File explorer, dependency map and file details for a finished analysis. */
function Workspace({analysis}: {analysis: Analysis}) {
  const graph = useAnalysisStore(state => state.graph);
  const graphFailure = useAnalysisStore(state => state.graphFailure);
  const loadGraph = useAnalysisStore(state => state.loadGraph);
  const selectedPath = useAnalysisStore(state => state.selectedPath);
  const expandedDirs = useAnalysisStore(state => state.expandedDirs);
  const selectFile = useAnalysisStore(state => state.selectFile);
  const toggleDir = useAnalysisStore(state => state.toggleDir);
  const detail = useAnalysisStore(state =>
    state.selectedPath === null
      ? null
      : (state.fileDetails[state.selectedPath] ?? null),
  );
  const fileFailure = useAnalysisStore(state => state.fileFailure);

  if (graphFailure !== null) {
    return <ErrorBanner error={graphFailure.error} onRetry={loadGraph} />;
  }
  if (graph === null) {
    return <p role="status">Loading the files…</p>;
  }

  return (
    <div className="workspace">
      <nav className="workspace__explorer" aria-label="File explorer">
        <FileExplorer
          files={graph.files}
          selectedPath={selectedPath}
          expandedDirs={expandedDirs}
          onSelectFile={selectFile}
          onToggleDir={toggleDir}
        />
      </nav>

      <MapPanel graph={graph} selectedPath={selectedPath} />

      <div className="workspace__detail">
        {selectedPath === null ? (
          <p className="workspace__hint">
            Select a file to see its symbols, imports and the files that import
            it.
          </p>
        ) : (
          <FileDetailPanel
            path={selectedPath}
            repoUrl={analysis.repoUrl}
            sha={analysis.sha}
            detail={detail}
            failure={fileFailure}
            onSelectFile={selectFile}
            onRetry={() => selectFile(selectedPath)}
            onClose={() => selectFile(null)}
          />
        )}
      </div>
    </div>
  );
}

// React Flow and dagre are most of the bundle, so the map loads on demand.
const DependencyMap = lazy(() =>
  import('../components/map/DependencyMap.tsx').then(module => ({
    default: module.DependencyMap,
  })),
);

const TOO_SLOW_MESSAGE =
  'The map could not be drawn quickly enough, so the files are listed ' +
  'instead. Every file can still be selected.';

const FAILED_MESSAGE =
  'The map could not be drawn in this browser, so the files are listed ' +
  'instead. Every file can still be selected.';

/** The dependency map, or the list view when the map is not available. */
function MapPanel({
  graph,
  selectedPath,
}: {
  graph: DependencyGraph;
  selectedPath: string | null;
}) {
  const expandedModules = useAnalysisStore(state => state.expandedModules);
  const selectFile = useAnalysisStore(state => state.selectFile);
  const toggleModule = useAnalysisStore(state => state.toggleModule);
  const collapseAllModules = useAnalysisStore(
    state => state.collapseAllModules,
  );
  // 'list' when chosen by the user; a message when the map failed.
  const [view, setView] = useState<'map' | 'list'>('map');
  const [fallbackMessage, setFallbackMessage] = useState<string | null>(null);
  const onTooSlow = useCallback(() => setFallbackMessage(TOO_SLOW_MESSAGE), []);
  const onMapError = useCallback(() => setFallbackMessage(FAILED_MESSAGE), []);
  const showList = view === 'list' || fallbackMessage !== null;

  const viewSwitch = (
    <div className="workspace__map-switch" role="group" aria-label="View">
      <button
        type="button"
        className="button"
        aria-pressed={!showList}
        onClick={() => {
          setFallbackMessage(null);
          setView('map');
        }}
      >
        Map
      </button>
      <button
        type="button"
        className="button"
        aria-pressed={showList}
        onClick={() => setView('list')}
      >
        List
      </button>
    </div>
  );

  return (
    <section className="workspace__map" aria-label="Dependency map">
      {showList ? (
        <ListFallback
          graph={graph}
          selectedPath={selectedPath}
          onSelectFile={selectFile}
          message={fallbackMessage}
          toolbarEnd={viewSwitch}
        />
      ) : (
        <MapErrorBoundary onError={onMapError}>
          <Suspense
            fallback={
              <p role="status" className="workspace__hint workspace__loading">
                Loading the map…
              </p>
            }
          >
            <DependencyMap
              graph={graph}
              expandedModules={expandedModules}
              selectedPath={selectedPath}
              onSelectFile={selectFile}
              onToggleModule={toggleModule}
              onCollapseAll={collapseAllModules}
              onTooSlow={onTooSlow}
              toolbarEnd={viewSwitch}
            />
          </Suspense>
        </MapErrorBoundary>
      )}
    </section>
  );
}

function LoadFailure({failure}: {failure: RequestFailure}) {
  const startPolling = useAnalysisStore(state => state.startPolling);
  return (
    <ErrorBanner error={failure.error} onRetry={startPolling}>
      {!failure.error.retryable && (
        <Link to="/" className="button">
          Analyze a repository
        </Link>
      )}
    </ErrorBanner>
  );
}

function FailedAnalysis({analysis}: {analysis: Analysis}) {
  const error = describeError(
    analysis.error === null
      ? new ApiError('ANALYSIS_FAILED', 'The analysis did not finish.')
      : ApiError.fromBody(analysis.error),
  );
  return (
    <ErrorBanner error={error}>
      {error.retryable && (
        <ReanalyzeButton analysis={analysis} label="Try again" />
      )}
      <Link to="/" className="button">
        Analyze another repository
      </Link>
    </ErrorBanner>
  );
}

/** Starts a new analysis of the same repository and ref. */
function ReanalyzeButton({
  analysis,
  label,
}: {
  analysis: Analysis;
  label: string;
}) {
  const api = useApiClient();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const [failure, setFailure] = useState<RequestFailure | null>(null);

  async function reanalyze() {
    setStarting(true);
    setFailure(null);
    try {
      const {analysisId} = await api.startAnalysis(
        analysis.ref === null
          ? {url: analysis.repoUrl}
          : {url: analysis.repoUrl, ref: analysis.ref},
      );
      void navigate(`/analysis/${encodeURIComponent(analysisId)}`);
    } catch (error: unknown) {
      const apiError = toApiError(error);
      setFailure({code: apiError.code, error: describeError(apiError)});
      setStarting(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="button button--primary"
        onClick={() => void reanalyze()}
        disabled={starting}
      >
        {starting ? 'Starting…' : label}
      </button>
      {failure !== null && <ErrorBanner error={failure.error} />}
    </>
  );
}

/** "owner/repo" from https://github.com/owner/repo. */
function repoName(repoUrl: string): string {
  return repoUrl.replace(/^https?:\/\/[^/]+\//, '');
}
