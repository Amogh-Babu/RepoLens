import type {ReactNode} from 'react';
import {useId, useState} from 'react';
import {encodeFilePath} from '../api/client.ts';
import type {
  FileAiSummary,
  FileDetail,
  ImportInfo,
  SymbolKind,
} from '../api/types.ts';
import type {RequestFailure} from '../state/analysisStore.ts';
import {AiSummarySection} from './AiSummarySection.tsx';
import {ErrorBanner} from './ErrorBanner.tsx';
import './FileDetailPanel.css';

interface FileDetailPanelProps {
  path: string;
  /**
   * The analysis the file belongs to. When set, the panel shows the AI File
   * Summary section, which loads on its own without blocking the rest.
   */
  analysisId?: string;
  /** Repository URL and commit, to link the source before details load. */
  repoUrl: string;
  sha: string;
  /** Null while loading or after a failure. */
  detail: FileDetail | null;
  failure: RequestFailure | null;
  aiSummary?: FileAiSummary | null;
  aiSummaryLoading?: boolean;
  aiSummaryFailure?: RequestFailure | null;
  onRetryAiSummary?: () => void;
  onSelectFile: (path: string) => void;
  onRetry: () => void;
  onClose: () => void;
  /** Set when the file is in the current reading list (Use Case 3, 3b). */
  readingOrder?: ReadingOrderInfo | null;
}

/** Where the selected file sits in the current reading list. */
export interface ReadingOrderInfo {
  query: string;
  position: number;
  total: number;
  reason: string;
  /** Why the file sits at this position in the order. */
  orderReason: string;
  /** Selects the previous file in the reading order; null at the start. */
  onPrev: (() => void) | null;
  /** Selects the next file in the reading order; null at the end. */
  onNext: (() => void) | null;
}

const KIND_LABELS: Record<SymbolKind, string> = {
  function: 'fn',
  class: 'class',
  variable: 'var',
};

/**
 * File detail panel with a compact inline GitHub link icon to the left of the
 * filename, a single combined File info accordion (Path, Commit, Module), and
 * animated Collapse accordions starting closed for Symbols, Imports, Imported
 * by, and External libraries.
 */
