import {useEffect, useState} from 'react';
import {useApiClient} from '../api/apiClientContext.ts';
import type {ApiClient} from '../api/client.ts';
import {describeError} from '../api/describeError.ts';
import {ApiError} from '../api/errors.ts';
import type {AiStatus, FileSummary} from '../api/types.ts';
import {AiSummaryDetails} from './AiSummaryDetails.tsx';
import {ErrorBanner} from './ErrorBanner.tsx';

interface AiSummarySectionProps {
  analysisId: string;
  path: string;
  onSelectFile?: (path: string) => void;
}

type State =
  | {kind: 'checking'}
  | {kind: 'disabled'}
  | {kind: 'idle'; notice: string | null}
  | {kind: 'generating'; notice: string | null; previous: FileSummary | null}
  | {kind: 'ready'; notice: string | null; data: FileSummary}
  | {
      kind: 'failed';
      notice: string | null;
      error: ApiError;
      previous: FileSummary | null;
    };

const statusRequests = new WeakMap<ApiClient, Promise<AiStatus>>();

function loadStatus(api: ApiClient): Promise<AiStatus> {
  let request = statusRequests.get(api);
  if (request === undefined) {
    request = api.getAiStatus();
    request.catch(() => statusRequests.delete(api));
    statusRequests.set(api, request);
  }
  return request;
}

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError('UNKNOWN', 'The AI overview could not be loaded.');
}

/** Cache-read and explicit-generation controller for the existing overview UI. */
export function AiSummarySection({
  analysisId,
  path,
  onSelectFile,
}: AiSummarySectionProps) {
  const api = useApiClient();
  const key = `${analysisId}\n${path}`;
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
        const status = await loadStatus(api);
        if (!status.enabled) {
          settle({kind: 'disabled'});
          return;
        }
        const data = await api.getFileSummary(analysisId, path, {
          signal: controller.signal,
        });
        settle(
          data.status === 'completed'
            ? {kind: 'ready', notice: status.notice, data}
            : {kind: 'idle', notice: status.notice},
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
  }, [api, analysisId, path, key]);

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
      .generateFileSummary(analysisId, path, {regenerate})
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

  return (
    <>
      {state.kind === 'idle' && (
        <>
          {state.notice && <p className="detail__muted">{state.notice}</p>}
          <button
            type="button"
            className="button"
            onClick={() => generate(false)}
          >
            Generate AI overview
          </button>
        </>
      )}
      {state.kind === 'generating' && data === null && (
        <div role="status" aria-label="Generating AI overview…">
          <span className="detail__ai-skeleton-line detail__ai-skeleton-line--wide" />
          <span className="detail__ai-skeleton-line detail__ai-skeleton-line--full" />
          <span className="detail__ai-skeleton-line detail__ai-skeleton-line--mid" />
        </div>
      )}
      {state.kind === 'failed' && (
        <ErrorBanner
          error={describeError(state.error)}
          onRetry={() => generate(data !== null)}
        />
      )}
      {data?.summary !== null && data?.summary !== undefined && (
        <>
          <AiSummaryDetails
            summary={data.summary}
            metadata={data.metadata}
            onSelectFile={onSelectFile}
          />
          {state.kind !== 'generating' && (
            <button
              type="button"
              className="button button--quiet"
              onClick={() => generate(true)}
            >
              Regenerate
            </button>
          )}
        </>
      )}
    </>
  );
}
