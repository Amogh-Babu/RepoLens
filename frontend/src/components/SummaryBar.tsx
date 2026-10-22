import type {Analysis, AnalysisSummary} from '../api/types.ts';
import {formatAge} from '../utils/formatAge.ts';
import './SummaryBar.css';

interface SummaryBarProps {
  analysis: Analysis;
  summary: AnalysisSummary;
}

function plural(count: number, noun: string): string {
  return `${count.toLocaleString('en')} ${noun}${count === 1 ? '' : 's'}`;
}

/**
 * The commit that was analyzed and how many files were analyzed, excluded
 * and could not be parsed (Use Case 1 postconditions).
 */
export function SummaryBar({analysis, summary}: SummaryBarProps) {
  const shortSha = analysis.sha.slice(0, 7);
  return (
    <section className="summary" aria-label="Analysis summary">
      <dl className="summary__items">
        <div>
          <dt>Commit</dt>
          <dd>
            <a
              href={`${analysis.repoUrl}/tree/${analysis.sha}`}
              target="_blank"
              rel="noreferrer"
              title={analysis.sha}
            >
              <code>{shortSha}</code>
            </a>
            {analysis.ref !== null && analysis.ref !== analysis.sha && (
              <span className="summary__ref"> ({analysis.ref})</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Analyzed</dt>
          <dd>{plural(summary.filesAnalyzed, 'file')}</dd>
        </div>
        <div>
          <dt>Excluded</dt>
          <dd title="Generated and vendored files, which are not searched">
            {plural(summary.filesExcluded, 'file')}
          </dd>
        </div>
        <div>
          <dt>Could not parse</dt>
          <dd>{plural(summary.filesUnparsed, 'file')}</dd>
        </div>
      </dl>
      <p className="summary__age">
        {analysis.fromCache
          ? `Loaded from cache, analyzed ${formatAge(analysis.createdAt)}`
          : `Analyzed ${formatAge(analysis.createdAt)}`}
      </p>
    </section>
  );
}
