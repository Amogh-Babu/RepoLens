import type {KeyboardEvent} from 'react';
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useState,
} from 'react';
import type {Analysis, DependencyGraph, OverviewFile} from '../api/types.ts';
import type {SearchState} from '../state/analysisStore.ts';
import {useAnalysisStore} from '../state/analysisStoreContext.ts';
import {hasSeen, markSeen} from '../utils/seenFlags.ts';
import {subgraph} from '../utils/subgraph.ts';
import {loadViewState, saveViewState} from '../utils/workspaceStorage.ts';
import {ErrorBanner} from './ErrorBanner.tsx';
import type {ReadingOrderInfo} from './FileDetailPanel.tsx';
import {FileDetailPanel} from './FileDetailPanel.tsx';
import {FileExplorer} from './FileExplorer.tsx';
import {ListFallback} from './map/ListFallback.tsx';
import {MapErrorBoundary} from './map/MapErrorBoundary.tsx';
import {OverviewPanel} from './OverviewPanel.tsx';
import {ReadingList} from './ReadingList.tsx';
import {ReanalyzeButton} from './ReanalyzeButton.tsx';
import {SearchBar} from './SearchBar.tsx';
import type {TourStep} from './WorkspaceTour.tsx';
import {WorkspaceTour} from './WorkspaceTour.tsx';
import './Workspace.css';

// React Flow and dagre are most of the bundle, so the map loads on demand.
const DependencyMap = lazy(() =>
  import('./map/DependencyMap.tsx').then(module => ({
    default: module.DependencyMap,
  })),
);

type SidebarTab = 'overview' | 'reading' | 'files';

/**
 * Full-width search bar, collapsible left sidebar (overview, reading list,
 * file explorer), full-screen-capable dependency map, and collapsible right
 * file detail sidebar.
 */
