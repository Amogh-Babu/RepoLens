import {screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MockApiClient} from '../api/mock/mockClient.ts';
import type {Analysis} from '../api/types.ts';
import {renderApp} from '../test/renderApp.tsx';

const RUNNING: Analysis = {
  analysisId: 'a1',
  repoUrl: 'https://github.com/someone/flask-auth',
  ref: 'main',
  sha: '3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f',
  status: 'running',
  stage: 'parsing',
  summary: null,
  fromCache: false,
  createdAt: new Date().toISOString(),
  expiresAt: new Date(Date.now() + 86_400_000).toISOString(),
  error: null,
};

/** A client whose getAnalysis always returns `analysis`. */
function clientReturning(analysis: Analysis) {
  const client = new MockApiClient({latencyMs: 0});
  vi.spyOn(client, 'getAnalysis').mockResolvedValue(analysis);
  return client;
}

/** Starts a real mock analysis that finishes instantly and opens its page. */
async function renderFinished(repo: string) {
  const client = new MockApiClient({latencyMs: 0, stageDurationMs: 0});
  const {analysisId} = await client.startAnalysis({
    url: `https://github.com/someone/${repo}`,
  });
  renderApp(`/analysis/${analysisId}`, client);
  return client;
}

describe('AnalysisPage', () => {
  it('shows the current stage while the analysis runs', async () => {
    renderApp('/analysis/a1', clientReturning(RUNNING));

    expect(
      await screen.findByRole('heading', {name: 'someone/flask-auth'}),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Parsing Python files…',
    );
    const current = screen.getByText('Parsing Python files', {
      selector: 'li',
    });
    expect(current).toHaveAttribute('aria-current', 'step');
    expect(screen.getByRole('button', {name: 'Cancel'})).toBeInTheDocument();
  });

  it('says it is waiting while the analysis is queued', async () => {
    renderApp(
      '/analysis/a1',
      clientReturning({...RUNNING, status: 'queued', stage: 'resolving'}),
    );

    expect(await screen.findByText('Waiting to start…')).toBeInTheDocument();
  });

  it('shows the summary once the analysis completes', async () => {
    await renderFinished('flask-auth');

    expect(
      await screen.findByRole('region', {name: 'Analysis summary'}),
    ).toHaveTextContent('15 files');
    expect(screen.getByText('3f9c2a1')).toBeInTheDocument();
    expect(screen.getByText(/Analyzed (just now|1 minute ago)/)).toBeVisible();
  });

  it('says when the result came from the cache', async () => {
    await renderFinished('cached');

    expect(
      await screen.findByText(/Loaded from cache, analyzed/),
    ).toBeInTheDocument();
  });

  it('cancels the analysis', async () => {
    const user = userEvent.setup();
    const client = new MockApiClient({latencyMs: 0, stageDurationMs: 60_000});
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/someone/flask-auth',
    });
    renderApp(`/analysis/${analysisId}`, client);

    await user.click(await screen.findByRole('button', {name: 'Cancel'}));

    expect(
      await screen.findByText(/This analysis was cancelled/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: 'Analyze again'}),
    ).toBeInTheDocument();
  });

  it('explains a failed analysis without a Retry for bad input', async () => {
    await renderFinished('no-python');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('No Python files found');
    expect(alert).toHaveTextContent('supports only Python repositories');
    expect(screen.queryByRole('button', {name: 'Try again'})).toBeNull();
  });

  it('offers Try again for an unexpected failure and starts a new run', async () => {
    const user = userEvent.setup();
    const client = await renderFinished('crash');

    await user.click(await screen.findByRole('button', {name: 'Try again'}));

    // The mock fails this repository every time, so the new run (mock-2)
    // also ends in the failure banner, but at a new URL.
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect((await client.getAnalysis('mock-2')).repoUrl).toBe(
      'https://github.com/someone/crash',
    );
  });

  it('reports an unknown analysis id', async () => {
    renderApp('/analysis/does-not-exist');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Analysis not found');
    expect(
      screen.getByRole('link', {name: 'Analyze a repository'}),
    ).toBeInTheDocument();
  });
});

describe('AnalysisPage workspace', () => {
  it('opens a file from the explorer and follows its imports', async () => {
    const user = userEvent.setup();
    await renderFinished('flask-auth');

    await user.click(await screen.findByRole('treeitem', {name: 'auth/'}));
    await user.click(screen.getByRole('treeitem', {name: 'service.py'}));

    const panel = await screen.findByRole('complementary', {
      name: 'service.py',
    });
    expect(
      await within(panel).findByRole('link', {name: 'authenticate'}),
    ).toBeInTheDocument();

    await user.click(
      within(panel).getByRole('button', {name: 'app/models/user.py'}),
    );

    expect(
      await screen.findByRole('complementary', {name: 'user.py'}),
    ).toBeInTheDocument();
    expect(screen.getByRole('treeitem', {name: 'user.py'})).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('prompts the user to select a file', async () => {
    await renderFinished('flask-auth');

    expect(
      await screen.findByText(/Select a file to see its symbols/),
    ).toBeInTheDocument();
  });
});

describe('AnalysisPage map', () => {
  it('shows the dependency map with collapsed modules', async () => {
    await renderFinished('flask-auth');

    expect(
      await screen.findByRole('button', {name: /Module app\/auth, 4 files/}),
    ).toBeInTheDocument();
  });

  it('expands the module of a file selected in the explorer', async () => {
    const user = userEvent.setup();
    await renderFinished('flask-auth');

    await user.click(await screen.findByRole('treeitem', {name: 'db.py'}));

    expect(
      await screen.findByRole('button', {name: 'File app/db.py'}),
    ).toBeInTheDocument();
  });

  it('switches between the map and the list view', async () => {
    const user = userEvent.setup();
    await renderFinished('flask-auth');

    await user.click(await screen.findByRole('button', {name: 'List'}));
    expect(
      screen.getByRole('button', {name: /service\.py.*imported by 3/}),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', {name: 'Map'}));
    expect(
      await screen.findByRole('button', {name: 'Reset view'}),
    ).toBeInTheDocument();
  });
});
