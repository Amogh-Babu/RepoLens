import {screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MockApiClient} from '../api/mock/mockClient.ts';
import type {Analysis} from '../api/types.ts';
import {renderApp} from '../test/renderApp.tsx';
import {clearSeen, hasSeen} from '../utils/seenFlags.ts';

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
    const startAnalysis = vi.spyOn(client, 'startAnalysis');

    await user.click(await screen.findByRole('button', {name: 'Try again'}));

    expect(startAnalysis).toHaveBeenCalledWith({
      url: 'https://github.com/someone/crash',
    });
    // The mock fails this repository every time, so the new run (mock-2)
    // ends in the failure banner too. Query afresh each time: the old
    // banner is replaced when the page moves to the new run.
    await vi.waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'The analysis failed',
      ),
    );
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
    await user.click(await screen.findByRole('tab', {name: 'Files'}));

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

describe('AnalysisPage tour', () => {
  it('opens the tour on the first visit and not after it is skipped', async () => {
    clearSeen('workspace-tour');
    const user = userEvent.setup();
    await renderFinished('flask-auth');

    expect(
      await screen.findByRole('dialog', {name: 'Welcome to RepoLens'}),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', {name: 'Skip tour'}));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(hasSeen('workspace-tour')).toBe(true);
  });

  it('does not open by itself once seen, and Help reopens it', async () => {
    const user = userEvent.setup();
    await renderFinished('flask-auth');

    await user.click(await screen.findByRole('button', {name: 'Help'}));

    expect(
      screen.getByRole('dialog', {name: 'Welcome to RepoLens'}),
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

  it('scopes the map to a feature area and restores it on outside selection', async () => {
    const user = userEvent.setup();
    await renderFinished('flask-auth');

    const featureAreas = await screen.findByRole('heading', {
      name: 'Feature areas',
    });
    const featureAreaSection = featureAreas.closest('section');
    if (featureAreaSection === null)
      throw new Error('Feature area section missing.');
    await user.click(
      within(featureAreaSection).getByRole('button', {name: /auth.*4 files/}),
    );
    expect(
      await screen.findByRole('button', {name: 'File app/auth/views.py'}),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('tab', {name: 'Files'}));
    await user.click(await screen.findByRole('treeitem', {name: 'db.py'}));

    expect(
      await screen.findByRole('button', {name: 'File app/db.py'}),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: 'All files'}),
    ).not.toBeInTheDocument();
  });

  it('expands the module of a file selected in the explorer', async () => {
    const user = userEvent.setup();
    await renderFinished('flask-auth');
    await user.click(await screen.findByRole('tab', {name: 'Files'}));

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
      await screen.findByRole('button', {name: 'Fit'}),
    ).toBeInTheDocument();
  });
});

describe('AnalysisPage search', () => {
  async function search(query: string) {
    const user = userEvent.setup();
    await renderFinished('flask-auth');
    await user.type(
      await screen.findByRole('searchbox', {name: 'Search this repository'}),
      `${query}{Enter}`,
    );
    return user;
  }

  it('shows the reading list in its own tab', async () => {
    await search('login');

    expect(
      await screen.findByRole('tab', {name: /Reading list \(\d+\)/}),
    ).toHaveAttribute('aria-selected', 'true');
    expect(
      await screen.findByRole('heading', {name: /Reading order for/}),
    ).toBeInTheDocument();
  });

  it('opens an entry and steps through the reading order', async () => {
    const user = await search('login');

    await user.click(
      await screen.findByRole('button', {name: /1\. app\/auth\/service\.py/}),
    );
    const panel = await screen.findByRole('complementary', {
      name: 'service.py',
    });
    expect(within(panel).getByText(/#1 of \d+ for/)).toBeInTheDocument();

    await user.click(
      within(panel).getByRole('button', {name: /Next in reading order/}),
    );

    const next = await screen.findByRole('complementary', {
      name: /^(?!service\.py)/,
    });
    expect(within(next).getByText(/#2 of \d+ for/)).toBeInTheDocument();
  });

  it('says when nothing matches', async () => {
    await search('kubernetes');

    expect(await screen.findByText(/No files match/)).toBeInTheDocument();
  });

  it('filters the list view to search matches and can show all files', async () => {
    const user = await search('login');
    await user.click(await screen.findByRole('button', {name: 'List'}));
    const map = screen.getByRole('region', {name: 'Dependency map'});
    expect(
      within(map).queryByRole('button', {name: /config\.py/}),
    ).not.toBeInTheDocument();
    await user.click(
      within(map).getByRole('checkbox', {name: 'Only show matches'}),
    );
    expect(
      within(map).getByRole('button', {name: /config\.py/}),
    ).toBeInTheDocument();
  });

  it('reranks the same topic when the reading goal changes', async () => {
    const user = await search('login');
    await user.selectOptions(
      await screen.findByLabelText('What would you like to understand?'),
      'tests',
    );
    expect(
      await screen.findByText('Prioritized for tests.', {exact: false}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {name: 'Reading order for “login”'}),
    ).toBeInTheDocument();
  });

  it('closes the reading list when the search is cleared', async () => {
    const user = await search('login');
    await screen.findByRole('heading', {name: /Reading order for/});

    await user.click(screen.getByRole('button', {name: 'Clear search'}));

    expect(screen.queryByRole('tab', {name: /Reading list/})).toBeNull();
    expect(screen.getByRole('tab', {name: 'Files'})).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});

describe('AnalysisPage expiry', () => {
  it('offers Re-analyze when the analysis has already expired', async () => {
    await renderFinished('expired-repo');

    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent('This analysis has expired');
    expect(
      within(banner).getByRole('button', {name: 'Re-analyze'}),
    ).toBeInTheDocument();
  });

  it('keeps the workspace visible but read-only after it expires', async () => {
    const user = userEvent.setup();
    const client = new MockApiClient({latencyMs: 0, stageDurationMs: 0});
    const {analysisId} = await client.startAnalysis({
      url: 'https://github.com/someone/flask-auth',
    });
    const original = client.getAnalysis.bind(client);
    vi.spyOn(client, 'getAnalysis').mockImplementation(async (...args) => ({
      ...(await original(...args)),
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    }));
    renderApp(`/analysis/${analysisId}`, client);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This analysis has expired',
    );
    await user.click(await screen.findByRole('tab', {name: 'Files'}));
    expect(
      await screen.findByRole('treeitem', {name: 'auth/'}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('searchbox', {name: 'Search this repository'}),
    ).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Search'})).toBeDisabled();
  });

  it('starts a new analysis of the same repository from the banner', async () => {
    const user = userEvent.setup();
    const client = await renderFinished('expired-repo');
    const startAnalysis = vi.spyOn(client, 'startAnalysis');

    await user.click(await screen.findByRole('button', {name: 'Re-analyze'}));

    expect(startAnalysis).toHaveBeenCalledWith({
      url: 'https://github.com/someone/expired-repo',
    });
  });
});

describe('AnalysisPage titles', () => {
  it('names the tab after the repository', async () => {
    await renderFinished('flask-auth');

    await vi.waitFor(() =>
      expect(document.title).toBe('someone/flask-auth · RepoLens'),
    );
  });
});
