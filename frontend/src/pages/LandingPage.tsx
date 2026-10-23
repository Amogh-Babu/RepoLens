import {useEffect, useRef, useState} from 'react';
import {useNavigate} from 'react-router';
import {useApiClient} from '../api/apiClientContext.ts';
import type {ErrorDescription} from '../api/describeError.ts';
import {describeError} from '../api/describeError.ts';
import {toApiError} from '../api/errors.ts';
import {ErrorBanner} from '../components/ErrorBanner.tsx';
import type {RepoInputValue} from '../components/RepoInputForm.tsx';
import {RepoInputForm} from '../components/RepoInputForm.tsx';
import type {RepoTarget} from '../utils/repoInput.ts';
import {useDocumentTitle} from '../utils/useDocumentTitle.ts';
import './LandingPage.css';

interface FailedStart {
  error: ErrorDescription;
  code: string;
  target: RepoTarget;
}

/** Landing page: repository input and a short user guide. */
export function LandingPage() {
  const api = useApiClient();
  const navigate = useNavigate();
  useDocumentTitle(null);
  const [input, setInput] = useState<RepoInputValue>({url: '', ref: ''});
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<FailedStart | null>(null);
  const pending = useRef<AbortController | null>(null);

  // Cancel an in-flight request if the user leaves the page.
  useEffect(() => () => pending.current?.abort(), []);

  async function start(target: RepoTarget) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setSubmitting(true);
    setFailure(null);

    try {
      const {analysisId} = await api.startAnalysis(
        target.ref === null
          ? {url: target.url}
          : {url: target.url, ref: target.ref},
        {signal: controller.signal},
      );
      void navigate(`/analysis/${encodeURIComponent(analysisId)}`);
    } catch (error: unknown) {
      const apiError = toApiError(error);
      if (apiError.code !== 'ABORTED') {
        setFailure({
          error: describeError(apiError),
          code: apiError.code,
          target,
        });
      }
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setSubmitting(false);
      }
    }
  }

  function analyzeDefaultBranch(target: RepoTarget) {
    setInput(current => ({...current, ref: ''}));
    void start({...target, ref: null});
  }

  return (
    <main className="page landing" id="main" tabIndex={-1}>
      <header className="landing__intro">
        <h1>RepoLens</h1>
        <p className="lede">
          See how the files in a Python repository depend on each other, and get
          a suggested reading order for the feature you want to learn.
        </p>
      </header>

      <section className="landing__card" aria-label="Analyze a repository">
        <RepoInputForm
          value={input}
          onChange={setInput}
          onSubmit={target => void start(target)}
          submitting={submitting}
        />
        {failure !== null && (
          <ErrorBanner
            error={failure.error}
            onRetry={() => void start(failure.target)}
            onDismiss={() => setFailure(null)}
          >
            {failure.code === 'REF_NOT_FOUND' && (
              <button
                type="button"
                className="button"
                onClick={() => analyzeDefaultBranch(failure.target)}
              >
                Analyze the default branch
              </button>
            )}
          </ErrorBanner>
        )}
      </section>

      <section className="landing__guide" aria-labelledby="guide-heading">
        <h2 id="guide-heading">How it works</h2>
        <ol className="landing__steps">
          <li>
            <strong>Paste a repository URL.</strong> RepoLens downloads the code
            at that commit and maps which files import which. It never runs the
            code.
          </li>
          <li>
            <strong>Search for a feature.</strong> Type a word like
            &ldquo;login&rdquo; or a function name to get a ranked list of the
            files involved.
          </li>
          <li>
            <strong>Read in the suggested order.</strong> Each file comes with a
            reason, its place on the dependency map, and a link to its source on
            GitHub.
          </li>
        </ol>

        <h3>What this version supports</h3>
        <ul className="landing__limits">
          <li>Public repositories on github.com</li>
          <li>Python code, up to 1,000 Python files</li>
          <li>Results are kept for 24 hours, then analyzed again</li>
        </ul>
      </section>
    </main>
  );
}
