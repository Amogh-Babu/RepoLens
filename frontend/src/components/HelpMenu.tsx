import {useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import './HelpMenu.css';

const GUIDE_URL = 'https://github.com/Amogh-Babu/RepoLens/blob/main/REPOLENS_USER_GUIDE.md';
const BUG_URL = 'https://github.com/Amogh-Babu/RepoLens/issues/new';

export function HelpMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  const menu = (
    <div ref={ref} className="help-menu">
      <button
        type="button"
        className="help-menu__trigger"
        aria-label="Help and feedback"
        title="Help and feedback"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
      >
        ?
      </button>

      {open && (
        <ul role="menu" className="help-menu__list">
          <li role="none">
            <a role="menuitem" className="help-menu__item" href={GUIDE_URL}>
              User Guide
            </a>
          </li>
          <li role="none">
            <a
              role="menuitem"
              className="help-menu__item"
              href={BUG_URL}
              target="_blank"
              rel="noopener noreferrer"
            >
              Report a Bug
            </a>
          </li>
        </ul>
      )}
    </div>
  );

  return createPortal(menu, document.body);
}