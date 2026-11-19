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

/** Small subtext under the repository heading with repo and commit details. */
export function SummaryBar({analysis, summary}: SummaryBarProps) {
  const shortSha = analysis.sha.slice(0, 7);

  return (
    <section className="summary" aria-label="Analysis summary">
      <a href={analysis.repoUrl} target="_blank" rel="noreferrer">
        <code>{analysis.repoUrl}</code>
      </a>
      <span aria-hidden="true">·</span>
      <span>
        Commit{' '}
        <a
          href={`${analysis.repoUrl}/tree/${analysis.sha}`}
          target="_blank"
          rel="noreferrer"
          title={analysis.sha}
        >
          <code>{shortSha}</code>
        </a>
        {analysis.ref !== null && analysis.ref !== analysis.sha && (
          <> ({analysis.ref})</>
        )}
      </span>
      <span aria-hidden="true">·</span>
      <span>{plural(summary.filesAnalyzed, 'file')} analyzed</span>
      <span aria-hidden="true">·</span>
      <span title="Generated and vendored files, which are not searched">
        {plural(summary.filesExcluded, 'file')} excluded
      </span>
      <span aria-hidden="true">·</span>
      <span>{plural(summary.filesUnparsed, 'file')} could not be parsed</span>
      <span aria-hidden="true">·</span>
      <span>
        {analysis.fromCache
          ? `Loaded from cache, analyzed ${formatAge(analysis.createdAt)}`
          : `Analyzed ${formatAge(analysis.createdAt)}`}
      </span>
    </section>
  );
}
