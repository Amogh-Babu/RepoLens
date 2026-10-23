import type {ReactNode} from 'react';
import {Component} from 'react';

interface MapErrorBoundaryProps {
  onError: () => void;
  children: ReactNode;
}

interface MapErrorBoundaryState {
  failed: boolean;
}

/** Switches to the list view if drawing the map throws. */
export class MapErrorBoundary extends Component<
  MapErrorBoundaryProps,
  MapErrorBoundaryState
> {
  override state: MapErrorBoundaryState = {failed: false};

  static getDerivedStateFromError(): MapErrorBoundaryState {
    return {failed: true};
  }

  override componentDidCatch(error: unknown) {
    console.error('The dependency map failed to render', error);
    this.props.onError();
  }

  override render() {
    return this.state.failed ? null : this.props.children;
  }
}
