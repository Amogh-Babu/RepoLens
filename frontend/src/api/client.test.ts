import {encodeFilePath, HttpApiClient} from './client.ts';
import {ApiError} from './errors.ts';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {'Content-Type': 'application/json'},
  });
}

/** A fetch stub that records each call and answers with `respond`. */
function stubFetch(respond: (url: string, init: RequestInit) => Response) {
  const calls: Array<{url: string; init: RequestInit}> = [];
  const fetchFn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const call = {url: String(input), init: init ?? {}};
    calls.push(call);
    return Promise.resolve(respond(call.url, call.init));
  });
  return {calls, fetchFn: fetchFn as typeof fetch};
}

/** A fetch stub that never answers until its signal aborts. */
function hangingFetch(): typeof fetch {
  return ((_input: RequestInfo | URL, init?: RequestInit) =>
    new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () =>
        reject(new DOMException('Aborted', 'AbortError')),
      );
    })) as typeof fetch;
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error: unknown) {
    if (error instanceof ApiError) return error;
    throw new Error('Expected ApiError', {cause: error});
  }
  throw new Error('Expected the promise to reject');
}

describe('HttpApiClient', () => {
  it('posts a new analysis as JSON', async () => {
    const {calls, fetchFn} = stubFetch(() =>
      jsonResponse({analysisId: 'a1', sha: 'abc', status: 'queued'}),
    );
    const client = new HttpApiClient('http://api.test/', fetchFn);

    const result = await client.startAnalysis({
      url: 'https://github.com/o/r',
      ref: 'main',
    });

    expect(result).toEqual({analysisId: 'a1', sha: 'abc', status: 'queued'});
    expect(calls[0]?.url).toBe('http://api.test/analyses');
    expect(calls[0]?.init.method).toBe('POST');
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({
      url: 'https://github.com/o/r',
      ref: 'main',
    });
  });

  it('builds the URL for each endpoint', async () => {
    const {calls, fetchFn} = stubFetch(() => jsonResponse({}));
    const client = new HttpApiClient('/api', fetchFn);

    await client.getAnalysis('a 1');
    await client.getGraph('a1');
    await client.getFile('a1', 'app/auth/my views.py');
    await client.search('a1', {q: 'login user', limit: 20, offset: 40});

    expect(calls.map(c => c.url)).toEqual([
      '/api/analyses/a%201',
      '/api/analyses/a1/graph',
      '/api/analyses/a1/files/app/auth/my%20views.py',
      '/api/analyses/a1/search?q=login+user&limit=20&offset=40',
    ]);
  });

  it('sends DELETE to cancel and accepts an empty 204 response', async () => {
    const {calls, fetchFn} = stubFetch(() => new Response(null, {status: 204}));
    const client = new HttpApiClient('/api', fetchFn);

    await expect(client.cancelAnalysis('a1')).resolves.toBeUndefined();
    expect(calls[0]?.init.method).toBe('DELETE');
  });

  it('turns a structured error response into an ApiError', async () => {
    const {fetchFn} = stubFetch(() =>
      jsonResponse(
        {
          code: 'REPO_NOT_FOUND',
          message: 'Not found or not public.',
          hint: 'Check the spelling.',
        },
        404,
      ),
    );
    const client = new HttpApiClient('/api', fetchFn);

    const error = await rejection(
      client.startAnalysis({url: 'https://github.com/o/r'}),
    );

    expect(error.code).toBe('REPO_NOT_FOUND');
    expect(error.message).toBe('Not found or not public.');
    expect(error.hint).toBe('Check the spelling.');
    expect(error.httpStatus).toBe(404);
  });

  it('keeps unrecognized error codes and their message', async () => {
    const {fetchFn} = stubFetch(() =>
      jsonResponse({code: 'SOMETHING_NEW', message: 'Explained.'}, 400),
    );
    const client = new HttpApiClient('/api', fetchFn);

    const error = await rejection(client.getGraph('a1'));

    expect(error.code).toBe('SOMETHING_NEW');
    expect(error.message).toBe('Explained.');
    expect(error.hint).toBeNull();
  });

  it('falls back to UNKNOWN when the error body is not the error shape', async () => {
    const {fetchFn} = stubFetch(() => jsonResponse({detail: []}, 422));
    const client = new HttpApiClient('/api', fetchFn);

    const error = await rejection(client.getGraph('a1'));

    expect(error.code).toBe('UNKNOWN');
    expect(error.httpStatus).toBe(422);
  });

  it('falls back to UNKNOWN when the error body is not JSON', async () => {
    const {fetchFn} = stubFetch(
      () => new Response('<html>Bad gateway</html>', {status: 502}),
    );
    const client = new HttpApiClient('/api', fetchFn);

    const error = await rejection(client.getGraph('a1'));

    expect(error.code).toBe('UNKNOWN');
    expect(error.httpStatus).toBe(502);
  });

  it('reports UNKNOWN when a success body is not JSON', async () => {
    const {fetchFn} = stubFetch(() => new Response('oops', {status: 200}));
    const client = new HttpApiClient('/api', fetchFn);

    const error = await rejection(client.getGraph('a1'));

    expect(error.code).toBe('UNKNOWN');
  });

  it('reports NETWORK_ERROR when the server cannot be reached', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const fetchFn = (() =>
      Promise.reject(new TypeError('Failed to fetch'))) as typeof fetch;
    const client = new HttpApiClient('/api', fetchFn);

    const error = await rejection(client.getGraph('a1'));

    expect(error.code).toBe('NETWORK_ERROR');
    expect(error.httpStatus).toBeNull();
  });

  it('reports TIMEOUT when the server does not answer in time', async () => {
    const client = new HttpApiClient('/api', hangingFetch());

    const error = await rejection(client.getGraph('a1', {timeoutMs: 10}));

    expect(error.code).toBe('TIMEOUT');
  });

  it('reports ABORTED when the caller cancels', async () => {
    const client = new HttpApiClient('/api', hangingFetch());
    const controller = new AbortController();

    const pending = rejection(
      client.search('a1', {q: 'auth'}, {signal: controller.signal}),
    );
    controller.abort();

    expect((await pending).code).toBe('ABORTED');
  });
});

describe('encodeFilePath', () => {
  it('encodes each segment but keeps the slashes', () => {
    expect(encodeFilePath('a b/c#d/e?.py')).toBe('a%20b/c%23d/e%3F.py');
  });
});
