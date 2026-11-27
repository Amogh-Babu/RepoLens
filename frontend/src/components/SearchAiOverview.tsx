import {useEffect, useState} from 'react';
import {loadAiStatus} from '../api/aiStatus.ts';
import {useApiClient} from '../api/apiClientContext.ts';
import {describeError} from '../api/describeError.ts';
import {ApiError} from '../api/errors.ts';
import type {
  SearchIntent,
  SearchOverviewResponse,
  SearchOverviewStep,
} from '../api/types.ts';
import {AiSummaryContent} from './AiSummaryContent.tsx';
import {ErrorBanner} from './ErrorBanner.tsx';
import './SearchAiOverview.css';

interface SearchAiOverviewProps {
  analysisId: string;
  /** Query whose reading list is shown. */
  query: string;
  intent?: SearchIntent | null;
  onSelectFile: (path: string) => void;
}

type State =
  | {kind: 'checking'}
  | {kind: 'disabled'}
  | {kind: 'idle'; notice: string | null}
  | {
      kind: 'generating';
      notice: string | null;
      previous: SearchOverviewResponse | null;
    }
  | {kind: 'ready'; notice: string | null; data: SearchOverviewResponse}
  | {
      kind: 'failed';
      notice: string | null;
      error: ApiError;
      previous: SearchOverviewResponse | null;
    };

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError('UNKNOWN', 'The AI overview could not be loaded.');
}

/**
 * AI overview above the reading list: where to start and what to read next.
 * Reads the cache automatically; only a click asks the model.
 */
export function SearchAiOverview({
  analysisId,
  query,
  intent = null,
  onSelectFile,
}: SearchAiOverviewProps) {
  const api = useApiClient();
  const key = `${analysisId}\n${query}\n${intent ?? ''}`;
  const [entry, setEntry] = useState<{key: string; state: State}>({
    key,
    state: {kind: 'checking'},
  });
  const state: State = entry.key === key ? entry.state : {kind: 'checking'};

  useEffect(() => {
    const controller = new AbortController();
    const settle = (next: State) => {
      if (!controller.signal.aborted) setEntry({key, state: next});
    };
    void (async () => {
      try {
        const status = await loadAiStatus(api);
        if (!status.enabled) {
          settle({kind: 'disabled'});
          return;
        }
        const notice = status.searchNotice ?? null;
        const data = await api.getSearchOverview(
          analysisId,
          {q: query, intent},
          {signal: controller.signal},
        );
        settle(
          data.status === 'notGenerated'
            ? {kind: 'idle', notice}
            : {kind: 'ready', notice, data},
        );
      } catch (error: unknown) {
        const apiError = toApiError(error);
        if (apiError.code === 'ABORTED') return;
        settle(
          apiError.code === 'AI_DISABLED'
            ? {kind: 'disabled'}
            : {kind: 'failed', notice: null, error: apiError, previous: null},
        );
      }
    })();
    return () => controller.abort();
  }, [api, analysisId, query, intent, key]);

  const generate = (regenerate: boolean) => {
    const notice = 'notice' in state ? state.notice : null;
    const previous =
      state.kind === 'ready'
        ? state.data
        : state.kind === 'failed'
          ? state.previous
          : null;
    setEntry({key, state: {kind: 'generating', notice, previous}});
    api
      .generateSearchOverview(analysisId, {q: query, intent}, {regenerate})
      .then(data => {
        setEntry(current =>
          current.key === key
            ? {key, state: {kind: 'ready', notice, data}}
            : current,
        );
      })
      .catch((error: unknown) => {
        const apiError = toApiError(error);
        setEntry(current =>
          current.key === key
            ? {
                key,
                state:
                  apiError.code === 'AI_DISABLED'
                    ? {kind: 'disabled'}
                    : {kind: 'failed', notice, error: apiError, previous},
              }
            : current,
        );
      });
  };

  if (state.kind === 'checking' || state.kind === 'disabled') return null;
  const data =
    state.kind === 'ready'
      ? state.data
      : 'previous' in state
        ? state.previous
        : null;
  const overview = data?.overview ?? null;

  return (
    <section className="search-ai" aria-label="AI search overview">
      <div className="search-ai__header">
        <span className="search-ai__badge">AI overview</span>
        {data?.metadata?.cached && (
          <span className="search-ai__muted">Cached</span>
        )}
      </div>
      {state.kind === 'idle' && (
        <>
          {state.notice && <p className="search-ai__muted">{state.notice}</p>}
          <button
            type="button"
            className="button"
            onClick={() => generate(false)}
          >
            Generate AI overview
          </button>
        </>
      )}
      {state.kind === 'generating' && overview === null && (
        <div
          className="ai-skeleton"
          role="status"
          aria-label="Generating AI overview…"
        >
          <span className="ai-skeleton-line ai-skeleton-line--wide" />
          <span className="ai-skeleton-line ai-skeleton-line--full" />
          <span className="ai-skeleton-line ai-skeleton-line--mid" />
        </div>
      )}
      {state.kind === 'failed' && (
        <ErrorBanner
          error={describeError(state.error)}
          onRetry={() => generate(overview !== null)}
        />
      )}
      {data?.status === 'noResults' && (
        <p className="search-ai__muted">
          No files match this search, so there is nothing to summarize.
        </p>
      )}
      {overview !== null && (
        <>
          <div className="search-ai__summary">
            <AiSummaryContent text={overview.summary} />
          </div>
          <div className="search-ai__step">
            <p className="search-ai__label">Start here</p>
            <StepButton step={overview.startHere} onSelect={onSelectFile} />
          </div>
          {overview.readNext.length > 0 && (
            <div className="search-ai__step">
              <p className="search-ai__label">Then read</p>
              <ol className="search-ai__list">
                {overview.readNext.map(step => (
                  <li key={step.path}>
                    <StepButton step={step} onSelect={onSelectFile} />
                  </li>
                ))}
              </ol>
            </div>
          )}
          {overview.uncertainties.length > 0 && (
            <div className="search-ai__step">
              <p className="search-ai__label">Not sure about</p>
              <ul className="search-ai__uncertainties">
                {overview.uncertainties.map((item, index) => (
                  <li key={index}>
                    <AiSummaryContent text={item} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="search-ai__disclaimer">
            AI-generated — check the files.
          </p>
          {state.kind !== 'generating' && (
            <button
              type="button"
              className="button button--quiet search-ai__regenerate"
              onClick={() => generate(true)}
            >
              Regenerate
            </button>
          )}
          {state.kind === 'generating' && (
            <p className="search-ai__muted" role="status">
              Regenerating…
            </p>
          )}
        </>
      )}
    </section>
  );
}

function StepButton({
  step,
  onSelect,
}: {
  step: SearchOverviewStep;
  onSelect: (path: string) => void;
}) {
  return (
    <div className="search-ai__file">
      <button
        type="button"
        className="search-ai__path"
        onClick={() => onSelect(step.path)}
      >
        <code>{step.path}</code>
      </button>
      <div className="search-ai__reason">
        <AiSummaryContent text={step.reason} />
      </div>
    </div>
  );
}
