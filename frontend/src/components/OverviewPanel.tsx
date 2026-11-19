import type {ReactNode} from 'react';
import {useEffect, useState} from 'react';
import {useApiClient} from '../api/apiClientContext.ts';
import type {OverviewFile, RepositoryOverview} from '../api/types.ts';
import './OverviewPanel.css';

interface OverviewPanelProps {
  analysisId: string;
  selectedPath?: string | null;
  onSelectFile: (path: string) => void;
  onSelectArea: (paths: string[]) => void;
  onTourLoaded?: (tour: OverviewFile[]) => void;
}

type OverviewResult =
  | {analysisId: string; attempt: number; overview: RepositoryOverview}
  | {analysisId: string; attempt: number; failure: string};

export function OverviewPanel({
  analysisId,
  onSelectFile,
  onSelectArea,
  onTourLoaded,
}: OverviewPanelProps) {
  const api = useApiClient();
  const [result, setResult] = useState<OverviewResult | null>(null);
  const [retry, setRetry] = useState(0);
  const current =
    result?.analysisId === analysisId && result.attempt === retry
      ? result
      : null;

  useEffect(() => {
    const controller = new AbortController();
    void api
      .getOverview(analysisId, {signal: controller.signal})
      .then(overview => {
        setResult({analysisId, attempt: retry, overview});
        onTourLoaded?.(overview.tour);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setResult({
          analysisId,
          attempt: retry,
          failure:
            error instanceof Error
              ? error.message
              : 'The repository overview could not be loaded.',
        });
      });
    return () => controller.abort();
  }, [analysisId, api, retry]);

  if (current !== null && 'failure' in current) {
    return (
      <div className="overview__failure" role="alert">
        <p>{current.failure}</p>
        <button
          type="button"
          className="button"
          onClick={() => setRetry(value => value + 1)}
        >
          Retry
        </button>
      </div>
    );
  }
  if (current === null || !('overview' in current)) {
    return (
      <p className="workspace__hint" role="status">
        Building your starting guide…
      </p>
    );
  }

  const {overview} = current;
  const openFile = (file: OverviewFile) => onSelectFile(file.path);
  const firstTourStep = overview.tour[0];

  return (
    <div className="overview" aria-label="Repository overview">
      <header className="overview__header">
        <div className="overview__header-row">
          <h2>Start here</h2>
          {firstTourStep !== undefined && (
            <button
              type="button"
              className="button overview__tour-btn"
              onClick={() => openFile(firstTourStep)}
            >
              Start
            </button>
          )}
        </div>
      </header>

      <OverviewCollapse
        title="Entry points"
        empty="No conventional entry point found."
      >
        {overview.entryPoints.map(file => (
          <OverviewFileButton key={file.path} file={file} onSelect={openFile} />
        ))}
      </OverviewCollapse>

      <OverviewCollapse
        title="Core files"
        empty="No parsed source files found."
      >
        {overview.coreFiles.slice(0, 5).map(file => (
          <OverviewFileButton key={file.path} file={file} onSelect={openFile} />
        ))}
      </OverviewCollapse>

      <OverviewCollapse
        title="Architecture"
        headingId="overview-architecture"
        empty="No packages found."
      >
        <ul className="overview__packages">
          {overview.architecture.packages.slice(0, 8).map(pkg => (
            <li key={pkg.id}>
              <span>{pkg.id === '.' ? '(root)' : pkg.id}</span>
              <span className="overview__meta">{pkg.fileCount} files</span>
            </li>
          ))}
        </ul>
      </OverviewCollapse>

      <OverviewCollapse
        title="Feature areas"
        empty="No connected source areas found."
      >
        {overview.areas.slice(0, 8).map(area => (
          <button
            key={area.id}
            type="button"
            className="overview__area"
            disabled={area.files.length === 0}
            onClick={() => onSelectArea(area.files)}
          >
            <span>{area.name}</span>
            <span className="overview__meta">{area.files.length} files</span>
          </button>
        ))}
      </OverviewCollapse>
    </div>
  );
}

/** Ant Design-style animated collapse section that starts closed by default. */
function OverviewCollapse({
  title,
  headingId,
  empty,
  children,
}: {
  title: string;
  headingId?: string;
  empty: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const hasItems = Array.isArray(children)
    ? children.length > 0
    : children !== null;

  return (
    <section
      className={`overview__section${open ? ' overview__section--open' : ''}`}
      aria-labelledby={headingId}
    >
      <div
        className="overview__collapse-header"
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
        <svg
          className="overview__collapse-arrow"
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
        <h3 id={headingId}>{title}</h3>
      </div>

      <div className="overview__collapse-motion">
        <div className="overview__collapse-inner">
          <div className="overview__collapse-body">
            {hasItems ? children : <p className="overview__meta">{empty}</p>}
          </div>
        </div>
      </div>
    </section>
  );
}

function OverviewFileButton({
  file,
  index,
  onSelect,
}: {
  file: OverviewFile;
  index?: number;
  onSelect: (file: OverviewFile) => void;
}) {
  return (
    <button
      type="button"
      className="overview__file"
      aria-label={`Open ${file.path}`}
      onClick={() => onSelect(file)}
    >
      {index !== undefined && <span className="overview__step">{index}</span>}
      <span className="overview__file-copy">
        <span className="overview__path">{file.path}</span>
        {file.summary && (
          <span className="overview__meta">
            {file.summarySource === 'ai' && (
              <span
                className="overview__ai-label"
                title="AI-generated summary, checked against static analysis"
              >
                AI
                <span className="visually-hidden"> summary:</span>
              </span>
            )}
            {file.summary}
          </span>
        )}
        <span className="overview__reason">{file.reason}</span>
      </span>
    </button>
  );
}
