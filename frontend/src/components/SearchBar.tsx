import type {FormEvent} from 'react';
import {useId, useState} from 'react';
import {checkQuery} from '../utils/searchQuery.ts';
import './SearchBar.css';

interface SearchBarProps {
  /** Called with a trimmed, valid query. */
  onSearch: (query: string) => void;
  /** Called when the user clears the search. */
  onClear: () => void;
  /** True while a search is active, so the bar offers to clear it. */
  active: boolean;
  /** True while results for a new query are loading. */
  searching: boolean;
  /** True when searching is not possible, e.g. the analysis expired. */
  disabled?: boolean;
}

/**
 * Feature search. Empty and over-long queries are rejected here with a
 * hint, without a request (Use Case 2 exceptions).
 */
export function SearchBar({
  onSearch,
  onClear,
  active,
  searching,
  disabled = false,
}: SearchBarProps) {
  const inputId = useId();
  const hintId = useId();
  const [value, setValue] = useState('');
  const [hint, setHint] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const check = checkQuery(value);
    if (!check.ok) {
      setHint(check.message);
      return;
    }
    setHint(null);
    onSearch(check.query);
  }

  function clear() {
    setValue('');
    setHint(null);
    onClear();
  }

  return (
    <form className="search-bar" role="search" onSubmit={handleSubmit}>
      <label htmlFor={inputId} className="visually-hidden">
        Search this repository
      </label>
      <div className="search-bar__field">
        <input
          id={inputId}
          type="search"
          autoComplete="off"
          spellCheck={false}
          placeholder={
            disabled
              ? 'Re-analyze the repository to search again'
              : 'Search for a feature, file or function, e.g. login'
          }
          disabled={disabled}
          value={value}
          onChange={event => {
            setValue(event.target.value);
            setHint(null);
            // Emptying the box ends the search (Use Case 2, 1c).
            if (event.target.value === '' && active) onClear();
          }}
          aria-invalid={hint !== null}
          aria-describedby={hint !== null ? hintId : undefined}
        />
        {(value !== '' || active) && !disabled && (
          <button
            type="button"
            className="search-bar__clear"
            onClick={clear}
            aria-label="Clear search"
          >
            ✕
          </button>
        )}
      </div>
      <button
        type="submit"
        className="button button--primary"
        disabled={searching || disabled}
      >
        {searching ? 'Searching…' : 'Search'}
      </button>
      {hint !== null && (
        <p id={hintId} className="search-bar__hint">
          {hint}
        </p>
      )}
    </form>
  );
}
