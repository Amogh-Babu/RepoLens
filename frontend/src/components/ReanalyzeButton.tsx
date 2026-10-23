import {useState} from 'react';
import {useNavigate} from 'react-router';
import {useApiClient} from '../api/apiClientContext.ts';
import {describeError} from '../api/describeError.ts';
import {toApiError} from '../api/errors.ts';
import type {Analysis} from '../api/types.ts';
import type {RequestFailure} from '../state/analysisStore.ts';
import {ErrorBanner} from './ErrorBanner.tsx';

/** Starts a new analysis of the same repository and ref, then opens it. */
export function ReanalyzeButton({
  analysis,
  label,
}: {
  analysis: Analysis;
  label: string;
}) {
  const api = useApiClient();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const [failure, setFailure] = useState<RequestFailure | null>(null);

  async function reanalyze() {
    setStarting(true);
    setFailure(null);
    try {
      const {analysisId} = await api.startAnalysis(
        analysis.ref === null
          ? {url: analysis.repoUrl}
          : {url: analysis.repoUrl, ref: analysis.ref},
      );
      void navigate(`/analysis/${encodeURIComponent(analysisId)}`);
    } catch (error: unknown) {
      const apiError = toApiError(error);
      setFailure({code: apiError.code, error: describeError(apiError)});
      setStarting(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="button button--primary"
        onClick={() => void reanalyze()}
        disabled={starting}
      >
        {starting ? 'Starting…' : label}
      </button>
      {failure !== null && <ErrorBanner error={failure.error} />}
    </>
  );
}
