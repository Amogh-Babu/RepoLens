import {screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {ApiClient} from '../api/client.ts';
import {ApiError} from '../api/errors.ts';
import {MockApiClient} from '../api/mock/mockClient.ts';
import {renderApp} from '../test/renderApp.tsx';

async function analyze(url: string, ref = '') {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('GitHub repository URL'), url);
  if (ref !== '') {
    await user.type(screen.getByLabelText(/Branch, tag or commit/), ref);
  }
  await user.click(screen.getByRole('button', {name: 'Analyze'}));
  return user;
}

describe('LandingPage', () => {
  it('starts an analysis and opens the analysis page', async () => {
    renderApp('/');

    await analyze('https://github.com/someone/flask-auth');

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: 'someone/flask-auth',
      }),
    ).toBeInTheDocument();
  });

  it('sends the normalized URL and ref to the backend', async () => {
    const client = new MockApiClient({latencyMs: 0});
    const startAnalysis = vi.spyOn(client, 'startAnalysis');
    renderApp('/', client);

    await analyze('github.com/someone/flask-auth/tree/dev');

    expect(startAnalysis).toHaveBeenCalledWith(
      {url: 'https://github.com/someone/flask-auth', ref: 'dev'},
      expect.anything(),
    );
  });

  it('shows the backend error and keeps the input', async () => {
    renderApp('/');

    await analyze('https://github.com/someone/private-repo');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Repository not found');
    expect(alert).toHaveTextContent('does not exist or is not public');
    // Not retryable: the input itself has to change.
    expect(screen.queryByRole('button', {name: 'Retry'})).toBeNull();
    expect(screen.getByLabelText('GitHub repository URL')).toHaveValue(
      'https://github.com/someone/private-repo',
    );
  });

  it('offers Retry for a temporary failure', async () => {
    renderApp('/');

    await analyze('https://github.com/someone/rate-limited');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'GitHub is limiting requests',
    );
    expect(screen.getByRole('button', {name: 'Retry'})).toBeInTheDocument();
  });

  it('offers to analyze the default branch when the ref is missing', async () => {
    const client = new MockApiClient({latencyMs: 0});
    const startAnalysis = vi.spyOn(client, 'startAnalysis');
    renderApp('/', client);

    const user = await analyze(
      'https://github.com/someone/flask-auth',
      'missing-ref',
    );
    await user.click(
      await screen.findByRole('button', {name: 'Analyze the default branch'}),
    );

    expect(startAnalysis).toHaveBeenLastCalledWith(
      {url: 'https://github.com/someone/flask-auth'},
      expect.anything(),
    );
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: 'someone/flask-auth',
      }),
    ).toBeInTheDocument();
  });

  it('shows the message for an error code it does not know', async () => {
    const client: ApiClient = new MockApiClient({latencyMs: 0});
    vi.spyOn(client, 'startAnalysis').mockRejectedValue(
      new ApiError('BRAND_NEW_CODE', 'A new kind of failure.', null, 500),
    );
    renderApp('/', client);

    await analyze('https://github.com/someone/flask-auth');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Something went wrong');
    expect(alert).toHaveTextContent('A new kind of failure.');
    expect(screen.getByRole('button', {name: 'Retry'})).toBeInTheDocument();
  });

  it('shows a short user guide', () => {
    renderApp('/');

    expect(
      screen.getByRole('heading', {name: 'How it works'}),
    ).toBeInTheDocument();
    expect(screen.getByText(/up to 1,000 Python files/)).toBeInTheDocument();
  });
});
