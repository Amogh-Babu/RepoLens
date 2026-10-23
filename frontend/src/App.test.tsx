import {screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {renderApp} from './test/renderApp.tsx';

describe('App routes', () => {
  it('renders the landing page at /', () => {
    renderApp('/');
    expect(
      screen.getByRole('heading', {level: 1, name: 'RepoLens'}),
    ).toBeInTheDocument();
  });

  it('renders the analysis page while the analysis loads', () => {
    renderApp('/analysis/abc123');
    expect(
      screen.getByRole('heading', {level: 1, name: 'Analysis'}),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Loading the analysis…',
    );
  });

  it('renders the not-found page for an unknown route', () => {
    renderApp('/does-not-exist');
    expect(
      screen.getByRole('heading', {level: 1, name: 'Page not found'}),
    ).toBeInTheDocument();
  });

  it('sets the page title on the home page', () => {
    renderApp('/');
    expect(document.title).toBe('RepoLens');
  });

  it('titles the not-found page', () => {
    renderApp('/nope');
    expect(document.title).toBe('Page not found · RepoLens');
  });

  it('has a skip link to the main content', () => {
    renderApp('/');

    expect(screen.getByRole('link', {name: 'Skip to content'})).toHaveAttribute(
      'href',
      '#main',
    );
    expect(document.getElementById('main')).toBe(screen.getByRole('main'));
  });

  it('moves focus to the new page after navigating', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.type(
      screen.getByLabelText('GitHub repository URL'),
      'https://github.com/someone/flask-auth',
    );
    await user.click(screen.getByRole('button', {name: 'Analyze'}));

    await vi.waitFor(() => expect(screen.getByRole('main')).toHaveFocus());
    expect(screen.getByRole('main')).toHaveClass('analysis');
  });
});
