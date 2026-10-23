import type {ApiErrorBody} from './types.ts';

/**
 * Error codes the backend is expected to return, taken from the use cases in
 * the living document. The backend may add codes; the UI must still show the
 * message for any code it does not recognize (Use Case 5).
 */
export const SERVER_ERROR_CODES = [
  'INVALID_URL',
  'UNSUPPORTED_HOST',
  'REPO_NOT_FOUND',
  'REF_NOT_FOUND',
  'REPO_EMPTY',
  'NO_PYTHON_FILES',
  'TOO_MANY_FILES',
  'REPO_TOO_LARGE',
  'RATE_LIMITED',
  'GITHUB_UNAVAILABLE',
  'DOWNLOAD_FAILED',
  'ANALYSIS_FAILED',
  'ANALYSIS_NOT_FOUND',
  'ANALYSIS_NOT_READY',
  'ANALYSIS_EXPIRED',
  'FILE_NOT_FOUND',
  'INVALID_QUERY',
  'INTERNAL_ERROR',
] as const;

/** Error codes produced by the client itself, never by the backend. */
export const CLIENT_ERROR_CODES = [
  /** The backend could not be reached. */
  'NETWORK_ERROR',
  /** The backend did not answer within the timeout. */
  'TIMEOUT',
  /** The caller cancelled the request. */
  'ABORTED',
  /** The backend answered with an error we could not read. */
  'UNKNOWN',
] as const;

export type ServerErrorCode = (typeof SERVER_ERROR_CODES)[number];
export type ClientErrorCode = (typeof CLIENT_ERROR_CODES)[number];
export type KnownErrorCode = ServerErrorCode | ClientErrorCode;

const KNOWN_CODES: ReadonlySet<string> = new Set<string>([
  ...SERVER_ERROR_CODES,
  ...CLIENT_ERROR_CODES,
]);

/** Whether the UI has a specific message for this code. */
export function isKnownErrorCode(code: string): code is KnownErrorCode {
  return KNOWN_CODES.has(code);
}

/** The single error type every ApiClient method rejects with. */
export class ApiError extends Error {
  /**
   * Backend or client error code. Kept as a string because the backend may
   * send codes this version of the UI does not know.
   */
  readonly code: string;
  /** Suggested next step for the user, if any. */
  readonly hint: string | null;
  /** HTTP status, or null when no response was received. */
  readonly httpStatus: number | null;

  constructor(
    code: string,
    message: string,
    hint: string | null = null,
    httpStatus: number | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.hint = hint;
    this.httpStatus = httpStatus;
  }

  /** Builds an ApiError from an error response body. */
  static fromBody(body: ApiErrorBody, httpStatus: number | null = null) {
    return new ApiError(body.code, body.message, body.hint ?? null, httpStatus);
  }

  /** Converts the error back to the `{code, message, hint}` shape. */
  toBody(): ApiErrorBody {
    return {code: this.code, message: this.message, hint: this.hint};
  }
}

/**
 * Returns `error` if it is an ApiError, or wraps anything else (a bug, most
 * likely) as UNKNOWN so the UI can still show it.
 */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  console.error('Unexpected error', error);
  return new ApiError('UNKNOWN', 'Something unexpected went wrong.');
}

/** Whether a parsed JSON value has the `{code, message, hint}` shape. */
export function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record['code'] === 'string' &&
    typeof record['message'] === 'string' &&
    (record['hint'] === undefined ||
      record['hint'] === null ||
      typeof record['hint'] === 'string')
  );
}