export function Workspace({
  analysis,
  helpTourOpen = false,
  onCloseHelpTour,
}: {
  analysis: Analysis;
  helpTourOpen?: boolean;
  onCloseHelpTour?: () => void;
}) {
  const graph = useAnalysisStore(state => state.graph);
  const graphFailure = useAnalysisStore(state => state.graphFailure);
  const loadGraph = useAnalysisStore(state => state.loadGraph);
  const selectedPath = useAnalysisStore(state => state.selectedPath);
  const selectionRevision = useAnalysisStore(state => state.selectionRevision);
  const selectFile = useAnalysisStore(state => state.selectFile);
  const detail = useAnalysisStore(state =>
    state.selectedPath === null
      ? null
      : (state.fileDetails[state.selectedPath] ?? null),
  );
  const fileFailure = useAnalysisStore(state => state.fileFailure);
  const aiSummary = useAnalysisStore(state =>
    state.selectedPath === null
      ? null
      : (state.fileSummaries[state.selectedPath] ?? null),
  );
  const aiSummaryLoading = useAnalysisStore(state =>
    state.selectedPath === null
      ? false
      : Boolean(state.fileSummaryLoading[state.selectedPath]),
  );
  const aiSummaryFailure = useAnalysisStore(state =>
    state.selectedPath === null
      ? null
      : (state.fileSummaryFailures[state.selectedPath] ?? null),
  );
  const retryFileSummary = useAnalysisStore(state => state.retryFileSummary);
  const search = useAnalysisStore(state => state.search);
  const runSearch = useAnalysisStore(state => state.runSearch);
  const clearSearch = useAnalysisStore(state => state.clearSearch);
  const expired = useAnalysisStore(state => state.expired);
  const [savedView] = useState(() => loadViewState(analysis.repoUrl));
  const [tab, setTab] = useState<SidebarTab>(savedView?.tab ?? 'overview');
  const [scopePaths, setScopePaths] = useState<ReadonlySet<string> | null>(
    () => (savedView?.scopePaths ? new Set(savedView.scopePaths) : null),
  );
  const [tourSteps, setTourSteps] = useState<readonly OverviewFile[] | null>(
    null,
  );
  const [inTour, setInTour] = useState(false);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const changeTab = useCallback(
    (nextTab: SidebarTab) => {
      setTab(nextTab);
      saveViewState(analysis.repoUrl, {tab: nextTab});
    },
    [analysis.repoUrl],
  );
  const changeScopePaths = useCallback(
    (nextScope: ReadonlySet<string> | null) => {
      setScopePaths(nextScope);
      saveViewState(analysis.repoUrl, {
        scopePaths: nextScope === null ? null : [...nextScope],
      });
    },
    [analysis.repoUrl],
  );
  const selectWorkspaceFile = useCallback(
    (path: string | null) => {
      setInTour(false);
      if (path !== null) {
        setRightCollapsed(false);
      }
      if (path !== null && scopePaths !== null && !scopePaths.has(path)) {
        changeScopePaths(null);
      }
      selectFile(path);
    },
    [scopePaths, changeScopePaths, selectFile],
  );
  const selectTourFile = useCallback(
    (path: string) => {
      selectWorkspaceFile(path);
      setInTour(true);
    },
    [selectWorkspaceFile],
  );
  // The tour opens by itself the first time a viewer reaches a workspace.
  const [firstRunTouring, setFirstRunTouring] = useState(
    () => !hasSeen('workspace-tour'),
  );
  const touring = firstRunTouring || helpTourOpen;

  const endTour = useCallback(() => {
    markSeen('workspace-tour');
    setFirstRunTouring(false);
    onCloseHelpTour?.();
  }, [onCloseHelpTour]);

  const matchedPaths = useMemo(
    () =>
      search === null || search.query === ''
        ? null
        : new Set(search.matchedPaths ?? search.results.map(r => r.path)),
    [search],
  );
  const readingOrder = inTour
    ? readingOrderFor(search, tourSteps, selectedPath, selectTourFile)
    : null;

  const expiredBanner = expired && <ExpiredBanner analysis={analysis} />;

  if (graphFailure !== null) {
    return <ErrorBanner error={graphFailure.error} onRetry={loadGraph} />;
  }
  if (graph === null) {
    return (
      expiredBanner || (
        <p role="status" className="analysis__status-box">
          Loading the files…
        </p>
      )
    );
  }

  const gridClass = [
    'workspace',
    leftCollapsed ? 'workspace--left-collapsed' : '',
    rightCollapsed ? 'workspace--right-collapsed' : '',
  ]
    .filter(Boolean)
    .join(' ');

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
              changeScopePaths(null);
              selectFile(null);
              setLeftCollapsed(false);
              changeTab('reading');
              runSearch(query);
            }}
            onClear={() => {
              changeScopePaths(null);
              changeTab('files');
              clearSearch();
            }}
          />
        </div>
      </div>

      <div className={gridClass}>
        <Sidebar
          analysisId={analysis.analysisId}
          selectedPath={selectedPath}
          tab={search === null && tab === 'reading' ? 'overview' : tab}
          onTabChange={changeTab}
          readingAvailable={search !== null}
          readingCount={search?.query === '' ? null : (search?.total ?? null)}
          onSelectFile={selectWorkspaceFile}
          onStartTour={() => setInTour(true)}
          onSelectArea={files => {
            changeScopePaths(new Set(files));
            const firstPath = files[0];
            if (firstPath !== undefined) selectWorkspaceFile(firstPath);
          }}
          onTourLoaded={setTourSteps}
          collapsed={leftCollapsed}
          onToggleCollapse={() => setLeftCollapsed(current => !current)}
        />

        <MapPanel
          repoUrl={analysis.repoUrl}
          graph={graph}
          selectedPath={selectedPath}
          selectionRevision={selectionRevision}
          matchedPaths={matchedPaths}
          scopePaths={scopePaths}
          onClearScope={() => changeScopePaths(null)}
        />

        <div
          className={`workspace__detail${rightCollapsed ? ' workspace__detail--collapsed' : ''}`}
          data-tour="detail"
        >
          {rightCollapsed ? (
            <button
              type="button"
              className="workspace__rail-btn"
              onClick={() => setRightCollapsed(false)}
              aria-label="Show right sidebar"
              title="Show file details sidebar"
            >
              &laquo; Details
            </button>
          ) : (
            <>
              <div className="workspace__detail-bar">
                <span className="workspace__detail-title">File details</span>
                <button
                  type="button"
                  className="workspace__collapse-toggle"
                  onClick={() => setRightCollapsed(true)}
                  aria-label="Hide right sidebar"
                  title="Hide file details sidebar"
                >
                  Hide &raquo;
                </button>
              </div>
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
                  aiSummary={aiSummary}
                  aiSummaryLoading={aiSummaryLoading}
                  aiSummaryFailure={aiSummaryFailure}
                  onRetryAiSummary={() => retryFileSummary(selectedPath)}
                  onSelectFile={selectWorkspaceFile}
                  onRetry={() => selectWorkspaceFile(selectedPath)}
                  onClose={() => selectWorkspaceFile(null)}
                  readingOrder={readingOrder}
                />
              )}
            </>
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
      <p>
        Type the feature you want to understand, like “checkout”, or a function
        or class name. RepoLens lists the files involved, in the order to read
        them.
      </p>
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
          <strong>Files</strong> lists every analyzed file by folder.{' '}
          <strong>Overview</strong> highlights entry points, core files, and a
          guided reading tour.
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
          Each box is a folder. Click one to zoom in and see its files. Arrows
          point from a file to the files it imports. <strong>Key</strong> in the
          toolbar explains the colors, and <strong>Full screen</strong> expands
          the map.
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
        a reading list, the <strong>next arrow</strong> takes you to the next
        file.
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