export function FileDetailPanel({
  path,
  analysisId,
  repoUrl,
  sha,
  detail,
  failure,
  aiSummary = null,
  aiSummaryLoading = false,
  aiSummaryFailure = null,
  onRetryAiSummary,
  onSelectFile,
  onRetry,
  onClose,
  readingOrder = null,
}: FileDetailPanelProps) {
  const headingId = useId();
  const sourceUrl =
    detail?.sourceUrl ?? `${repoUrl}/blob/${sha}/${encodeFilePath(path)}`;
  const name = path.slice(path.lastIndexOf('/') + 1);

  return (
    <aside className="detail" aria-labelledby={headingId}>
      <div className="detail__header">
        <div className="detail__title-row">
          <a
            className="detail__source-icon"
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            title="Open source on GitHub"
          >
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path
                d="M6.5 9.5L9.5 6.5M7.2 4.6L8.8 3C10.1255 1.67452 12.2745 1.67452 13.6 3C14.9255 4.32548 14.9255 6.47452 13.6 7.8L12 9.4M8.8 11.4L7.2 13C5.87452 14.3255 3.72548 14.3255 2.4 13C1.07452 11.6745 1.07452 9.52548 2.4 8.2L4 6.6"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
            <span className="visually-hidden">
              Open source on GitHub (opens in a new tab)
            </span>
          </a>
          <h2 id={headingId}>{name}</h2>
        </div>

        <button
          type="button"
          className="button button--quiet detail__close"
          onClick={onClose}
          aria-label="Close file details"
        >
          ✕
        </button>
      </div>

      {(() => {
        const hasAiBlock =
          aiSummaryLoading || aiSummary !== null || aiSummaryFailure !== null;
        const aiBlock = !hasAiBlock ? null : aiSummaryLoading &&
          aiSummary === null ? (
          <div
            className="detail__ai-skeleton"
            role="status"
            aria-busy="true"
            aria-label="Generating AI overview…"
          >
            <span className="detail__ai-skeleton-line detail__ai-skeleton-line--wide" />
            <span className="detail__ai-skeleton-line detail__ai-skeleton-line--full" />
            <span className="detail__ai-skeleton-line detail__ai-skeleton-line--mid" />
          </div>
        ) : aiSummaryFailure !== null ? (
          aiSummaryFailure.code === 'TIMEOUT' ? (
            <p className="detail__muted">AI overview timed out.</p>
          ) : aiSummaryFailure.code === 'FILE_NOT_FOUND' ||
            aiSummaryFailure.code === 'UNKNOWN' ? (
            <p className="detail__muted">AI overview unavailable.</p>
          ) : (
            <ErrorBanner
              error={aiSummaryFailure.error}
              onRetry={onRetryAiSummary}
            />
          )
        ) : (
          aiSummary !== null && <AiSummaryContent text={aiSummary.summary} />
        );

        if (readingOrder !== null) {
          return (
            <section className="detail__reading" aria-label="Reading order">
              <div className="detail__reading-nav">
                <button
                  type="button"
                  className="detail__reading-arrow"
                  aria-label="Previous in reading order"
                  onClick={readingOrder.onPrev ?? undefined}
                  disabled={readingOrder.onPrev === null}
                >
                  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M10 3L5 8L10 13"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
                <p className="detail__reading-position">
                  <span className="detail__reading-step">
                    #{readingOrder.position} of {readingOrder.total}
                  </span>{' '}
                  <span className="detail__reading-query">
                    for “{readingOrder.query}”
                  </span>
                </p>
                <button
                  type="button"
                  className="detail__reading-arrow"
                  aria-label="Next in reading order"
                  onClick={readingOrder.onNext ?? undefined}
                  disabled={readingOrder.onNext === null}
                >
                  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M6 3L11 8L6 13"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </div>
              {aiBlock !== null && (
                <div className="detail__reading-summary">{aiBlock}</div>
              )}
            </section>
          );
        }

        return aiBlock !== null ? (
          <div className="detail__ai-summary" aria-label="AI overview">
            {aiBlock}
          </div>
        ) : null;
      })()}

      {/* Single accordion combining Path, Commit, and Module info */}
      <CollapseSection title="File info">
        <dl className="detail__facts">
          <div>
            <dt>Path</dt>
            <dd>
              <code className="detail__fact-value">{path}</code>
            </dd>
          </div>
          <div>
            <dt>Commit</dt>
            <dd>
              <code className="detail__fact-value" title={sha}>
                {sha.slice(0, 7)}
              </code>
            </dd>
          </div>
          {detail !== null && (
            <div>
              <dt>Module</dt>
              <dd>
                <code className="detail__fact-value">{detail.module}</code>
              </dd>
            </div>
          )}
        </dl>
      </CollapseSection>

      {analysisId !== undefined && (
        <AiSummarySection
          analysisId={analysisId}
          path={path}
          onSelectFile={onSelectFile}
        />
      )}

      {failure !== null ? (
        <ErrorBanner error={failure.error} onRetry={onRetry} />
      ) : detail === null ? (
        <p role="status" className="detail__muted">
          Loading file details…
        </p>
      ) : (
        <DetailBody detail={detail} onSelectFile={onSelectFile} />
      )}
    </aside>
  );
}

