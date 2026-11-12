import {act, fireEvent, render, screen, within} from '@testing-library/react';
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
        matchedPaths={null}
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

  it('keeps a selected file visible through its collapsed module', () => {
    renderMap({selectedPath: 'app/auth/tokens.py'});

    expect(nodeOf(/Module app\/auth,/)).toHaveClass('map-node--selected');
    expect(screen.getByRole('status')).toHaveTextContent(
      'Inside app/auth/ (collapsed). Expand to see app/auth/tokens.py.',
    );
  });

  it('distinguishes imports from imported-by edges around the selection', () => {
    renderMap({
      expandedModules: new Set(['app/auth']),
      selectedPath: 'app/auth/service.py',
    });

    expect(
      document.querySelector('.react-flow__edge.map-edge--imports'),
    ).toBeInTheDocument();
    expect(
      document.querySelector('.react-flow__edge.map-edge--imported-by'),
    ).toBeInTheDocument();
    const key = screen.getByRole('region', {name: 'Map key'});
    expect(key).toHaveTextContent('The selected file imports this');
    expect(key).toHaveTextContent('This imports the selected file');
  });

  it('greys out unrelated files by default and offers to hide them', () => {
    renderMap({
      expandedModules: new Set(['app/auth']),
      selectedPath: 'app/auth/tokens.py',
      onHideUnrelatedChange: vi.fn(),
    });

    expect(
      screen.getByRole('checkbox', {name: 'Hide unrelated files'}),
    ).not.toBeChecked();
    expect(nodeOf(/Module app,/)).toHaveClass('map-node--dimmed');
  });

  it('draws only the selected file and its neighbors when hiding unrelated files', () => {
    renderMap({
      selectedPath: 'app/auth/tokens.py',
      hideUnrelated: true,
      onHideUnrelatedChange: vi.fn(),
    });

    expect(nodeOf(/File app\/auth\/tokens\.py/)).toHaveClass(
      'map-node--selected',
    );
    expect(nodeOf(/File app\/auth\/service\.py/)).toHaveClass(
      'map-node--related',
    );
    expect(
      screen.queryByRole('button', {name: /views\.py|Module app,/}),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: 'Collapse all'}),
    ).not.toBeInTheDocument();
  });

  it('shows only the neighbors of the selection even during a search', () => {
    renderMap({
      selectedPath: 'app/views.py',
      matchedPaths: new Set(['app/auth/tokens.py']),
      matchesOnly: true,
      onMatchesOnlyChange: vi.fn(),
      hideUnrelated: true,
      onHideUnrelatedChange: vi.fn(),
    });

    expect(
      screen.getByRole('button', {name: 'File app/auth/service.py'}),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: /tokens\.py/}),
    ).not.toBeInTheDocument();
  });

  it('switches hiding unrelated files from the toolbar', async () => {
    const user = userEvent.setup();
    const onHideUnrelatedChange = vi.fn();
    renderMap({selectedPath: 'app/views.py', onHideUnrelatedChange});

    await user.click(
      screen.getByRole('checkbox', {name: 'Hide unrelated files'}),
    );

    expect(onHideUnrelatedChange).toHaveBeenCalledWith(true);
  });

  it('offers to hide unrelated files only while a file is selected', () => {
    renderMap({hideUnrelated: true, onHideUnrelatedChange: vi.fn()});

    expect(
      screen.queryByRole('checkbox', {name: 'Hide unrelated files'}),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: /Module app,/}),
    ).toBeInTheDocument();
  });

  it('explains every box, color and line in a key that starts open', () => {
    renderMap();

    const key = screen.getByRole('region', {name: 'Map key'});
    for (const text of [
      'Folder. Click to open it.',
      'Open folder. Click its name to close it.',
      'Selected file',
      'Imports or is imported by the selected file',
      'Matches your search',
      'Not connected to the selection or search',
      'The arrow points to the file being imported.',
      'Number of imports along one line',
    ]) {
      expect(key).toHaveTextContent(text);
    }
    expect(screen.getByRole('button', {name: 'Key'})).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('hides the key and remembers it', async () => {
    const user = userEvent.setup();
    renderMap();

    await user.click(screen.getByRole('button', {name: 'Hide the key'}));

    expect(
      screen.queryByRole('region', {name: 'Map key'}),
    ).not.toBeInTheDocument();
    expect(localStorage.getItem('repolens.map-key')).toBe('closed');

    await user.click(screen.getByRole('button', {name: 'Key'}));
    expect(screen.getByRole('region', {name: 'Map key'})).toBeInTheDocument();
  });

  it('starts with the key closed if the viewer closed it before', () => {
    localStorage.setItem('repolens.map-key', 'closed');
    renderMap();

    expect(
      screen.queryByRole('region', {name: 'Map key'}),
    ).not.toBeInTheDocument();
  });

  it('highlights search matches when nothing is selected', () => {
    renderMap({
      expandedModules: new Set(['app/auth']),
      matchedPaths: new Set(['app/auth/service.py']),
    });

    expect(nodeOf(/File app\/auth\/service\.py/)).toHaveClass(
      'map-node--match',
    );
    expect(nodeOf(/File app\/auth\/tokens\.py/)).toHaveClass(
      'map-node--dimmed',
    );
    expect(nodeOf(/Module app,/)).toHaveClass('map-node--dimmed');
  });

  it('marks a collapsed module that contains a match', () => {
    renderMap({matchedPaths: new Set(['app/auth/tokens.py'])});

    expect(nodeOf(/Module app\/auth,/)).toHaveClass('map-node--match');
  });

  it('lets the selection take over from search highlighting', () => {
    renderMap({
      expandedModules: new Set(['app/auth']),
      selectedPath: 'app/auth/tokens.py',
      matchedPaths: new Set(['app/views.py']),
    });

    expect(nodeOf(/File app\/auth\/tokens\.py/)).toHaveClass(
      'map-node--selected',
    );
    expect(nodeOf(/Module app,/)).not.toHaveClass('map-node--match');
  });

  it('draws only the matches, with their modules open, in matches-only mode', () => {
    renderMap({
      matchedPaths: new Set(['app/auth/tokens.py']),
      matchesOnly: true,
      onMatchesOnlyChange: vi.fn(),
    });

    expect(
      screen.getByRole('button', {name: 'File app/auth/tokens.py, not parsed'}),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: 'File app/auth/service.py'}),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {name: /Module app,/}),
    ).not.toBeInTheDocument();
    // Modules cannot be collapsed while only matches are shown.
    expect(
      screen.queryByRole('button', {name: /Collapse/}),
    ).not.toBeInTheDocument();
  });

  it('keeps the selected file on the map even if it is not a match', () => {
    renderMap({
      matchedPaths: new Set(['app/auth/tokens.py']),
      selectedPath: 'app/views.py',
      matchesOnly: true,
      onMatchesOnlyChange: vi.fn(),
    });

    expect(nodeOf(/File app\/views\.py/)).toHaveClass('map-node--selected');
  });

  it('switches matches-only off from the toolbar', async () => {
    const user = userEvent.setup();
    const onMatchesOnlyChange = vi.fn();
    renderMap({
      matchedPaths: new Set(['app/auth/tokens.py']),
      matchesOnly: true,
      onMatchesOnlyChange,
    });

    await user.click(screen.getByRole('checkbox', {name: 'Only show matches'}));

    expect(onMatchesOnlyChange).toHaveBeenCalledWith(false);
  });

  it('shows the whole map and no matches toggle without a search', () => {
    renderMap({matchesOnly: true, onMatchesOnlyChange: vi.fn()});

    expect(
      screen.queryByRole('checkbox', {name: 'Only show matches'}),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {name: /Module app,/}),
    ).toBeInTheDocument();
  });

  it('keeps zoom and fit in the one toolbar', () => {
    renderMap();

    const toolbar = screen.getByRole('toolbar', {name: 'Map controls'});
    for (const name of ['Zoom out', 'Zoom in', 'Fit', 'Collapse all']) {
      expect(within(toolbar).getByRole('button', {name})).toBeInTheDocument();
    }
    expect(
      document.querySelector('.react-flow__controls'),
    ).not.toBeInTheDocument();
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