/** The selected file's place in the reading list or reading tour, if it is in one. */
function readingOrderFor(
  search: SearchState | null,
  tourSteps: readonly OverviewFile[] | null,
  selectedPath: string | null,
  selectFile: (path: string) => void,
): ReadingOrderInfo | null {
  if (selectedPath === null) return null;
  if (search !== null) {
    const index = search.results.findIndex(r => r.path === selectedPath);
    const entry = search.results[index];
    if (entry === undefined) return null;
    const next = search.results[index + 1];
    const prev = index > 0 ? search.results[index - 1] : undefined;
    return {
      query: search.query,
      position: entry.position,
      total: search.total,
      reason: entry.reason,
      orderReason: entry.orderReason,
      onPrev: prev === undefined ? null : () => selectFile(prev.path),
      onNext: next === undefined ? null : () => selectFile(next.path),
    };
  }
  if (tourSteps !== null && tourSteps.length > 0) {
    const index = tourSteps.findIndex(step => step.path === selectedPath);
    const step = tourSteps[index];
    if (step === undefined) return null;
    const next = tourSteps[index + 1];
    const prev = tourSteps[index - 1];
    return {
      query: 'reading tour',
      position: index + 1,
      total: tourSteps.length,
      reason: '',
      orderReason: step.reason,
      onPrev: prev === undefined ? null : () => selectFile(prev.path),
      onNext: next === undefined ? null : () => selectFile(next.path),
    };
  }
  return null;
}

