import type {Analysis, AnalysisStage} from '../api/types.ts';
import {ANALYSIS_STAGES} from '../api/types.ts';
import './ProgressIndicator.css';

const STAGE_LABELS: Record<AnalysisStage, string> = {
  resolving: 'Resolving the commit',
  downloading: 'Downloading the source',
  filtering: 'Filtering out generated files',
  parsing: 'Parsing Python files',
  classifying: 'Classifying imports',
  storing: 'Saving the results',
};

interface ProgressIndicatorProps {
  analysis: Analysis;
  onCancel: () => void;
  cancelling: boolean;
}

/** Shows which pipeline stage a running analysis is in, with Cancel. */
export function ProgressIndicator({
  analysis,
  onCancel,
  cancelling,
}: ProgressIndicatorProps) {
  const current =
    analysis.stage === null ? -1 : ANALYSIS_STAGES.indexOf(analysis.stage);
  const currentLabel =
    analysis.status === 'queued' || analysis.stage === null
      ? 'Waiting to start'
      : STAGE_LABELS[analysis.stage];

  return (
    <section className="progress" aria-labelledby="progress-heading">
      <div className="progress__header">
        <h2 id="progress-heading">Analyzing the repository</h2>
        <button
          type="button"
          className="button"
          onClick={onCancel}
          disabled={cancelling}
        >
          {cancelling ? 'Cancelling…' : 'Cancel'}
        </button>
      </div>

      {/* Announced to screen readers as the stage changes. */}
      <p className="progress__current" role="status">
        {currentLabel}…
      </p>

      <ol className="progress__stages">
        {ANALYSIS_STAGES.map((stage, index) => {
          const state =
            index < current
              ? 'done'
              : index === current
                ? 'current'
                : 'pending';
          return (
            <li
              key={stage}
              className={`progress__stage progress__stage--${state}`}
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <span className="progress__marker" aria-hidden="true" />
              {STAGE_LABELS[stage]}
              {state === 'done' && (
                <span className="visually-hidden"> (done)</span>
              )}
            </li>
          );
        })}
      </ol>

      <p className="progress__note">
        RepoLens reads the code without running it. Large repositories can take
        up to a few minutes.
      </p>
    </section>
  );
}
