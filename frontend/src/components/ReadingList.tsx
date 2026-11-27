import type {RankedFile, SearchIntent, SemanticStatus} from '../api/types.ts';
import type {SearchState} from '../state/analysisStore.ts';
import {ErrorBanner} from './ErrorBanner.tsx';
import {SearchAiOverview} from './SearchAiOverview.tsx';
import './ReadingList.css';

interface ReadingListProps {
  analysisId: string;
  search: SearchState;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  onStartTour?: () => void;
  onLoadMore: () => void;
  onRefine: (intent?: SearchIntent) => void;
  refinementDisabled?: boolean;
  onRetry: () => void;
}

/**
 * The ranked reading list for a search (Use Cases 2 and 4): position, path,
 * just the position and path per file, 20 at a time.
 */
export function ReadingList({
  analysisId,
  search,
  selectedPath,
  onSelectFile,
  onStartTour,
  onLoadMore,
  onRefine,
  refinementDisabled = false,
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

      {hasResults && (
        <label className="reading-list__refine">
          What would you like to understand?
          <select
            value={search.intent ?? ''}
            disabled={refinementDisabled || pendingQuery !== null}
            onChange={event =>
              onRefine(
                (event.target.value || undefined) as SearchIntent | undefined,
              )
            }
          >
            <option value="">The topic overall</option>
            <option value="implementation">How it works</option>
            <option value="configuration">Configuration and deployment</option>
            <option value="tests">Tests and examples</option>
          </select>
        </label>
      )}

      {hasResults && total === 0 && <NoResults query={query} />}

      {hasResults && total > 0 && (
        <>
          <SearchAiOverview
            analysisId={analysisId}
            query={query}
            intent={search.intent}
            onSelectFile={onSelectFile}
          />
          {results[0] !== undefined && (
            <button
              type="button"
              className="reading-list__start"
              onClick={() => {
                onSelectFile((results[0] as RankedFile).path);
                onStartTour?.();
              }}
            >
              <span>Start reading tour</span>
              <span aria-hidden="true">→</span>
            </button>
          )}
          <div className="reading-list__header">
            <h2>Reading order for “{query}”</h2>
            <p className="reading-list__meta">
              Showing {results.length} of {total}.
            </p>
          </div>
          <KeywordOnlyNote status={search.semanticStatus} />
          <p className="reading-list__meta">
            Suggestions are based on matches and imports; verify them for your
            task.
          </p>
          {(
            [
              ['Read first', 'prerequisite'],
              ['Edit here', 'edit'],
              ['Other matches', null],
              ['Tests to run', 'test'],
            ] as const
          ).map(([title, role]) => {
            const entries = results.filter(entry => entry.role === role);
            const extraTests =
              role === 'test'
                ? (search.testRecommendations ?? []).filter(
                    path => !results.some(entry => entry.path === path),
                  )
                : [];
            if (entries.length === 0 && extraTests.length === 0) return null;
            return (
              <section key={title} aria-label={title}>
                <h3 className="reading-list__group-title">{title}</h3>
                <ol className="reading-list__entries">
                  {entries.map(entry => (
                    <ReadingListEntry
                      key={entry.path}
                      entry={entry}
                      selected={entry.path === selectedPath}
                      onSelect={() => {
                        onSelectFile(entry.path);
                        onStartTour?.();
                      }}
                    />
                  ))}
                  {extraTests.map(path => (
                    <li
                      key={path}
                      className={`reading-list__entry${path === selectedPath ? ' reading-list__entry--selected' : ''}`}
                    >
                      <button
                        type="button"
                        className="reading-list__select"
                        aria-current={
                          path === selectedPath ? 'true' : undefined
                        }
                        onClick={() => onSelectFile(path)}
                      >
                        <code>{path}</code>
                      </button>
                    </li>
                  ))}
                </ol>
              </section>
            );
          })}
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
  onSelect,
}: {
  entry: RankedFile;
  selected: boolean;
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

const KEYWORD_ONLY_REASONS: Partial<Record<SemanticStatus, string>> = {
  over_budget:
    'This repository is larger than the server indexes for search by meaning, so results match keywords only.',
  disabled:
    'Search by meaning is turned off on this server, so results match keywords only.',
  failed:
    'Search by meaning was unavailable for this analysis, so results match keywords only.',
};

/** Says when results could not use search by meaning, and why. */
function KeywordOnlyNote({status}: {status?: SemanticStatus | null}) {
  const reason = status == null ? undefined : KEYWORD_ONLY_REASONS[status];
  if (reason === undefined) return null;
  return <p className="reading-list__keyword-only">{reason}</p>;
}
