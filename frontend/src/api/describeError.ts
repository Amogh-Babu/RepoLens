import type {ApiError} from './errors.ts';

/** What the UI shows for an error. */
export interface ErrorDescription {
  title: string;
  /** The explanation from the backend (or client), always shown. */
  message: string;
  hint: string | null;
  /** Whether trying the same request again might work. */
  retryable: boolean;
}

/** Titles for the error codes the UI knows. */
const TITLES: Record<string, string> = {
  INVALID_URL: 'That URL cannot be analyzed',
  UNSUPPORTED_HOST: 'Only GitHub is supported for now',
  REPO_NOT_FOUND: 'Repository not found',
  REF_NOT_FOUND: 'Branch, tag or commit not found',
  REPO_EMPTY: 'The repository is empty',
  NO_PYTHON_FILES: 'No Python files found',
  TOO_MANY_FILES: 'The repository is too large',
  REPO_TOO_LARGE: 'The repository is too large',
  RATE_LIMITED: 'GitHub is limiting requests',
  GITHUB_UNAVAILABLE: 'Cannot reach GitHub',
  DOWNLOAD_FAILED: 'The download failed',
  ANALYSIS_FAILED: 'The analysis failed',
  ANALYSIS_NOT_FOUND: 'Analysis not found',
  ANALYSIS_NOT_READY: 'The analysis is still running',
  ANALYSIS_EXPIRED: 'This analysis has expired',
  FILE_NOT_FOUND: 'File not found',
  INVALID_QUERY: 'Check your search',
  INTERNAL_ERROR: 'Something went wrong',
  NETWORK_ERROR: 'Cannot reach RepoLens',
  TIMEOUT: 'RepoLens is taking too long',
  ABORTED: 'Request cancelled',
  AI_DISABLED: 'AI summaries are off',
  AI_BUSY: 'AI summaries are busy',
  AI_DAILY_LIMIT: "Today's AI budget is used up",
  AI_CLIENT_LIMIT: 'AI summary limit reached',
  AI_REGENERATE_COOLDOWN: 'Summary generated moments ago',
  AI_TIMEOUT: 'The AI summary took too long',
  AI_UNAVAILABLE: 'AI summary unavailable',
  AI_SUMMARY_UNVERIFIED: 'AI summary could not be verified',
  AI_SUMMARY_FAILED: 'AI summary unavailable',
  SOURCE_UNSUPPORTED: 'This file cannot be summarized',
  SOURCE_UNAVAILABLE: 'Cannot fetch the source from GitHub',
  SOURCE_NOT_FOUND: 'Source not found on GitHub',
  SOURCE_RATE_LIMITED: 'GitHub is limiting requests',
  SOURCE_MISMATCH: 'The source changed',
};

/** Errors caused by the input, where retrying unchanged cannot help. */
const NOT_RETRYABLE = new Set([
  'INVALID_URL',
  'UNSUPPORTED_HOST',
  'REPO_NOT_FOUND',
  'REF_NOT_FOUND',
  'REPO_EMPTY',
  'NO_PYTHON_FILES',
  'TOO_MANY_FILES',
  'REPO_TOO_LARGE',
  'ANALYSIS_NOT_FOUND',
  'ANALYSIS_EXPIRED',
  'FILE_NOT_FOUND',
  'INVALID_QUERY',
  'ABORTED',
  'AI_DISABLED',
  'AI_DAILY_LIMIT',
  'AI_CLIENT_LIMIT',
  'SOURCE_UNSUPPORTED',
  'SOURCE_NOT_FOUND',
  'SOURCE_MISMATCH',
]);

/**
 * Turns an ApiError into what the UI shows. Codes the UI does not know get a
 * generic title, but the backend's message is still shown (Use Case 5).
 */
export function describeError(error: ApiError): ErrorDescription {
  return {
    title: TITLES[error.code] ?? 'Something went wrong',
    message: error.message,
    hint: error.hint,
    retryable: !NOT_RETRYABLE.has(error.code),
  };
}
