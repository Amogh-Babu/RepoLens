import type {KeyboardEvent} from 'react';
import {lazy, Suspense, useCallback, useId, useMemo, useState} from 'react';
import {encodeFilePath} from '../api/client.ts';
import type {Analysis, DependencyGraph} from '../api/types.ts';
import type {SearchState} from '../state/analysisStore.ts';
import {useAnalysisStore} from '../state/analysisStoreContext.ts';
import {hasSeen, markSeen} from '../utils/seenFlags.ts';
import {ErrorBanner} from './ErrorBanner.tsx';
import type {ReadingOrderInfo} from './FileDetailPanel.tsx';
import {FileDetailPanel} from './FileDetailPanel.tsx';
import {FileExplorer} from './FileExplorer.tsx';
import {ListFallback} from './map/ListFallback.tsx';
import {MapErrorBoundary} from './map/MapErrorBoundary.tsx';
import {ReadingList} from './ReadingList.tsx';
import {ReanalyzeButton} from './ReanalyzeButton.tsx';
import {SearchBar} from './SearchBar.tsx';
import {SearchHelp} from './SearchHelp.tsx';
import type {TourStep} from './WorkspaceTour.tsx';
import {WorkspaceTour} from './WorkspaceTour.tsx';
import './Workspace.css';

// React Flow and dagre are most of the bundle, so the map loads on demand.
const DependencyMap = lazy(() =>
  import('./map/DependencyMap.tsx').then(module => ({
    default: module.DependencyMap,
  })),
);

type SidebarTab = 'reading' | 'files';

/**
 * Search, reading list, file explorer, dependency map and file details for
 * a finished analysis.
 */
export function Workspace({analysis}: {analysis: Analysis}) {
  const graph = useAnalysisStore(state => state.graph);
  const graphFailure = useAnalysisStore(state => state.graphFailure);
  const loadGraph = useAnalysisStore(state => state.loadGraph);
  const selectedPath = useAnalysisStore(state => state.selectedPath);
  const selectFile = useAnalysisStore(state => state.selectFile);
  const detail = useAnalysisStore(state =>
    state.selectedPath === null
      ? null
      : (state.fileDetails[state.selectedPath] ?? null),
  );
  const fileFailure = useAnalysisStore(state => state.fileFailure);
  const search = useAnalysisStore(state => state.search);
  const runSearch = useAnalysisStore(state => state.runSearch);
  const clearSearch = useAnalysisStore(state => state.clearSearch);
  const expired = useAnalysisStore(state => state.expired);
  const [tab, setTab] = useState<SidebarTab>('files');
  // The tour opens by itself the first time a viewer reaches a workspace.
  const [touring, setTouring] = useState(() => !hasSeen('workspace-tour'));
  const endTour = useCallback(() => {
    markSeen('workspace-tour');
    setTouring(false);
  }, []);

  const sourceUrlFor = useCallback(
    (path: string) =>
      `${analysis.repoUrl}/blob/${analysis.sha}/${encodeFilePath(path)}`,
    [analysis.repoUrl, analysis.sha],
  );
  const matchedPaths = useMemo(
    () =>
      search === null || search.query === ''
        ? null
        : new Set(search.results.map(r => r.path)),
    [search],
  );
  const readingOrder = readingOrderFor(search, selectedPath, selectFile);

  const expiredBanner = expired && <ExpiredBanner analysis={analysis} />;

  if (graphFailure !== null) {
    return <ErrorBanner error={graphFailure.error} onRetry={loadGraph} />;
  }
  if (graph === null) {
    return expiredBanner || <p role="status">Loading the files…</p>;
  }

  return (
    <div className="workspace-area">
      {expiredBanner}
      <div className="workspace__top">
        <div className="workspace__search" data-tour="search">
          <SearchBar
            active={search !== null}
            disabled={expired}
            searching={search?.pendingQuery != null}
            onSearch={query => {
              setTab('reading');
              runSearch(query);
            }}
            onClear={() => {
              setTab('files');
              clearSearch();
            }}
          />
        </div>
        <SearchHelp />
        <button
          type="button"
          className="button"
          onClick={() => setTouring(true)}
          title="Take the tour of this page again"
        >
          Help
        </button>
      </div>

      <div className="workspace">
        <Sidebar
          tab={search === null ? 'files' : tab}
          onTabChange={setTab}
          readingAvailable={search !== null}
          readingCount={search?.query === '' ? null : (search?.total ?? null)}
          sourceUrlFor={sourceUrlFor}
        />

        <MapPanel
          graph={graph}
          selectedPath={selectedPath}
          matchedPaths={matchedPaths}
        />

        <div className="workspace__detail" data-tour="detail">
          {selectedPath === null ? (
            <p className="workspace__hint">
              Select a file to see its symbols, imports and the files that
              import it.
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
              readingOrder={readingOrder}
            />
          )}
        </div>
      </div>
      {touring && <WorkspaceTour steps={TOUR_STEPS} onClose={endTour} />}
    </div>
  );
}

