/**
 * Picking parts of a dependency graph. Kept free of the map's layout
 * libraries so the workspace can filter the list view without loading
 * the (lazily loaded) map.
 */

import type {DependencyGraph} from '../api/types.ts';

/**
 * The part of the graph made of `keep`: those files, the modules that hold
 * them, and the imports between them. With a `center`, only the imports to
 * and from that file are kept, so the map puts its importers on one side
 * and its imports on the other.
 */
export function subgraph(
  graph: DependencyGraph,
  keep: ReadonlySet<string>,
  center?: string,
): DependencyGraph {
  return {
    modules: graph.modules
      .map(module => ({
        ...module,
        filePaths: module.filePaths.filter(path => keep.has(path)),
      }))
      .filter(module => module.filePaths.length > 0),
    files: graph.files.filter(file => keep.has(file.path)),
    edges: graph.edges.filter(
      edge =>
        keep.has(edge.source) &&
        keep.has(edge.target) &&
        (center === undefined ||
          edge.source === center ||
          edge.target === center),
    ),
  };
}

/**
 * A file and its direct neighbors: the files it imports and the files that
 * import it. Used to hide everything unrelated to the selected file.
 */
export function neighborhood(
  graph: DependencyGraph,
  path: string,
): Set<string> {
  const keep = new Set([path]);
  for (const edge of graph.edges) {
    if (edge.source === path) keep.add(edge.target);
    else if (edge.target === path) keep.add(edge.source);
  }
  return keep;
}
