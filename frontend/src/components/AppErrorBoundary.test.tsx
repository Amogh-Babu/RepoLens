import {render, screen} from '@testing-library/react';
import {AppErrorBoundary} from './AppErrorBoundary.tsx';

function Broken(): never {
  throw new Error('boom');
}

describe('AppErrorBoundary', () => {
  it('shows a way back instead of a blank page', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <AppErrorBoundary>
        <Broken />
      </AppErrorBoundary>,
    );

    expect(
      screen.getByRole('heading', {name: 'Something went wrong'}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: 'Reload the page'}),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', {name: 'Go to the home page'}),
    ).toHaveAttribute('href', '/');
  });

  it('renders its children when nothing fails', () => {
    render(
      <AppErrorBoundary>
        <p>Fine</p>
      </AppErrorBoundary>,
    );

    expect(screen.getByText('Fine')).toBeInTheDocument();
  });
});