/** The first-run tour: one stop per area of the workspace. */
const TOUR_STEPS: readonly TourStep[] = [
  {
    target: null,
    title: 'Welcome to RepoLens',
    body: (
      <>
        <p>
          RepoLens has mapped which files in this repository import which. This
          short tour shows where everything is.
        </p>
        <p>You can take it again at any time with the Help button.</p>
      </>
    ),
  },
  {
    target: 'search',
    title: 'Start with a search',
    body: (
      <>
        <p>
          Type the feature you want to understand, like “checkout”, or a
          function or class name. RepoLens lists the files involved, in the
          order to read them.
        </p>
        <p>
          It combines exact matches in names, code and prose with local semantic
          search, so plain-language questions can find related files.{' '}
          <strong>How search works</strong>, next to the search bar, explains
          how results are ranked and ordered.
        </p>
      </>
    ),
  },
  {
    target: 'sidebar',
    title: 'Reading list and files',
    body: (
      <>
        <p>
          After a search, the <strong>Reading list</strong> shows each file with
          why it matches and why it comes at that spot in the order.
        </p>
        <p>
          <strong>Files</strong> lists every analyzed file by folder.
        </p>
      </>
    ),
  },
  {
    target: 'map',
    title: 'The dependency map',
    body: (
      <>
        <p>
          Each box is a folder. Click one to open it and see its files. Arrows
          point from a file to the files it imports.
        </p>
        <p>
          During a search the map shows only the matching files. Untick
          <strong> Only show matches</strong> to see everything again.
        </p>
      </>
    ),
  },
  {
    target: 'detail',
    title: 'File details',
    body: (
      <p>
        Select a file, in the list or on the map, to see what it defines, what
        it imports and what imports it, with links to its source on GitHub. From
        a reading list, <strong>Next in reading order</strong> takes you to the
        next file.
      </p>
    ),
  },
];

/**
 * Shown once the cached analysis has expired (Use Cases 2-4): what is on
 * screen stays for reference, and Re-analyze starts over with the same URL
 * and ref.
 */
function ExpiredBanner({analysis}: {analysis: Analysis}) {
  return (
    <div className="workspace__expired" role="alert">
      <div>
        <p className="workspace__expired-title">This analysis has expired</p>
        <p>
          Results are kept for 24 hours. You can still look at what is on
          screen, but searching and opening new files need a fresh analysis.
        </p>
      </div>
      <ReanalyzeButton analysis={analysis} label="Re-analyze" />
    </div>
  );
}

/** The selected file's place in the reading list, if it is in it. */
function readingOrderFor(
  search: SearchState | null,
  selectedPath: string | null,
  selectFile: (path: string) => void,
): ReadingOrderInfo | null {
  if (search === null || selectedPath === null) return null;
  const index = search.results.findIndex(r => r.path === selectedPath);
  const entry = search.results[index];
  if (entry === undefined) return null;
  const next = search.results[index + 1];
  return {
    query: search.query,
    position: entry.position,
    total: search.total,
    reason: entry.reason,
    orderReason: entry.orderReason,
    onNext: next === undefined ? null : () => selectFile(next.path),
  };
}

