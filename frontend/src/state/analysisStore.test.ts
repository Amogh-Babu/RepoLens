import {ApiError} from '../api/errors.ts';
import {MockApiClient} from '../api/mock/mockClient.ts';
import {ANALYSIS_STAGES} from '../api/types.ts';
import {createAnalysisStore} from './analysisStore.ts';

const STAGE_MS = 1_000;
const POLL_MS = 5;

/** A mock client whose clock the test moves forward. */
function setUp() {
  let time = 1_000_000;
  const client = new MockApiClient({
    latencyMs: 0,
    stageDurationMs: STAGE_MS,
    now: () => time,
  });
  return {
    client,
    advance(ms: number) {
      time += ms;
    },
  };
}

describe('createAnalysisStore', () => {
  it('polls until the analysis completes, then stops', async () => {
    const {client, advance} = setUp();
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/o/flask-auth',
    });
    const getAnalysis = vi.spyOn(client, 'getAnalysis');
    const store = createAnalysisStore(client, analysisId, {
      pollIntervalMs: POLL_MS,
    });

    store.getState().startPolling();
    await vi.waitFor(() =>
      expect(store.getState().analysis?.stage).toBe('resolving'),
    );
    advance(STAGE_MS * 2);
    await vi.waitFor(() =>
      expect(store.getState().analysis?.stage).toBe('filtering'),
    );
    advance(STAGE_MS * ANALYSIS_STAGES.length);
    await vi.waitFor(() =>
      expect(store.getState().analysis?.status).toBe('completed'),
    );

    const calls = getAnalysis.mock.calls.length;
    await new Promise(resolve => setTimeout(resolve, POLL_MS * 5));
    expect(getAnalysis.mock.calls.length).toBe(calls);
  });

  it('stops polling when asked', async () => {
    const {client} = setUp();
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/o/flask-auth',
    });
    const getAnalysis = vi.spyOn(client, 'getAnalysis');
    const store = createAnalysisStore(client, analysisId, {
      pollIntervalMs: POLL_MS,
    });

    store.getState().startPolling();
    await vi.waitFor(() => expect(store.getState().analysis).not.toBeNull());
    store.getState().stopPolling();

    const calls = getAnalysis.mock.calls.length;
    await new Promise(resolve => setTimeout(resolve, POLL_MS * 5));
    expect(getAnalysis.mock.calls.length).toBe(calls);
  });

  it('records a load failure and recovers on retry', async () => {
    const {client} = setUp();
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/o/flask-auth',
    });
    vi.spyOn(client, 'getAnalysis').mockRejectedValueOnce(
      new ApiError('NETWORK_ERROR', 'Could not reach the server.'),
    );
    const store = createAnalysisStore(client, analysisId, {
      pollIntervalMs: POLL_MS,
    });

    store.getState().startPolling();
    await vi.waitFor(() =>
      expect(store.getState().loadFailure?.code).toBe('NETWORK_ERROR'),
    );
    expect(store.getState().loadFailure?.error.retryable).toBe(true);

    store.getState().startPolling();
    await vi.waitFor(() => expect(store.getState().analysis).not.toBeNull());
    expect(store.getState().loadFailure).toBeNull();
    store.getState().stopPolling();
  });

  it('cancels a running analysis and shows it as cancelled', async () => {
    const {client} = setUp();
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/o/flask-auth',
    });
    const store = createAnalysisStore(client, analysisId, {
      pollIntervalMs: POLL_MS,
    });
    store.getState().startPolling();
    await vi.waitFor(() => expect(store.getState().analysis).not.toBeNull());

    await store.getState().cancel();

    await vi.waitFor(() =>
      expect(store.getState().analysis?.status).toBe('cancelled'),
    );
    expect(store.getState().cancelling).toBe(false);
  });

  it('records a cancel failure', async () => {
    const {client} = setUp();
    vi.spyOn(client, 'cancelAnalysis').mockRejectedValue(
      new ApiError('TIMEOUT', 'Too slow.'),
    );
    const store = createAnalysisStore(client, 'mock-1');

    await store.getState().cancel();

    expect(store.getState().cancelFailure?.code).toBe('TIMEOUT');
    expect(store.getState().cancelling).toBe(false);
  });
});