/** Reading list and file explorer, as tabs, with a collapse toggle. */
function Sidebar({
  analysisId,
  selectedPath,
  tab,
  onTabChange,
  readingAvailable,
  readingCount,
  onSelectFile,
  onStartTour,
  onSelectArea,
  onTourLoaded,
  collapsed,
  onToggleCollapse,
}: {
  analysisId: string;
  selectedPath: string | null;
  tab: SidebarTab;
  onTabChange: (tab: SidebarTab) => void;
  readingAvailable: boolean;
  readingCount: number | null;
  onSelectFile: (path: string) => void;
  onStartTour: () => void;
  onSelectArea: (paths: string[]) => void;
  onTourLoaded: (tour: OverviewFile[]) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const id = useId();
  const tabs: Array<{key: SidebarTab; label: string}> = [
    {key: 'overview', label: 'Overview'},
  ];
  if (readingAvailable) {
    tabs.push({
      key: 'reading',
      label:
        readingCount === null
          ? 'Reading list'
          : `Reading list (${readingCount})`,
    });
  }
  tabs.push({key: 'files', label: 'Files'});

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

  if (collapsed) {
    return (
      <div
        className="workspace__sidebar workspace__sidebar--collapsed"
        data-tour="sidebar"
      >
        <button
          type="button"
          className="workspace__rail-btn"
          onClick={onToggleCollapse}
          aria-label="Show left sidebar"
          title="Show overview and files sidebar"
        >
          Sidebar &raquo;
        </button>
      </div>
    );
  }

  return (
    <div className="workspace__sidebar" data-tour="sidebar">
      <div className="workspace__sidebar-header">
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
        <button
          type="button"
          className="workspace__collapse-toggle"
          onClick={onToggleCollapse}
          aria-label="Hide left sidebar"
          title="Hide sidebar"
        >
          &laquo; Hide
        </button>
      </div>
      <div
        id={`${id}-panel`}
        className="workspace__panel"
        role="tabpanel"
        aria-labelledby={`${id}-tab-${tab}`}
      >
        {tab === 'overview' ? (
          <OverviewPanel
            analysisId={analysisId}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
            onStartTour={onStartTour}
            onSelectArea={onSelectArea}
            onTourLoaded={onTourLoaded}
          />
        ) : tab === 'reading' ? (
          <ReadingPanel onSelectFile={onSelectFile} onStartTour={onStartTour} />
        ) : (
          <ExplorerPanel onSelectFile={onSelectFile} />
        )}
      </div>
    </div>
  );
}

function ReadingPanel({
  onSelectFile,
  onStartTour,
}: {
  onSelectFile: (path: string) => void;
  onStartTour: () => void;
}) {
  const search = useAnalysisStore(state => state.search);
  const selectedPath = useAnalysisStore(state => state.selectedPath);
  const runSearch = useAnalysisStore(state => state.runSearch);
  const loadMoreResults = useAnalysisStore(state => state.loadMoreResults);
  const expired = useAnalysisStore(state => state.expired);
  if (search === null) return null;

  return (
    <ReadingList
      search={search}
      selectedPath={selectedPath}
      onSelectFile={onSelectFile}
      onStartTour={onStartTour}
      onLoadMore={loadMoreResults}
      onRefine={intent => runSearch(search.query, intent)}
      refinementDisabled={expired}
      onRetry={() => {
        if (search.failure?.request === 'search') {
          runSearch(search.failure.query, search.failure.intent);
        } else {
          loadMoreResults();
        }
      }}
    />
  );
}

function ExplorerPanel({onSelectFile}: {onSelectFile: (path: string) => void}) {
  const graph = useAnalysisStore(state => state.graph);
  const selectedPath = useAnalysisStore(state => state.selectedPath);
  const expandedDirs = useAnalysisStore(state => state.expandedDirs);
  const toggleDir = useAnalysisStore(state => state.toggleDir);
  if (graph === null) return null;

  return (
    <nav aria-label="File explorer">
      <FileExplorer
        files={graph.files}
        selectedPath={selectedPath}
        expandedDirs={expandedDirs}
        onSelectFile={onSelectFile}
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
  repoUrl,
  graph,
  selectedPath,
  selectionRevision,
  matchedPaths,
  scopePaths,
  onClearScope,
}: {
  repoUrl: string;
  graph: DependencyGraph;
  selectedPath: string | null;
  selectionRevision: number;
  matchedPaths: ReadonlySet<string> | null;
  scopePaths: ReadonlySet<string> | null;
  onClearScope: () => void;
}) {
  const expandedModules = useAnalysisStore(state => state.expandedModules);
  const selectFile = useAnalysisStore(state => state.selectFile);
  const toggleModule = useAnalysisStore(state => state.toggleModule);
  const collapseAllModules = useAnalysisStore(
    state => state.collapseAllModules,
  );
  // 'list' when chosen by the user; a message when the map failed.
  const [view, setView] = useState<'map' | 'list'>('map');
  const [fullScreen, setFullScreen] = useState(false);
  // During a search the map shows only the matches unless the user asks
  // for everything (user test feedback, #92).
  const [matchesOnly, setMatchesOnly] = useState(true);
  // A selection greys out unrelated files; this hides them instead.
  const [hideUnrelated, setHideUnrelated] = useState(false);
  // Each new search starts with matches only, even if the user turned it off
  // for an earlier search.
  const [hadMatches, setHadMatches] = useState(matchedPaths !== null);
  if (hadMatches !== (matchedPaths !== null)) {
    setHadMatches(matchedPaths !== null);
    if (matchedPaths !== null) {
      setMatchesOnly(true);
      setHideUnrelated(true);
    }
  }

  useEffect(() => {
    if (!fullScreen) return;
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') {
        setFullScreen(false);
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [fullScreen]);

  const changeMatchesOnly = useCallback(
    (next: boolean) => {
      setMatchesOnly(next);
      saveViewState(repoUrl, {matchesOnly: next});
    },
    [repoUrl],
  );
  const changeHideUnrelated = useCallback(
    (next: boolean) => {
      setHideUnrelated(next);
      saveViewState(repoUrl, {hideUnrelated: next});
    },
    [repoUrl],
  );
  const [fallbackMessage, setFallbackMessage] = useState<string | null>(null);
  const onTooSlow = useCallback(() => setFallbackMessage(TOO_SLOW_MESSAGE), []);
  const onMapError = useCallback(() => setFallbackMessage(FAILED_MESSAGE), []);
  const showList = view === 'list' || fallbackMessage !== null;
  const visibleGraph = useMemo(
    () => (scopePaths === null ? graph : subgraph(graph, scopePaths)),
    [graph, scopePaths],
  );
  const listGraph = useMemo(
    () =>
      !matchesOnly || matchedPaths === null
        ? visibleGraph
        : subgraph(visibleGraph, matchedPaths),
    [visibleGraph, matchesOnly, matchedPaths],
  );

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
      <button
        type="button"
        className="button workspace__fullscreen-btn"
        aria-label={fullScreen ? 'Exit full screen' : 'Full screen'}
        title={fullScreen ? 'Exit full screen' : 'Full screen'}
        aria-pressed={fullScreen}
        onClick={() => setFullScreen(current => !current)}
      >
        {fullScreen ? (
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d="M6 2V6H2M10 2V6H14M6 14V10H2M10 14V10H14"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d="M2 6V2H6M14 6V2H10M2 10V14H6M14 10V14H10"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>
      {showList && matchedPaths !== null && (
        <label className="workspace__list-filter">
          <input
            type="checkbox"
            checked={matchesOnly}
            onChange={event => changeMatchesOnly(event.target.checked)}
          />
          Only show matches
        </label>
      )}
      {scopePaths !== null && (
        <button type="button" className="button" onClick={onClearScope}>
          All files
        </button>
      )}
    </div>
  );

  return (
    <section
      className={`workspace__map${fullScreen ? ' workspace__map--fullscreen' : ''}`}
      aria-label="Dependency map"
      data-tour="map"
    >
      {showList ? (
        <ListFallback
          graph={listGraph}
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
              graph={visibleGraph}
              expandedModules={expandedModules}
              selectedPath={selectedPath}
              selectionRevision={selectionRevision}
              matchedPaths={matchedPaths}
              matchesOnly={matchesOnly}
              onMatchesOnlyChange={changeMatchesOnly}
              hideUnrelated={hideUnrelated}
              onHideUnrelatedChange={changeHideUnrelated}
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
