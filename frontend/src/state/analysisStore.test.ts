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
