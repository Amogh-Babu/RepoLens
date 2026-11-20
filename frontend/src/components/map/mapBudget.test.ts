import type {DependencyGraph} from '../../api/types.ts';
import {budgetExpansion, mapSize} from './mapBudget.ts';

/** Modules `m0`..`m{n-1}` of `filesPer` files; each file imports the next. */
function chainGraph(modules: number, filesPer: number): DependencyGraph {
  const graph: DependencyGraph = {modules: [], files: [], edges: []};
  const paths: string[] = [];
  for (let m = 0; m < modules; m++) {
    const filePaths = Array.from(
      {length: filesPer},
      (_, f) => `m${m}/f${f}.py`,
    );
    graph.modules.push({id: `m${m}`, name: `m${m}`, filePaths});
    for (const path of filePaths) {
      graph.files.push({path, module: `m${m}`, parsed: true, lineCount: 1});
      paths.push(path);
    }
  }
  paths.slice(1).forEach((target, i) => {
    graph.edges.push({source: paths[i] ?? target, target});
  });
  return graph;
}

/** `modules` single-file modules where every module imports every other. */
function denseGraph(modules: number): DependencyGraph {
  const graph = chainGraph(modules, 1);
  graph.edges = [];
  for (const a of graph.files) {
    for (const b of graph.files) {
      if (a !== b) graph.edges.push({source: a.path, target: b.path});
    }
  }
  return graph;
}

describe('mapSize', () => {
  it('counts boxes and merged lines without laying anything out', () => {
    const graph = chainGraph(3, 4);

    expect(mapSize(graph, new Set())).toEqual({nodes: 3, edges: 2});
    // An open module is its box plus a box per file; lines inside it count.
    expect(mapSize(graph, new Set(['m1']))).toEqual({nodes: 7, edges: 5});
  });
});

describe('budgetExpansion', () => {
  it('opens every requested module that fits', () => {
    const graph = chainGraph(3, 4);
    const expanded = new Set(['m0', 'm2']);

    const result = budgetExpansion(graph, expanded, {nodes: 100, edges: 100});

    expect(result.expanded).toBe(expanded);
    expect(result.keptClosed).toEqual([]);
    expect(result.tooLarge).toBe(false);
  });

  it('keeps the module that would overflow the budget closed', () => {
    const graph = chainGraph(3, 10);

    // Collapsed: 3 boxes. m0 open: 13 boxes. m0 and m1 open: 23 boxes.
    const result = budgetExpansion(graph, new Set(['m0', 'm1', 'm2']), {
      nodes: 15,
      edges: 1_000,
    });

    expect([...result.expanded]).toEqual(['m0']);
    expect(result.keptClosed).toEqual(['m1', 'm2']);
    expect(result.size).toEqual({nodes: 13, edges: 11});
    expect(result.requestedSize.nodes).toBe(33);
    expect(result.tooLarge).toBe(false);
  });

  it('opens modules in the order they were opened', () => {
    const graph = chainGraph(3, 10);

    const result = budgetExpansion(graph, new Set(['m2', 'm0']), {
      nodes: 15,
      edges: 1_000,
    });

    expect([...result.expanded]).toEqual(['m2']);
    expect(result.keptClosed).toEqual(['m0']);
  });

  it('flags a map too large even with every module closed', () => {
    const graph = denseGraph(40); // 1,560 lines between 40 boxes

    const result = budgetExpansion(graph, new Set(['m3']), {
      nodes: 400,
      edges: 1_000,
    });

    expect(result.tooLarge).toBe(true);
    expect(result.expanded.size).toBe(0);
    expect(result.size).toEqual({nodes: 40, edges: 1_560});
  });

  it('ignores requested modules that are not in the graph', () => {
    const graph = chainGraph(2, 2);

    const result = budgetExpansion(graph, new Set(['gone']), {
      nodes: 1,
      edges: 0,
    });

    expect(result.keptClosed).toEqual([]);
  });
});
