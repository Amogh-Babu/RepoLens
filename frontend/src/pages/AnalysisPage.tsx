import {useEffect, useState} from 'react';
import {Link, useParams} from 'react-router';
import {useApiClient} from '../api/apiClientContext.ts';
import {describeError} from '../api/describeError.ts';
import {ApiError} from '../api/errors.ts';
import type {Analysis} from '../api/types.ts';
import {ErrorBanner} from '../components/ErrorBanner.tsx';
import {ProgressIndicator} from '../components/ProgressIndicator.tsx';
import {ReanalyzeButton} from '../components/ReanalyzeButton.tsx';
import {SummaryBar} from '../components/SummaryBar.tsx';
import {Workspace} from '../components/Workspace.tsx';
import type {RequestFailure} from '../state/analysisStore.ts';
import {createAnalysisStore, isInProgress} from '../state/analysisStore.ts';
import {
  AnalysisStoreContext,
  useAnalysisStore,
} from '../state/analysisStoreContext.ts';
import {useDocumentTitle} from '../utils/useDocumentTitle.ts';
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
  useDocumentTitle(analysis === null ? 'Analysis' : repoName(analysis.repoUrl));
  const loadFailure = useAnalysisStore(state => state.loadFailure);

  return (
    <main className="page analysis" id="main" tabIndex={-1}>
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

/** "owner/repo" from https://github.com/owner/repo. */
function repoName(repoUrl: string): string {
  return repoUrl.replace(/^https?:\/\/[^/]+\//, '');
}
