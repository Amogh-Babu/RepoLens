import {Link, useParams} from 'react-router';

/**
 * Analysis page: summary, file explorer, dependency map, search and reading
 * list for one analyzed repository.
 */
export function AnalysisPage() {
  const {analysisId} = useParams();

  return (
    <main className="page">
      <h1>Analysis</h1>
      <p>
        Analysis ID: <code>{analysisId}</code>
      </p>
      <Link to="/">Analyze another repository</Link>
    </main>
  );
}
