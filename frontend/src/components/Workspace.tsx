import type {KeyboardEvent} from 'react';
import {lazy, Suspense, useCallback, useId, useMemo, useState} from 'react';
import {encodeFilePath} from '../api/client.ts';
import type {Analysis, DependencyGraph} from '../api/types.ts';
import type {SearchState} from '../state/analysisStore.ts';
import {useAnalysisStore} from '../state/analysisStoreContext.ts';
import {ErrorBanner} from './ErrorBanner.tsx';
import type {ReadingOrderInfo} from './FileDetailPanel.tsx';
import {FileDetailPanel} from './FileDetailPanel.tsx';
import {FileExplorer} from './FileExplorer.tsx';
import {ListFallback} from './map/ListFallback.tsx';
import {MapErrorBoundary} from './map/MapErrorBoundary.tsx';
import {ReadingList} from './ReadingList.tsx';
import {SearchBar} from './SearchBar.tsx';
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
  const [tab, setTab] = useState<SidebarTab>('files');

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

  if (graphFailure !== null) {
    return <ErrorBanner error={graphFailure.error} onRetry={loadGraph} />;
  }
  if (graph === null) {
    return <p role="status">Loading the files…</p>;
  }

  return (
    <div className="workspace-area">
      <SearchBar
        active={search !== null}
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

        <div className="workspace__detail">
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
    <div className="workspace__sidebar">
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
              matchedPaths={matchedPaths}
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
