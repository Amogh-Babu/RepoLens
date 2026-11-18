import type {ReactNode} from 'react';
import {useEffect, useId, useState} from 'react';
import {useApiClient} from '../api/apiClientContext.ts';
import type {ApiClient} from '../api/client.ts';
import {describeError} from '../api/describeError.ts';
import {ApiError} from '../api/errors.ts';
import type {AiStatus, CodeSummary, FileSummary} from '../api/types.ts';
import {ErrorBanner} from './ErrorBanner.tsx';
import './AiSummarySection.css';

interface AiSummarySectionProps {
  analysisId: string;
  path: string;
  onSelectFile: (path: string) => void;
}

type SectionState =
  | {kind: 'loading'}
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

/** One status request per client, shared by every panel. */
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
    : new ApiError('UNKNOWN', 'The AI summary could not be loaded.');
}

/**
 * The AI File Summary for one file: loads a cached summary if there is one,
 * otherwise offers to generate it. Loads independently of the rest of the
 * file panel, so symbols, imports and links stay usable while it works.
 */
export function AiSummarySection({
  analysisId,
  path,
  onSelectFile,
}: AiSummarySectionProps) {
  const api = useApiClient();
  const headingId = useId();
  const key = `${analysisId}\n${path}`;
  const [entry, setEntry] = useState<{key: string; state: SectionState}>({
    key,
    state: {kind: 'loading'},
  });
  const state: SectionState =
    entry.key === key ? entry.state : {kind: 'loading'};

  useEffect(() => {
    const controller = new AbortController();
    const settle = (next: SectionState) => {
      if (!controller.signal.aborted) setEntry({key, state: next});
    };
    void (async () => {
      let status: AiStatus;
      try {
        status = await loadStatus(api);
      } catch {
        settle({kind: 'disabled'});
        return;
      }
      if (!status.enabled) {
        settle({kind: 'disabled'});
        return;
      }
      try {
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
            : {
                kind: 'failed',
                notice: status.notice,
                error: apiError,
                previous: null,
              },
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

  return (
    <section
      className="ai-summary"
      aria-labelledby={headingId}
      aria-busy={state.kind === 'loading' || state.kind === 'generating'}
    >
      <h3 id={headingId} className="ai-summary__heading">
        AI File Summary
        {(state.kind === 'ready' ||
          (state.kind !== 'disabled' &&
            'previous' in state &&
            state.previous !== null)) && (
          <span className="ai-summary__badge">AI-generated</span>
        )}
      </h3>
      <SectionBody
        state={state}
        onGenerate={() => generate(false)}
        onRegenerate={() => generate(true)}
        onSelectFile={onSelectFile}
      />
    </section>
  );
}

function SectionBody({
  state,
  onGenerate,
  onRegenerate,
  onSelectFile,
}: {
  state: SectionState;
  onGenerate: () => void;
  onRegenerate: () => void;
  onSelectFile: (path: string) => void;
}) {
  switch (state.kind) {
    case 'loading':
      return (
        <p role="status" className="detail__muted">
          Checking for an AI summary…
        </p>
      );
    case 'disabled':
      return (
        <p className="detail__muted">
          AI summaries are not enabled on this server. Everything below comes
          from static analysis of the code.
        </p>
      );
    case 'idle':
      return (
        <>
          {state.notice && <p className="ai-summary__notice">{state.notice}</p>}
          <button type="button" className="button" onClick={onGenerate}>
            Generate AI summary
          </button>
        </>
      );
    case 'generating':
      return (
        <>
          <p role="status" className="detail__muted">
            Generating and verifying a summary. This can take a little while;
            the rest of this panel stays usable.
          </p>
          {state.previous?.summary && (
            <SummaryView
              data={state.previous}
              summary={state.previous.summary}
              onSelectFile={onSelectFile}
            />
          )}
        </>
      );
    case 'ready':
      return state.data.summary === null ? null : (
        <>
          <SummaryView
            data={state.data}
            summary={state.data.summary}
            onSelectFile={onSelectFile}
          />
          <button
            type="button"
            className="button button--quiet ai-summary__regenerate"
            onClick={onRegenerate}
          >
            Regenerate
          </button>
        </>
      );
    case 'failed':
      return (
        <>
          <ErrorBanner
            error={describeError(state.error)}
            onRetry={state.previous === null ? onGenerate : onRegenerate}
          />
          {state.previous?.summary && (
            <SummaryView
              data={state.previous}
              summary={state.previous.summary}
              onSelectFile={onSelectFile}
            />
          )}
        </>
      );
  }
}

function formatSpans(spans: Array<[number, number]>): string {
  return spans
    .map(([start, end]) => (start === end ? `${start}` : `${start}–${end}`))
    .join(', ');
}

/** Renders `backticked` names as code; everything else as plain text. */
function withCode(text: string): ReactNode[] {
  return text
    .split(/`([^`]+)`/)
    .map((part, index) =>
      index % 2 === 1 ? <code key={index}>{part}</code> : part,
    );
}

function SummaryView({
  data,
  summary,
  onSelectFile,
}: {
  data: FileSummary;
  summary: CodeSummary;
  onSelectFile: (path: string) => void;
}) {
  const metadata = data.metadata;
  const detailCount =
    summary.responsibilities.length +
    summary.keySymbols.length +
    summary.evidence.length;
  return (
    <div className="ai-summary__body">
      {summary.coverage === 'partial' && metadata !== null && (
        <p className="detail__warning" role="note">
          Partial: only lines {formatSpans(metadata.inspectedLines)} of{' '}
          {metadata.lineCount} were inspected, so this summary does not cover
          the rest of the file.
        </p>
      )}
      <p className="ai-summary__text">{withCode(summary.summary)}</p>
      <details className="ai-summary__details">
        <summary>
          Purpose, responsibilities and evidence ({detailCount}
          {summary.uncertainties.length > 0 &&
            `, ${summary.uncertainties.length} uncertain`}
          )
        </summary>
        <h4>Purpose</h4>
        <p>{withCode(summary.purpose)}</p>

        <h4>Responsibilities</h4>
        <ul>
          {summary.responsibilities.map(item => (
            <li key={item}>{withCode(item)}</li>
          ))}
        </ul>

        {summary.keySymbols.length > 0 && (
          <>
            <h4>Important functions and classes</h4>
            <ul>
              {summary.keySymbols.map(symbol => (
                <li key={`${symbol.name}:${symbol.line}`}>
                  <a
                    href={symbol.url}
                    target="_blank"
                    rel="noreferrer"
                    title={`Open line ${symbol.line} on GitHub`}
                  >
                    <code>{symbol.name}</code>
                  </a>{' '}
                  <span className="detail__muted">
                    {symbol.kind}, line {symbol.line}
                  </span>
                  : {withCode(symbol.description)}
                </li>
              ))}
            </ul>
          </>
        )}

        {summary.dependencies.length > 0 && (
          <>
            <h4>Verified dependencies</h4>
            <ul>
              {summary.dependencies.map(dependency => (
                <li key={`${dependency.relationship}:${dependency.path}`}>
                  <span className="detail__muted">
                    {dependency.relationship === 'imports'
                      ? 'Imports '
                      : 'Imported by '}
                  </span>
                  <button
                    type="button"
                    className="detail__file-link"
                    onClick={() => onSelectFile(dependency.path)}
                  >
                    <code>{dependency.path}</code>
                  </button>
                  : {withCode(dependency.description)}
                </li>
              ))}
            </ul>
          </>
        )}

        {summary.sideEffects.length > 0 && (
          <>
            <h4>Side effects</h4>
            <ul>
              {summary.sideEffects.map(effect => (
                <li key={`${effect.kind}:${effect.startLine}`}>
                  <span className="detail__muted">{effect.kind}: </span>
                  {withCode(effect.description)}{' '}
                  <a href={effect.url} target="_blank" rel="noreferrer">
                    {lineLabel(effect.startLine, effect.endLine)}
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}

        {summary.uncertainties.length > 0 && (
          <>
            <h4>Uncertainties</h4>
            <ul>
              {summary.uncertainties.map(item => (
                <li key={item}>{withCode(item)}</li>
              ))}
            </ul>
          </>
        )}

        <h4>Source evidence</h4>
        <ul>
          {summary.evidence.map(item => (
            <li key={`${item.startLine}-${item.endLine}`}>
              <a href={item.url} target="_blank" rel="noreferrer">
                {lineLabel(item.startLine, item.endLine)}
                <span className="visually-hidden">
                  {' '}
                  (opens on GitHub at the analyzed commit)
                </span>
              </a>
              : {withCode(item.description)}
            </li>
          ))}
        </ul>
      </details>
      {metadata !== null && (
        <p className="ai-summary__meta">
          Generated by {metadata.model}
          {metadata.cached ? ' · cached' : ''} · Names, dependencies and line
          references are checked against static analysis; the wording is not.
        </p>
      )}
    </div>
  );
}

function lineLabel(start: number, end: number): string {
  return start === end ? `Line ${start}` : `Lines ${start}–${end}`;
}
