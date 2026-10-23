import dagre from '@dagrejs/dagre';
import type {Edge, Node} from '@xyflow/react';
import {MarkerType} from '@xyflow/react';
import type {DependencyGraph} from '../../api/types.ts';

export const MODULE_SIZE = {width: 190, height: 56};
export const FILE_SIZE = {width: 170, height: 40};
/** Extra room above an expanded module's files for its header. */
export const GROUP_HEADER = 22;

export type ModuleNodeData = {
  kind: 'module';
  moduleId: string;
  name: string;
  fileCount: number;
};

export type FileNodeData = {
  kind: 'file';
  path: string;
  moduleId: string;
  name: string;
  parsed: boolean;
};

export type GroupNodeData = {
  kind: 'group';
  moduleId: string;
  name: string;
  fileCount: number;
};

export type MapNode =
  | Node<ModuleNodeData, 'module'>
  | Node<FileNodeData, 'file'>
  | Node<GroupNodeData, 'moduleGroup'>;

/** An import edge between two visible units. */
export type MapEdge = Edge<{count: number}>;

export interface MapLayout {
  nodes: MapNode[];
  edges: MapEdge[];
}

export function moduleNodeId(moduleId: string): string {
  return `module:${moduleId}`;
}

export function fileNodeId(path: string): string {
  return `file:${path}`;
}

function groupNodeId(moduleId: string): string {
  return `group:${moduleId}`;
}

/**
 * The map node that stands for a file: the file itself if its module is
 * expanded, otherwise its collapsed module.
 */
export function unitFor(
  path: string,
  moduleOf: ReadonlyMap<string, string>,
  expandedModules: ReadonlySet<string>,
): string | null {
  const moduleId = moduleOf.get(path);
  if (moduleId === undefined) return null;
  return expandedModules.has(moduleId)
    ? fileNodeId(path)
    : moduleNodeId(moduleId);
}

/** Maps every file path to its module id. */
export function moduleIndex(graph: DependencyGraph): Map<string, string> {
  return new Map(graph.files.map(file => [file.path, file.module]));
}

/**
 * Lays out the dependency map: collapsed modules as single nodes, expanded
 * modules as a box of file nodes, and import edges between whatever is
 * visible (several file imports between two units become one edge with a
 * count). Importers are placed left of the files they import.
 */
export function layoutMap(
  graph: DependencyGraph,
  expandedModules: ReadonlySet<string>,
): MapLayout {
  const moduleOf = moduleIndex(graph);
  const files = new Map(graph.files.map(file => [file.path, file]));

  const layout = new dagre.graphlib.Graph({compound: true});
  layout.setGraph({
    rankdir: 'LR',
    nodesep: 32,
    ranksep: 80,
    marginx: 24,
    marginy: 24 + GROUP_HEADER,
  });
  layout.setDefaultEdgeLabel(() => ({}));

  for (const module of graph.modules) {
    if (module.filePaths.length === 0) continue;
    if (expandedModules.has(module.id)) {
      const groupId = groupNodeId(module.id);
      layout.setNode(groupId, {});
      for (const path of module.filePaths) {
        layout.setNode(fileNodeId(path), {...FILE_SIZE});
        layout.setParent(fileNodeId(path), groupId);
      }
    } else {
      layout.setNode(moduleNodeId(module.id), {...MODULE_SIZE});
    }
  }

  const edgeCounts = new Map<
    string,
    {source: string; target: string; count: number}
  >();
  for (const edge of graph.edges) {
    const source = unitFor(edge.source, moduleOf, expandedModules);
    const target = unitFor(edge.target, moduleOf, expandedModules);
    if (source === null || target === null || source === target) continue;
    const key = `${source}->${target}`;
    const existing = edgeCounts.get(key);
    if (existing === undefined) {
      edgeCounts.set(key, {source, target, count: 1});
      layout.setEdge(source, target);
    } else {
      existing.count++;
    }
  }

  dagre.layout(layout);

  const groups: MapNode[] = [];
  const leaves: MapNode[] = [];
  const groupOrigin = new Map<string, {x: number; y: number}>();

  for (const module of graph.modules) {
    if (module.filePaths.length === 0 || !expandedModules.has(module.id)) {
      continue;
    }
    const groupId = groupNodeId(module.id);
    const box = layout.node(groupId);
    const x = (box.x ?? 0) - box.width / 2;
    const y = (box.y ?? 0) - box.height / 2 - GROUP_HEADER;
    groupOrigin.set(groupId, {x, y});
    groups.push({
      id: groupId,
      type: 'moduleGroup',
      position: {x, y},
      width: box.width,
      height: box.height + GROUP_HEADER,
      data: {
        kind: 'group',
        moduleId: module.id,
        name: module.id === '.' ? module.name : module.id,
        fileCount: module.filePaths.length,
      },
      selectable: false,
    });
  }

  for (const module of graph.modules) {
    if (module.filePaths.length === 0) continue;
    if (!expandedModules.has(module.id)) {
      const id = moduleNodeId(module.id);
      const box = layout.node(id);
      leaves.push({
        id,
        type: 'module',
        position: {
          x: (box.x ?? 0) - box.width / 2,
          y: (box.y ?? 0) - box.height / 2,
        },
        ...MODULE_SIZE,
        data: {
          kind: 'module',
          moduleId: module.id,
          name: module.id === '.' ? module.name : module.id,
          fileCount: module.filePaths.length,
        },
      });
      continue;
    }
    const groupId = groupNodeId(module.id);
    const origin = groupOrigin.get(groupId) ?? {x: 0, y: 0};
    for (const path of module.filePaths) {
      const id = fileNodeId(path);
      const box = layout.node(id);
      leaves.push({
        id,
        type: 'file',
        parentId: groupId,
        extent: 'parent',
        position: {
          x: (box.x ?? 0) - box.width / 2 - origin.x,
          y: (box.y ?? 0) - box.height / 2 - origin.y,
        },
        ...FILE_SIZE,
        data: {
          kind: 'file',
          path,
          moduleId: module.id,
          name: path.slice(path.lastIndexOf('/') + 1),
          parsed: files.get(path)?.parsed ?? true,
        },
      });
    }
  }

  const edges: MapEdge[] = [...edgeCounts.values()].map(
    ({source, target, count}) => ({
      id: `${source}->${target}`,
      source,
      target,
      label: count > 1 ? String(count) : undefined,
      markerEnd: {type: MarkerType.ArrowClosed, width: 16, height: 16},
      data: {count},
    }),
  );

  // React Flow needs parents before their children.
  return {nodes: [...groups, ...leaves], edges};
}

/** Which nodes and edges to emphasize around the selected unit. */
export interface MapHighlight {
  selected: string | null;
  /** Units the selected one imports or is imported by. */
  related: ReadonlySet<string>;
  /** Edges touching the selected unit. */
  edges: ReadonlySet<string>;
}

export function highlightAround(
  edges: readonly MapEdge[],
  selectedUnit: string | null,
): MapHighlight {
  const related = new Set<string>();
  const touching = new Set<string>();
  if (selectedUnit !== null) {
    for (const edge of edges) {
      if (edge.source === selectedUnit) {
        related.add(edge.target);
        touching.add(edge.id);
      } else if (edge.target === selectedUnit) {
        related.add(edge.source);
        touching.add(edge.id);
      }
    }
  }
  return {selected: selectedUnit, related, edges: touching};
}
