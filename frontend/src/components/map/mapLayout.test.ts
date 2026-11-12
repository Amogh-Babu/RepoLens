import type {DependencyGraph} from '../../api/types.ts';
import type {MapNode} from './mapLayout.ts';
import {
  focusGraph,
  highlightAround,
  layoutMap,
  neighborhood,
} from './mapLayout.ts';

const GRAPH: DependencyGraph = {
  modules: [
    {id: '.', name: '(root)', filePaths: ['manage.py']},
    {id: 'app', name: 'app', filePaths: ['app/views.py', 'app/db.py']},
    {
      id: 'app/auth',
      name: 'auth',
      filePaths: ['app/auth/service.py', 'app/auth/tokens.py'],
    },
  ],
  files: [
    {path: 'manage.py', module: '.', parsed: true, lineCount: 1},
    {path: 'app/views.py', module: 'app', parsed: true, lineCount: 1},
    {path: 'app/db.py', module: 'app', parsed: true, lineCount: 1},
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
    {source: 'manage.py', target: 'app/views.py'},
    {source: 'app/views.py', target: 'app/auth/service.py'},
    {source: 'app/views.py', target: 'app/auth/tokens.py'},
    {source: 'app/views.py', target: 'app/db.py'},
    {source: 'app/auth/service.py', target: 'app/auth/tokens.py'},
    {source: 'app/auth/service.py', target: 'app/db.py'},
  ],
};

function ids(nodes: MapNode[]) {
  return nodes.map(n => n.id).sort();
}

describe('neighborhood', () => {
  it('is a file plus the files it imports and the files that import it', () => {
    expect([...neighborhood(GRAPH, 'app/auth/service.py')].sort()).toEqual([
      'app/auth/service.py',
      'app/auth/tokens.py',
      'app/db.py',
      'app/views.py',
    ]);
  });
});

describe('focusGraph', () => {
  const keep = neighborhood(GRAPH, 'app/auth/service.py');

  it('keeps the imports between the kept files', () => {
    const edges = focusGraph(GRAPH, keep).edges;

    expect(edges).toContainEqual({
      source: 'app/views.py',
      target: 'app/db.py',
    });
    expect(edges).toHaveLength(5);
  });

  it('keeps only the imports to and from the center when given one', () => {
    const focused = focusGraph(GRAPH, keep, 'app/auth/service.py');

    expect(focused.edges).toEqual([
      {source: 'app/views.py', target: 'app/auth/service.py'},
      {source: 'app/auth/service.py', target: 'app/auth/tokens.py'},
      {source: 'app/auth/service.py', target: 'app/db.py'},
    ]);
    expect(focused.files.map(file => file.path).sort()).toEqual(
      [...keep].sort(),
    );
    expect(focused.modules.map(module => module.id)).toEqual([
      'app',
      'app/auth',
    ]);
  });
});

describe('layoutMap', () => {
  it('shows one node per module when everything is collapsed', () => {
    const {nodes, edges} = layoutMap(GRAPH, new Set());

    expect(ids(nodes)).toEqual(['module:.', 'module:app', 'module:app/auth']);
    // Edges inside a module disappear; parallel edges merge with a count.
    expect(edges.map(e => [e.source, e.target, e.data?.count]).sort()).toEqual([
      ['module:.', 'module:app', 1],
      ['module:app', 'module:app/auth', 2],
      ['module:app/auth', 'module:app', 1],
    ]);
    expect(edges.find(e => e.data?.count === 2)?.label).toBe('2');
  });

  it('shows an expanded module as a box of its files', () => {
    const {nodes, edges} = layoutMap(GRAPH, new Set(['app/auth']));

    expect(ids(nodes)).toEqual([
      'file:app/auth/service.py',
      'file:app/auth/tokens.py',
      'group:app/auth',
      'module:.',
      'module:app',
    ]);
    // The group comes before its children, which React Flow requires.
    expect(nodes[0]?.id).toBe('group:app/auth');
    const tokens = nodes.find(n => n.id === 'file:app/auth/tokens.py');
    expect(tokens).toMatchObject({
      parentId: 'group:app/auth',
      extent: 'parent',
      data: {kind: 'file', name: 'tokens.py', parsed: false},
    });
    expect(edges.map(e => e.id).sort()).toEqual([
      'file:app/auth/service.py->file:app/auth/tokens.py',
      'file:app/auth/service.py->module:app',
      'module:.->module:app',
      'module:app->file:app/auth/service.py',
      'module:app->file:app/auth/tokens.py',
    ]);
  });

  it('places files inside their group and importers left of imports', () => {
    const {nodes} = layoutMap(GRAPH, new Set(['app/auth']));
    const group = nodes.find(n => n.id === 'group:app/auth');
    const service = nodes.find(n => n.id === 'file:app/auth/service.py');
    const tokens = nodes.find(n => n.id === 'file:app/auth/tokens.py');

    for (const child of [service, tokens]) {
      expect(child?.position.x).toBeGreaterThanOrEqual(0);
      expect(child?.position.y).toBeGreaterThanOrEqual(0);
      expect(
        (child?.position.x ?? 0) + (child?.width ?? 0),
      ).toBeLessThanOrEqual(group?.width ?? 0);
    }
    expect(service?.position.x).toBeLessThan(tokens?.position.x ?? 0);
  });

  it('names the root module after the repository root', () => {
    const {nodes} = layoutMap(GRAPH, new Set());
    expect(nodes.find(n => n.id === 'module:.')?.data).toMatchObject({
      name: '(root)',
      fileCount: 1,
    });
  });
});

describe('highlightAround', () => {
  const {edges} = layoutMap(GRAPH, new Set(['app/auth']));

  it('marks what the selected unit imports and what imports it', () => {
    const highlight = highlightAround(edges, 'file:app/auth/service.py');

    expect([...highlight.related].sort()).toEqual([
      'file:app/auth/tokens.py',
      'module:app',
    ]);
    expect(highlight.edges.size).toBe(3);
  });

  it('marks nothing without a selection', () => {
    const highlight = highlightAround(edges, null);

    expect(highlight.selected).toBeNull();
    expect(highlight.related.size).toBe(0);
  });
});