function DetailBody({
  detail,
  onSelectFile,
}: {
  detail: FileDetail;
  onSelectFile: (path: string) => void;
}) {
  if (!detail.parsed) {
    return (
      <p className="detail__warning" role="note">
        This file could not be parsed, probably because of a syntax error, so
        its imports and symbols are unavailable. It has no edges on the map.
      </p>
    );
  }

  const internal = detail.imports.filter(
    (imp): imp is ImportInfo & {targetPath: string} =>
      imp.kind === 'internal' && imp.targetPath !== null,
  );
  const external = [
    ...new Set(
      detail.imports
        .filter(imp => imp.kind === 'external')
        .map(imp => imp.targetPackage ?? imp.rawName),
    ),
  ].sort();
  const unresolved = detail.imports.filter(imp => imp.kind === 'unresolved');
  const isolated =
    detail.imports.length === 0 && detail.importedBy.length === 0;

  return (
    <>
      {isolated && (
        <p className="detail__muted">
          This file imports nothing and no other analyzed file imports it.
        </p>
      )}

      <CollapseSection title="Symbols" count={detail.symbols.length}>
        {detail.symbols.length === 0 ? (
          <p className="detail__muted">No functions, classes or variables.</p>
        ) : (
          <ul className="detail__list">
            {detail.symbols.map(symbol => (
              <li key={`${symbol.name}:${symbol.line}`}>
                <span className={`detail__kind detail__kind--${symbol.kind}`}>
                  {KIND_LABELS[symbol.kind]}
                </span>
                <a
                  href={`${detail.sourceUrl}#L${symbol.line}`}
                  target="_blank"
                  rel="noreferrer"
                  title={`Open line ${symbol.line} on GitHub`}
                >
                  <code>{symbol.name}</code>
                </a>
                <span className="detail__muted"> line {symbol.line}</span>
              </li>
            ))}
          </ul>
        )}
      </CollapseSection>

      <CollapseSection title="Imports" count={internal.length}>
        <FileLinks
          paths={internal.map(imp => imp.targetPath)}
          empty="No files from this repository."
          onSelectFile={onSelectFile}
        />
      </CollapseSection>

      <CollapseSection title="Imported by" count={detail.importedBy.length}>
        <FileLinks
          paths={detail.importedBy}
          empty="No other analyzed file imports this one."
          onSelectFile={onSelectFile}
        />
      </CollapseSection>

      <CollapseSection title="External libraries" count={external.length}>
        {external.length === 0 ? (
          <p className="detail__muted">None.</p>
        ) : (
          <ul className="detail__tags">
            {external.map(name => (
              <li key={name}>
                <code>{name}</code>
              </li>
            ))}
          </ul>
        )}
      </CollapseSection>

      {unresolved.length > 0 && (
        <CollapseSection title="Unresolved imports" count={unresolved.length}>
          <p className="detail__muted">
            Not matched to a file in this repository or a known library, for
            example a dynamic import.
          </p>
          <ul className="detail__tags">
            {unresolved.map(imp => (
              <li key={imp.rawName}>
                <code>{imp.rawName}</code>
              </li>
            ))}
          </ul>
        </CollapseSection>
      )}
    </>
  );
}

/** Ant Design-style animated collapse panel that starts closed by default. */
function CollapseSection({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <section
      className={`detail__section${open ? ' detail__section--open' : ''}`}
    >
      <div
        className="detail__collapse-header"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setOpen(current => !current)}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setOpen(current => !current);
          }
        }}
      >
        <div className="detail__collapse-title">
          <svg
            className="detail__collapse-arrow"
            viewBox="0 0 12 12"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M4 2.25L8 6L4 9.75"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <h3>
            {title}
            {count !== undefined && (
              <>
                {' '}
                <span className="detail__count">{count}</span>
              </>
            )}
          </h3>
        </div>
      </div>

      <div className="detail__collapse-motion">
        <div className="detail__collapse-inner">
          <div className="detail__collapse-body">{children}</div>
        </div>
      </div>
    </section>
  );
}

function FileLinks({
  paths,
  empty,
  onSelectFile,
}: {
  paths: readonly string[];
  empty: string;
  onSelectFile: (path: string) => void;
}) {
  if (paths.length === 0) {
    return <p className="detail__muted">{empty}</p>;
  }
  return (
    <ul className="detail__list">
      {paths.map(path => (
        <li key={path}>
          <button
            type="button"
            className="detail__file-link"
            onClick={() => onSelectFile(path)}
          >
            <code>{path}</code>
          </button>
        </li>
      ))}
    </ul>
  );
}

function renderInlineCode(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

function AiSummaryContent({text}: {text: string}) {
  const lines = text.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = (keyPrefix: string) => {
    if (listItems.length === 0) return;
    blocks.push(
      <ul key={`${keyPrefix}-ul`} className="detail__ai-list">
        {listItems.map((item, idx) => (
          <li key={idx}>{renderInlineCode(item)}</li>
        ))}
      </ul>,
    );
    listItems = [];
  };

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (line === '') {
      flushList(`line-${index}`);
      return;
    }
    if (line.startsWith('- ') || line.startsWith('* ')) {
      listItems.push(line.slice(2).trim());
      return;
    }
    flushList(`line-${index}`);
    blocks.push(
      <p key={`p-${index}`} className="detail__ai-paragraph">
        {renderInlineCode(line)}
      </p>,
    );
  });
  flushList('end');

  return <div className="detail__ai-body">{blocks}</div>;
}