describe('createAnalysisStore graph and selection', () => {
  /** A store for an analysis that has already finished. */
  async function completedStore() {
    const client = new MockApiClient({latencyMs: 0, stageDurationMs: 0});
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/o/flask-auth',
    });
    const store = createAnalysisStore(client, analysisId, {
      pollIntervalMs: POLL_MS,
    });
    store.getState().startPolling();
    await vi.waitFor(() => expect(store.getState().graph).not.toBeNull());
    return {client, store};
  }

  it('loads the graph when the analysis completes', async () => {
    const {store} = await completedStore();

    expect(store.getState().graph?.files.length).toBeGreaterThan(0);
    expect([...store.getState().expandedDirs].sort()).toEqual(['app', 'tests']);
  });

  it('selects a file, expands its directories and loads its details', async () => {
    const {store} = await completedStore();

    store.getState().selectFile('app/auth/service.py');

    expect(store.getState().selectedPath).toBe('app/auth/service.py');
    expect(store.getState().expandedDirs.has('app/auth')).toBe(true);
    await vi.waitFor(() =>
      expect(
        store.getState().fileDetails['app/auth/service.py']?.importedBy,
      ).toHaveLength(3),
    );
  });

  it('does not refetch a file it already has', async () => {
    const {client, store} = await completedStore();
    const getFile = vi.spyOn(client, 'getFile');

    store.getState().selectFile('app/db.py');
    await vi.waitFor(() =>
      expect(store.getState().fileDetails['app/db.py']).toBeDefined(),
    );
    store.getState().selectFile('app/config.py');
    store.getState().selectFile('app/db.py');

    expect(getFile.mock.calls.map(call => call[1])).toEqual([
      'app/db.py',
      'app/config.py',
    ]);
  });

  it('records a file failure for the selected file', async () => {
    const {store} = await completedStore();

    store.getState().selectFile('missing.py');

    await vi.waitFor(() =>
      expect(store.getState().fileFailure?.code).toBe('FILE_NOT_FOUND'),
    );
  });

  it('clears the selection', async () => {
    const {store} = await completedStore();
    store.getState().selectFile('app/db.py');

    store.getState().selectFile(null);

    expect(store.getState().selectedPath).toBeNull();
  });

  it('expands and collapses directories', async () => {
    const {store} = await completedStore();

    store.getState().toggleDir('app/auth');
    expect(store.getState().expandedDirs.has('app/auth')).toBe(true);
    store.getState().toggleDir('app/auth');
    expect(store.getState().expandedDirs.has('app/auth')).toBe(false);
    store.getState().toggleDir('app/auth', false);
    expect(store.getState().expandedDirs.has('app/auth')).toBe(false);
  });
});

describe('createAnalysisStore map state', () => {
  async function completedStore() {
    const client = new MockApiClient({latencyMs: 0, stageDurationMs: 0});
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/o/flask-auth',
    });
    const store = createAnalysisStore(client, analysisId);
    store.getState().startPolling();
    await vi.waitFor(() => expect(store.getState().graph).not.toBeNull());
    return store;
  }

  it('starts with every module collapsed', async () => {
    const store = await completedStore();

    expect(store.getState().expandedModules.size).toBe(0);
  });

  it("expands the selected file's module", async () => {
    const store = await completedStore();

    store.getState().selectFile('app/auth/tokens.py');

    expect([...store.getState().expandedModules]).toEqual(['app/auth']);
  });

  it('toggles modules and collapses them all', async () => {
    const store = await completedStore();

    store.getState().toggleModule('app');
    store.getState().toggleModule('tests', true);
    expect([...store.getState().expandedModules].sort()).toEqual([
      'app',
      'tests',
    ]);
    store.getState().toggleModule('app');
    expect([...store.getState().expandedModules]).toEqual(['tests']);

    store.getState().collapseAllModules();
    expect(store.getState().expandedModules.size).toBe(0);
  });
});
