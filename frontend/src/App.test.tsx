import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {App} from './App.tsx';

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('App routes', () => {
  it('renders the landing page at /', () => {
    renderAt('/');
    expect(
      screen.getByRole('heading', {level: 1, name: 'RepoLens'}),
    ).toBeInTheDocument();
  });

  it('renders the analysis page with the analysis ID from the URL', () => {
    renderAt('/analysis/abc123');
    expect(
      screen.getByRole('heading', {level: 1, name: 'Analysis'}),
    ).toBeInTheDocument();
    expect(screen.getByText('abc123')).toBeInTheDocument();
  });

  it('renders the not-found page for an unknown route', () => {
    renderAt('/does-not-exist');
    expect(
      screen.getByRole('heading', {level: 1, name: 'Page not found'}),
    ).toBeInTheDocument();
  });
});
