import type {CodeSummary, SummaryMetadata} from '../api/types.ts';
import {AiSummaryContent} from './AiSummaryContent.tsx';

interface AiSummaryDetailsProps {
  summary: CodeSummary;
  metadata: SummaryMetadata | null;
  onSelectFile?: (path: string) => void;
}

/** The model writes prose; only the named structure and cited ranges are verified. */
export function AiSummaryDetails({
  summary,
  metadata,
  onSelectFile,
}: AiSummaryDetailsProps) {
  const partial =
    summary.coverage === 'partial' || metadata?.coverage === 'partial';

  return (
    <section className="detail__ai-details" aria-label="AI-generated summary">
      <div className="detail__ai-header">
        <span className="detail__ai-badge">AI-generated overview</span>
        {metadata?.cached && <span className="detail__muted">Cached</span>}
      </div>
      <AiSummaryContent text={summary.summary} />
      <p className="detail__ai-disclaimer">
        Names, dependencies, and source ranges are checked against static
        analysis. The explanation itself may still be inaccurate.
      </p>
      {partial && (
        <p className="detail__warning" role="note">
          Partial summary: only part of this file was inspected.
          {metadata && metadata.inspectedLines.length > 0 && (
            <span>
              {' '}
              Inspected lines:{' '}
              {metadata.inspectedLines
                .map(([start, end]) => `${start}–${end}`)
                .join(', ')}
              .
            </span>
          )}
        </p>
      )}
      <details className="detail__ai-expandable">
        <summary>Purpose and responsibilities</summary>
        <div className="detail__ai-expanded-body">
          <AiSummaryContent text={summary.purpose} />
          {summary.responsibilities.length > 0 && (
            <ul className="detail__ai-list">
              {summary.responsibilities.map((item, index) => (
                <li key={index}>
                  <AiSummaryContent text={item} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
      {summary.keySymbols.length > 0 && (
        <details className="detail__ai-expandable">
          <summary>Key symbols ({summary.keySymbols.length})</summary>
          <ul className="detail__ai-expanded-list">
            {summary.keySymbols.map(item => (
              <li key={`${item.name}:${item.line}`}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  <code>{item.name}</code> (line {item.line})
                </a>
                <span className="detail__muted"> · {item.kind}</span>
                <AiSummaryContent text={item.description} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {summary.dependencies.length > 0 && (
        <details className="detail__ai-expandable">
          <summary>Dependencies ({summary.dependencies.length})</summary>
          <ul className="detail__ai-expanded-list">
            {summary.dependencies.map(item => (
              <li key={`${item.relationship}:${item.path}`}>
                {onSelectFile ? (
                  <button
                    type="button"
                    className="detail__file-link"
                    onClick={() => onSelectFile(item.path)}
                  >
                    <code>{item.path}</code>
                  </button>
                ) : (
                  <code>{item.path}</code>
                )}
                <span className="detail__muted">
                  {' '}
                  ·{' '}
                  {item.relationship === 'imports' ? 'imports' : 'imported by'}
                </span>
                <AiSummaryContent text={item.description} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {summary.sideEffects.length > 0 && (
        <details className="detail__ai-expandable">
          <summary>Side effects ({summary.sideEffects.length})</summary>
          <ul className="detail__ai-expanded-list">
            {summary.sideEffects.map((item, index) => (
              <li key={index}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  {item.kind} · lines {item.startLine}–{item.endLine}
                </a>
                <AiSummaryContent text={item.description} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {summary.uncertainties.length > 0 && (
        <details className="detail__ai-expandable">
          <summary>Uncertainties ({summary.uncertainties.length})</summary>
          <ul className="detail__ai-expanded-list">
            {summary.uncertainties.map((item, index) => (
              <li key={index}>
                <AiSummaryContent text={item} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {summary.evidence.length > 0 && (
        <details className="detail__ai-expandable">
          <summary>Source evidence ({summary.evidence.length})</summary>
          <ul className="detail__ai-expanded-list">
            {summary.evidence.map((item, index) => (
              <li key={index}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  Lines {item.startLine}–{item.endLine}
                </a>
                <AiSummaryContent text={item.description} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
