import {ApiError, isApiErrorBody} from './errors.ts';
import type {
  Analysis,
  DependencyGraph,
  FileDetail,
  SearchRequest,
  SearchResponse,
  StartAnalysisRequest,
  StartAnalysisResponse,
} from './types.ts';

/** Per-request options accepted by every ApiClient method. */
export interface RequestOptions {
  /** Cancels the request. The promise then rejects with code ABORTED. */
  signal?: AbortSignal;
  /** Overrides the default timeout. The promise rejects with code TIMEOUT. */
  timeoutMs?: number;
}

/** Default timeout for every request except search. */
export const DEFAULT_TIMEOUT_MS = 10_000;

/** Search must answer within 5 seconds (Use Case 2). */
export const SEARCH_TIMEOUT_MS = 5_000;

/**
 * Everything the UI needs from the backend. Every method rejects only with
 * ApiError.
 */
export interface ApiClient {
  /** POST /analyses: starts a new analysis or reuses a cached one. */
  startAnalysis(
    request: StartAnalysisRequest,
    options?: RequestOptions,
  ): Promise<StartAnalysisResponse>;

  /** GET /analyses/{id}: status, stage and summary. */
  getAnalysis(analysisId: string, options?: RequestOptions): Promise<Analysis>;

  /**
   * DELETE /analyses/{id}: cancels a running analysis (Use Case 1, 3a).
   * Not yet in the documented API; proposed to the backend team.
   */
  cancelAnalysis(analysisId: string, options?: RequestOptions): Promise<void>;

  /** GET /analyses/{id}/graph: module groups, file nodes and import edges. */
  getGraph(
    analysisId: string,
    options?: RequestOptions,
  ): Promise<DependencyGraph>;

  /** GET /analyses/{id}/files/{path}: data for the file detail panel. */
  getFile(
    analysisId: string,
    path: string,
    options?: RequestOptions,
  ): Promise<FileDetail>;

  /** GET /analyses/{id}/search: one page of the ranked reading list. */
  search(
    analysisId: string,
    request: SearchRequest,
    options?: RequestOptions,
  ): Promise<SearchResponse>;
}

/**
 * Encodes a repository path for the URL, keeping the slashes between
 * segments. The backend route needs FastAPI's `{path:path}` converter.
 */
export function encodeFilePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/');
}

/** ApiClient that talks to the real backend over fetch. */
export class HttpApiClient implements ApiClient {
  private readonly baseUrl: string;
  private readonly fetchFn: typeof fetch;

  /**
   * @param baseUrl Where the API lives, e.g. "/api" or
   *     "http://localhost:8000". A trailing slash is ignored.
   * @param fetchFn Replaceable for tests.
   */
  constructor(baseUrl: string, fetchFn: typeof fetch = fetch) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    // Calling fetch as a method of another object throws "Illegal
    // invocation" in browsers, so keep it unbound from this class.
    this.fetchFn = (input, init) => fetchFn(input, init);
  }

  startAnalysis(
    request: StartAnalysisRequest,
    options?: RequestOptions,
  ): Promise<StartAnalysisResponse> {
    return this.request('POST', '/analyses', options, request);
  }

  getAnalysis(analysisId: string, options?: RequestOptions): Promise<Analysis> {
    return this.request(
      'GET',
      `/analyses/${encodeURIComponent(analysisId)}`,
      options,
    );
  }

  async cancelAnalysis(
    analysisId: string,
    options?: RequestOptions,
  ): Promise<void> {
    await this.request<unknown>(
      'DELETE',
      `/analyses/${encodeURIComponent(analysisId)}`,
      options,
    );
  }

  getGraph(
    analysisId: string,
    options?: RequestOptions,
  ): Promise<DependencyGraph> {
    return this.request(
      'GET',
      `/analyses/${encodeURIComponent(analysisId)}/graph`,
      options,
    );
  }

  getFile(
    analysisId: string,
    path: string,
    options?: RequestOptions,
  ): Promise<FileDetail> {
    return this.request(
      'GET',
      `/analyses/${encodeURIComponent(analysisId)}/files/${encodeFilePath(path)}`,
      options,
    );
  }

  search(
    analysisId: string,
    request: SearchRequest,
    options?: RequestOptions,
  ): Promise<SearchResponse> {
    const params = new URLSearchParams({q: request.q});
    if (request.limit !== undefined) {
      params.set('limit', String(request.limit));
    }
    if (request.offset !== undefined) {
      params.set('offset', String(request.offset));
    }
    return this.request(
      'GET',
      `/analyses/${encodeURIComponent(analysisId)}/search?${params.toString()}`,
      {timeoutMs: SEARCH_TIMEOUT_MS, ...options},
    );
  }

  /**
   * Sends one request and parses the JSON response. Turns every failure
   * (network, timeout, cancel, error status, unreadable body) into ApiError.
   */
  private async request<T>(
    method: string,
    path: string,
    options: RequestOptions = {},
    body?: unknown,
  ): Promise<T> {
    const timeoutSignal = AbortSignal.timeout(
      options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    );
    const signal = options.signal
      ? AbortSignal.any([options.signal, timeoutSignal])
      : timeoutSignal;

    let response: Response;
    try {
      response = await this.fetchFn(`${this.baseUrl}${path}`, {
        method,
        signal,
        headers:
          body === undefined
            ? {Accept: 'application/json'}
            : {Accept: 'application/json', 'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (error: unknown) {
      throw toRequestError(error, options.signal, timeoutSignal);
    }

    if (!response.ok) {
      throw await toResponseError(response);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    try {
      return (await response.json()) as T;
    } catch (error: unknown) {
      // Reading the body can also be interrupted by a cancel or timeout.
      if (options.signal?.aborted || timeoutSignal.aborted) {
        throw toRequestError(error, options.signal, timeoutSignal);
      }
      throw new ApiError(
        'UNKNOWN',
        'The server sent a response RepoLens could not read.',
        null,
        response.status,
      );
    }
  }
}

/** Maps a failure to send a request (no response) to an ApiError. */
function toRequestError(
  error: unknown,
  callerSignal: AbortSignal | undefined,
  timeoutSignal: AbortSignal,
): ApiError {
  if (callerSignal?.aborted) {
    return new ApiError('ABORTED', 'The request was cancelled.');
  }
  if (timeoutSignal.aborted) {
    return new ApiError(
      'TIMEOUT',
      'The server took too long to respond.',
      'Try again in a moment.',
    );
  }
  console.error('RepoLens API request failed', error);
  return new ApiError(
    'NETWORK_ERROR',
    'Could not reach the RepoLens server.',
    'Check your connection and try again.',
  );
}

/** Maps a non-2xx response to an ApiError, reading its body if possible. */
async function toResponseError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON; fall through to the generic error below.
  }
  if (isApiErrorBody(body)) {
    return ApiError.fromBody(body, response.status);
  }
  return new ApiError(
    'UNKNOWN',
    `The server returned an unexpected error (HTTP ${response.status}).`,
    'Try again in a moment.',
    response.status,
  );
}
