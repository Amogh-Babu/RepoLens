import {ApiError} from '../errors.ts';
import {ANALYSIS_STAGES} from '../types.ts';
import {FLASK_AUTH_REPO} from './fixtureRepo.ts';
import {MockApiClient} from './mockClient.ts';

const STAGE_MS = 100;
const REPO_URL = 'https://github.com/someone/flask-auth';

/** A mock client with no latency and a clock the test controls. */
function setUp() {
  let time = 1_000_000;
  const client = new MockApiClient({
    latencyMs: 0,
    stageDurationMs: STAGE_MS,
    now: () => time,
  });
  return {
    client,
    advance: (ms: number) => {
      time += ms;
    },
    /** Starts an analysis and moves the clock until it has finished. */
    async completed(url = REPO_URL) {
      const {analysisId} = await client.startAnalysis({url});
      time += STAGE_MS * ANALYSIS_STAGES.length;
      return analysisId;
    },
  };
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error: unknown) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error('Expected the promise to reject');
}

describe('MockApiClient analyses', () => {
  it('moves through every stage, then completes with a summary', async () => {
    const {client, advance} = setUp();
    const {analysisId, status} = await client.startAnalysis({url: REPO_URL});
    expect(status).toBe('queued');

    const stages = [];
    for (let i = 0; i < ANALYSIS_STAGES.length; i++) {
      stages.push((await client.getAnalysis(analysisId)).stage);
      advance(STAGE_MS);
    }
    expect(stages).toEqual(ANALYSIS_STAGES);

    const done = await client.getAnalysis(analysisId);
    expect(done.status).toBe('completed');
    expect(done.repoUrl).toBe(REPO_URL);
    expect(done.summary).toEqual({
      filesAnalyzed: FLASK_AUTH_REPO.files.length,
      filesExcluded: FLASK_AUTH_REPO.filesExcluded,
      filesUnparsed: 1,
    });
  });

  it('uses a full commit SHA given as the ref', async () => {
    const {client} = setUp();
    const sha = 'a'.repeat(40);

    const result = await client.startAnalysis({url: REPO_URL, ref: sha});

    expect(result.sha).toBe(sha);
  });

  it('completes immediately for a cached repository', async () => {
    const {client} = setUp();
    const {analysisId, status} = await client.startAnalysis({
      url: 'https://github.com/someone/cached',
    });

    expect(status).toBe('completed');
    expect((await client.getAnalysis(analysisId)).fromCache).toBe(true);
  });

  it('cancels a running analysis', async () => {
    const {client, advance} = setUp();
    const {analysisId} = await client.startAnalysis({url: REPO_URL});
    advance(STAGE_MS);

    await client.cancelAnalysis(analysisId);

    expect((await client.getAnalysis(analysisId)).status).toBe('cancelled');
  });

  it.each([
    ['private-repo', 'REPO_NOT_FOUND', 404],
    ['rate-limited', 'RATE_LIMITED', 429],
  ])('rejects %s when starting', async (name, code, httpStatus) => {
    const {client} = setUp();

    const error = await rejection(
      client.startAnalysis({url: `https://github.com/someone/${name}`}),
    );

    expect(error.code).toBe(code);
    expect(error.httpStatus).toBe(httpStatus);
  });

  it('rejects a missing ref and a malformed URL', async () => {
    const {client} = setUp();

    const refError = await rejection(
      client.startAnalysis({url: REPO_URL, ref: 'missing-ref'}),
    );
    const urlError = await rejection(
      client.startAnalysis({url: 'https://gitlab.com/someone/repo'}),
    );

    expect(refError.code).toBe('REF_NOT_FOUND');
    expect(urlError.code).toBe('INVALID_URL');
  });

  it.each([
    ['empty-repo', 'REPO_EMPTY'],
    ['no-python', 'NO_PYTHON_FILES'],
    ['huge-repo', 'TOO_MANY_FILES'],
    ['crash', 'ANALYSIS_FAILED'],
  ])('fails %s partway through with %s', async (name, code) => {
    const {client, completed} = setUp();

    const analysisId = await completed(`https://github.com/someone/${name}`);
    const analysis = await client.getAnalysis(analysisId);

    expect(analysis.status).toBe('failed');
    expect(analysis.error?.code).toBe(code);
    expect(analysis.summary).toBeNull();
  });

  it('reports ANALYSIS_NOT_FOUND for an unknown id', async () => {
    const {client} = setUp();

    expect((await rejection(client.getAnalysis('nope'))).code).toBe(
      'ANALYSIS_NOT_FOUND',
    );
  });

  it('rejects with ABORTED when the signal is already aborted', async () => {
    const {client} = setUp();

    const error = await rejection(
      client.getAnalysis('mock-1', {signal: AbortSignal.abort()}),
    );

    expect(error.code).toBe('ABORTED');
  });
});

