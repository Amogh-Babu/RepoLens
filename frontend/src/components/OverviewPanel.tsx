import {useEffect, useState} from 'react';
import {useApiClient} from '../api/apiClientContext.ts';
import type {OverviewFile, RepositoryOverview} from '../api/types.ts';
import './OverviewPanel.css';

interface OverviewPanelProps {
  analysisId: string;
  onSelectFile: (path: string) => void;
  onSelectArea: (paths: string[]) => void;
}

type OverviewResult =
  | {analysisId: string; attempt: number; overview: RepositoryOverview}
  | {analysisId: string; attempt: number; failure: string};

export function OverviewPanel({
  analysisId,
  onSelectFile,
  onSelectArea,
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
      .then(overview => setResult({analysisId, attempt: retry, overview}))
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
        <h2>Start here</h2>
        <p>Begin with an entry point, then follow the files it depends on.</p>
        {firstTourStep !== undefined && (
          <button
            type="button"
            className="button"
            onClick={() => openFile(firstTourStep)}
          >
            Start reading tour
          </button>
        )}
      </header>

      <OverviewSection
        title="Entry points"
        empty="No conventional entry point found."
      >
        {overview.entryPoints.map(file => (
          <OverviewFileButton key={file.path} file={file} onSelect={openFile} />
        ))}
      </OverviewSection>

      <OverviewSection title="Core files" empty="No parsed source files found.">
        {overview.coreFiles.slice(0, 5).map(file => (
          <OverviewFileButton key={file.path} file={file} onSelect={openFile} />
        ))}
      </OverviewSection>

      <section
        className="overview__section"
        aria-labelledby="overview-architecture"
      >
        <h3 id="overview-architecture">Architecture</h3>
        <p className="overview__meta">
          {overview.architecture.packages.length} packages
          {' · '}
          {overview.architecture.layers.length} layers
          {overview.architecture.hasCycles ? ' · import cycles detected' : ''}
        </p>
        <ul className="overview__packages">
          {overview.architecture.packages.slice(0, 8).map(pkg => (
            <li key={pkg.id}>
              <span>{pkg.id === '.' ? '(root)' : pkg.id}</span>
              <span className="overview__meta">{pkg.fileCount} files</span>
            </li>
          ))}
        </ul>
      </section>

      <OverviewSection
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
      </OverviewSection>

      <OverviewSection title="Reading tour" empty="No tour steps available.">
        {overview.tour.slice(0, 12).map((file, index) => (
          <OverviewFileButton
            key={file.path}
            file={file}
            index={index + 1}
            onSelect={openFile}
          />
        ))}
      </OverviewSection>

      <section
        className="overview__section"
        aria-labelledby="overview-inventory"
      >
        <h3 id="overview-inventory">File inventory</h3>
        <p className="overview__meta">
          {categoryCounts(overview)
            .map(([category, count]) => `${count} ${category}`)
            .join(' · ')}
        </p>
      </section>
    </div>
  );
}

function OverviewSection({
  title,
  empty,
  children,
}: {
  title: string;
  empty: string;
  children: React.ReactNode;
}) {
  const hasItems = Array.isArray(children)
    ? children.length > 0
    : children !== null;
  return (
    <section className="overview__section">
      <h3>{title}</h3>
      {hasItems ? children : <p className="overview__meta">{empty}</p>}
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
        {file.summary && <span className="overview__meta">{file.summary}</span>}
        <span className="overview__reason">{file.reason}</span>
      </span>
    </button>
  );
}

function categoryCounts(overview: RepositoryOverview): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const item of overview.categories) {
    counts.set(item.category, (counts.get(item.category) ?? 0) + 1);
  }
  return [...counts].sort(([left], [right]) => left.localeCompare(right));
}
