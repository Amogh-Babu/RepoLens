import {Link} from 'react-router';
import {useDocumentTitle} from '../utils/useDocumentTitle.ts';

/** Shown for any route that does not exist. */
export function NotFoundPage() {
  useDocumentTitle('Page not found');
  return (
    <main className="page" id="main" tabIndex={-1}>
      <h1>Page not found</h1>
      <Link to="/">Go to the RepoLens home page</Link>
    </main>
  );
}