describe('MockApiClient results', () => {
  it('refuses results before the analysis has finished', async () => {
    const {client} = setUp();
    const {analysisId} = await client.startAnalysis({url: REPO_URL});

    expect((await rejection(client.getGraph(analysisId))).code).toBe(
      'ANALYSIS_NOT_READY',
    );
  });

  it('reports ANALYSIS_EXPIRED for an expired repository', async () => {
    const {client, completed} = setUp();
    const analysisId = await completed(
      'https://github.com/someone/expired-repo',
    );

    expect((await rejection(client.search(analysisId, {q: 'x'}))).code).toBe(
      'ANALYSIS_EXPIRED',
    );
  });

  it('groups files into modules with internal import edges', async () => {
    const {client, completed} = setUp();

    const graph = await client.getGraph(await completed());

    expect(graph.files).toHaveLength(FLASK_AUTH_REPO.files.length);
    expect(graph.modules.find(m => m.id === 'app/auth')?.filePaths).toEqual([
      'app/auth/__init__.py',
      'app/auth/views.py',
      'app/auth/service.py',
      'app/auth/tokens.py',
    ]);
    expect(graph.modules.find(m => m.id === '.')?.name).toBe('(root)');
    expect(graph.edges).toContainEqual({
      source: 'app/auth/service.py',
      target: 'app/models/user.py',
    });
    // Only internal imports become edges.
    const paths = new Set(graph.files.map(f => f.path));
    for (const edge of graph.edges) {
      expect(paths.has(edge.target)).toBe(true);
    }
  });

  it('returns file details with importers and a source link', async () => {
    const {client, completed} = setUp();

    const file = await client.getFile(await completed(), 'app/auth/service.py');

    expect(file.importedBy.sort()).toEqual([
      'app/auth/views.py',
      'app/routes.py',
      'tests/test_auth.py',
    ]);
    expect(file.sourceUrl).toBe(
      `${REPO_URL}/blob/${FLASK_AUTH_REPO.sha}/app/auth/service.py`,
    );
    expect(file.imports[0]).toEqual({
      rawName: 'app.models.user',
      kind: 'internal',
      targetPath: 'app/models/user.py',
      targetPackage: null,
    });
  });

  it('reports FILE_NOT_FOUND for a path outside the analysis', async () => {
    const {client, completed} = setUp();

    const error = await rejection(client.getFile(await completed(), 'nope.py'));

    expect(error.code).toBe('FILE_NOT_FOUND');
  });

  it('ranks files that other matches depend on first', async () => {
    const {client, completed} = setUp();

    const response = await client.search(await completed(), {q: ' login '});

    expect(response.query).toBe('login');
    expect(response.results[0]?.path).toBe('app/auth/service.py');
    expect(response.results[0]?.reason).toMatch(/^Defines login_user/);
    expect(response.results[0]?.orderReason).toMatch(/^Comes before /);
    expect(response.results.map(r => r.position)).toEqual(
      response.results.map((_r, i) => i + 1),
    );
  });

  it('pages results with limit and offset', async () => {
    const {client, completed} = setUp();
    const analysisId = await completed();

    const all = await client.search(analysisId, {q: 'app'});
    const page = await client.search(analysisId, {
      q: 'app',
      limit: 2,
      offset: 2,
    });

    expect(all.total).toBeGreaterThan(4);
    expect(page.total).toBe(all.total);
    expect(page.results).toEqual(all.results.slice(2, 4));
  });

  it('returns no results for a query that matches nothing', async () => {
    const {client, completed} = setUp();

    const response = await client.search(await completed(), {q: 'kubernetes'});

    expect(response.total).toBe(0);
    expect(response.results).toEqual([]);
  });

  it.each(['   ', 'x'.repeat(201)])(
    'rejects an invalid query (%#)',
    async q => {
      const {client, completed} = setUp();

      const error = await rejection(client.search(await completed(), {q}));

      expect(error.code).toBe('INVALID_QUERY');
    },
  );
});

describe('MockApiClient AI summaries', () => {
  async function finished(aiEnabled = true) {
    const client = new MockApiClient({
      latencyMs: 0,
      stageDurationMs: 0,
      aiEnabled,
    });
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/someone/flask-auth',
    });
    return {client, analysisId};
  }

  it('generates once, then serves the cached summary', async () => {
    const {client, analysisId} = await finished();

    expect((await client.getAiStatus()).enabled).toBe(true);
    expect(
      (await client.getFileSummary(analysisId, 'app/auth/service.py')).status,
    ).toBe('notGenerated');
    const generated = await client.generateFileSummary(
      analysisId,
      'app/auth/service.py',
    );
    const cached = await client.getFileSummary(
      analysisId,
      'app/auth/service.py',
    );

    expect(generated.metadata?.cacheStatus).toBe('miss');
    expect(cached.status).toBe('completed');
    expect(cached.metadata?.cached).toBe(true);
    expect(cached.summary).toEqual(generated.summary);
    for (const item of generated.summary?.evidence ?? []) {
      expect(item.url).toContain(
        `/blob/${generated.sha}/app/auth/service.py#L`,
      );
    }
  });

  it('answers AI_DISABLED when AI summaries are off', async () => {
    const {client, analysisId} = await finished(false);

    expect((await client.getAiStatus()).enabled).toBe(false);
    await expect(
      client.generateFileSummary(analysisId, 'app/auth/service.py'),
    ).rejects.toMatchObject({code: 'AI_DISABLED'});
  });
});

