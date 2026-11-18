import {lazy, Suspense, useCallback, useEffect, useRef, useState} from 'react';
import {Link, useNavigate} from 'react-router';
import {useApiClient} from '../api/apiClientContext.ts';
import type {ErrorDescription} from '../api/describeError.ts';
import {describeError} from '../api/describeError.ts';
import {toApiError} from '../api/errors.ts';
import type {DependencyGraph} from '../api/types.ts';
import {ErrorBanner} from '../components/ErrorBanner.tsx';
import {ListFallback} from '../components/map/ListFallback.tsx';
import {MapErrorBoundary} from '../components/map/MapErrorBoundary.tsx';
import type {RepoInputValue} from '../components/RepoInputForm.tsx';
import {RepoInputForm} from '../components/RepoInputForm.tsx';
import type {TourStep} from '../components/WorkspaceTour.tsx';
import {WorkspaceTour} from '../components/WorkspaceTour.tsx';
import type {RepoTarget} from '../utils/repoInput.ts';
import {hasSeen, markSeen} from '../utils/seenFlags.ts';
import {useDocumentTitle} from '../utils/useDocumentTitle.ts';
import {loadRecentRepos} from '../utils/workspaceStorage.ts';
import './LandingPage.css';

const DependencyMap = lazy(() =>
  import('../components/map/DependencyMap.tsx').then(module => ({
    default: module.DependencyMap,
  })),
);

interface FailedStart {
  error: ErrorDescription;
  code: string;
  target: RepoTarget;
}

/** Simple 5-file dependency graph under a single `app` directory. */
const SAMPLE_GRAPH: DependencyGraph = {
  modules: [
    {
      id: 'app',
      name: 'app',
      filePaths: [
        'app/main.py',
        'app/routes.py',
        'app/auth.py',
        'app/db.py',
        'app/config.py',
      ],
    },
  ],
  files: [
    {path: 'app/main.py', module: 'app', parsed: true, lineCount: 28},
    {path: 'app/routes.py', module: 'app', parsed: true, lineCount: 44},
    {path: 'app/auth.py', module: 'app', parsed: true, lineCount: 52},
    {path: 'app/db.py', module: 'app', parsed: true, lineCount: 36},
    {path: 'app/config.py', module: 'app', parsed: true, lineCount: 19},
  ],
  edges: [
    {source: 'app/main.py', target: 'app/routes.py'},
    {source: 'app/routes.py', target: 'app/auth.py'},
    {source: 'app/routes.py', target: 'app/db.py'},
    {source: 'app/auth.py', target: 'app/db.py'},
    {source: 'app/db.py', target: 'app/config.py'},
  ],
};

const LANDING_TOUR_STEPS: readonly TourStep[] = [
  {
    target: 'repo-url-field',
    title: '1. Submit a repository link',
    body: (
      <p>
        This is where you submit repository links. Only Python codebases work
        right now, but support for more languages is on the way.
      </p>
    ),
  },
  {
    target: 'repo-ref-field',
    title: '2. Specific branch, tag, or commit',
    body: (
      <p>
        This is optional, but if you want to investigate a specific version of
        the code, you can specify the branch, tag, or commit here.
      </p>
    ),
  },
  {
    target: 'repo-analyze-btn',
    title: '3. Submit with Analyze',
    body: (
      <p>
        Click <strong>Analyze</strong> to submit once all your repository
        information is entered.
      </p>
    ),
  },
  {
    target: 'sample-map',
    title: '4. Sample dependency map',
    body: (
      <p>
        This sample map shows what your repository&apos;s interactive dependency
        graph output will look like.
      </p>
    ),
  },
];

