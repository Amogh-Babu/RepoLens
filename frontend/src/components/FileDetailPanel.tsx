import type {ReactNode} from 'react';
import {useId} from 'react';
import {encodeFilePath} from '../api/client.ts';
import type {FileDetail, ImportInfo, SymbolKind} from '../api/types.ts';
import type {RequestFailure} from '../state/analysisStore.ts';
import {ErrorBanner} from './ErrorBanner.tsx';
import './FileDetailPanel.css';

interface FileDetailPanelProps {
  path: string;
  /** Repository URL and commit, to link the source before details load. */
  repoUrl: string;
  sha: string;
  /** Null while loading or after a failure. */
  detail: FileDetail | null;
  failure: RequestFailure | null;
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
  /** Selects the next file in the reading order; null at the end. */
  onNext: (() => void) | null;
}

const KIND_LABELS: Record<SymbolKind, string> = {
  function: 'fn',
  class: 'class',
  variable: 'var',
};

/**
 * Path, module, symbols, imports and importers of the selected file, with a
 * link to its source on GitHub at the analyzed commit (Use Case 3).
 */
export function FileDetailPanel({
  path,
  repoUrl,
  sha,
  detail,
  failure,
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
        <h2 id={headingId}>{name}</h2>
        <button
          type="button"
          className="button button--quiet detail__close"
          onClick={onClose}
          aria-label="Close file details"
        >
          ✕
        </button>
      </div>

      {readingOrder !== null && (
        <section className="detail__reading" aria-label="Reading order">
          <p className="detail__reading-position">
            #{readingOrder.position} of {readingOrder.total} for “
            {readingOrder.query}”
          </p>
          <p className="detail__muted">{readingOrder.reason}</p>
          <button
            type="button"
            className="button"
            onClick={readingOrder.onNext ?? undefined}
            disabled={readingOrder.onNext === null}
          >
            Next in reading order →
          </button>
        </section>
      )}

      {/* Always shown, so the file can be found even if the link breaks. */}
      <dl className="detail__facts">
        <div>
          <dt>Path</dt>
          <dd>
            <code>{path}</code>
          </dd>
        </div>
        <div>
          <dt>Commit</dt>
          <dd>
            <code title={sha}>{sha.slice(0, 7)}</code>
          </dd>
        </div>
        {detail !== null && (
          <div>
            <dt>Module</dt>
            <dd>
              <code>{detail.module}</code>
            </dd>
          </div>
        )}
      </dl>

      <a
        className="button button--primary detail__source"
        href={sourceUrl}
        target="_blank"
        rel="noreferrer"
      >
        Open source on GitHub
        <span className="visually-hidden"> (opens in a new tab)</span>
      </a>

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

      <Section title="Symbols" count={detail.symbols.length}>
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
      </Section>

      <Section title="Imports" count={internal.length}>
        <FileLinks
          paths={internal.map(imp => imp.targetPath)}
          empty="No files from this repository."
          onSelectFile={onSelectFile}
        />
      </Section>

      <Section title="Imported by" count={detail.importedBy.length}>
        <FileLinks
          paths={detail.importedBy}
          empty="No other analyzed file imports this one."
          onSelectFile={onSelectFile}
        />
      </Section>

      <Section title="External libraries" count={external.length}>
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
      </Section>

      {unresolved.length > 0 && (
        <Section title="Unresolved imports" count={unresolved.length}>
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
        </Section>
      )}
    </>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section className="detail__section">
      <h3>
        {title} <span className="detail__count">{count}</span>
      </h3>
      {children}
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
