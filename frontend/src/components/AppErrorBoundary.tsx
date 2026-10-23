import type {ReactNode} from 'react';
import {Component} from 'react';

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  failed: boolean;
}

/**
 * Last line of defense: if rendering throws, show a way back instead of a
 * blank page (Use Case 5: the app must not crash).
 */
export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  override state: AppErrorBoundaryState = {failed: false};

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return {failed: true};
  }

  override componentDidCatch(error: unknown) {
    console.error('RepoLens failed to render', error);
  }

  override render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="page" id="main" tabIndex={-1}>
        <h1>Something went wrong</h1>
        <p className="lede">
          RepoLens hit an unexpected problem showing this page. Reloading
          usually fixes it.
        </p>
        <p>
          <button
            type="button"
            className="button button--primary"
            onClick={() => window.location.reload()}
          >
            Reload the page
          </button>{' '}
          <a className="button" href="/">
            Go to the home page
          </a>
        </p>
      </main>
    );
  }
}