/** Landing page: persistent top bar, hero, repo input, recent repos, sample map, how it works, and features. */
export function LandingPage() {
  const api = useApiClient();
  const navigate = useNavigate();
  useDocumentTitle(null);
  const [input, setInput] = useState<RepoInputValue>({url: '', ref: ''});
  const [recentRepos] = useState(() => loadRecentRepos());
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<FailedStart | null>(null);
  const [tourOpen, setTourOpen] = useState(false);
  const [welcomeOpen, setWelcomeOpen] = useState(
    () => !hasSeen('landing-welcome') && recentRepos.length === 0,
  );

  function openHelpTour() {
    markSeen('landing-welcome');
    setWelcomeOpen(false);
    setTourOpen(true);
  }

  function dismissWelcome() {
    markSeen('landing-welcome');
    setWelcomeOpen(false);
  }

  // State for the 5-file single-directory sample DependencyMap window.
  // Pre-selects `app/routes.py` so the selected, imported, and importer colors show immediately.
  const [expandedModules, setExpandedModules] = useState<ReadonlySet<string>>(
    () => new Set(['app']),
  );
  const [selectedPath, setSelectedPath] = useState<string | null>(
    'app/routes.py',
  );
  const [selectionRevision, setSelectionRevision] = useState(0);
  const [hideUnrelated, setHideUnrelated] = useState(false);
  const [sampleView, setSampleView] = useState<'map' | 'list'>('map');
  const [mapFallback, setMapFallback] = useState<string | null>(null);

  const pending = useRef<AbortController | null>(null);
  const sampleMapRef = useRef<HTMLElement | null>(null);

  // Cancel an in-flight request if the user leaves the page.
  useEffect(() => () => pending.current?.abort(), []);

  async function start(target: RepoTarget) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setSubmitting(true);
    setFailure(null);

    try {
      const {analysisId} = await api.startAnalysis(
        target.ref === null
          ? {url: target.url}
          : {url: target.url, ref: target.ref},
        {signal: controller.signal},
      );
      void navigate(`/analysis/${encodeURIComponent(analysisId)}`);
    } catch (error: unknown) {
      const apiError = toApiError(error);
      if (apiError.code !== 'ABORTED') {
        setFailure({
          error: describeError(apiError),
          code: apiError.code,
          target,
        });
      }
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setSubmitting(false);
      }
    }
  }

  function analyzeDefaultBranch(target: RepoTarget) {
    setInput(current => ({...current, ref: ''}));
    void start({...target, ref: null});
  }

  function scrollToSection(id: string) {
    document
      .getElementById(id)
      ?.scrollIntoView?.({behavior: 'smooth', block: 'start'});
  }

  const handleSelectSampleFile = useCallback((path: string) => {
    setSelectedPath(current => (current === path ? null : path));
    setSelectionRevision(rev => rev + 1);
  }, []);

  const handleToggleSampleModule = useCallback(
    (moduleId: string, expanded?: boolean) => {
      setExpandedModules(current => {
        const next = new Set(current);
        const shouldExpand = expanded ?? !next.has(moduleId);
        if (shouldExpand) {
          next.add(moduleId);
        } else {
          next.delete(moduleId);
        }
        return next;
      });
    },
    [],
  );

  const handleCollapseAllSample = useCallback(() => {
    setExpandedModules(new Set());
  }, []);

  const handleMapTooSlow = useCallback(() => {
    setMapFallback(
      'The map could not be drawn quickly enough, so the files are listed instead.',
    );
  }, []);

  const handleMapError = useCallback(() => {
    setMapFallback(
      'The map could not be drawn in this browser, so the files are listed instead.',
    );
  }, []);

  const showSampleList = sampleView === 'list' || mapFallback !== null;

  const sampleViewSwitch = (
    <div
      className="landing__sample-switch"
      role="group"
      aria-label="Sample view"
    >
      <button
        type="button"
        className="button"
        aria-pressed={!showSampleList}
        onClick={() => {
          setMapFallback(null);
          setSampleView('map');
        }}
      >
        Map
      </button>
      <button
        type="button"
        className="button"
        aria-pressed={showSampleList}
        onClick={() => setSampleView('list')}
      >
        List
      </button>
    </div>
  );

  return (
    <main className="page landing" id="main" tabIndex={-1}>
      {/* Persistent Sticky Top Bar */}
      <header className="landing__topbar">
        <div className="landing__topbar-inner">
          <a href="#main" className="landing__logo" aria-label="RepoLens home">
            <span className="landing__logo-mark" aria-hidden="true">
              RL
            </span>
          </a>

          <nav className="landing__topbar-nav" aria-label="Page navigation">
            <button
              type="button"
              className="landing__nav-link"
              onClick={openHelpTour}
            >
              Help
            </button>
            <button
              type="button"
              className="landing__nav-link"
              onClick={() => scrollToSection('sample-map')}
            >
              Sample map
            </button>
            <button
              type="button"
              className="landing__nav-link"
              onClick={() => scrollToSection('how-it-works')}
            >
              How it works
            </button>
            <button
              type="button"
              className="landing__nav-link"
              onClick={() => scrollToSection('features')}
            >
              Features
            </button>
          </nav>
        </div>
      </header>

      <div className="landing__container">
        <section className="landing__intro">
          <h1 className="landing__headline">
            Map your next <span className="landing__word-token">commit</span>{' '}
            like an architect
          </h1>
          <p className="landing__deck">
            Paste a link to a Python project on GitHub. RepoLens shows which
            files depend on which, and what to read first for the feature you
            care about.
          </p>
        </section>

        {/* 1. GitHub Repo URL Section */}
        <section
          className="landing__card"
          aria-label="Analyze a repository"
          data-tour="repo-input"
        >
          <RepoInputForm
            value={input}
            onChange={setInput}
            onSubmit={target => void start(target)}
            submitting={submitting}
          />

          {failure !== null && (
            <ErrorBanner
              error={failure.error}
              onRetry={() => void start(failure.target)}
              onDismiss={() => setFailure(null)}
            >
              {failure.code === 'REF_NOT_FOUND' && (
                <button
                  type="button"
                  className="button"
                  onClick={() => analyzeDefaultBranch(failure.target)}
                >
                  Analyze the default branch
                </button>
              )}
            </ErrorBanner>
          )}
        </section>

        {/* 2. Recent Repositories Section */}
        {recentRepos.length > 0 && (
          <section
            className="landing__recent"
            aria-labelledby="recent-repos-heading"
          >
            <div className="landing__recent-header">
              <div className="landing__recent-title-group">
                <span
                  className="landing__recent-indicator"
                  aria-hidden="true"
                />
                <h2 id="recent-repos-heading">Recent repositories</h2>
              </div>
              <span className="landing__recent-count">
                {recentRepos.length}{' '}
                {recentRepos.length === 1 ? 'project' : 'projects'}
              </span>
            </div>

            <ul className="landing__recent-list">
              {recentRepos.map(entry => (
                <li key={entry.analysisId} className="landing__recent-item">
                  <Link
                    to={`/analysis/${encodeURIComponent(entry.analysisId)}`}
                    className="landing__recent-link"
                  >
                    <span className="landing__recent-name">
                      {repoDisplayName(entry.repoUrl)}
                    </span>
                    <span className="landing__recent-meta">
                      <code className="landing__recent-sha">
                        {entry.ref
                          ? `${entry.ref} (${entry.sha.slice(0, 7)})`
                          : entry.sha.slice(0, 7)}
                      </code>
                      <span
                        className="landing__recent-arrow"
                        aria-hidden="true"
                      >
                        &rarr;
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* 3. Sample Dependency Map Section (Single Directory, Pre-Selected File) */}
        <section
          ref={sampleMapRef}
          id="sample-map"
          className="landing__sample-section"
          aria-labelledby="sample-map-heading"
          data-tour="sample-map"
        >
          <h2 id="sample-map-heading" className="landing__section-title">
            Sample dependency map
          </h2>

          <div className="landing__sample-window">
            {showSampleList ? (
              <ListFallback
                graph={SAMPLE_GRAPH}
                selectedPath={selectedPath}
                onSelectFile={handleSelectSampleFile}
                message={mapFallback}
                toolbarEnd={sampleViewSwitch}
              />
            ) : (
              <MapErrorBoundary onError={handleMapError}>
                <Suspense
                  fallback={
                    <p role="status" className="landing__sample-loading">
                      Loading sample dependency map&hellip;
                    </p>
                  }
                >
                  <DependencyMap
                    graph={SAMPLE_GRAPH}
                    expandedModules={expandedModules}
                    selectedPath={selectedPath}
                    selectionRevision={selectionRevision}
                    matchedPaths={null}
                    hideUnrelated={hideUnrelated}
                    onHideUnrelatedChange={setHideUnrelated}
                    onSelectFile={handleSelectSampleFile}
                    onToggleModule={handleToggleSampleModule}
                    onCollapseAll={handleCollapseAllSample}
                    onTooSlow={handleMapTooSlow}
                    toolbarEnd={sampleViewSwitch}
                  />
                </Suspense>
              </MapErrorBoundary>
            )}
          </div>
        </section>

        {/* 4. How It Works Section (3-Block Left-to-Right Flow Graph) */}
        <section
          id="how-it-works"
          className="landing__how-section"
          aria-labelledby="how-it-works-heading"
          data-tour="how-it-works"
        >
          <h2 id="how-it-works-heading" className="landing__section-title">
            How it works
          </h2>

          <div className="landing__flow-graph">
            {/* Block 1: Downloading the code */}
            <div className="landing__flow-block">
              <div className="landing__flow-icon" aria-hidden="true">
                <svg viewBox="0 0 40 40" fill="none">
                  <path
                    d="M20 8V25M20 25L13 18M20 25L27 18"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M8 28V31C8 32.1046 8.89543 33 10 33H30C31.1046 33 32 32.1046 32 31V28"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
              <h3>Downloading the code</h3>
              <p>
                Paste a GitHub link and RepoLens fetches a snapshot of the
                project files.
              </p>
            </div>

            <div className="landing__flow-arrow" aria-hidden="true">
              <svg viewBox="0 0 48 24" fill="none">
                <path
                  d="M2 12H44M44 12L35 4M44 12L35 20"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            {/* Block 2: Running an analysis */}
            <div className="landing__flow-block">
              <div className="landing__flow-icon" aria-hidden="true">
                <svg viewBox="0 0 40 40" fill="none">
                  <circle
                    cx="18"
                    cy="18"
                    r="9"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  />
                  <path
                    d="M25 25L33 33"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                  <path
                    d="M15 18H21M18 15V21"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
              <h3>Running an analysis</h3>
              <p>
                RepoLens reads each file to find its functions, classes, and
                connections.
              </p>
            </div>

            <div className="landing__flow-arrow" aria-hidden="true">
              <svg viewBox="0 0 48 24" fill="none">
                <path
                  d="M2 12H44M44 12L35 4M44 12L35 20"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            {/* Block 3: Creating dependency graph */}
            <div className="landing__flow-block">
              <div className="landing__flow-icon" aria-hidden="true">
                <svg viewBox="0 0 40 40" fill="none">
                  <circle
                    cx="10"
                    cy="20"
                    r="4"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  />
                  <circle
                    cx="30"
                    cy="11"
                    r="4"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  />
                  <circle
                    cx="30"
                    cy="29"
                    r="4"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  />
                  <path
                    d="M14 18L26 13M14 22L26 27"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
              <h3>Creating dependency graph</h3>
              <p>
                Explore the visual map and ranked reading order for any feature.
              </p>
            </div>
          </div>
        </section>

        {/* 5. Features Section */}
        <section
          id="features"
          className="landing__features-section"
          aria-labelledby="features-heading"
        >
          <h2 id="features-heading" className="landing__section-title">
            Features
          </h2>

          <div className="landing__features-grid">
            <article className="landing__feature-card">
              <div className="landing__feature-icon" aria-hidden="true">
                <svg viewBox="0 0 32 32" fill="none">
                  <circle
                    cx="14"
                    cy="14"
                    r="8"
                    stroke="currentColor"
                    strokeWidth="2.2"
                  />
                  <path
                    d="M20 20L27 27"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
              <h3>Semantic search</h3>
              <p>Search by topic in plain English to find the right files.</p>
            </article>

            <article className="landing__feature-card">
              <div className="landing__feature-icon" aria-hidden="true">
                <svg viewBox="0 0 32 32" fill="none">
                  <path
                    d="M6 9H26M6 16H20M6 23H14"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
              <h3>Reading graph &amp; order</h3>
              <p>See which files to read first and why.</p>
            </article>

            <article className="landing__feature-card">
              <div className="landing__feature-icon" aria-hidden="true">
                <svg viewBox="0 0 32 32" fill="none">
                  <rect
                    x="6"
                    y="5"
                    width="20"
                    height="22"
                    rx="3"
                    stroke="currentColor"
                    strokeWidth="2.2"
                  />
                  <path
                    d="M11 11H21M11 16H21M11 21H16"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
              <h3>File summaries</h3>
              <p>
                View a quick breakdown of what each file contains and connects
                to.
              </p>
            </article>

            <article className="landing__feature-card">
              <div className="landing__feature-icon" aria-hidden="true">
                <svg viewBox="0 0 32 32" fill="none">
                  <path
                    d="M13 19L19 13M15 10L18 7C20.2091 4.79086 23.7909 4.79086 26 7C28.2091 9.20914 28.2091 12.7909 26 15L23 18M17 22L14 25C11.7909 27.2091 8.20914 27.2091 6 25C3.79086 22.7909 3.79086 19.2091 6 17L9 14"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
              <h3>Direct GitHub source links</h3>
              <p>Open any file or function on GitHub in one click.</p>
            </article>
          </div>
        </section>
      </div>

      {welcomeOpen && !tourOpen && (
        <aside
          className="landing__welcome-popup"
          aria-labelledby="welcome-popup-heading"
        >
          <div className="landing__welcome-header">
            <h2 id="welcome-popup-heading">First time using RepoLens?</h2>
            <button
              type="button"
              className="landing__welcome-close"
              aria-label="Close welcome prompt"
              onClick={dismissWelcome}
            >
              &times;
            </button>
          </div>
          <p className="landing__welcome-body">
            Would you like a quick tour on how to get started?
          </p>
          <div className="landing__welcome-actions">
            <button
              type="button"
              className="button button--primary"
              onClick={openHelpTour}
            >
              Start tour
            </button>
            <button
              type="button"
              className="button button--secondary landing__welcome-dismiss"
              onClick={dismissWelcome}
            >
              No thanks
            </button>
          </div>
        </aside>
      )}

      {tourOpen && (
        <WorkspaceTour
          steps={LANDING_TOUR_STEPS}
          onClose={() => setTourOpen(false)}
        />
      )}
    </main>
  );
}

function repoDisplayName(repoUrl: string): string {
  return repoUrl.replace(/^https?:\/\/[^/]+\//, '');
}