describe('MockApiClient AI search overviews', () => {
  async function finished(aiEnabled = true) {
    const client = new MockApiClient({
      latencyMs: 0,
      stageDurationMs: 0,
      aiEnabled,
    });
    const {analysisId} = await client.startAnalysis({url: REPO_URL});
    return {client, analysisId};
  }

  it('reads a search notice with the AI status', async () => {
    const {client} = await finished();
    expect((await client.getAiStatus()).searchNotice).toMatch(/Mock mode/);
    const off = await finished(false);
    expect((await off.client.getAiStatus()).searchNotice).toBeNull();
  });

  it('generates once, then serves the cached overview', async () => {
    const {client, analysisId} = await finished();
    const request = {q: 'login', intent: 'implementation' as const};

    const before = await client.getSearchOverview(analysisId, request);
    const generated = await client.generateSearchOverview(analysisId, request);
    const cached = await client.getSearchOverview(analysisId, request);
    const again = await client.generateSearchOverview(analysisId, request);
    const regenerated = await client.generateSearchOverview(
      analysisId,
      request,
      {regenerate: true},
    );

    expect(before).toMatchObject({
      analysisId,
      query: 'login',
      intent: 'implementation',
      status: 'notGenerated',
      overview: null,
      metadata: null,
    });
    expect(generated.status).toBe('completed');
    expect(generated.metadata).toMatchObject({
      cached: false,
      cacheStatus: 'miss',
    });
    expect(cached.status).toBe('completed');
    expect(cached.overview).toEqual(generated.overview);
    expect(cached.metadata).toMatchObject({cached: true, cacheStatus: 'hit'});
    expect(again.metadata?.cacheStatus).toBe('hit');
    expect(regenerated.metadata).toMatchObject({
      cached: false,
      cacheStatus: 'regenerated',
    });
  });

  it('points at files from the reading list, in reading order', async () => {
    const {client, analysisId} = await finished();
    const search = await client.search(analysisId, {q: 'login'});

    const {overview} = await client.generateSearchOverview(analysisId, {
      q: 'login',
    });

    const paths = search.results.map(entry => entry.path);
    expect(overview?.startHere.path).toBe(paths[0]);
    expect(overview?.readNext.map(step => step.path)).toEqual(
      paths.slice(1, 1 + (overview?.readNext.length ?? 0)),
    );
    expect(overview?.summary).toContain('login');
  });

  it('keeps a separate overview per query and intent', async () => {
    const {client, analysisId} = await finished();
    await client.generateSearchOverview(analysisId, {q: 'login'});

    expect(
      (await client.getSearchOverview(analysisId, {q: 'login'})).status,
    ).toBe('completed');
    expect(
      (
        await client.getSearchOverview(analysisId, {
          q: 'login',
          intent: 'tests',
        })
      ).status,
    ).toBe('notGenerated');
    expect(
      (await client.getSearchOverview(analysisId, {q: 'session'})).status,
    ).toBe('notGenerated');
  });

  it('lists the cached file summaries it used', async () => {
    const {client, analysisId} = await finished();
    const {overview} = await client.generateSearchOverview(analysisId, {
      q: 'login',
    });
    const start = overview?.startHere.path ?? '';
    await client.generateFileSummary(analysisId, start);

    const regenerated = await client.generateSearchOverview(
      analysisId,
      {q: 'login'},
      {regenerate: true},
    );

    expect(regenerated.metadata?.usedFileSummaries).toEqual([start]);
  });

  it('reports noResults for a query that matches nothing', async () => {
    const {client, analysisId} = await finished();
    const request = {q: 'zzzz-nothing-matches'};

    expect((await client.getSearchOverview(analysisId, request)).status).toBe(
      'noResults',
    );
    const generated = await client.generateSearchOverview(analysisId, request);
    expect(generated).toMatchObject({status: 'noResults', overview: null});
  });

  it('rejects an empty query and answers AI_DISABLED when AI is off', async () => {
    const {client, analysisId} = await finished();
    expect(
      (await rejection(client.getSearchOverview(analysisId, {q: '  '}))).code,
    ).toBe('INVALID_QUERY');

    const off = await finished(false);
    await expect(
      off.client.getSearchOverview(off.analysisId, {q: 'login'}),
    ).rejects.toMatchObject({code: 'AI_DISABLED'});
    await expect(
      off.client.generateSearchOverview(off.analysisId, {q: 'login'}),
    ).rejects.toMatchObject({code: 'AI_DISABLED'});
  });

  it('rejects with ABORTED when the signal is already aborted', async () => {
    const {client, analysisId} = await finished();
    const controller = new AbortController();
    controller.abort();

    await expect(
      client.generateSearchOverview(
        analysisId,
        {q: 'login'},
        {signal: controller.signal},
      ),
    ).rejects.toMatchObject({code: 'ABORTED'});
  });
});
