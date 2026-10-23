import type {MatchKind, RankedFile} from '../api/types.ts';
import type {SearchState} from '../state/analysisStore.ts';
import {ErrorBanner} from './ErrorBanner.tsx';
import './ReadingList.css';

interface ReadingListProps {
  search: SearchState;
  selectedPath: string | null;
  /** Builds the GitHub link for a file at the analyzed commit. */
  sourceUrlFor: (path: string) => string;
  onSelectFile: (path: string) => void;
  onLoadMore: () => void;
  onRetry: () => void;
}

const MATCH_LABELS: Record<MatchKind, string> = {
  filename: 'file name',
  symbol: 'symbol',
  import: 'import',
  comment: 'comment',
};

/**
 * The ranked reading list for a search (Use Cases 2 and 4): position, path,
 * a one-line reason and a source link per file, 20 at a time.
 */
export function ReadingList({
  search,
  selectedPath,
  sourceUrlFor,
  onSelectFile,
  onLoadMore,
  onRetry,
}: ReadingListProps) {
  const {query, results, total, pendingQuery, loadingMore, failure} = search;
  const hasResults = query !== '';

  return (
    <div className="reading-list">
      {/* Announces progress and the result count to screen readers. */}
      <p
        role="status"
        className={
          pendingQuery !== null ? 'reading-list__status' : 'visually-hidden'
        }
      >
        {pendingQuery !== null
          ? `Searching for “${pendingQuery}”…`
          : hasResults
            ? `${total} ${total === 1 ? 'file matches' : 'files match'} “${query}”.`
            : ''}
      </p>
      {failure?.request === 'search' && (
        <ErrorBanner error={failure.error} onRetry={onRetry} />
      )}

      {hasResults && total === 0 && <NoResults query={query} />}

      {hasResults && total > 0 && (
        <>
          <div className="reading-list__header">
            <h2>Reading order for “{query}”</h2>
            <p className="reading-list__meta">
              Showing {results.length} of {total}. A suggested order to read,
              not the order the code runs in.
            </p>
          </div>
          <ol className="reading-list__entries">
            {results.map(entry => (
              <ReadingListEntry
                key={entry.path}
                entry={entry}
                selected={entry.path === selectedPath}
                sourceUrl={sourceUrlFor(entry.path)}
                onSelect={() => onSelectFile(entry.path)}
              />
            ))}
          </ol>
          {failure?.request === 'more' && (
            <ErrorBanner error={failure.error} onRetry={onRetry} />
          )}
          {results.length < total && failure?.request !== 'more' && (
            <button
              type="button"
              className="button reading-list__more"
              onClick={onLoadMore}
              disabled={loadingMore}
            >
              {loadingMore
                ? 'Loading…'
                : `Show more (${total - results.length} left)`}
            </button>
          )}
        </>
      )}
    </div>
  );
}

function ReadingListEntry({
  entry,
  selected,
  sourceUrl,
  onSelect,
}: {
  entry: RankedFile;
  selected: boolean;
  sourceUrl: string;
  onSelect: () => void;
}) {
  return (
    <li
      className={`reading-list__entry${selected ? ' reading-list__entry--selected' : ''}`}
    >
      <button
        type="button"
        className="reading-list__select"
        onClick={onSelect}
        aria-current={selected ? 'true' : undefined}
        aria-label={`${entry.position}. ${entry.path}`}
      >
        <span className="reading-list__position">{entry.position}</span>
        <code>{entry.path}</code>
      </button>
      <p className="reading-list__reason">{entry.reason}</p>
      <div className="reading-list__links">
        {entry.matches.length > 0 && (
          <details>
            <summary>
              {entry.matches.length}{' '}
              {entry.matches.length === 1 ? 'match' : 'matches'}
            </summary>
            <ul className="reading-list__matches">
              {entry.matches.map((match, index) => (
                <li key={`${match.kind}:${match.text}:${index}`}>
                  <span className="reading-list__match-kind">
                    {MATCH_LABELS[match.kind]}
                  </span>{' '}
                  {match.line === null ? (
                    <code>{match.text}</code>
                  ) : (
                    <a
                      href={`${sourceUrl}#L${match.line}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <code>{match.text}</code>
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
        <a href={sourceUrl} target="_blank" rel="noreferrer">
          Source<span className="visually-hidden"> of {entry.path}</span>
        </a>
      </div>
    </li>
  );
}

function NoResults({query}: {query: string}) {
  return (
    <div className="reading-list__empty">
      <p>No files match “{query}”.</p>
      <ul>
        <li>Try a single word, or a function or class name.</li>
        <li>Check the spelling.</li>
        <li>Generated and vendored files are not searched.</li>
      </ul>
    </div>
  );
}
