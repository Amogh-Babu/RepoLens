import {useEffect, useId, useRef, useState} from 'react';
import './SearchHelp.css';

/**
 * "How search works": what search looks at, how it ranks, and what the
 * reading order means (user test feedback, #94). Keep this in step with
 * SearchService in the backend: its fields, weights and stop words.
 */
export function SearchHelp() {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);

  // Escape or a click elsewhere closes the panel.
  useEffect(() => {
    if (!open) return;
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    function handlePointer(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('keydown', handleKey);
    document.addEventListener('pointerdown', handlePointer);
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.removeEventListener('pointerdown', handlePointer);
    };
  }, [open]);

  return (
    <div className="search-help" ref={rootRef}>
      <button
        type="button"
        className="button button--quiet search-help__toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
      >
        How search works
      </button>
      <div
        id={panelId}
        className="search-help__panel"
        role="region"
        aria-label="How search works"
        hidden={!open}
      >
        <SearchExplanation />
        <button
          type="button"
          className="button search-help__close"
          onClick={() => setOpen(false)}
        >
          Got it
        </button>
      </div>
    </div>
  );
}

function SearchExplanation() {
  return (
    <div className="search-explanation">
      <h3>What it looks at</h3>
      <p>
        File and folder names, functions and classes, methods and class
        attributes, imported module names, docstrings and comments. Every file
        that matches your words or is semantically related may be listed.
      </p>
      <p>
        Search combines keyword matches with a local language model, so a
        question like “where do I start with production?” can find relevant
        files even when their names use different words. Search runs locally;
        repository text is not sent to an embedding service.
      </p>

      <h3>How results are ranked</h3>
      <p>
        Exact matches and semantic similarity are combined. Exact file-name,
        symbol and import matches remain strong signals; dependency order then
        puts required files before the callers that use them.
      </p>

      <h3>What the order means</h3>
      <p>
        The list is an order to read in. Each file comes after the matching
        files it imports, so the building blocks come first. Every entry says
        why it matches and why it is at that spot.
      </p>

      <h3>Tips</h3>
      <ul>
        <li>
          Describe the task in your own words, or use a feature name like
          “checkout”.
        </li>
        <li>Common words like “the”, “how” or “where” are ignored.</li>
        <li>
          If the results are broad, add a feature name or a file you already
          know.
        </li>
      </ul>
    </div>
  );
}
