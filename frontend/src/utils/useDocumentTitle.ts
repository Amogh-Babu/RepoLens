import {useEffect} from 'react';

const APP_NAME = 'RepoLens';

/**
 * Sets the browser tab title, e.g. "pallets/flask · RepoLens", so tabs and
 * screen readers can tell pages apart. With no title, just "RepoLens".
 */
export function useDocumentTitle(title: string | null) {
  useEffect(() => {
    document.title = title === null ? APP_NAME : `${title} · ${APP_NAME}`;
  }, [title]);
}
