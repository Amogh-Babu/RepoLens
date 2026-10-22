import {screen} from '@testing-library/react';
import {renderApp} from './test/renderApp.tsx';

describe('App routes', () => {
  it('renders the landing page at /', () => {
    renderApp('/');
    expect(
      screen.getByRole('heading', {level: 1, name: 'RepoLens'}),
    ).toBeInTheDocument();
  });

  it('renders the analysis page with the analysis ID from the URL', () => {
    renderApp('/analysis/abc123');
    expect(
      screen.getByRole('heading', {level: 1, name: 'Analysis'}),
    ).toBeInTheDocument();
    expect(screen.getByText('abc123')).toBeInTheDocument();
  });

  it('renders the not-found page for an unknown route', () => {
    renderApp('/does-not-exist');
    expect(
      screen.getByRole('heading', {level: 1, name: 'Page not found'}),
    ).toBeInTheDocument();
  });
});
