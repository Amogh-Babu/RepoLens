import {Link} from 'react-router';

/** Shown for any route that does not exist. */
export function NotFoundPage() {
  return (
    <main className="page">
      <h1>Page not found</h1>
      <Link to="/">Go to the RepoLens home page</Link>
    </main>
  );
}
