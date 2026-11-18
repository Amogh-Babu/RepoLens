import type {ReactNode} from 'react';
import type {Analysis, AnalysisStage} from '../api/types.ts';
import {ANALYSIS_STAGES} from '../api/types.ts';
import './ProgressIndicator.css';

const STAGE_LABELS: Record<AnalysisStage, string> = {
  resolving: 'Resolving the commit',
  downloading: 'Downloading the source',
  filtering: 'Filtering out generated files',
  parsing: 'Parsing Python files',
  classifying: 'Classifying imports',
  indexing: 'Indexing search content',
  storing: 'Saving the results',
};

function renderStageIcon(stage: AnalysisStage): ReactNode {
  switch (stage) {
    case 'resolving':
      return (
        <svg viewBox="0 0 32 32" fill="none">
          <circle
            cx="16"
            cy="16"
            r="5"
            stroke="currentColor"
            strokeWidth="2.2"
          />
          <path
            d="M4 16H11M21 16H28"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'downloading':
      return (
        <svg viewBox="0 0 32 32" fill="none">
          <path
            d="M16 6V20M16 20L10.5 14.5M16 20L21.5 14.5"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M6 23V25C6 25.5523 6.44772 26 7 26H25C25.5523 26 26 25.5523 26 25V23"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'filtering':
      return (
        <svg viewBox="0 0 32 32" fill="none">
          <path
            d="M5 7H27L19 16.5V24L13 26V16.5L5 7Z"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'parsing':
      return (
        <svg viewBox="0 0 32 32" fill="none">
          <path
            d="M11 10L5 16L11 22M21 10L27 16L21 22M18 7L14 25"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'classifying':
      return (
        <svg viewBox="0 0 32 32" fill="none">
          <circle
            cx="8"
            cy="16"
            r="3.5"
            stroke="currentColor"
            strokeWidth="2.2"
          />
          <circle
            cx="24"
            cy="9"
            r="3.5"
            stroke="currentColor"
            strokeWidth="2.2"
          />
          <circle
            cx="24"
            cy="23"
            r="3.5"
            stroke="currentColor"
            strokeWidth="2.2"
          />
          <path
            d="M11.5 14.5L20.5 10.5M11.5 17.5L20.5 21.5"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'indexing':
      return (
        <svg viewBox="0 0 32 32" fill="none">
          <circle
            cx="14"
            cy="14"
            r="7.5"
            stroke="currentColor"
            strokeWidth="2.2"
          />
          <path
            d="M19.5 19.5L26 26"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'storing':
      return (
        <svg viewBox="0 0 32 32" fill="none">
          <rect
            x="6"
            y="6"
            width="20"
            height="20"
            rx="4"
            stroke="currentColor"
            strokeWidth="2.2"
          />
          <path
            d="M11 16.5L14.5 20L21.5 12.5"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
  }
}

interface ProgressIndicatorProps {
  analysis: Analysis;
  onCancel: () => void;
  cancelling: boolean;
}

/** Shows which pipeline stage a running analysis is in, with horizontal cards and a synced progress bar. */
export function ProgressIndicator({
  analysis,
  onCancel,
  cancelling,
}: ProgressIndicatorProps) {
  const current =
    analysis.status === 'queued' || analysis.stage === null
      ? -1
      : ANALYSIS_STAGES.indexOf(analysis.stage);
  const currentLabel =
    analysis.status === 'queued' || analysis.stage === null
      ? 'Waiting to start'
      : STAGE_LABELS[analysis.stage];

  // Sync the horizontal progress bar fill to the center of the active card column.
  const progressPercent =
    current < 0
      ? 2
      : Number((((current + 0.5) / ANALYSIS_STAGES.length) * 100).toFixed(2));

  return (
    <section className="progress" aria-labelledby="progress-heading">
      <div className="progress__header">
        <div className="progress__title-group">
          <h2 id="progress-heading">Analyzing the repository</h2>
          {/* Announced to screen readers as the stage changes. */}
          <p className="progress__current" role="status">
            {currentLabel}…
          </p>
        </div>

        <button
          type="button"
          className="button progress__cancel"
          onClick={onCancel}
          disabled={cancelling}
        >
          {cancelling ? 'Cancelling…' : 'Cancel'}
        </button>
      </div>

      {/* Horizontal row of stage cards */}
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
              <span className="progress__card-top" aria-hidden="true">
                <span className="progress__icon">{renderStageIcon(stage)}</span>
                <span className="progress__marker" />
              </span>
              {STAGE_LABELS[stage]}
              {state === 'done' && (
                <span className="visually-hidden"> (done)</span>
              )}
            </li>
          );
        })}
      </ol>

      {/* Horizontal progress bar synced to each card's horizontal location */}
      <div className="progress__sync">
        <div className="progress__sync-Connectors" aria-hidden="true">
          {ANALYSIS_STAGES.map((stage, index) => {
            const state =
              index < current
                ? 'done'
                : index === current
                  ? 'current'
                  : 'pending';
            return (
              <div
                key={stage}
                className={`progress__sync-column progress__sync-column--${state}`}
              >
                <span className="progress__sync-stem" />
                <span className="progress__sync-node" />
              </div>
            );
          })}
        </div>

        <div
          className="progress__bar-track"
          role="progressbar"
          aria-label="Analysis stage progress"
          aria-valuemin={0}
          aria-valuemax={ANALYSIS_STAGES.length}
          aria-valuenow={current < 0 ? 0 : current + 1}
        >
          <div
            className="progress__bar-fill"
            style={{width: `${progressPercent}%`}}
          />
        </div>
      </div>

      <p className="progress__note">
        RepoLens reads the code without running it. Large repositories can take
        up to a few minutes.
      </p>
    </section>
  );
}
