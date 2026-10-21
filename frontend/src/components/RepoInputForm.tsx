import type {FormEvent} from 'react';
import {useId, useState} from 'react';
import type {RepoTarget} from '../utils/repoInput.ts';
import {EXAMPLE_REPO_URL, parseRepoInput} from '../utils/repoInput.ts';
import './RepoInputForm.css';

/** What the user has typed into the form. */
export interface RepoInputValue {
  url: string;
  ref: string;
}

interface RepoInputFormProps {
  value: RepoInputValue;
  onChange: (value: RepoInputValue) => void;
  /** Called with the normalized repository when the input is valid. */
  onSubmit: (target: RepoTarget) => void;
  /** True while the analysis request is being sent. */
  submitting?: boolean;
}

/**
 * Repository URL and optional ref. Checks the URL format as the user types
 * and enables Analyze only for a valid github.com repository URL; nothing
 * invalid is sent to the backend.
 */
export function RepoInputForm({
  value,
  onChange,
  onSubmit,
  submitting = false,
}: RepoInputFormProps) {
  const urlId = useId();
  const refId = useId();
  const urlErrorId = useId();
  const refErrorId = useId();
  const refNoteId = useId();
  // Errors appear once the user leaves or pastes into the field, so they do
  // not flash while a URL is still being typed.
  const [showErrors, setShowErrors] = useState(false);

  const result = parseRepoInput(value.url, value.ref);
  const error = result.ok ? null : result.error;
  const urlError =
    showErrors && error !== null && error.kind !== 'invalid-ref'
      ? error.message
      : null;
  const refError = error?.kind === 'invalid-ref' ? error.message : null;
  const refFromUrl =
    result.ok && value.ref.trim() === '' ? result.target.ref : null;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setShowErrors(true);
    if (result.ok && !submitting) {
      onSubmit(result.target);
    }
  }

  return (
    <form className="repo-form" onSubmit={handleSubmit} noValidate>
      <div className="repo-form__field">
        <label htmlFor={urlId}>GitHub repository URL</label>
        <input
          id={urlId}
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder={EXAMPLE_REPO_URL}
          value={value.url}
          onChange={event => onChange({...value, url: event.target.value})}
          onBlur={() => {
            if (value.url.trim() !== '') setShowErrors(true);
          }}
          onPaste={() => setShowErrors(true)}
          aria-invalid={urlError !== null}
          aria-describedby={urlError !== null ? urlErrorId : undefined}
        />
        {urlError !== null && (
          <p id={urlErrorId} className="repo-form__error">
            {urlError}
          </p>
        )}
      </div>

      <div className="repo-form__field">
        <label htmlFor={refId}>
          Branch, tag or commit <span className="optional">(optional)</span>
        </label>
        <input
          id={refId}
          type="text"
          autoComplete="off"
          spellCheck={false}
          placeholder={refFromUrl ?? 'Default branch'}
          value={value.ref}
          onChange={event => onChange({...value, ref: event.target.value})}
          aria-invalid={refError !== null}
          aria-describedby={
            refError !== null
              ? refErrorId
              : refFromUrl !== null
                ? refNoteId
                : undefined
          }
        />
        {refError !== null && (
          <p id={refErrorId} className="repo-form__error">
            {refError}
          </p>
        )}
        {refError === null && refFromUrl !== null && (
          <p id={refNoteId} className="repo-form__note">
            Using <code>{refFromUrl}</code> from the URL.
          </p>
        )}
      </div>

      <button
        type="submit"
        className="button button--primary repo-form__submit"
        disabled={!result.ok || submitting}
      >
        {submitting ? 'Starting…' : 'Analyze'}
      </button>
    </form>
  );
}
