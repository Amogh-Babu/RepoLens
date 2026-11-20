import type {DependencyGraph} from '../../api/types.ts';
import {moduleIndex, unitFor} from './mapLayout.ts';

/**
 * The most boxes and lines the map draws at once. Laying out and drawing
 * grow quickly with these: numpy with every folder open (837 boxes, 1,972
 * lines) took 12 s to lay out and drew at 37 frames a second (#118), while
 * pyvmomi with every folder open (188 boxes, 450 lines) stays smooth.
 */
export const MAP_BUDGET = {nodes: 400, edges: 1_000};

export interface MapSize {
  nodes: number;
  edges: number;
}

export interface BudgetedExpansion {
  /** The open folders that fit, in the order they were opened. */
  expanded: ReadonlySet<string>;
  /** Folders asked to be open that stay closed to keep within the budget. */
  keptClosed: string[];
  /** The size of the map that will be drawn. */
  size: MapSize;
  /** The size of the map with every requested folder open. */
  requestedSize: MapSize;
  /** True when even with every folder closed the map is over the budget. */
  tooLarge: boolean;
}

/**
 * Counts the boxes and lines the map would draw, without laying it out:
 * a box per closed folder, an open folder's box plus one per file, and one
 * line per pair of boxes with imports between them.
 */
export function mapSize(
  graph: DependencyGraph,
  expandedModules: ReadonlySet<string>,
  moduleOf: ReadonlyMap<string, string> = moduleIndex(graph),
): MapSize {
  let nodes = 0;
  for (const module of graph.modules) {
    if (module.filePaths.length === 0) continue;
    nodes += expandedModules.has(module.id) ? 1 + module.filePaths.length : 1;
  }
  const lines = new Set<string>();
  for (const edge of graph.edges) {
    const source = unitFor(edge.source, moduleOf, expandedModules);
    const target = unitFor(edge.target, moduleOf, expandedModules);
    if (source === null || target === null || source === target) continue;
    lines.add(`${source}->${target}`);
  }
  return {nodes, edges: lines.size};
}

function fits(size: MapSize, budget: MapSize): boolean {
  return size.nodes <= budget.nodes && size.edges <= budget.edges;
}

/**
 * Opens as many of the requested folders as fit in the budget, in the
 * order they were opened, so the folder that would overflow the map is the
 * one that stays closed. Runs before any layout, so an oversized map is
 * never handed to the layout engine.
 */
export function budgetExpansion(
  graph: DependencyGraph,
  expandedModules: ReadonlySet<string>,
  budget: MapSize = MAP_BUDGET,
): BudgetedExpansion {
  const moduleOf = moduleIndex(graph);
  const requested = [...expandedModules].filter(id =>
    graph.modules.some(module => module.id === id && module.filePaths.length),
  );
  const all = mapSize(graph, new Set(requested), moduleOf);
  if (fits(all, budget)) {
    return {
      expanded: expandedModules,
      keptClosed: [],
      size: all,
      requestedSize: all,
      tooLarge: false,
    };
  }
  const collapsed = mapSize(graph, new Set(), moduleOf);
  if (!fits(collapsed, budget)) {
    return {
      expanded: new Set(),
      keptClosed: requested,
      size: collapsed,
      requestedSize: all,
      tooLarge: true,
    };
  }
  const expanded = new Set<string>();
  let size = collapsed;
  let fitted = 0;
  for (const moduleId of requested) {
    expanded.add(moduleId);
    const next = mapSize(graph, expanded, moduleOf);
    if (!fits(next, budget)) {
      expanded.delete(moduleId);
      break;
    }
    size = next;
    fitted++;
  }
  return {
    expanded,
    keptClosed: requested.slice(fitted),
    size,
    requestedSize: all,
    tooLarge: false,
  };
}