/** Reading list and file explorer, as tabs. */
function Sidebar({
  tab,
  onTabChange,
  readingAvailable,
  readingCount,
  sourceUrlFor,
}: {
  tab: SidebarTab;
  onTabChange: (tab: SidebarTab) => void;
  readingAvailable: boolean;
  readingCount: number | null;
  sourceUrlFor: (path: string) => string;
}) {
  const id = useId();
  const tabs: Array<{key: SidebarTab; label: string}> = readingAvailable
    ? [
        {
          key: 'reading',
          label:
            readingCount === null
              ? 'Reading list'
              : `Reading list (${readingCount})`,
        },
        {key: 'files', label: 'Files'},
      ]
    : [{key: 'files', label: 'Files'}];

  // Arrow keys move between tabs, as in the WAI-ARIA tabs pattern.
  function handleKeyDown(event: KeyboardEvent) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    const index = tabs.findIndex(t => t.key === tab);
    const step = event.key === 'ArrowRight' ? 1 : -1;
    const next = tabs[(index + step + tabs.length) % tabs.length];
    if (next !== undefined) {
      onTabChange(next.key);
      document.getElementById(`${id}-tab-${next.key}`)?.focus();
    }
    event.preventDefault();
  }

  return (
    <div className="workspace__sidebar" data-tour="sidebar">
      <div
        className="workspace__tabs"
        role="tablist"
        aria-label="Sidebar"
        onKeyDown={handleKeyDown}
      >
        {tabs.map(t => (
          <button
            key={t.key}
            id={`${id}-tab-${t.key}`}
            type="button"
            role="tab"
            className="workspace__tab"
            aria-selected={tab === t.key}
            aria-controls={`${id}-panel`}
            tabIndex={tab === t.key ? 0 : -1}
            onClick={() => onTabChange(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div
        id={`${id}-panel`}
        className="workspace__panel"
        role="tabpanel"
        aria-labelledby={`${id}-tab-${tab}`}
      >
        {tab === 'reading' ? (
          <ReadingPanel sourceUrlFor={sourceUrlFor} />
        ) : (
          <ExplorerPanel />
        )}
      </div>
    </div>
  );
}

function ReadingPanel({
  sourceUrlFor,
}: {
  sourceUrlFor: (path: string) => string;
}) {
  const search = useAnalysisStore(state => state.search);
  const selectedPath = useAnalysisStore(state => state.selectedPath);
  const selectFile = useAnalysisStore(state => state.selectFile);
  const runSearch = useAnalysisStore(state => state.runSearch);
  const loadMoreResults = useAnalysisStore(state => state.loadMoreResults);
  if (search === null) return null;

  return (
    <ReadingList
      search={search}
      selectedPath={selectedPath}
      sourceUrlFor={sourceUrlFor}
      onSelectFile={selectFile}
      onLoadMore={loadMoreResults}
      onRetry={() => {
        if (search.failure?.request === 'search') {
          runSearch(search.failure.query);
        } else {
          loadMoreResults();
        }
      }}
    />
  );
}

function ExplorerPanel() {
  const graph = useAnalysisStore(state => state.graph);
  const selectedPath = useAnalysisStore(state => state.selectedPath);
  const expandedDirs = useAnalysisStore(state => state.expandedDirs);
  const selectFile = useAnalysisStore(state => state.selectFile);
  const toggleDir = useAnalysisStore(state => state.toggleDir);
  if (graph === null) return null;

  return (
    <nav aria-label="File explorer">
      <FileExplorer
        files={graph.files}
        selectedPath={selectedPath}
        expandedDirs={expandedDirs}
        onSelectFile={selectFile}
        onToggleDir={toggleDir}
      />
    </nav>
  );
}

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
  matchedPaths,
}: {
  graph: DependencyGraph;
  selectedPath: string | null;
  matchedPaths: ReadonlySet<string> | null;
}) {
  const expandedModules = useAnalysisStore(state => state.expandedModules);
  const selectFile = useAnalysisStore(state => state.selectFile);
  const toggleModule = useAnalysisStore(state => state.toggleModule);
  const collapseAllModules = useAnalysisStore(
    state => state.collapseAllModules,
  );
  // 'list' when chosen by the user; a message when the map failed.
  const [view, setView] = useState<'map' | 'list'>('map');
  // During a search the map shows only the matches unless the user asks
  // for everything (user test feedback, #92).
  const [matchesOnly, setMatchesOnly] = useState(true);
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
    <section
      className="workspace__map"
      aria-label="Dependency map"
      data-tour="map"
    >
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
              matchedPaths={matchedPaths}
              matchesOnly={matchesOnly}
              onMatchesOnlyChange={setMatchesOnly}
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
