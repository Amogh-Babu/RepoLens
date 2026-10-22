import {act, fireEvent, render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type {DependencyGraph} from '../../api/types.ts';
import {DependencyMap, RENDER_BUDGET_MS} from './DependencyMap.tsx';
import {ListFallback} from './ListFallback.tsx';

const GRAPH: DependencyGraph = {
  modules: [
    {id: 'app', name: 'app', filePaths: ['app/views.py']},
    {
      id: 'app/auth',
      name: 'auth',
      filePaths: ['app/auth/service.py', 'app/auth/tokens.py'],
    },
  ],
  files: [
    {path: 'app/views.py', module: 'app', parsed: true, lineCount: 1},
    {
      path: 'app/auth/service.py',
      module: 'app/auth',
      parsed: true,
      lineCount: 1,
    },
    {
      path: 'app/auth/tokens.py',
      module: 'app/auth',
      parsed: false,
      lineCount: 1,
    },
  ],
  edges: [
    {source: 'app/views.py', target: 'app/auth/service.py'},
    {source: 'app/auth/service.py', target: 'app/auth/tokens.py'},
  ],
};

function renderMap(props: Partial<Parameters<typeof DependencyMap>[0]> = {}) {
  const handlers = {
    onSelectFile: vi.fn(),
    onToggleModule: vi.fn(),
    onCollapseAll: vi.fn(),
    onTooSlow: vi.fn(),
  };
  render(
    <div style={{width: '800px', height: '600px'}}>
      <DependencyMap
        graph={GRAPH}
        expandedModules={new Set()}
        selectedPath={null}
        {...handlers}
        {...props}
      />
    </div>,
  );
  return handlers;
}

/** The React Flow node element that contains `name`. */
function nodeOf(name: RegExp) {
  const element = screen
    .getByRole('button', {name})
    .closest('.react-flow__node');
  if (element === null) throw new Error(`No map node for ${name}`);
  return element;
}

describe('DependencyMap', () => {
  // Map nodes are clicked with fireEvent: d3-drag reads event.view on
  // mousedown, which user-event leaves null in jsdom.
  it('starts with collapsed modules that expand when activated', () => {
    const {onToggleModule} = renderMap();

    expect(
      screen.getByRole('button', {name: /Module app, 1 file\./}),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {name: /Module app\/auth, 2 files/}),
    );

    expect(onToggleModule).toHaveBeenCalledWith('app/auth', true);
  });

  it('shows the files of an expanded module and selects one', () => {
    const {onSelectFile, onToggleModule} = renderMap({
      expandedModules: new Set(['app/auth']),
    });

    expect(
      screen.getByRole('button', {name: 'File app/auth/tokens.py, not parsed'}),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole('button', {name: 'File app/auth/service.py'}),
    );
    fireEvent.click(
      screen.getByRole('button', {name: 'Module app/auth. Collapse.'}),
    );

    expect(onSelectFile).toHaveBeenCalledWith('app/auth/service.py');
    expect(onToggleModule).toHaveBeenCalledWith('app/auth', false);
  });

  it('highlights the selection and its neighbors, dimming the rest', () => {
    renderMap({
      expandedModules: new Set(['app/auth']),
      selectedPath: 'app/auth/tokens.py',
    });

    expect(nodeOf(/File app\/auth\/tokens\.py/)).toHaveClass(
      'map-node--selected',
    );
    expect(nodeOf(/File app\/auth\/service\.py/)).toHaveClass(
      'map-node--related',
    );
    expect(nodeOf(/Module app,/)).toHaveClass('map-node--dimmed');
  });

  it('collapses every module from the toolbar', async () => {
    const user = userEvent.setup();
    const {onCollapseAll} = renderMap();

    await user.click(screen.getByRole('button', {name: 'Collapse all'}));

    expect(onCollapseAll).toHaveBeenCalled();
  });

  it('reports when the map does not draw within the budget', () => {
    vi.useFakeTimers();
    // Without size measurements React Flow never finishes drawing nodes.
    const original = globalThis.ResizeObserver;
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
    try {
      const {onTooSlow} = renderMap();

      act(() => vi.advanceTimersByTime(RENDER_BUDGET_MS - 1));
      expect(onTooSlow).not.toHaveBeenCalled();
      act(() => vi.advanceTimersByTime(1));
      expect(onTooSlow).toHaveBeenCalled();
    } finally {
      globalThis.ResizeObserver = original;
      vi.useRealTimers();
    }
  });

  it('does not count time while the page is hidden', () => {
    vi.useFakeTimers();
    const original = globalThis.ResizeObserver;
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
    const visibility = vi.spyOn(document, 'visibilityState', 'get');
    try {
      visibility.mockReturnValue('hidden');
      const {onTooSlow} = renderMap();

      act(() => vi.advanceTimersByTime(RENDER_BUDGET_MS * 5));
      expect(onTooSlow).not.toHaveBeenCalled();

      visibility.mockReturnValue('visible');
      act(() => {
        document.dispatchEvent(new Event('visibilitychange'));
        vi.advanceTimersByTime(RENDER_BUDGET_MS);
      });
      expect(onTooSlow).toHaveBeenCalled();
    } finally {
      visibility.mockRestore();
      globalThis.ResizeObserver = original;
      vi.useRealTimers();
    }
  });
});

describe('ListFallback', () => {
  it('lists files by module with import counts and selects them', async () => {
    const user = userEvent.setup();
    const onSelectFile = vi.fn();
    render(
      <ListFallback
        graph={GRAPH}
        selectedPath="app/views.py"
        onSelectFile={onSelectFile}
        message="The map could not be drawn."
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent(
      'The map could not be drawn.',
    );
    expect(screen.getByRole('heading', {name: 'app/auth'})).toBeInTheDocument();
    const service = screen.getByRole('button', {name: /service\.py/});
    expect(service).toHaveTextContent('imports 1 · imported by 1');
    expect(screen.getByRole('button', {name: /views\.py/})).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await user.click(service);
    expect(onSelectFile).toHaveBeenCalledWith('app/auth/service.py');
  });
});
