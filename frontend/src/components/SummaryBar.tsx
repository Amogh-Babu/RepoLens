import {useState} from 'react';
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
 * Inline horizontal accordion next to the repository heading. Starts closed
 * and smoothly expands horizontally to show the repository URL, commit SHA,
 * and analyzed/excluded/unparsed file counts.
 */
export function SummaryBar({analysis, summary}: SummaryBarProps) {
  const [open, setOpen] = useState(false);
  const shortSha = analysis.sha.slice(0, 7);

  return (
    <section
      className={`summary${open ? ' summary--open' : ''}`}
      aria-label="Analysis summary"
    >
      <button
        type="button"
        className="summary__trigger"
        aria-expanded={open}
        onClick={() => setOpen(current => !current)}
      >
        <svg
          className="summary__chevron"
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
        <span>Repo &amp; commit details</span>
      </button>

      <div className="summary__horizontal-motion">
        <div className="summary__horizontal-inner">
          <div className="summary__drawer">
            <dl className="summary__items">
              <div>
                <dt>Repo</dt>
                <dd>
                  <a href={analysis.repoUrl} target="_blank" rel="noreferrer">
                    <code>{analysis.repoUrl}</code>
                  </a>
                </dd>
              </div>
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
            <span className="summary__age">
              {analysis.fromCache
                ? `Loaded from cache, analyzed ${formatAge(analysis.createdAt)}`
                : `Analyzed ${formatAge(analysis.createdAt)}`}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
